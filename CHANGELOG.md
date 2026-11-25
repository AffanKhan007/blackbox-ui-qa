# Changelog

All notable changes to `blackbox-ui-qa` are documented here.

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
