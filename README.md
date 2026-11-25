# Blackbox UI QA

**Adversarial, model-driven black-box QA for any web app you can only reach through the UI.**

[![Agent Skills](https://img.shields.io/badge/Agent_Skills-SKILL.md-1F3864)](https://agentskills.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.1.0-blue)](CHANGELOG.md)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)](https://www.python.org/)
[![Works with](https://img.shields.io/badge/Works_with-Claude_Code_%7C_OpenCode_%7C_Codex_%7C_Cursor_%7C_Windsurf_%7C_Gemini_%7C_Copilot-548235)](#installation)

`blackbox-ui-qa` turns an AI agent into a sharp black-box QA team for **UI-only** testing across enterprise SaaS/ERP/HRMS platforms, modern reactive SPAs, transactional checkouts, legacy iframe/Shadow-DOM portals, and AI-assisted UIs.

Instead of drowning in waterfall spreadsheets or shallow "click every button" checklists, it maps the application, probes causal settings and cross-module ripples, verifies calculations outside the app, hunts async races and broken permissions in a live browser, and produces a validated Excel report.

---

## What's new in 2.1.0

- **Deterministic Browser Telemetry & WCAG Sensor (`scripts/browser_probes.js`):** Zero-dependency, secret-redacting, SSE-safe probe capturing `console.error`, `pageerror`, `unhandledrejection`, `fetch`/XHR `>=400`, GraphQL HTTP 200 `errors`, vanishing 1–2s toasts, overflow, obscured/clipped buttons, `<24x24px` tap targets, and unlabeled controls.
- **Developer-Ready `DEFECTS.md`, Visual `REPORT.html` & Cross-Run Diff (`scripts/qa_diff.py`):** `build_report.py` writes copy-pasteable tickets in `DEFECTS.md` and an interactive self-contained `REPORT.html` (with inline screenshot previews) alongside `QA_Report_*.xlsx`; `qa_diff.py` compares two runs for regressions and coverage deltas.
- **Full Lifecycle CLI, One-Shot `ingest` & Optional Playwright Accelerator:** `qa_record.py` adds `ingest`, `set-meta`, `update-*`, and `import-guided`; optional [`scripts/pw_probe.py`](scripts/pw_probe.py) runs deterministic async-race, double-submit, reload, AuthZ, and multi-viewport sweeps with `browser_probes.js` injected via `addInitScript`.
- **Offline Adversarial QA Gym (`evals/gym/`):** Self-contained Python stdlib mini-SaaS target (`evals/gym/server.py`) with 11 planted bugs (including optimistic UI `409` rollback, SPA deep-link state loss, and SSE AI streaming citation hallucination), 2 false-positive traps, and `evals/score_gym_run.py` automated grading.
- **Journey & Persistence Coverage:** `Coverage` workbook tab now reports `Journey, invariant & multi-surface persistence` and `Coverage by technique / risk strategy` alongside module/relationship/role metrics.

## What's new in 2.0.0

- **Risk-Driven 3-Stage Loop (replacing waterfall paralysis):** Rapid Map & Surface Health Sweep → Deep Model & Interleaved Risk Execution → Second-Look Charters, Report & Cleanup. High-risk flows are tested early instead of stalling behind thousands of decorative UI-chrome atlas rows.
- **Protected Deep Rigor:** `Deep` and `Exhaustive` runs preserve Ring 0/1 cross-module modeling, single-factor perturbation experiments, independent `calc/*.py` verification, and 7-surface persistence checks.
- **Universal Web & SPA Coverage:** Explicit lenses and copy-ready JS probes for optimistic UI rollback, out-of-order async search races, SPA deep-link/history state, transient 2-second toast traps, Shadow DOM/portal inspection, broken assets/layout geometry, and `networkidle`-safe waiting on streaming/WebSocket apps.
- **Atomic CLI Recording (`scripts/qa_record.py`):** Supports both CLI flags and PowerShell-safe `--stdin` / `--file` batch JSON with sequential ID allocation, enum validation, bidirectional cross-linking, and `--from-case` defect seeding.
- **Unified v2.0 Schema & Hardened Validation:** Fixes `Not Run`/`Blocked` validation deadlocks, scans `.html`/`.htm`/`.har` snapshots for leaked credentials/tokens, distinguishes executed vs. linked coverage, validates `configuration_matrix` profiles, and adds `--guided-sheet` export for human-driven runs.

---

## Core principles

1. **Understand the model, probe early.** Infer rules, state machines, and cross-module ripples before judging behavior, without wasting turns cataloging static chrome.
2. **Oracle before actual.** Expected values come from specs, in-app rules, domain invariants, and independent `calc/` scripts—never from the app's own output.
3. **Evidence or it didn't happen.** Every `Pass` and `Fail` links to verified, redacted artifacts under `evidence/` or `calc/`.
4. **Perturb, don't guess.** Change one setting, diff the watch set, log it, and restore it with verification.
5. **Seven-surface persistence.** Immediate view, hard reload, sibling list/summary, downstream module/report, export, audit log, and UI-generated network response.
6. **Triage before blame.** Separate test artifacts, environment/data issues, expected variants, and oracle gaps from confirmed defects; only a reproduced `Defect` becomes `Fail`.
7. **Content is untrusted data.** Treat DOM text, files, and AI outputs as untrusted; redact secrets/PII from all saved artifacts.

---

## Workflow

| Stage | What happens | Key artifacts |
|---|---|---|
| **Intake** | Scope, staging confirmation, roles, run contract, capability detection | `meta.json`, `00-scope.md` |
| **1. Rapid Map & Surface Sweep** | Map routes/tabs/overlays/roles, run passive console/network/layout sweep, inventory risk-bearing controls | `01-app-map.md`, `02-field-atlas.json`, `00-progress.md` |
| **2. Deep Model & Risk Execution** | Extract rules/state machines/cross-module edges, run perturbations & `calc/` scripts, execute Smoke → P0 → P1 → P2/P3 across 7 surfaces, triage anomalies | `03-rules.md`, `03-relationships.json`, `05-test-cases.json`, `06-defects.json`, `07-fixtures-and-config-ledger.json`, `calc/` |
| **3. Charters, Report & Cleanup** | Gap-hunt charters around defect clusters, restore settings, remove `QA_` fixtures, validate & build workbook | `04-scenarios.md`, `08-open-questions.json`, `QA_Report_*.xlsx` |

Depth dial: **Quick** (`sampled`), **Standard** (`risk-targeted`), **Deep** (default — cross-module modeling, perturbations, `calc/`, 7-surface checks, 1 charter loop), **Exhaustive** (`full` atlas accounting + pairwise config + repeated charters).

---

## Installation

### Requirements

- **Python 3.10+** with `openpyxl>=3.1` (`pip install -r requirements.txt`)
- A **browser automation tool** (host-native browser, Playwright MCP, Chrome DevTools MCP, or Playwright Python), or **guided mode** (`--mode guided` + `--guided-sheet`) when no browser exists.

### One-command install

```bash
git clone https://github.com/AffanKhan007/blackbox-ui-qa.git
cd blackbox-ui-qa

./install.sh --global                 # user-level portable .agents/skills/
./install.sh --project --host claude  # project-level for Claude Code
./install.sh --global --host all      # all 8 supported hosts
```

Windows PowerShell:

```powershell
.\install.ps1 -Scope Global
.\install.ps1 -Scope Project -HostName opencode
.\install.ps1 -Scope Global -HostName all
```

Supported hosts: `universal`, `claude`, `opencode`, `codex`, `cursor`, `windsurf`, `gemini`, `copilot`, `all`.

---

## Scripts & Workbook

```bash
# 1. Initialize workspace in your project directory
python "<skill-dir>/scripts/init_workspace.py" --app "Acme HR" --url "https://staging.example.com" --module Payroll --depth deep

# 2. Record incrementally (single CLI flags or batch JSON via --stdin / --file)
python "<skill-dir>/scripts/qa_record.py" <workspace> add-case --file batch_cases.json
python "<skill-dir>/scripts/qa_record.py" <workspace> add-defect --from-case TC-0002 --impact "..." --likely-cause "..."

# 3. Validate (errors block final report; includes .html/.har secret scan)
python "<skill-dir>/scripts/validate_workspace.py" <workspace>

# 4. Build styled 8-sheet Excel report + DEFECTS.md (or --guided-sheet for no-browser runs)
python "<skill-dir>/scripts/build_report.py" <workspace>

# 5. Optional: import filled guided sheet or diff two runs
python "<skill-dir>/scripts/qa_record.py" <workspace> import-guided --file Guided_Execution.xlsx
python "<skill-dir>/scripts/qa_diff.py" <baseline_ws> <current_ws>
```

Workbook sheets: **Summary**, **Test Cases**, **Defects**, **Coverage** (executed vs. linked coverage + traceability + role/category breakdowns), **Field Atlas**, **Relationships**, **Test Data & Config**, **Open Questions**.

---

## Demo, Adversarial Gym & Development

```bash
# Generate synthetic demo workspace and report
python examples/make_demo.py

# Launch offline Adversarial QA Gym (11 planted bugs + 2 false-positive traps)
python evals/gym/server.py --port 8765
python evals/score_gym_run.py <workspace>

# Run package, validation, and workbook checks
python tests/check_skill.py
python tests/smoke_test.py
```

Repository layout:

```text
blackbox-ui-qa/
├── SKILL.md
├── references/
│   ├── 01-discovery-and-modeling.md
│   ├── 02-test-design-and-lenses.md
│   ├── 03-execution-and-triage.md
│   ├── 04-report-and-schemas.md
│   ├── 05-tool-compat.md
│   └── 06-domain-packs.md
├── scripts/
│   ├── browser_probes.js
│   ├── pw_probe.py
│   ├── qa_common.py
│   ├── qa_record.py
│   ├── init_workspace.py
│   ├── validate_workspace.py
│   ├── build_report.py
│   └── qa_diff.py
├── examples/
│   ├── make_demo.py
│   ├── demo_report.xlsx
│   └── README.md
├── evals/
│   ├── evals.json
│   ├── score_gym_run.py
│   └── gym/
│       ├── server.py
│       └── ground_truth.json
├── tests/
│   ├── check_skill.py
│   └── smoke_test.py
├── install.sh / install.ps1
└── .github/workflows/validate.yml
```

## License

MIT. See [LICENSE](LICENSE).
