# 03 Execution, Triage & Cleanup

Read in Stage 2/3 before mutating data, logging defects, or wrapping up.

---

## 1. Pre-Flight Safety Gate

Before any create, edit, or delete:
- `meta.json` confirms `staging_confirmed: true` and populated `run_contract` (`authorized_origins`, `allowed_actions`, `forbidden_actions`, `mutation_budget`, `time_anchor`, `end_state`).
- Watch-set baseline snapshot saved; `07-fixtures-and-config-ledger.json` ready; outgoing side effects (emails, webhooks, billing, payroll finalisation) gated.
- Credentials exist only in session memory—never in files, shell commands, URLs, or logs.

## 2. Risk-Ordered Interleaved Execution

Run **Smoke → P0 → P1 → P2 → P3** within each module as soon as its Ring 0/1 model is known, keeping fixture state warm:
1. **Smoke:** Sign in, verify main nav, one create/read/update/reload cycle, one core output, and passive surface health.
2. **P0:** Money, calculations, security/permissions, data integrity, irreversible state locks, checkout/core blockers.
3. **P1:** Core workflows, role matrix, cross-module ripples, multi-cycle carry-forward.
4. **P2/P3:** Validation edges, sorting/pagination, exports, layout/accessibility, cosmetic wording.

Update `00-progress.md` and record results incrementally with `qa_record.py` (`add-case`, `update-case`).

## 3. Evidence Capture & Redaction

Every `Pass` and `Fail` needs workspace-relative evidence checked by `validate_workspace.py`:

| Channel | When | Path Pattern |
|---|---|---|
| Screenshot | Every `Fail`, visual/layout check, key `Pass` | `evidence/screenshots/TC-0001.png` |
| DOM/text snapshot | Forms, lists, `Fail` states, toast captures | `evidence/snapshots/TC-0001.html` or `.txt` |
| Network excerpt | Status ≥400, GraphQL errors, payload mismatch | `evidence/network/TC-0001.json` |
| Console excerpt | JS errors / uncaught rejections | `evidence/console/TC-0001.log` |
| Exported file | CSV, XLSX, PDF downloads | `evidence/outputs/TC-0001.csv` |
| Independent math | Every calculation check in `Deep`/`Exhaustive` | `calc/TC-0001.py` (+ `.txt`) |
| Security excerpt | Unexpected prompt injection encountered passively | `evidence/security/SEC-001.txt` |

**Redaction rule (strictly enforced by `scan_secrets()` across `.html`, `.har`, `.json`, `.txt`, `.log`, `.md`):**
Mask or strip all passwords, bearer/JWT tokens, cookies, API keys, URL userinfo, and real PII before saving any snapshot, HAR, or screenshot. Never download/retain real customer/employee documents.

## 4. Seven-Surface Verification & End-State Checks

Never trust an inline success toast alone. For high-impact mutations/calculations, verify and record `surfaces_checked`:
1. **Immediate view** (form/detail right after action)
2. **After hard reload** (proves backend persistence—frontend-only state loss is a High defect)
3. **Sibling summary/list** (table row, counter, dashboard card)
4. **Downstream module** (payroll run, ledger, report, analytics)
5. **Export/document** (CSV/XLSX/PDF/print view)
6. **Audit log** (actor, timestamp, old -> new value)
7. **UI-generated network payload** (read-only status + payload check; never hand-craft requests)

**End-state assertion:** After multi-module scenarios, verify the record settled in its terminal/expected state, downstream totals match, settings are restored, and fixtures clean up without residue.

## 5. Reproduction, Isolation & Anomaly Triage

Before logging a defect:
1. **Reproduce** cleanly (reload / fresh fixture); minimize to the fewest steps.
2. **Isolate** with an `isolate` fixture pair differing in one attribute if found on a `stacked` subject.
3. **Triage** every unexpected result through this funnel—**only `Defect` becomes `Fail`**:

| Disposition | Meaning | Resulting Status |
|---|---|---|
| **Test artifact** | Bad fixture, wrong role, stale cache, missed step | Fix test & rerun (do not report as Fail) |
| **Environment/data** | Staging outage, eventual-consistency lag, missing role access | Rerun when stable or `Blocked` |
| **Expected variant** | Plan, country, role, or setting legitimately changes the rule | Re-derive expected or `Pass` |
| **Oracle gap** | No credible expected result or conflicting specs | `Needs Clarification` + question in `08-open-questions.json` |
| **Observation** | Real UX/terminology/perf concern not violating a functional oracle | `Observation` |
| **Defect** | Reproduced cleanly, contradicts credible oracle | `Fail` + `triage` + linked `DEF-XXXX` |

## 6. Writing Actionable Defects (`06-defects.json`)

Seed directly from a failed case to avoid duplication:
`python "<skill-dir>/scripts/qa_record.py" <ws> add-defect --from-case TC-0002 --impact "..." --likely-cause "... (hypothesis)"`

- **Severity:** `Critical` (money/security/data loss/blocker, no workaround), `High` (major flow/calc broken, painful workaround), `Medium` (functional defect with workaround / significant edge), `Low` (minor UI/usability), `Enhancement` (non-defect suggestion).
- **Important schema rule:** `module` must be the **top-level module name** (e.g., `"Payroll"`), and `path` holds the breadcrumb (`"Payroll > Run > Deductions"`). Never put a breadcrumb in `module`, or `Coverage` traceability will split across phantom rows.
- Mark `likely_cause` explicitly as a hypothesis. Provide concrete, safe `suggestion` directions.

## 7. Chartered Gap Hunts (Stage 3)

After risk-ordered execution, run focused 30–60 minute charters (`Explore <area> using <lens> to discover <risk>`):
- Cluster hunting around modules that already produced `Fail`s
- Untested `03-relationships.json` edges, roles, illegal transitions, and date/cycle boundaries
- Async races, SPA back/forward loops, and visual/mobile checks

Debrief each charter in `04-scenarios.md` (covered / found / remains). Run 1 loop for `Deep`; repeat until dry for `Exhaustive`.

## 8. Config Ledger, Cleanup & Stop Conditions

- Log every setting change **before** mutating (`qa_record.py log-config`), and restore + verify watch set immediately after (`restore-config`). Any unrestored setting requires an explicit explanation in `notes`.
- Delete `QA_` fixtures in reverse dependency order (archive/deactivate if foreign-key locked, and document).
- Delete temporary auth storage files outside the workspace, verify logout + Back button protection, and confirm `run_contract.end_state`.
- **Stop and ask the user** if: production data appears, an action would trigger irreversible external side effects, a config restore fails, MFA/CAPTCHA blocks progress, or time runs out.
