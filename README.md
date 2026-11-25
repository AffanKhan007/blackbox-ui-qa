# Blackbox UI QA

**Turn any coding agent into an adversarial, evidence-backed QA engineer for web apps you can only test through the UI.**

[![Agent Skills](https://img.shields.io/badge/Agent_Skills-SKILL.md-1F3864)](SKILL.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.1.0-blue)](CHANGELOG.md)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)](requirements.txt)
[![Works with](https://img.shields.io/badge/Works_with-Claude_Code_%7C_OpenCode_%7C_Codex_%7C_Cursor_%7C_Windsurf_%7C_Gemini_%7C_Copilot-548235)](#installation)

When source code is unavailable, generic AI "QA" turns into shallow button-clicking that misses math errors, reload data loss, async search races, and direct-URL permission bypasses—or floods you with false alarms.

`blackbox-ui-qa` gives your agent a disciplined black-box methodology, a deterministic browser telemetry sensor, optional millisecond-precision Playwright probes, a strict evidence & secret-scan validator, and three ready-to-ship deliverables. See [CHANGELOG.md](CHANGELOG.md) for release history.

---

## Why `blackbox-ui-qa` Beats Ad-Hoc UI Clicking

| Failure Mode of Ad-Hoc AI QA | How `blackbox-ui-qa` Solves It |
|---|---|
| **Trusts the app's own math** | **Oracle before actual:** Computes expected totals, proration, and rounding externally in `calc/*.py` before judging UI output. |
| **Trusts a green "Saved!" toast** | **7-surface persistence:** Verifies immediate UI, hard reload, sibling lists, downstream modules/reports, exports, audit logs, and network payloads. |
| **Misses 1.5s toasts & GraphQL HTTP 200 errors** | **`browser_probes.js` telemetry:** Attaches `MutationObserver`, `fetch`/XHR hooks (SSE-safe), and DOM/WCAG audits with automatic secret redaction. |
| **Can't catch millisecond race conditions** | **`pw_probe.py` accelerator:** Optional Playwright runner triggers true concurrent search races, double-submits, reload diffs, and isolated-role URL checks. |
| **Cries wolf on ambiguous UX** | **6-way anomaly triage:** Separates `Test artifact`, `Environment/data`, `Expected variant`, `Oracle gap`, and `Observation`—only reproduced, oracle-backed bugs become `Fail`. |
| **Hand-written, unverified summaries** | **Hard validation gate:** Blocks un-evidenced `Pass`/`Fail`, `0`-byte files, unrestored settings, and leaked tokens/passwords across `.html`/`.har`/`.json`/`.txt`. |

---

## How to Use It

Once [installed](#installation), prompt your AI agent normally—it handles workspace creation, browser probing, recording, validation, and report generation automatically.

### Example Prompts

**1. Deep Staging Audit (SaaS / ERP / Billing)**
> Use `blackbox-ui-qa` to audit our staging app at `https://staging.example.com` (staging confirmed). Logins: Admin (`admin@test.com` / `...`) and Viewer (`viewer@test.com` / `...`). Scope: Orders, Settings, and Billing. Forbidden: do not send real emails or delete non-`QA_` records. Depth: Deep.

**2. Modern SPA & AI Copilot Audit**
> Run `blackbox-ui-qa` on `https://staging.board.example` (staging confirmed). Focus on optimistic toggle rollbacks on 4xx/5xx, live search races, deep-linked `?tab=` URLs across reload, mobile `390x844` layout, and AI Copilot SSE streaming + citation grounding + prompt-injection boundaries.

**3. Guided Mode (No Browser Tool Available)**
> Use `blackbox-ui-qa` in guided mode (`--mode guided`) for `https://staging.portal.example`. Attached are 2 screenshots and a note that PDF export ignored date filters last month. Produce an execution runbook without fabricating results.

### Depth Modes

| Depth | Rigor & Coverage |
|---|---|
| **`Quick`** | Navigation map, passive error/layout sweep, smoke + top P0 risks (`sampled` atlas). |
| **`Standard`** | Full navigation map, risk-targeted controls, interleaved P0/P1 flows, multi-role checks. |
| **`Deep`** *(default)* | `Standard` **plus** Ring 0/1 cross-module modeling, single-factor config perturbations (logged & restored), external `calc/*.py` math checks, 7-surface persistence, `configuration_matrix`, and 1 chartered gap-hunt loop. |
| **`Exhaustive`** | `Deep` **plus** `full` atlas accounting (every control tested or explained), pairwise config interactions, and repeated gap-hunt loops until dry. |

---

## Architecture & 3-Stage Workflow

```mermaid
flowchart LR
    Intake["Intake & Safety Gate\n(meta.json, staging_confirmed)"] --> S1["Stage 1: Rapid Map & Sweep\n(browser_probes.js, 01-app-map.md)"]
    S1 --> S2["Stage 2: Model & Risk Execution\n(perturbations, calc/*.py, pw_probe.py)"]
    S2 --> Rec["Atomic Recording\n(qa_record.py ingest / CLI)"]
    Rec --> Val["Hard Validation Gate\n(validate_workspace.py + scan_secrets)"]
    Val --> Out["build_report.py"]
    Out --> Xlsx["QA_Report_*.xlsx\n(8 tabs + charts)"]
    Out --> Html["REPORT.html\n(interactive + screenshots)"]
    Out --> Md["DEFECTS.md\n(copy-paste tickets)"]
```

---

## Deliverables

Every validated run outputs three synchronized artifacts (or an interactive Excel runbook in `--guided-sheet` mode):

1. **`QA_Report_<app>_<timestamp>.xlsx`** — Styled 8-sheet workbook (`Summary` with charts & reconciliation, `Test Cases`, `Defects`, `Coverage` including *Journey, invariant & multi-surface persistence* and *Technique* tables, `Field Atlas`, `Relationships`, `Test Data & Config`, `Open Questions`).
2. **`REPORT.html`** — Zero-dependency, XSS-escaped interactive HTML report with KPI cards, live Module/Status/Severity/text filters, collapsible defect tickets, and inline screenshot previews.
3. **`DEFECTS.md`** — Severity-sorted (`Critical` → `Enhancement`), copy-pasteable GitHub/Jira/Linear defect tickets complete with reproduction steps, linked test-case oracles, expected vs. actual, impact, and evidence paths.

Inspect sample generated outputs in [`examples/`](examples/README.md): [`demo_report.xlsx`](examples/demo_report.xlsx), [`REPORT.html`](examples/REPORT.html), and [`DEFECTS.md`](examples/DEFECTS.md).

---

## Installation

### Prerequisites
- **Python 3.10+** with `openpyxl>=3.1` (`pip install -r requirements.txt`)
- A **browser automation tool** (host-native browser, Playwright MCP, Chrome DevTools MCP, or optional `playwright` Python: `pip install playwright && playwright install chromium`), or **Guided Mode** when no browser is available.

### One-Command Install

**macOS / Linux:**
```bash
git clone https://github.com/AffanKhan007/blackbox-ui-qa.git
cd blackbox-ui-qa

./install.sh --global                 # portable ~/.agents/skills/blackbox-ui-qa
./install.sh --project --host claude  # project-local .claude/skills/blackbox-ui-qa
./install.sh --global --host all      # install to all 8 supported hosts
```

**Windows PowerShell:**
```powershell
.\install.ps1 -Scope Global
.\install.ps1 -Scope Project -HostName opencode
.\install.ps1 -Scope Global -HostName all
```

Supported `--host` / `-HostName` targets: `universal`, `claude`, `opencode`, `codex`, `cursor`, `windsurf`, `gemini`, `copilot`, `all`.

---

## CLI Quick Reference

All workspace scripts live under `scripts/` (`init_workspace.py`, `qa_record.py`, `validate_workspace.py`, and `qa_diff.py` are pure Python stdlib):

```bash
# 1. Initialize workspace (local qa-* folders are gitignored)
python scripts/init_workspace.py --app "Acme HR" --url "https://staging.example.com" --module Payroll --depth deep

# 2. Optional deterministic Playwright probes (injects browser_probes.js via addInitScript)
python scripts/pw_probe.py <ws> sweep --login-url <url>/login --user admin --password "..." --url <url>/orders
python scripts/pw_probe.py <ws> race-search --url <url>/orders --selector "#order-search" --query-a alpha --query-b beta
python scripts/pw_probe.py <ws> double-submit --url <url>/orders --fill 'input[name="customer"]=QA_DBL' --submit-selector "#create-order-btn"
python scripts/pw_probe.py <ws> reload-check --url <url>/orders/detail?id=1 --fill "#note-input=QA_NOTE" --submit-selector '#note-form button[type="submit"]' --watch-selector "#note-display"
python scripts/pw_probe.py <ws> authz-url --login-url <url>/login --user viewer --password "..." --role viewer --target-url <url>/orders/edit?id=1

# 3. Record atomically (one-shot ingest bundle OR incremental subcommands)
python scripts/qa_record.py <ws> ingest --file bundle.json
python scripts/qa_record.py <ws> set-meta --staging-confirmed true --role admin --role viewer
python scripts/qa_record.py <ws> add-defect --from-case TC-0002 --impact "..." --likely-cause "... (hypothesis)"

# 4. Validate (blocks missing/0-byte evidence, bad refs, unrestored configs, and secrets)
python scripts/validate_workspace.py <ws> --strict

# 5. Build deliverables (.xlsx + DEFECTS.md + REPORT.html) or guided sheet round-trip
python scripts/build_report.py <ws>
python scripts/build_report.py <ws> --guided-sheet
python scripts/qa_record.py <ws> import-guided --file Guided_Execution_acme-hr.xlsx

# 6. Compare two runs across releases
python scripts/qa_diff.py <baseline_ws> <current_ws>
```

---

## Adversarial QA Gym & Benchmarks

`blackbox-ui-qa` includes a self-contained, zero-dependency local web app ([`evals/gym/server.py`](evals/gym/server.py)) and automated grader ([`evals/score_gym_run.py`](evals/score_gym_run.py)) to benchmark agents without touching external sites.

```bash
# Start local mini-SaaS gym (11 planted bugs + 2 false-positive traps)
python evals/gym/server.py --port 8765

# Grade a completed workspace against evals/gym/ground_truth.json
python evals/score_gym_run.py <workspace> --json
```

### What the Gym Tests
- **11 planted real bugs:** tax-before-discount rounding error, broken cross-module settings toggle, frontend-only save lost on reload, async search race + duplicate submit, direct-URL RBAC bypass, vanishing 1.5s toast + HTTP 200 GraphQL error, mobile `390x844` overflow & clipped button, indirect prompt-injection ticket content, optimistic UI `HTTP 409` rollback failure, SPA `?tab=` deep-link filter loss, and SSE AI streaming citation hallucination.
- **2 false-positive traps:** ambiguous `"Loyalty points apply to eligible orders"` copy (`Needs Clarification`) and cosmetic `State` vs. `Status` label drift (`Observation`).

### Observed Benchmark Results
- **Restricted webview (`js_eval: false`) on 8-bug baseline:** `7/8` (`87.5%` recall), `0` false-positive trap violations, `0` validation errors (interactive click timing missed the 30ms async search race).
- **Playwright accelerator (`pw_probe.py` + `browser_probes.js`) + `ingest` on 8-bug baseline:** `8/8` (`100.0%` recall in `24.13s`), `1` atomic `ingest` call (`33` IDs), `0` trap violations, `0` validation/secret errors.
- **Current 11-bug SPA/AI suite:** Verified end-to-end in [`tests/smoke_test.py`](tests/smoke_test.py) (`11/11` grader match + live Playwright verification of `HTTP 409` optimistic rollback, `?tab=confirmed` reload loss, and non-hanging SSE stream inspection).

---

## Development & Repository Layout

```bash
python examples/make_demo.py    # Regenerate demo report, DEFECTS.md, and REPORT.html
python tests/check_skill.py     # Validate SKILL.md, references, installers, and version parity
python tests/smoke_test.py      # Run end-to-end validation, report, diff, and live Gym tests
```

```text
blackbox-ui-qa/
├── SKILL.md                             # Core skill instructions & 3-stage loop
├── references/                          # Progressive-disclosure playbooks (loaded per stage)
│   ├── 01-discovery-and-modeling.md
│   ├── 02-test-design-and-lenses.md
│   ├── 03-execution-and-triage.md
│   ├── 04-report-and-schemas.md
│   ├── 05-tool-compat.md
│   └── 06-domain-packs.md
├── scripts/
│   ├── browser_probes.js                # Idempotent, SSE-safe telemetry & WCAG/layout probe
│   ├── pw_probe.py                      # Optional deterministic Playwright accelerator
│   ├── qa_common.py                     # Stdlib schema, validation, redaction & coverage kernel
│   ├── qa_record.py                     # Atomic CLI & one-shot JSON ingest / guided importer
│   ├── init_workspace.py                # Workspace scaffolder
│   ├── validate_workspace.py            # Workspace & secret-scan gate
│   ├── build_report.py                  # Generates .xlsx, DEFECTS.md, REPORT.html & guided sheet
│   └── qa_diff.py                       # Release-over-release regression diff
├── examples/                            # Synthetic demo generator & sample deliverables
├── evals/                               # Eval prompts, offline Adversarial QA Gym & grader
├── tests/                               # Package integrity & end-to-end smoke suite
├── install.sh / install.ps1             # Cross-platform installers for 8 agent hosts
└── .github/workflows/validate.yml       # Ubuntu/Windows × Python 3.10–3.12 + Node JS check
```

## License

MIT — see [LICENSE](LICENSE).
