#!/usr/bin/env python3
"""Optional deterministic Playwright probe runner for blackbox-ui-qa workspaces.

Requires Playwright only when invoked (`pip install playwright && playwright install chromium`).
Automatically injects scripts/browser_probes.js via addInitScript, enforces
run_contract.authorized_origins and staging_confirmed, and redacts saved telemetry.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from qa_common import (
    as_list,
    as_text,
    configure_utf8_stdio,
    read_json,
    redact_text,
    slugify,
    write_json_atomic,
)

PROBE_JS_PATH = Path(__file__).with_name("browser_probes.js")


def _load_meta(workspace: Path) -> dict:
    meta, err = read_json(workspace / "meta.json")
    if err or not isinstance(meta, dict):
        raise SystemExit(f"ERROR: Cannot load meta.json in {workspace}: {err or 'invalid object'}")
    return meta


def _check_origin(url: str, authorized_origins: list[str]) -> None:
    if not authorized_origins:
        return
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}".lower()
    allowed = {f"{urlparse(o).scheme}://{urlparse(o).netloc}".lower() for o in authorized_origins if o}
    if origin not in allowed:
        raise SystemExit(f"ERROR: Target URL origin '{origin}' is outside run_contract.authorized_origins {sorted(allowed)}.")


def _require_staging(meta: dict, action: str) -> None:
    if meta.get("staging_confirmed") is not True:
        raise SystemExit(f"ERROR: Refusing mutating probe '{action}' because meta.json staging_confirmed is not true.")


def _parse_viewport(text: str) -> dict[str, int]:
    w, h = text.lower().split("x", 1)
    return {"width": int(w), "height": int(h)}


def _parse_fill(pair: str) -> tuple[str, str]:
    """Split selector=value at the first '=' outside brackets/quotes."""
    depth = 0
    quote = ""
    for idx, ch in enumerate(pair):
        if quote:
            if ch == quote and (idx == 0 or pair[idx - 1] != "\\"):
                quote = ""
        elif ch in ("'", '"'):
            quote = ch
        elif ch in ("[", "("):
            depth += 1
        elif ch in ("]", ")") and depth > 0:
            depth -= 1
        elif ch == "=" and depth == 0:
            return pair[:idx], pair[idx + 1 :]
    raise SystemExit(f"ERROR: --fill expects selector=value, got '{pair}'.")


def _redact_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, list):
        return [_redact_obj(v) for v in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in ("password", "passwd", "pwd", "token", "authorization", "cookie", "secret"):
                out[k] = "[REDACTED]"
            else:
                out[k] = _redact_obj(v)
        return out
    return obj


def _validate_storage_state(workspace: Path, raw_path: str, *, must_exist: bool = False) -> Path | None:
    if not raw_path:
        return None
    ws_resolved = workspace.resolve()
    state_path = Path(raw_path).expanduser().resolve()
    try:
        state_path.relative_to(ws_resolved)
        inside_ws = True
    except ValueError:
        inside_ws = False
    if inside_ws:
        raise SystemExit(
            f"ERROR: --storage-state path '{state_path}' must reside outside QA workspace '{ws_resolved}' (Rule 5)."
        )
    if must_exist and not state_path.is_file():
        raise SystemExit(f"ERROR: --storage-state file not found: {state_path}")
    return state_path


def _open_context(
    browser,
    meta: dict,
    viewport: dict[str, int] | None = None,
    storage_state: Path | None = None,
):
    vp = viewport or {"width": 1440, "height": 900}
    ctx_kwargs: dict[str, Any] = {"viewport": vp}
    if storage_state is not None:
        ctx_kwargs["storage_state"] = str(storage_state)
    context = browser.new_context(**ctx_kwargs)
    if PROBE_JS_PATH.is_file():
        context.add_init_script(path=str(PROBE_JS_PATH))
    page = context.new_page()
    return context, page


def _login_if_needed(page, args: argparse.Namespace, authorized_origins: list[str]) -> None:
    if not getattr(args, "login_url", ""):
        return
    _check_origin(args.login_url, authorized_origins)
    page.goto(args.login_url, wait_until="domcontentloaded")
    if getattr(args, "user", ""):
        page.fill(args.user_sel, args.user)
    if getattr(args, "password", ""):
        page.fill(args.pass_sel, args.password)
    if getattr(args, "submit_sel", ""):
        page.click(args.submit_sel)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(150)


def _url_slug(url: str) -> str:
    parsed = urlparse(url)
    base = slugify(parsed.path.strip("/") or "home")
    extra = f"{parsed.query}#{parsed.fragment}" if parsed.fragment else parsed.query
    if not extra:
        return base
    digest = hashlib.sha1(extra.encode("utf-8")).hexdigest()[:6]
    return f"{base}_{slugify(extra, 'q')[:24]}_{digest}"


def _wait_dom_stable(page, *, settle_ms: int = 350, timeout_ms: int = 5000) -> bool:
    deadline = 0
    prev = None
    while deadline <= timeout_ms:
        cur = page.evaluate(
            "(() => `${location.href}|${(document.body && document.body.innerText ? document.body.innerText : '').slice(0, 600)}`)()"
        )
        if prev is not None and cur == prev:
            return True
        prev = cur
        page.wait_for_timeout(settle_ms)
        deadline += settle_ms
    return False


def _save_probe_artifacts(
    workspace: Path,
    page,
    out_prefix: str,
    payload: dict[str, Any],
    *,
    shot_suffix: str = "",
) -> None:
    if not out_prefix:
        return
    shot_rel = f"evidence/screenshots/{out_prefix}{shot_suffix}.png"
    shot_abs = workspace / shot_rel
    shot_abs.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(shot_abs))
    payload["screenshot"] = shot_rel
    payload["evidence_json"] = _save_evidence_json(workspace, f"evidence/network/{out_prefix}.json", payload)


def _authorized_origins(meta: dict) -> list[str]:
    return [as_text(o) for o in as_list((meta.get("run_contract") or {}).get("authorized_origins")) if as_text(o)]


@contextmanager
def _probe_session(
    workspace: Path,
    meta: dict,
    args: argparse.Namespace,
    p,
    *,
    target_urls: list[str] | None = None,
    viewport: dict[str, int] | None = None,
    raw_state: str | None = None,
    run_login: bool = True,
):
    origins = _authorized_origins(meta)
    state_input = getattr(args, "storage_state", "") if raw_state is None else raw_state
    state_path = _validate_storage_state(workspace, state_input, must_exist=True)
    for url in target_urls or []:
        _check_origin(url, origins)

    browser = p.chromium.launch(headless=not args.headed)
    try:
        context, page = _open_context(browser, meta, viewport=viewport, storage_state=state_path)
        try:
            if run_login:
                _login_if_needed(page, args, origins)
            yield origins, context, page
        finally:
            context.close()
    finally:
        browser.close()


def _drain_and_audit(page) -> dict:
    try:
        telemetry = page.evaluate("window.__QA_DRAIN__ ? window.__QA_DRAIN__() : {}")
    except Exception as exc:
        telemetry = {"error": str(exc)}
    try:
        audit = page.evaluate("window.__QA_AUDIT__ ? window.__QA_AUDIT__() : {}")
    except Exception as exc:
        audit = {"error": str(exc)}
    return _redact_obj({"telemetry": telemetry, "audit": audit})


def _save_evidence_json(workspace: Path, rel_path: str, payload: Any) -> str:
    dest = workspace / rel_path
    write_json_atomic(dest, _redact_obj(payload))
    return rel_path


def cmd_sweep(workspace: Path, meta: dict, args: argparse.Namespace, p) -> dict:
    results = []
    with _probe_session(
        workspace, meta, args, p, target_urls=args.url, viewport=_parse_viewport(args.viewport[0])
    ) as (_origins, _ctx, page):
        for u in args.url:
            for vp_str in args.viewport:
                vp = _parse_viewport(vp_str)
                page.set_viewport_size(vp)
                resp = page.goto(u, wait_until="domcontentloaded")
                page.wait_for_timeout(args.wait_ms)
                slug = _url_slug(u)
                shot_rel = f"evidence/screenshots/sweep_{slug}_{vp_str}.png"
                shot_abs = workspace / shot_rel
                shot_abs.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(shot_abs), full_page=False)
                data = _drain_and_audit(page)
                data["url"] = redact_text(page.url)
                data["status"] = resp.status if resp else None
                data["viewport"] = vp_str
                data["screenshot"] = shot_rel
                ev_rel = f"evidence/network/sweep_{slug}_{vp_str}.json"
                _save_evidence_json(workspace, ev_rel, data)
                data["evidence_json"] = ev_rel
                results.append(data)
    return {"ok": True, "command": "sweep", "results": results}


def cmd_race_search(workspace: Path, meta: dict, args: argparse.Namespace, p) -> dict:
    with _probe_session(workspace, meta, args, p, target_urls=[args.url]) as (_origins, _ctx, page):
        page.goto(args.url, wait_until="domcontentloaded")
        requests_seen: list[dict] = []
        page.on(
            "response",
            lambda r: requests_seen.append({"url": redact_text(r.url), "status": r.status}),
        )

        locator = page.locator(args.selector)
        locator.fill(args.query_a)
        page.wait_for_timeout(args.delay_ms)
        locator.fill(args.query_b)
        page.wait_for_timeout(args.settle_ms)

        input_val = locator.input_value()
        settled_text = ""
        if args.result_selector:
            settled_text = redact_text(page.locator(args.result_selector).inner_text())
        probes = _drain_and_audit(page)
        out = {
            "ok": True,
            "command": "race-search",
            "query_a": args.query_a,
            "query_b": args.query_b,
            "delay_ms": args.delay_ms,
            "final_input_value": input_val,
            "settled_text": settled_text,
            "responses": requests_seen,
            **probes,
        }
        if args.out_prefix:
            out["evidence_json"] = _save_evidence_json(workspace, f"evidence/network/{args.out_prefix}.json", out)
        return out


def cmd_double_submit(workspace: Path, meta: dict, args: argparse.Namespace, p) -> dict:
    _require_staging(meta, "double-submit")
    with _probe_session(workspace, meta, args, p, target_urls=[args.url]) as (_origins, _ctx, page):
        page.goto(args.url, wait_until="domcontentloaded")
        before_count = page.locator(args.count_selector).count() if args.count_selector else None
        for pair in args.fill or []:
            sel, val = _parse_fill(pair)
            page.fill(sel, val)

        post_events: list[dict] = []
        page.on(
            "request",
            lambda req: post_events.append({"method": req.method, "url": redact_text(req.url)})
            if req.method == "POST"
            else None,
        )

        btn = page.locator(args.submit_selector)
        # Trigger two back-to-back clicks without awaiting navigation between them
        btn.click(no_wait_after=True)
        btn.click(no_wait_after=True)
        page.wait_for_timeout(args.settle_ms)

        after_count = page.locator(args.count_selector).count() if args.count_selector else None
        probes = _drain_and_audit(page)
        out = {
            "ok": True,
            "command": "double-submit",
            "final_url": redact_text(page.url),
            "post_requests_count": len(post_events),
            "post_requests": post_events,
            "count_before": before_count,
            "count_after": after_count,
            "created_delta": (after_count - before_count) if (before_count is not None and after_count is not None) else None,
            **probes,
        }
        _save_probe_artifacts(workspace, page, args.out_prefix, out)
        return out


def cmd_reload_check(workspace: Path, meta: dict, args: argparse.Namespace, p) -> dict:
    _require_staging(meta, "reload-check")
    with _probe_session(workspace, meta, args, p, target_urls=[args.url]) as (_origins, _ctx, page):
        page.goto(args.url, wait_until="domcontentloaded")
        before_text = redact_text(page.locator(args.watch_selector).inner_text())

        for pair in args.fill or []:
            sel, val = _parse_fill(pair)
            page.fill(sel, val)

        network_during_action: list[dict] = []
        page.on(
            "request",
            lambda req: network_during_action.append({"method": req.method, "url": redact_text(req.url)}),
        )
        page.click(args.submit_selector)
        page.wait_for_timeout(args.settle_ms)
        immediate_text = redact_text(page.locator(args.watch_selector).inner_text())

        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(args.settle_ms)
        post_reload_text = redact_text(page.locator(args.watch_selector).inner_text())

        probes = _drain_and_audit(page)
        out = {
            "ok": True,
            "command": "reload-check",
            "before_text": before_text,
            "immediate_text": immediate_text,
            "post_reload_text": post_reload_text,
            "persisted": immediate_text == post_reload_text and immediate_text != before_text,
            "network_requests_during_action": network_during_action,
            **probes,
        }
        if args.out_prefix:
            out["evidence_json"] = _save_evidence_json(workspace, f"evidence/network/{args.out_prefix}.json", out)
        return out


def cmd_authz_url(workspace: Path, meta: dict, args: argparse.Namespace, p) -> dict:
    with _probe_session(workspace, meta, args, p, target_urls=[args.target_url]) as (_origins, _ctx, page):
        resp = page.goto(args.target_url, wait_until="domcontentloaded")
        page.wait_for_timeout(args.settle_ms)
        probes = _drain_and_audit(page)
        body_excerpt = redact_text((page.locator("body").inner_text() or "").strip())[:500]
        out = {
            "ok": True,
            "command": "authz-url",
            "role": args.role,
            "target_url": redact_text(args.target_url),
            "final_url": redact_text(page.url),
            "status": resp.status if resp else None,
            "title": redact_text(page.title()),
            "body_excerpt": body_excerpt,
            **probes,
        }
        _save_probe_artifacts(workspace, page, args.out_prefix, out)
        return out


def cmd_save_auth(workspace: Path, meta: dict, args: argparse.Namespace, p) -> dict:
    out_path = _validate_storage_state(workspace, args.out, must_exist=False)
    assert out_path is not None
    login_url = args.login_url or args.url
    if not login_url:
        raise SystemExit("ERROR: save-auth requires --login-url (or --url).")

    with _probe_session(workspace, meta, args, p, target_urls=[login_url], run_login=False) as (_origins, context, page):
        page.goto(login_url, wait_until="domcontentloaded")
        if args.user:
            page.fill(args.user_sel, args.user)
        if args.password:
            page.fill(args.pass_sel, args.password)
        for pair in args.fill or []:
            sel, val = _parse_fill(pair)
            page.fill(sel, val)
        if (args.user or args.password) and args.submit_sel:
            page.click(args.submit_sel)
            page.wait_for_load_state("domcontentloaded")
        for sel in args.click or []:
            page.click(sel)
        if args.wait_ms > 0:
            page.wait_for_timeout(args.wait_ms)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(out_path))
        return {
            "ok": True,
            "command": "save-auth",
            "storage_state": str(out_path),
            "final_url": redact_text(page.url),
            "cookies_count": len(context.cookies()),
        }


def cmd_deeplink_check(workspace: Path, meta: dict, args: argparse.Namespace, p) -> dict:
    with _probe_session(workspace, meta, args, p, target_urls=[args.url]) as (_origins, _ctx, page):
        page.goto(args.url, wait_until="domcontentloaded")
        page.wait_for_timeout(args.settle_ms)
        if args.click:
            page.locator(args.click).first.click()
            page.wait_for_timeout(args.settle_ms)

        before_url = redact_text(page.url)
        before_text = redact_text(page.locator(args.watch_selector).first.inner_text())[:800]

        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(args.settle_ms)
        after_url = redact_text(page.url)
        after_text = redact_text(page.locator(args.watch_selector).first.inner_text())[:800]

        url_ok = (args.expected_url_part in after_url) if args.expected_url_part else (after_url == before_url)
        text_preserved = before_text == after_text
        probes = _drain_and_audit(page)
        out = {
            "ok": True,
            "command": "deeplink-check",
            "before_reload_url": before_url,
            "after_reload_url": after_url,
            "url_preserved": url_ok,
            "text_preserved": text_preserved,
            "before_reload_excerpt": before_text[:300],
            "after_reload_excerpt": after_text[:300],
            **probes,
        }
        _save_probe_artifacts(workspace, page, args.out_prefix, out)
        return out


def _load_exec_payload(args: argparse.Namespace) -> dict:
    if args.stdin:
        raw = sys.stdin.read()
    elif args.file:
        raw = Path(args.file).expanduser().read_text(encoding="utf-8")
    else:
        raise SystemExit("ERROR: exec requires --stdin or --file with a JSON plan.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: Invalid JSON for exec: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("steps"), list):
        raise SystemExit("ERROR: exec JSON payload must be an object with a 'steps' array.")
    return payload


def cmd_exec(workspace: Path, meta: dict, args: argparse.Namespace, p) -> dict:
    payload = _load_exec_payload(args)
    if payload.get("mutating") is True or any(isinstance(s, dict) and s.get("mutating") for s in payload["steps"]):
        _require_staging(meta, "exec (mutating)")
    raw_state = getattr(args, "storage_state", "") or as_text(payload.get("storage_state"))
    vp = _parse_viewport(as_text(payload.get("viewport")) or "1440x900")
    out_prefix = args.out_prefix or as_text(payload.get("out_prefix"))
    goto_urls = [
        as_text(step.get("url"))
        for step in payload["steps"]
        if isinstance(step, dict) and as_text(step.get("action")).lower() == "goto" and step.get("url")
    ]

    step_logs: list[dict[str, Any]] = []
    ok = True
    failed_reason = ""
    with _probe_session(
        workspace, meta, args, p, target_urls=goto_urls, viewport=vp, raw_state=raw_state
    ) as (_origins, _ctx, page):
        for idx, step in enumerate(payload["steps"], 1):
            if not isinstance(step, dict) or not as_text(step.get("action")):
                raise SystemExit(f"ERROR: exec step #{idx} must be an object with 'action'.")
            act = as_text(step["action"]).lower()
            rec: dict[str, Any] = {"step": idx, "action": act, "ok": True}
            try:
                if act == "goto":
                    resp = page.goto(as_text(step["url"]), wait_until=as_text(step.get("wait_until")) or "domcontentloaded")
                    rec["url"] = redact_text(page.url)
                    rec["status"] = resp.status if resp else None
                elif act == "fill":
                    page.fill(as_text(step["selector"]), as_text(step.get("value")))
                    rec["selector"] = as_text(step["selector"])
                elif act == "click":
                    loc = page.locator(as_text(step["selector"]))
                    (loc.first if step.get("first") else loc).click(no_wait_after=bool(step.get("no_wait_after")))
                    rec["selector"] = as_text(step["selector"])
                elif act == "select":
                    page.select_option(as_text(step["selector"]), as_text(step.get("value")))
                    rec["selector"] = as_text(step["selector"])
                elif act == "check":
                    page.check(as_text(step["selector"]))
                    rec["selector"] = as_text(step["selector"])
                elif act == "uncheck":
                    page.uncheck(as_text(step["selector"]))
                    rec["selector"] = as_text(step["selector"])
                elif act == "press":
                    target_sel = as_text(step.get("selector"))
                    if target_sel:
                        page.press(target_sel, as_text(step["key"]))
                    else:
                        page.keyboard.press(as_text(step["key"]))
                    rec["key"] = as_text(step["key"])
                elif act == "wait":
                    ms = int(step.get("ms", 300))
                    page.wait_for_timeout(ms)
                    rec["ms"] = ms
                elif act == "wait_stable":
                    settle_ms = int(step.get("settle_ms", 350))
                    timeout_ms = int(step.get("timeout_ms", 5000))
                    rec["settled"] = _wait_dom_stable(page, settle_ms=settle_ms, timeout_ms=timeout_ms)
                elif act == "wait_for":
                    timeout_ms = int(step.get("timeout_ms", 5000))
                    page.wait_for_selector(as_text(step["selector"]), timeout=timeout_ms)
                    rec["selector"] = as_text(step["selector"])
                elif act == "reload":
                    resp = page.reload(wait_until="domcontentloaded")
                    rec["status"] = resp.status if resp else None
                elif act == "screenshot":
                    raw_name = as_text(step.get("name")) or f"step_{idx}"
                    name = re.sub(r"[^A-Za-z0-9_-]+", "-", raw_name).strip("-") or f"step_{idx}"
                    shot_rel = f"evidence/screenshots/{name}.png"
                    shot_abs = workspace / shot_rel
                    shot_abs.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(shot_abs), full_page=bool(step.get("full_page")))
                    rec["screenshot"] = shot_rel
                elif act == "assert_text":
                    loc = page.locator(as_text(step["selector"]))
                    actual_txt = redact_text((loc.first if step.get("first") else loc).inner_text())
                    rec["actual"] = actual_txt
                    if "equals" in step and actual_txt != as_text(step["equals"]):
                        raise AssertionError(f"Expected text == '{step['equals']}', got '{actual_txt}'")
                    if "contains" in step and as_text(step["contains"]) not in actual_txt:
                        raise AssertionError(f"Expected text containing '{step['contains']}', got '{actual_txt}'")
                elif act == "assert_visible":
                    vis = page.locator(as_text(step["selector"])).first.is_visible()
                    rec["visible"] = vis
                    if not vis:
                        raise AssertionError(f"Locator '{step['selector']}' is not visible")
                elif act == "assert_url":
                    cur = redact_text(page.url)
                    rec["url"] = cur
                    if "contains" in step and as_text(step["contains"]) not in cur:
                        raise AssertionError(f"Expected URL containing '{step['contains']}', got '{cur}'")
                elif act == "assert_clean":
                    snap = _drain_and_audit(page)
                    tel = snap.get("telemetry") or {}
                    allow_statuses = {int(s) for s in step.get("allow_statuses") or []}
                    net_errs = [n for n in tel.get("networkFailures") or [] if n.get("status") not in allow_statuses]
                    found = []
                    for key in ("consoleErrors", "pageErrors", "unhandledRejections", "graphqlErrors"):
                        if tel.get(key):
                            found.append(f"{key}={len(tel[key])}")
                    if net_errs:
                        found.append(f"networkFailures={len(net_errs)}")
                    rec["audit"] = snap
                    if found:
                        raise AssertionError("Runtime errors detected: " + ", ".join(found))
                elif act == "audit":
                    rec["audit"] = _drain_and_audit(page)
                else:
                    raise SystemExit(f"ERROR: Unsupported exec action '{act}' at step #{idx}.")
            except SystemExit:
                raise
            except Exception as exc:
                rec["ok"] = False
                rec["error"] = redact_text(str(exc))
                ok = False
                failed_reason = f"step #{idx} ({act}): {rec['error']}"
                step_logs.append(rec)
                break
            step_logs.append(rec)

        probes = _drain_and_audit(page)
        out = {
            "ok": ok,
            "command": "exec",
            "final_url": redact_text(page.url),
            "steps": step_logs,
            **({"error": failed_reason} if failed_reason else {}),
            **probes,
        }
        _save_probe_artifacts(workspace, page, out_prefix, out, shot_suffix="_final")
        return out


_A11Y_FOCUS_JS = """() => {
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) {
    return { active: false, tag: el ? el.tagName.toLowerCase() : 'none' };
  }
  const rect = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  const label = (el.innerText || el.getAttribute('aria-label') || el.name || el.id || el.tagName).trim().slice(0, 60);
  const ow = parseFloat(cs.outlineWidth || '0') || 0;
  const hasOutline = cs.outlineStyle && cs.outlineStyle !== 'none' && ow > 0;
  const hasBoxShadow = cs.boxShadow && cs.boxShadow !== 'none';
  let obscuredBy = null;
  if (rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.bottom <= window.innerHeight && rect.left >= 0 && rect.right <= window.innerWidth) {
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    if (hit && hit !== el && !el.contains(hit) && !hit.contains(el)) {
      obscuredBy = (hit.id || hit.className || hit.tagName).toString().slice(0, 60);
    }
  }
  return {
    active: true,
    tag: el.tagName.toLowerCase(),
    id: el.id || '',
    type: el.getAttribute('type') || '',
    label,
    hasFocusIndicator: Boolean(hasOutline || hasBoxShadow),
    outline: `${cs.outlineStyle} ${cs.outlineWidth}`,
    boxShadow: cs.boxShadow !== 'none',
    obscuredBy,
    inViewport: rect.top >= 0 && rect.bottom <= window.innerHeight && rect.left >= 0 && rect.right <= window.innerWidth,
  };
}"""


def cmd_a11y_keyboard(workspace: Path, meta: dict, args: argparse.Namespace, p) -> dict:
    vp = _parse_viewport(args.viewport)
    with _probe_session(workspace, meta, args, p, target_urls=[args.url], viewport=vp) as (_origins, _ctx, page):
        page.goto(args.url, wait_until="domcontentloaded")
        page.wait_for_timeout(args.settle_ms)

        stops: list[dict[str, Any]] = []
        missing_indicator: list[dict[str, Any]] = []
        obscured: list[dict[str, Any]] = []
        seen_keys: list[str] = []

        for step_idx in range(1, args.tabs + 1):
            page.keyboard.press("Tab")
            info = page.evaluate(_A11Y_FOCUS_JS)
            info["tab_step"] = step_idx
            stops.append(info)
            if info.get("active"):
                key = f"{info.get('tag')}|{info.get('id')}|{info.get('label')}"
                seen_keys.append(key)
                if not info.get("hasFocusIndicator"):
                    missing_indicator.append({"tab_step": step_idx, "tag": info.get("tag"), "label": info.get("label")})
                if info.get("obscuredBy"):
                    obscured.append({"tab_step": step_idx, "label": info.get("label"), "coveredBy": info.get("obscuredBy")})

        escape_result: dict[str, Any] | None = None
        if args.dialog_trigger:
            page.locator(args.dialog_trigger).first.click()
            page.wait_for_timeout(150)
            before_esc = page.evaluate("document.querySelectorAll('[role=\"dialog\"], dialog[open]').length")
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)
            after_esc = page.evaluate("document.querySelectorAll('[role=\"dialog\"], dialog[open]').length")
            escape_result = {
                "trigger": args.dialog_trigger,
                "open_dialogs_before_escape": before_esc,
                "open_dialogs_after_escape": after_esc,
                "closed_on_escape": after_esc < before_esc,
            }

        trapped = len(seen_keys) >= 6 and len(set(seen_keys[-6:])) <= 1
        probes = _drain_and_audit(page)
        out: dict[str, Any] = {
            "ok": True,
            "command": "a11y-keyboard",
            "url": redact_text(page.url),
            "viewport": args.viewport,
            "tabs_pressed": args.tabs,
            "unique_focus_targets": len(set(seen_keys)),
            "suspected_focus_trap": trapped,
            "missing_focus_indicator": missing_indicator,
            "obscured_on_focus": obscured,
            "stops": stops,
            **({"escape_check": escape_result} if escape_result is not None else {}),
            **probes,
        }
        _save_probe_artifacts(workspace, page, args.out_prefix, out)
        return out


def _add_login_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--login-url", default="")
    p.add_argument("--user", default="")
    p.add_argument("--password", default="")
    p.add_argument("--user-sel", default='input[name="username"], input[name="email"], input[type="email"]')
    p.add_argument("--pass-sel", default='input[name="password"], input[type="password"]')
    p.add_argument("--submit-sel", default='button[type="submit"], input[type="submit"]')
    p.add_argument("--storage-state", default="", help="Path to Playwright storage_state JSON outside workspace")
    p.add_argument("--headed", action="store_true", help="Run browser in headed mode")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic Playwright probe runner for blackbox-ui-qa.")
    parser.add_argument("workspace", help="Workspace directory")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sw = sub.add_parser("sweep", help="Sweep routes across viewports and save screenshots + probe telemetry")
    _add_login_flags(p_sw)
    p_sw.add_argument("--url", action="append", required=True)
    p_sw.add_argument("--viewport", action="append", default=[])
    p_sw.add_argument("--wait-ms", type=int, default=350)

    p_rs = sub.add_parser("race-search", help="Fire back-to-back search inputs to detect async race conditions")
    _add_login_flags(p_rs)
    p_rs.add_argument("--url", required=True)
    p_rs.add_argument("--selector", required=True)
    p_rs.add_argument("--query-a", required=True)
    p_rs.add_argument("--query-b", required=True)
    p_rs.add_argument("--delay-ms", type=int, default=30)
    p_rs.add_argument("--settle-ms", type=int, default=600)
    p_rs.add_argument("--result-selector", default="")
    p_rs.add_argument("--out-prefix", default="")

    p_ds = sub.add_parser("double-submit", help="Trigger rapid double-click submit to test idempotency")
    _add_login_flags(p_ds)
    p_ds.add_argument("--url", required=True)
    p_ds.add_argument("--fill", action="append", help="selector=value")
    p_ds.add_argument("--submit-selector", required=True)
    p_ds.add_argument("--count-selector", default="")
    p_ds.add_argument("--settle-ms", type=int, default=500)
    p_ds.add_argument("--out-prefix", default="")

    p_rc = sub.add_parser("reload-check", help="Submit an action, hard-reload, and verify persistence")
    _add_login_flags(p_rc)
    p_rc.add_argument("--url", required=True)
    p_rc.add_argument("--fill", action="append", help="selector=value")
    p_rc.add_argument("--submit-selector", required=True)
    p_rc.add_argument("--watch-selector", required=True)
    p_rc.add_argument("--settle-ms", type=int, default=350)
    p_rc.add_argument("--out-prefix", default="")

    p_az = sub.add_parser("authz-url", help="Test direct URL access as a secondary role in an isolated context")
    _add_login_flags(p_az)
    p_az.add_argument("--role", default="viewer")
    p_az.add_argument("--target-url", required=True)
    p_az.add_argument("--settle-ms", type=int, default=300)
    p_az.add_argument("--out-prefix", default="")

    p_sa = sub.add_parser("save-auth", help="Log in cleanly and save Playwright storageState outside the workspace")
    _add_login_flags(p_sa)
    p_sa.add_argument("--url", default="", help="Alias for --login-url")
    p_sa.add_argument("--fill", action="append", help="selector=value")
    p_sa.add_argument("--click", action="append", help="selector to click")
    p_sa.add_argument("--wait-ms", type=int, default=400)
    p_sa.add_argument("--out", required=True, help="Output JSON path outside the QA workspace")

    p_ex = sub.add_parser("exec", help="Execute a declarative multi-step JSON browser sequence with assertions and probes")
    _add_login_flags(p_ex)
    p_ex.add_argument("--stdin", action="store_true", help="Read exec plan JSON from stdin")
    p_ex.add_argument("--file", default="", help="Read exec plan JSON from file")
    p_ex.add_argument("--out-prefix", default="")

    p_ak = sub.add_parser("a11y-keyboard", help="Run automated Tab/Shift/Escape keyboard traversal and WCAG 2.2 focus checks")
    _add_login_flags(p_ak)
    p_ak.add_argument("--url", required=True)
    p_ak.add_argument("--tabs", type=int, default=25)
    p_ak.add_argument("--viewport", default="1440x900")
    p_ak.add_argument("--dialog-trigger", default="", help="Optional selector to open a modal/dialog and verify Escape closes it")
    p_ak.add_argument("--settle-ms", type=int, default=300)
    p_ak.add_argument("--out-prefix", default="")

    p_dl = sub.add_parser("deeplink-check", help="Verify SPA query/hash state and view content survive hard reload")
    _add_login_flags(p_dl)
    p_dl.add_argument("--url", required=True)
    p_dl.add_argument("--click", default="", help="Optional selector to click before reload (e.g. a tab or filter)")
    p_dl.add_argument("--expected-url-part", default="", help="Substring expected in URL before and after reload")
    p_dl.add_argument("--watch-selector", default="body", help="Selector whose text should survive reload")
    p_dl.add_argument("--settle-ms", type=int, default=350)
    p_dl.add_argument("--out-prefix", default="")

    return parser


def main() -> int:
    configure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        print(f"ERROR: Workspace not found: {workspace}", file=sys.stderr)
        return 1

    if args.command == "sweep" and not args.viewport:
        args.viewport = ["1440x900", "390x844"]

    meta = _load_meta(workspace)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print(
            "Playwright is optional and not installed. Install with: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        print(f"Import error: {exc}", file=sys.stderr)
        return 2

    dispatch = {
        "sweep": cmd_sweep,
        "race-search": cmd_race_search,
        "double-submit": cmd_double_submit,
        "reload-check": cmd_reload_check,
        "authz-url": cmd_authz_url,
        "save-auth": cmd_save_auth,
        "exec": cmd_exec,
        "a11y-keyboard": cmd_a11y_keyboard,
        "deeplink-check": cmd_deeplink_check,
    }
    with sync_playwright() as p:
        result = dispatch[args.command](workspace, meta, args, p)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
