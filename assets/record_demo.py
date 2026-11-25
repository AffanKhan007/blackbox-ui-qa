#!/usr/bin/env python3
"""Render studio-light social banner (1280x640), report preview, and demo walkthrough video.

Requires Playwright (`pip install playwright && playwright install chromium`).
Optional GIF/MP4 conversion once recorded:
    ffmpeg -y -i assets/demo.webm -vf "fps=12,scale=1100:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" assets/demo.gif
    ffmpeg -y -i assets/demo.webm -c:v libx264 -pix_fmt yuv420p assets/demo.mp4
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).resolve().parent
DOCS_HTML = ROOT / "docs" / "index.html"

sys.path.insert(0, str(ROOT / "evals" / "gym"))
import server as gym_server  # type: ignore

BANNER_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    width: 1280px; height: 640px; overflow: hidden;
    font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 55%, #e0e7ff 100%);
    color: #0f172a;
    display: flex; flex-direction: column; justify-content: space-between;
    padding: 52px 64px;
    border: 1px solid #cbd5e1;
  }
  .top { display: flex; justify-content: space-between; align-items: center; }
  .pill {
    display: inline-flex; align-items: center; gap: 8px;
    background: #1f3864; color: #fff; padding: 8px 16px; border-radius: 999px;
    font-size: 15px; font-weight: 600; letter-spacing: 0.02em;
  }
  .gym-badge {
    background: #dcfce7; color: #166534; border: 1px solid #86efac;
    padding: 8px 16px; border-radius: 999px; font-size: 15px; font-weight: 700;
  }
  .hero { margin-top: 12px; }
  h1 { font-size: 62px; font-weight: 800; letter-spacing: -0.03em; color: #0f172a; line-height: 1.08; }
  h1 span { color: #1f3864; }
  .subtitle { font-size: 25px; color: #334155; margin-top: 16px; max-width: 960px; line-height: 1.38; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-top: 28px; }
  .card {
    background: #ffffff; border: 1px solid #cbd5e1; border-radius: 14px;
    padding: 20px 22px; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
  }
  .card .k { font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: #2f5597; font-weight: 700; }
  .card .v { font-size: 21px; font-weight: 700; margin-top: 6px; color: #0f172a; }
  .card .d { font-size: 14px; color: #475569; margin-top: 6px; line-height: 1.35; }
  .footer {
    display: flex; justify-content: space-between; align-items: center;
    padding-top: 18px; border-top: 1px solid #cbd5e1; font-size: 16px; color: #475569;
  }
  code {
    background: #e2e8f0; color: #0f172a; padding: 6px 12px; border-radius: 8px;
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 15px; font-weight: 600;
  }
</style>
</head>
<body>
  <div class="top">
    <div class="pill">Agent Skill &middot; v2.1.0 &middot; MIT</div>
    <div class="gym-badge">11/11 Gym Recall &middot; 0 False Positives</div>
  </div>

  <div class="hero">
    <h1><span>blackbox-ui-qa</span></h1>
    <p class="subtitle">UI-Only Black-Box QA Agent Skill &mdash; independent <code>calc/</code> math oracles, deterministic async-race &amp; telemetry probes, and validated reports when source code is unavailable.</p>
    <div class="grid">
      <div class="card">
        <div class="k">Deliverable 1</div>
        <div class="v">REPORT.html</div>
        <div class="d">Interactive XSS-safe report with inline screenshots &amp; live filters.</div>
      </div>
      <div class="card">
        <div class="k">Deliverable 2</div>
        <div class="v">DEFECTS.md</div>
        <div class="d">Severity-sorted, copy-pasteable tickets with linked oracles.</div>
      </div>
      <div class="card">
        <div class="k">Deliverable 3</div>
        <div class="v">QA_Report_*.xlsx</div>
        <div class="d">8-tab Excel workbook with charts, coverage &amp; reconciliation.</div>
      </div>
    </div>
  </div>

  <div class="footer">
    <code>npx skills add AffanKhan007/blackbox-ui-qa</code>
    <span>github.com/AffanKhan007/blackbox-ui-qa</span>
  </div>
</body>
</html>
"""


INTRO_SLATE_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    width: 1280px; height: 720px; overflow: hidden;
    font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
    color: #0f172a;
    display: flex; flex-direction: column; justify-content: center; gap: 22px;
    padding: 56px 72px;
  }
  .tag { display:inline-block; width:fit-content; background:#1f3864; color:#fff; padding:6px 14px; border-radius:999px; font-size:14px; font-weight:700; }
  h1 { font-size: 46px; font-weight: 800; letter-spacing: -0.02em; color: #0f172a; }
  .term {
    background: #0f172a; color: #e2e8f0; border-radius: 12px; padding: 24px 28px;
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 17px; line-height: 1.65;
    box-shadow: 0 12px 30px rgba(15,23,42,0.12);
  }
  .cmd { color: #93c5fd; }
  .ok { color: #86efac; font-weight: 700; }
  .sub { font-size: 20px; color: #334155; }
</style>
</head>
<body>
  <div class="tag">blackbox-ui-qa &middot; Live Walkthrough</div>
  <h1>Probing the 11-Bug Adversarial QA Gym</h1>
  <p class="sub">1. Run deterministic probes &rarr; 2. Catch live UI/network/AI bugs &rarr; 3. Inspect interactive <code>REPORT.html</code></p>
  <div class="term">
    <div><span class="cmd">$ python scripts/pw_probe.py qa-gym sweep / race-search / authz-url</span></div>
    <div><span class="cmd">$ python scripts/qa_record.py qa-gym ingest --stdin</span> &nbsp;&rarr; <span class="ok">42 artifacts recorded</span></div>
    <div><span class="cmd">$ python evals/score_gym_run.py qa-gym</span> &nbsp;&rarr; <span class="ok">11/11 Recall (100%) &middot; 0 False Positives</span></div>
  </div>
</body>
</html>
"""


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print(f"Playwright required: {exc}", file=sys.stderr)
        return 1

    ASSETS.mkdir(parents=True, exist_ok=True)
    banner_path = ASSETS / "social-preview.png"
    report_shot_path = ASSETS / "report-preview.png"
    demo_video_path = ASSETS / "demo.webm"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # 1. Render 1280x640 GitHub Social Preview banner
        ctx = browser.new_context(viewport={"width": 1280, "height": 640}, device_scale_factor=1)
        page = ctx.new_page()
        page.set_content(BANNER_HTML)
        page.screenshot(path=str(banner_path))
        ctx.close()

        # 2. Capture crisp preview of docs/index.html (if generated)
        if DOCS_HTML.is_file():
            ctx_r = browser.new_context(viewport={"width": 1280, "height": 760}, device_scale_factor=1)
            page_r = ctx_r.new_page()
            page_r.goto(DOCS_HTML.as_uri(), wait_until="load")
            page_r.wait_for_timeout(300)
            page_r.screenshot(path=str(report_shot_path))
            ctx_r.close()

        # 3. Record 15-20s live walkthrough video against evals/gym + docs/index.html
        httpd = gym_server.start_server("127.0.0.1", 0)
        port = httpd.server_address[1]
        base_url = f"http://127.0.0.1:{port}"
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()

        with tempfile.TemporaryDirectory() as vtmp:
            ctx_v = browser.new_context(
                viewport={"width": 1280, "height": 720},
                record_video_dir=vtmp,
                record_video_size={"width": 1280, "height": 720},
            )
            vp = ctx_v.new_page()
            try:
                vp.set_content(INTRO_SLATE_HTML)
                vp.wait_for_timeout(2400)

                vp.goto(f"{base_url}/login", wait_until="domcontentloaded")
                vp.wait_for_timeout(600)
                vp.fill('input[name="username"]', "admin")
                vp.fill('input[name="password"]', "qa-admin-password")
                vp.click('button[type="submit"]')
                vp.wait_for_load_state("domcontentloaded")
                vp.wait_for_timeout(800)

                # Trigger vanishing toast + GraphQL error on /orders
                vp.click("#reserve-btn")
                vp.wait_for_timeout(1100)

                # Visit /orders/detail?id=1 and trigger optimistic 409 toggle
                vp.goto(f"{base_url}/orders/detail?id=1", wait_until="domcontentloaded")
                vp.wait_for_timeout(700)
                vp.check("#priority-toggle")
                vp.wait_for_timeout(800)

                # Visit /copilot and stream SSE answer
                vp.goto(f"{base_url}/copilot", wait_until="domcontentloaded")
                vp.wait_for_timeout(600)
                vp.click("#copilot-ask")
                vp.wait_for_timeout(1100)

                # Open generated live sample report and filter defects
                if DOCS_HTML.is_file():
                    vp.goto(DOCS_HTML.as_uri(), wait_until="load")
                    vp.wait_for_timeout(1100)
                    vp.select_option("#q-sev", "critical")
                    vp.wait_for_timeout(1000)
                    vp.select_option("#q-sev", "")
                    vp.wait_for_timeout(600)
                    vp.evaluate("window.scrollTo({top: 520, behavior: 'smooth'})")
                    vp.wait_for_timeout(1500)
            finally:
                video = vp.video
                ctx_v.close()
                httpd.shutdown()
                httpd.server_close()
                if video:
                    shutil.copy2(video.path(), demo_video_path)

        browser.close()

    print(f"Generated: {banner_path} ({banner_path.stat().st_size} bytes)")
    if report_shot_path.is_file():
        print(f"Generated: {report_shot_path} ({report_shot_path.stat().st_size} bytes)")
    if demo_video_path.is_file():
        print(f"Generated: {demo_video_path} ({demo_video_path.stat().st_size} bytes)")
    print("To render GIF/MP4 (if ffmpeg is installed):")
    print('  ffmpeg -y -i assets/demo.webm -vf "fps=12,scale=1100:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" assets/demo.gif')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
