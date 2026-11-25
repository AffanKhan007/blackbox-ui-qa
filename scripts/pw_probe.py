#!/usr/bin/env python3
"""Optional deterministic Playwright probe runner for blackbox-ui-qa workspaces.

Requires Playwright only when invoked (`pip install playwright && playwright install chromium`).
Automatically injects scripts/browser_probes.js via addInitScript, enforces
run_contract.authorized_origins and staging_confirmed, and redacts saved telemetry.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from qa_common import as_list, as_text, read_json, redact_text, slugify, write_json_atomic

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


def _open_context(browser, meta: dict, viewport: dict[str, int] | None = None):
    vp = viewport or {"width": 1440, "height": 900}
    context = browser.new_context(viewport=vp)
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
    origins = [as_text(o) for o in as_list((meta.get("run_contract") or {}).get("authorized_origins")) if as_text(o)]
    for u in args.url:
        _check_origin(u, origins)

    browser = p.chromium.launch(headless=not args.headed)
    results = []
    try:
        context, page = _open_context(browser, meta, _parse_viewport(args.viewport[0]))
        try:
            _login_if_needed(page, args, origins)
            for u in args.url:
                for vp_str in args.viewport:
                    vp = _parse_viewport(vp_str)
                    page.set_viewport_size(vp)
                    resp = page.goto(u, wait_until="domcontentloaded")
                    page.wait_for_timeout(args.wait_ms)
                    slug = slugify(urlparse(u).path.strip("/") or "home")
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
        finally:
            context.close()
    finally:
        browser.close()
    return {"ok": True, "command": "sweep", "results": results}


def cmd_race_search(workspace: Path, meta: dict, args: argparse.Namespace, p) -> dict:
    origins = [as_text(o) for o in as_list((meta.get("run_contract") or {}).get("authorized_origins")) if as_text(o)]
    _check_origin(args.url, origins)

    browser = p.chromium.launch(headless=not args.headed)
    try:
        context, page = _open_context(browser, meta)
        try:
            _login_if_needed(page, args, origins)
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
        finally:
            context.close()
    finally:
        browser.close()


def cmd_double_submit(workspace: Path, meta: dict, args: argparse.Namespace, p) -> dict:
    _require_staging(meta, "double-submit")
    origins = [as_text(o) for o in as_list((meta.get("run_contract") or {}).get("authorized_origins")) if as_text(o)]
    _check_origin(args.url, origins)

    browser = p.chromium.launch(headless=not args.headed)
    try:
        context, page = _open_context(browser, meta)
        try:
            _login_if_needed(page, args, origins)
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
            if args.out_prefix:
                shot_rel = f"evidence/screenshots/{args.out_prefix}.png"
                shot_abs = workspace / shot_rel
                shot_abs.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(shot_abs))
                out["screenshot"] = shot_rel
                out["evidence_json"] = _save_evidence_json(workspace, f"evidence/network/{args.out_prefix}.json", out)
            return out
        finally:
            context.close()
    finally:
        browser.close()


def cmd_reload_check(workspace: Path, meta: dict, args: argparse.Namespace, p) -> dict:
    _require_staging(meta, "reload-check")
    origins = [as_text(o) for o in as_list((meta.get("run_contract") or {}).get("authorized_origins")) if as_text(o)]
    _check_origin(args.url, origins)

    browser = p.chromium.launch(headless=not args.headed)
    try:
        context, page = _open_context(browser, meta)
        try:
            _login_if_needed(page, args, origins)
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
        finally:
            context.close()
    finally:
        browser.close()


def cmd_authz_url(workspace: Path, meta: dict, args: argparse.Namespace, p) -> dict:
    origins = [as_text(o) for o in as_list((meta.get("run_contract") or {}).get("authorized_origins")) if as_text(o)]
    _check_origin(args.target_url, origins)

    browser = p.chromium.launch(headless=not args.headed)
    try:
        context, page = _open_context(browser, meta)
        try:
            _login_if_needed(page, args, origins)
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
            if args.out_prefix:
                shot_rel = f"evidence/screenshots/{args.out_prefix}.png"
                shot_abs = workspace / shot_rel
                shot_abs.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(shot_abs))
                out["screenshot"] = shot_rel
                out["evidence_json"] = _save_evidence_json(workspace, f"evidence/network/{args.out_prefix}.json", out)
            return out
        finally:
            context.close()
    finally:
        browser.close()


def _add_login_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--login-url", default="")
    p.add_argument("--user", default="")
    p.add_argument("--password", default="")
    p.add_argument("--user-sel", default='input[name="username"], input[name="email"], input[type="email"]')
    p.add_argument("--pass-sel", default='input[name="password"], input[type="password"]')
    p.add_argument("--submit-sel", default='button[type="submit"], input[type="submit"]')
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

    return parser


def main() -> int:
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
    }
    with sync_playwright() as p:
        result = dispatch[args.command](workspace, meta, args, p)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
