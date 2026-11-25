# Demo assets

A synthetic `blackbox-ui-qa` v2.0 run showing how `qa_record.py`, `validate_workspace.py`, and `build_report.py` work end-to-end with fake data (no login, network access, or PII).

## Generate it

```bash
python examples/make_demo.py
```

Writes `examples/demo-workspace/` (gitignored), `examples/demo_report.xlsx`, `examples/REPORT.html`, and `examples/DEFECTS.md`. Re-running safely refreshes only the demo folder and outputs.

## Deliverables

- **[`demo_report.xlsx`](demo_report.xlsx)** — 8-tab Excel QA workbook summarized below.
- **[`REPORT.html`](REPORT.html)** — Zero-dependency interactive HTML report with live filters and inline screenshot previews.
- **[`DEFECTS.md`](DEFECTS.md)** — Severity-sorted, copy-pasteable defect tickets seeded from failed test cases.

## What is inside `demo_report.xlsx`

| Sheet | Demo highlight |
|---|---|
| **Summary** | Run contract, defect status & severity breakdowns, executed coverage, open-question counts, reconciliation (`OK`), charts |
| **Test Cases** | `Pass`, `Fail`, `Blocked`, `Observation`, `Surfaces Checked`, triage dispositions, `calc/` references |
| **Defects** | Linked defect seeded from `TC-0002` via `qa_record.py add-defect --from-case` |
| **Coverage** | Executed vs. linked coverage, module traceability, category/relationship/role coverage |
| **Field Atlas** | Risk-targeted controls |
| **Relationships** | Verified cross-module edges |
| **Test Data & Config** | Isolate fixture, restored config change, `configuration_matrix` |
| **Open Questions** | Open product question and role limitation |
