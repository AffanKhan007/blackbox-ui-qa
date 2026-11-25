# 04 Report, Schemas & Tooling

Single source of truth for workspace structure, `qa_record.py`, JSON schemas (`schema_version: "2.0"`), validation rules, and Excel report generation.

---

## 1. Workspace Structure

```text
qa-<app>-<timestamp>/
├── 00-scope.md                          # User-supplied specs/policies & domain notes only
├── 00-progress.md                       # Lightweight stage checkpoint for resume
├── 01-app-map.md                        # Navigation tree & single state ledger
├── 02-field-atlas.json                  # Risk-targeted control inventory
├── 03-relationships.json                # Non-obvious cross-module / precedence / calc edges
├── 03-rules.md                          # IF/THEN rules & state machines
├── 04-scenarios.md                      # Multi-module scenarios & Stage 3 charters
├── 05-test-cases.json                   # Test cases & execution results
├── 06-defects.json                      # Confirmed defects (linked to Fail cases)
├── 07-fixtures-and-config-ledger.json   # QA_ fixtures, config changes & configuration matrix
├── 08-open-questions.json               # Questions, assumptions, limitations, conflicts
├── meta.json                            # Run metadata, roles, capabilities & run_contract
├── evidence/
│   ├── screenshots/
│   ├── snapshots/
│   ├── network/
│   ├── console/
│   ├── outputs/
│   └── security/
├── calc/                                # External Python verification scripts
├── DEFECTS.md                           # Severity-sorted, copy-pasteable defect tickets
└── QA_Report_<app>_<timestamp>.xlsx
```

JSON files are the sole source of truth for validation and workbook generation.

## 2. Recording Incrementally with `qa_record.py`

Prefer `qa_record.py` over editing JSON files manually. Every mutating subcommand supports single-item CLI flags OR batch JSON via `--stdin` / `--file` (PowerShell-safe for multi-line strings and bulk inserts), auto-assigns sequential IDs, validates enums, and atomically updates cross-links (`atlas_ids` -> `tested_by`, `relationship_ids` -> `verified_by`, `config_matrix_ids` -> `configuration_matrix[].tested_by`).

```bash
# Set intake / completion metadata without hand-editing meta.json
python "<skill-dir>/scripts/qa_record.py" <ws> set-meta --staging-confirmed true --role Admin --role Viewer

# Single control or test case via CLI flags
python "<skill-dir>/scripts/qa_record.py" <ws> add-control --state-id S-001 --module Payroll --path "Payroll > Run" --label "Net pay" --control computed
python "<skill-dir>/scripts/qa_record.py" <ws> add-case --module Payroll --path "Payroll > Run" --title "Net pay matches calc" --status Pass --expected "8,500.00" --actual "8,500.00" --evidence evidence/screenshots/TC-0001.png --atlas-id A-0001

# Batch insert/update via --stdin or --file (ideal on Windows PowerShell)
python "<skill-dir>/scripts/qa_record.py" <ws> add-case --file batch_cases.json
python "<skill-dir>/scripts/qa_record.py" <ws> import-guided --file Guided_Execution_app.xlsx

# Log and restore configuration changes; update cleanup/resolution status
python "<skill-dir>/scripts/qa_record.py" <ws> log-config --path "Settings > Loans" --setting Cap --original 30 --changed-to 10 --role Admin --reason "Perturbation"
python "<skill-dir>/scripts/qa_record.py" <ws> restore-config --id C-0001 --restored-value 30 --evidence evidence/snapshots/C-0001.txt
python "<skill-dir>/scripts/qa_record.py" <ws> update-fixture --id F-0001 --status deleted --cleanup "Deleted via UI"

# Seed a defect directly from a failed test case
python "<skill-dir>/scripts/qa_record.py" <ws> add-defect --from-case TC-0002 --impact "Employee underpaid" --likely-cause "Cap applied to gross (hypothesis)"
```

Supported subcommands: `set-meta`, `add-control`, `add-relationship`, `add-case`, `update-case`, `add-defect`, `update-defect`, `add-fixture`, `update-fixture`, `log-config`, `restore-config`, `add-config-matrix`, `add-question`, `update-question`, `import-guided`.

## 3. Shared Vocabularies

- **depth:** `Quick`, `Standard`, `Deep`, `Exhaustive`
- **execution_mode:** `browser`, `guided`
- **atlas_coverage_mode:** `sampled`, `risk-targeted`, `full`
- **status:** `Pass`, `Fail`, `Blocked`, `Needs Clarification`, `Observation`, `Not Run`
- **severity:** `Critical`, `High`, `Medium`, `Low`, `Enhancement`, `None`
- **priority:** `P0`, `P1`, `P2`, `P3`
- **category:** `UI & Content`, `Validation & Boundary`, `CRUD & Lifecycle`, `Business Rules & Calculation`, `Cross-Module Ripple`, `Workflow & State`, `Roles & Permissions`, `Data Volume & Search`, `Time & Dates`, `Outputs & Documents`, `Resilience & Concurrency`, `Accessibility & Locale`, `Security & Privacy`, `AI-Assisted UI`, `Other`
- **defect_type / defect.type:** `Functional`, `Calculation`, `Validation`, `Workflow/State`, `Permission/Security`, `Data Integrity`, `Integration`, `UI/UX`, `Accessibility`, `Performance`, `Content/Localization`, `Other`
- **defect.status:** `Open`, `In Progress`, `Retest`, `Fixed`, `Won't Fix`, `Duplicate`, `Not a Bug`
- **relationship.type:** `enables`, `hides`, `filters`, `populates`, `computes`, `validates`, `permits`, `schedules`, `precedence`, `locks`, `notifies`, `cascades`, `duplicates`
- **confidence:** `High`, `Medium`, `Low`
- **question.type:** `Question`, `Assumption`, `Limitation`, `Not Tested`, `Conflict`
- **question.status:** `Open`, `Answered`, `Closed`, `Accepted`
- **triage.disposition:** `Test artifact`, `Environment/data`, `Expected variant`, `Oracle gap`, `Observation`, `Defect`
- **fixture.design:** `stacked`, `isolate`, `control`, `boundary`, `state`, `volume`, `role`, `retroactive`, `other`
- **oracle.families (optional):** `Familiarity`, `Explainability`, `World`, `History`, `Image`, `Comparable products`, `Claims`, `Users' desires`, `Product`, `Purpose`, `Standards and statutes`
- **control:** `text`, `textarea`, `rich-text`, `number`, `currency`, `date`, `datetime`, `time`, `select`, `multiselect`, `searchable-select`, `radio`, `checkbox`, `toggle`, `file`, `button`, `link`, `table`, `virtual-list`, `column`, `filter`, `tab`, `menu`, `modal`, `drawer`, `toast`, `chart`, `badge`, `computed`, `canvas`, `drag-drop`, `command-palette`, `ai-stream`, `iframe`, `other`

## 4. JSON Schemas (v2.0)

### `meta.json`
Single source for metadata (no duplicate top-level `module`, `forbidden_actions`, `timezone`, or `workspace_version`).
```json
{
  "schema_version": "2.0",
  "app": "Acme HR",
  "url": "https://staging.example.com",
  "environment": "staging",
  "staging_confirmed": true,
  "version": "2026.10.3",
  "scope": "Payroll, Employees",
  "in_scope_modules": ["Payroll", "Employees"],
  "depth": "Deep",
  "execution_mode": "browser",
  "atlas_coverage_mode": "risk-targeted",
  "roles": ["Admin", "Payroll Admin"],
  "host": "OpenCode",
  "browser_tool": "Playwright MCP",
  "capabilities": { "dom_snapshot": true, "screenshot": true, "console": true, "network": true, "js_eval": true, "multiple_contexts": true, "downloads": true, "iframes": true, "can_freeze_time": false },
  "viewports": ["1440x900", "390x844"],
  "locale": "en-US",
  "started_at": "2026-11-24T09:00:00Z",
  "finished_at": "",
  "limitations": ["Manager role unavailable"],
  "run_contract": {
    "authorized_origins": ["https://staging.example.com"],
    "allowed_actions": ["read", "create QA_ records", "edit QA_ records", "delete QA_ records"],
    "forbidden_actions": ["finalise payroll", "send email"],
    "direct_url_authz_checks": true,
    "mutation_budget": "50 created records; 20 config changes",
    "data_classification": "synthetic test data only",
    "evidence_retention": "retain workspace until handoff",
    "time_anchor": { "clock": "2026-11-24T09:00:00Z", "user_timezone": "Asia/Karachi", "tenant_timezone": "Asia/Karachi", "can_freeze_time": false },
    "end_state": "All QA_ fixtures deleted or archived; config restored; no outbound messages."
  }
}
```

### `02-field-atlas.json` (`controls`)
Required: `id`, `module`, `path`, `label`, `control`. Optional: `state_id`, `required`, `default`, `options`, `constraints`, `helper_text`, `depends_on`, `affects`, `roles_visible`, `tested_by`, `not_tested_reason`, `notes`.

### `03-relationships.json` (`relationships`)
Required: `id`, `source`, `target`, `type`, `description`, plus either `verified_by` or `not_tested_reason`. Optional: `evidence`, `confidence`.

### `05-test-cases.json` (`test_cases`)
Required: `id`, `module`, `path`, `title`, `status`, `expected`.
- `Pass`: requires `actual` and existing workspace-relative `evidence`.
- `Fail`: requires `steps`, `severity` (`!= "None"`), `defect_type`, `expected`, `actual`, existing `evidence`, `triage` (`{"disposition": "Defect", "reason": "..."}`), and a linked defect in `06-defects.json` with a non-empty `suggestion`.
- `Blocked` / `Not Run`: requires `notes` or `actual` (no fake `actual` needed when `notes` explains why).
- Optional high-signal fields: `category`, `technique`, `priority`, `reason`, `role`, `preconditions`, `test_data`, `oracle` (`{type, source, confidence, families?, description}`), `surfaces_checked` (e.g. `["immediate", "reload", "list", "export", "network"]`), `correlated_modules`, `relationship_ids`, `atlas_ids`, `suggestion`, `executed_at`.

### `06-defects.json` (`defects`)
Required: `id`, `title`, `severity`, `type`, `module` (top-level module name only), `test_case_ids` (non-empty), `steps`, `expected`, `actual`, existing `evidence`, `suggestion`. Optional: `path`, `environment`, `preconditions`, `impact`, `likely_cause`, `workaround`, `status`, `notes`, `created_at`.

### `07-fixtures-and-config-ledger.json`
- `fixtures`: `id`, `name`, `purpose`, `design`, `created_via`, `status`, `cleanup`, `notes`.
- `config_changes`: `id`, `path`, `setting`, `original`, `changed_to`, `changed_at`, `role`, `reason`, `restored` (bool; if `false`, `notes` required), `restored_at`, `restored_value`, `evidence`, `notes`.
- `configuration_matrix`: `id`, `area`, `setting`, `options` (non-empty list), `branch`, `profile_value` (must be in `options`), plus `tested_by` or `not_tested_reason`.

### `08-open-questions.json` (`items`)
Required: `id`, `type`, `description`. Optional: `impact`, `owner`, `status` (`Open`/`Answered`/`Closed`/`Accepted`), `related`.

## 5. Validation Rules & Report Generation

`validate_workspace.py` and `build_report.py` enforce:
- **Blocking errors:** invalid JSON/schema version (`!= "2.0"`), duplicate IDs (including `configuration_matrix`), bad enums, broken cross-references, missing `Pass`/`Fail` evidence, non-existent/escaping/empty (`0`-byte) evidence paths, `Fail` missing `steps`/`severity`/`defect_type`/`triage`/`suggestion`/linked defect, `Defect` triage on non-`Fail`, `Blocked`/`Not Run` without explanation, unexplained `relationships` or `configuration_matrix` rows, `profile_value` outside `options`, `uncovered_control` when `depth == "Exhaustive"` or `atlas_coverage_mode == "full"`, `in_scope_modules` without cases, `restored: false` without `notes`, and any non-placeholder credential/token/password across workspace text files (including `.html`, `.htm`, `.har`, `.xml`, `.svg`).
- **Warnings:** unconfirmed staging, incomplete `run_contract`, `time_anchor.can_freeze_time` mismatch with `capabilities`, missing `Deep`/`Exhaustive` `calc/` reference or missing cross-module relationships when multiple modules are in scope, untouched `01-app-map.md` template in `Deep`/`Exhaustive` runs, `defect.module` containing `>`, untested configured `roles`, open `Assumption`/`Conflict`, `Needs Clarification`/`Observation` without explanation.

**Building deliverables:**
- Standard report (8 sheets: `Summary`, `Test Cases`, `Defects`, `Coverage` [5 tables: By module, Module traceability, By category, Relationships, Role coverage], `Field Atlas`, `Relationships`, `Test Data & Config`, `Open Questions`) plus developer-ready `DEFECTS.md` (pass `--no-defects-md` to skip):
  `python "<skill-dir>/scripts/build_report.py" <workspace>`
- Draft with errors marked: pass `--allow-incomplete`. Strict CI check: `--strict`.
- Guided execution workbook (human tester runbook): pass `--guided-sheet`, and ingest completed runs via `qa_record.py import-guided --file <xlsx>`.
- Release-over-release regression diff: `python "<skill-dir>/scripts/qa_diff.py" <baseline_ws> <current_ws>`.

## 6. Chat Handoff Format

Keep the chat reply under ~20 lines: state scope/depth/mode, case & triage breakdown, reconciliation check, top defects, unverified risks/limitations, cleanup status (config restored & `QA_` fixtures cleaned), and link to the generated `.xlsx`.
