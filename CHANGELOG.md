# Changelog

All notable changes to `blackbox-ui-qa` are documented here.

## [2.2.0] — 2026-11-25

- **Hardened Secret Scanning & Redaction (`scripts/qa_common.py`, `scripts/browser_probes.js`):** Added detection and redaction for raw un-prefixed JWTs (`eyJ...`), Slack tokens (`xox[baprs]-...`), and Stripe live keys (`sk_live_` / `rk_live_`), plus active-focus obscuration (`focusedObscured`) inside `window.__QA_AUDIT__()`.
- **Upgraded Playwright Probe Runner (`scripts/pw_probe.py`):** Added `--storage-state` reuse across all commands (enforcing Rule 5 by rejecting state paths inside the QA workspace), `save-auth` for login session capture outside the workspace, `exec` for declarative multi-step JSON browser workflows (`goto`, `fill`, `click`, `select`, `check`, `press`, `wait`, `wait_for`, `reload`, `screenshot`, `assert_text`, `assert_visible`, `assert_url`, `audit`), and automated `a11y-keyboard` traversal with WCAG 2.2 focus-indicator, sticky-overlay obscuration, focus-trap, and `Escape` dialog checks.
- **Zero-Duplication Recorder Core (`scripts/qa_record.py`):** Extracted shared `_prepare_*` helpers across all individual CLI subcommands and multi-artifact `ingest`, eliminating duplicated validation and ensuring strict all-or-nothing behavior across both paths.
- **Repo Hygiene & Docs:** Untracked and gitignored `assets/demo.webm` (kept `assets/record_demo.py` to regenerate locally on demand) and updated `examples/README.md` to document `REPORT.html` and `DEFECTS.md`.

## [2.1.0] — 2026-11-25

- **Deterministic Browser Sensor & Playwright Accelerator (`scripts/browser_probes.js`, `scripts/pw_probe.py`):** Added zero-dependency, idempotent, secret-redacting, SSE-safe telemetry (`console.error`, `pageerror`, `unhandledrejection`, `fetch`/XHR `>=400`, GraphQL HTTP 200 `errors`, `MutationObserver` toast capture) and `window.__QA_AUDIT__()` (overflow, broken images, obscured/clipped controls, `<24x24px` tap targets, unlabeled controls, duplicate IDs), plus optional deterministic `pw_probe.py` (`sweep`, `race-search`, `double-submit`, `reload-check`, `authz-url`). Updated `install.sh` and `install.ps1` to copy `.js` scripts.
- **Developer-Ready `DEFECTS.md`, Interactive `REPORT.html` & Cross-Run Diffing:** `build_report.py` now generates severity-sorted `DEFECTS.md` tickets (with linked test-case oracles) and a self-contained, XSS-safe `REPORT.html` (with inline screenshot previews and filters) alongside the Excel workbook; added `scripts/qa_diff.py` for baseline-vs-current regression and coverage deltas.
- **Closed-Loop `qa_record.py` (`ingest` + lifecycle commands) & Hardened Validator:** Added atomic multi-artifact `ingest` (with `auto_seed_defects`), `set-meta`, `update-fixture`, `update-defect`, `update-question`, `import-guided`, `--stdin`/`--file` support on `restore-config` and batch `update-case`, plus `--config-matrix-id` sync. `validate_workspace.py` now blocks `0`-byte evidence files and warns on untouched `01-app-map.md` in `Deep`/`Exhaustive` runs.
- **Offline Adversarial QA Gym (`evals/gym/`) & Journey Coverage:** Added a self-contained Python stdlib mini-SaaS server (`evals/gym/server.py`) with 11 planted real bugs (covering math, perturbation, reload persistence, async races, direct-URL RBAC, GraphQL/toast, mobile overflow, prompt injection, optimistic UI `409` rollback, SPA `?tab=` deep-link loss, and SSE AI streaming citation hallucination) and 2 false-positive traps, `evals/gym/ground_truth.json`, and `evals/score_gym_run.py`; added Journey/Multi-Surface Persistence and Technique tables to the `Coverage` sheet.
- **Precision Fixes in `SKILL.md`:** Added session-resume rule, explicit `staging_confirmed` gate on Stage 1 gated flows, and `Ring 0` / `Ring 1` definitions.

## [2.0.0] — 2026-11-24

Breaking v2.0.0 redesign focused on bug-finding intelligence, non-CRUD universality, and zero-bloat execution:

- **3-Stage Risk-Driven Loop:** Replaced the rigid 9-phase waterfall with Rapid Map & Surface Sweep → Deep Model & Interleaved Execution → Charters, Report & Cleanup, eliminating 2,000-control JSON bottlenecks while preserving cross-module modeling, setting perturbations, independent `calc/` scripts, and 7-surface checks in `Deep`/`Exhaustive` runs.
- **Lean Consolidated References:** Streamlined 7 bloated reference manuals into 6 single-source-of-truth guides (~55% token reduction), removing generic textbook padding and duplicate rule walls while sharpening edge-case heuristics (optimistic UI rollback, async search races, SPA history/URL state, transient toast capture, RBAC direct-URL access, Shadow DOM/portals, and `networkidle`-safe waiting).
- **Atomic Recorder CLI (`scripts/qa_record.py`):** Added stdlib CLI supporting both single-item flags and PowerShell-safe `--stdin`/`--file` batch JSON, sequential IDs, bidirectional cross-linking, and `--from-case` defect seeding.
- **Unified Schema `2.0` & Hardened Validator (`scripts/qa_common.py`):** Removed legacy v1.0 shims; fixed `Not Run`/`Blocked` `actual` deadlock; expanded `scan_secrets()` to `.html`/`.htm`/`.har` snapshots as blocking errors; added depth-aware atlas accounting (`sampled`/`risk-targeted`/`full`), executed vs. linked coverage metrics, `configuration_matrix` uniqueness & option membership checks, and open `Assumption`/`Conflict` warnings.
- **Report Builder Fixes (`scripts/build_report.py`):** Fixed `merge_write` borders/fills, `Test Data & Config` column/section spans, `Coverage` widths, `Summary` row heights, defect-status & open-question Summary metrics, inline printable charts, `Surfaces Checked` column, and `--guided-sheet` workbook export.
- **Evals, Installers & CI:** Expanded `evals/evals.json` to 6 archetype scenarios with anti-false-positive traps; fixed `install.sh`/`install.ps1` (`--host all` covering all 8 hosts and excluding `__pycache__`); updated `tests/` and CI to run `make_demo.py`.

## [1.1.0] — 2026-11-24

- Added run contracts, anomaly triage funnel, FEW HICCUPPS oracles, feature-complete configuration matrix, multi-cycle reconciliation, AI/WCAG lenses, and synthetic demo assets.

## [1.0.0] — 2026-11-04

- Initial release.
