# Demo assets

A small, entirely synthetic run that shows what `deep-ui-qa` produces. No login, network access, real company, real person or real financial data is involved.

## Generate it

From the repository root:

```bash
python examples/make_demo.py
```

This writes:

- `examples/demo-workspace/` — the workspace artifacts and text evidence
- `examples/demo_report.xlsx` — the generated Excel report

The pre-generated workbook is committed so you can open it without running anything. Re-running the script safely replaces the demo folder only; it refuses to overwrite a folder that is not the demo.

## What to look at

| Sheet | Demo highlight |
|---|---|
| **Summary** | Run contract, reconciliation rows marked `OK`, anomaly triage counts, limitations |
| **Test Cases** | Oracle families, `Pass`/`Fail`/`Blocked`/`Observation`, triage disposition and reason |
| **Defects** | One linked defect with reproduction, impact and suggestion |
| **Coverage** | Module traceability showing no unexplained gaps |
| **Field Atlas** | Controls with tested-by links or a stated reason not tested |
| **Relationships** | A verified edge and an edge with an explicit reason |
| **Test Data & Config** | Isolate fixture design, restored config change, configuration matrix |
| **Open Questions** | An open question and a limitation |

The demo deliberately includes one defect, one blocked case and one observation so the status vocabulary is visible in the workbook.

## Adapting it

Copy `make_demo.py`, change the synthetic records in `populate()`, and rerun. Keep the data fake; never put credentials or personal data into a demo workspace.
