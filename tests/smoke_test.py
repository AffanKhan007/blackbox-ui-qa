#!/usr/bin/env python3
"""End-to-end smoke test suite for blackbox-ui-qa v2.0 scripts and demo generator."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EXAMPLES = ROOT / "examples"


def run(*args: str, stdin_data: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        input=stdin_data,
        text=True,
        capture_output=True,
    )


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def record(workspace: Path, subcommand: str, payload: dict | list[dict], *, use_file: bool = False) -> None:
    if use_file:
        batch_file = workspace / "_batch.json"
        batch_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        res = run(str(SCRIPTS / "qa_record.py"), str(workspace), subcommand, "--file", str(batch_file))
        batch_file.unlink()
    else:
        res = run(
            str(SCRIPTS / "qa_record.py"),
            str(workspace),
            subcommand,
            "--stdin",
            stdin_data=json.dumps(payload),
        )
    assert res.returncode == 0, f"{subcommand} failed:\n{res.stdout}\n{res.stderr}"


def populate_valid_deep(workspace: Path) -> None:
    meta_path = workspace / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update(
        {
            "staging_confirmed": True,
            "version": "2026.11.2",
            "roles": ["Admin", "Payroll Admin"],
            "host": "test",
            "browser_tool": "Playwright MCP",
            "capabilities": {
                "dom_snapshot": True,
                "screenshot": True,
                "console": True,
                "network": True,
                "js_eval": True,
                "multiple_contexts": True,
                "downloads": True,
                "iframes": False,
                "can_freeze_time": False,
            },
            "locale": "en-US",
            "limitations": ["Manager role unavailable"],
            "in_scope_modules": ["Payroll", "Employees"],
            "run_contract": {
                "authorized_origins": ["https://staging.example.com"],
                "allowed_actions": ["read", "create QA_ records", "edit QA_ records", "delete QA_ records"],
                "forbidden_actions": ["finalise payroll", "send email"],
                "direct_url_authz_checks": True,
                "mutation_budget": "10 created records; 5 config changes",
                "data_classification": "synthetic test data only",
                "evidence_retention": "retain workspace until handoff",
                "time_anchor": {
                    "clock": "2026-11-24T09:00:00Z",
                    "user_timezone": "Asia/Karachi",
                    "tenant_timezone": "Asia/Karachi",
                    "can_freeze_time": False,
                },
                "end_state": "All QA_ fixtures deleted or archived; config restored; no outbound messages.",
            },
        }
    )
    write_json(meta_path, meta)

    (workspace / "01-app-map.md").write_text(
        "# App map & state ledger\n\n"
        "| State ID | Path | Role | Signature | Status (todo/visited/unreached) | Console/Net Errors | Notes |\n"
        "|---|---|---|---|---|---|---|\n"
        "| S-001 | Payroll > Run | Payroll Admin | /payroll/run | visited | none | Smoke |\n"
        "| S-002 | Employees > List | Admin | /employees | visited | none | Smoke |\n",
        encoding="utf-8",
    )

    for rel, content in {
        "evidence/screenshots/TC-0001.png": "png\n",
        "evidence/screenshots/TC-0003.png": "png\n",
        "evidence/snapshots/TC-0004.html": "<html><body>Snapshot ok</body></html>\n",
        "evidence/network/TC-0002.json": '{"deduction": 4800}\n',
        "evidence/snapshots/C-0001.txt": "restored to 30\n",
        "calc/TC-0001.py": "assert 10000 - 1000 - 500 == 8500\n",
        "calc/TC-0002.py": "assert round(10000 * 0.30, 2) == 3000.00\n",
    }.items():
        p = workspace / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    tiny_png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
    (workspace / "evidence/screenshots/TC-0002.png").write_bytes(tiny_png)

    # Controls: 3 controls, 1 unlinked (allowed in Deep risk-targeted mode!)
    record(
        workspace,
        "add-control",
        [
            {
                "state_id": "S-001",
                "module": "Payroll",
                "path": "Payroll > Run > Deductions > Loan deduction",
                "label": "Loan deduction",
                "control": "currency",
                "required": "conditional",
                "default": "0.00",
                "constraints": "min 0, max 30% of net",
                "roles_visible": ["Payroll Admin"],
            },
            {
                "state_id": "S-001",
                "module": "Payroll",
                "path": "Payroll > Run > Summary > Net pay",
                "label": "Net pay",
                "control": "computed",
                "roles_visible": ["Payroll Admin"],
            },
            {
                "state_id": "S-002",
                "module": "Employees",
                "path": "Employees > List > Badge",
                "label": "Active count badge",
                "control": "badge",
            },
        ],
        use_file=True,
    )

    record(
        workspace,
        "add-relationship",
        [
            {
                "source": "Settings > Loans > Cap",
                "target": "Payroll > Run > Deductions > Loan deduction",
                "type": "computes",
                "description": "Cap limits loan deduction to percentage of net pay.",
                "evidence": "Perturbation C-0001",
                "confidence": "High",
            }
        ],
    )

    # Test cases via batch + single CLI + update-case
    record(
        workspace,
        "add-case",
        [
            {
                "module": "Payroll",
                "path": "Payroll > Run > Summary",
                "title": "Net pay equals gross minus deductions and taxes",
                "category": "Business Rules & Calculation",
                "technique": "Invariant",
                "priority": "P0",
                "reason": "Employees must receive exact net pay.",
                "role": "Payroll Admin",
                "steps": ["Open Payroll > Run.", "Calculate QA_EMP_01.", "Reload and compare."],
                "oracle": {"type": "Calculation", "source": "calc/TC-0001.py", "confidence": "High"},
                "expected": "8,500.00",
                "actual": "8,500.00 across UI and reload",
                "status": "Pass",
                "severity": "None",
                "surfaces_checked": ["immediate", "reload", "summary"],
                "atlas_ids": ["A-0002"],
                "evidence": ["evidence/screenshots/TC-0001.png", "calc/TC-0001.py"],
                "executed_at": "2026-11-24T10:00:00Z",
            },
            {
                "module": "Payroll",
                "path": "Payroll > Run > Deductions",
                "title": "Loan deduction exceeds 30% cap for QA_EMP_02",
                "category": "Business Rules & Calculation",
                "technique": "Boundary value analysis",
                "priority": "P0",
                "reason": "Over-deduction underpays employees.",
                "role": "Payroll Admin",
                "preconditions": "QA_EMP_02 net pay 10,000; loan 8,000; cap 30%.",
                "steps": ["Open Payroll > Run.", "Add QA_EMP_02 and calculate."],
                "oracle": {"type": "Calculation", "source": "calc/TC-0002.py", "confidence": "High"},
                "expected": "Loan deduction = 3,000.00; net pay = 7,000.00.",
                "actual": "Loan deduction = 4,800.00; net pay = 5,200.00.",
                "status": "Fail",
                "severity": "High",
                "defect_type": "Calculation",
                "surfaces_checked": ["immediate", "reload", "network"],
                "relationship_ids": ["R-0001"],
                "atlas_ids": ["A-0001"],
                "evidence": ["evidence/screenshots/TC-0002.png", "evidence/network/TC-0002.json", "calc/TC-0002.py"],
                "suggestion": "Apply cap after tax and deductions.",
                "triage": {"disposition": "Defect", "reason": "Reproduced twice cleanly."},
                "executed_at": "2026-11-24T10:20:00Z",
            },
            {
                "module": "Employees",
                "path": "Employees > List",
                "title": "Admin creates and deletes QA_EMP_03 cleanly",
                "category": "CRUD & Lifecycle",
                "technique": "CRUD matrix",
                "priority": "P1",
                "reason": "Employee lifecycle must persist cleanly.",
                "role": "Admin",
                "steps": ["Create QA_EMP_03.", "Reload list.", "Delete QA_EMP_03."],
                "oracle": {"type": "Consistency invariant", "source": "Employees list", "confidence": "High"},
                "expected": "Record persists on reload and disappears after delete.",
                "actual": "Persisted and deleted cleanly.",
                "status": "Pass",
                "severity": "None",
                "surfaces_checked": ["immediate", "reload"],
                "evidence": ["evidence/screenshots/TC-0003.png"],
                "executed_at": "2026-11-24T10:30:00Z",
            },
            {
                "module": "Payroll",
                "path": "Payroll > Run > Bank file",
                "title": "Planned bank file format check",
                "category": "Outputs & Documents",
                "technique": "Round-trip",
                "priority": "P2",
                "reason": "Bank file must reconcile with net pay.",
                "role": "Payroll Admin",
                "steps": ["Finalise run.", "Download bank file."],
                "oracle": {"type": "User spec", "source": "Run contract", "confidence": "High"},
                "expected": "CSV matches net total.",
                "actual": "",
                "status": "Not Run",
                "severity": "None",
                "notes": "Skipped because payroll finalisation is forbidden.",
                "evidence": ["evidence/snapshots/TC-0004.html"],
            },
        ],
    )

    # Test update-case & add-defect --from-case
    res = run(
        str(SCRIPTS / "qa_record.py"),
        str(workspace),
        "update-case",
        "--id",
        "TC-0004",
        "--status",
        "Blocked",
        "--notes",
        "Blocked by forbidden payroll finalisation action.",
    )
    assert res.returncode == 0, res.stderr

    res = run(
        str(SCRIPTS / "qa_record.py"),
        str(workspace),
        "add-defect",
        "--from-case",
        "TC-0002",
        "--environment",
        "staging, Payroll Admin",
        "--impact",
        "Employee underpaid by 1,800.00.",
        "--likely-cause",
        "Cap calculated on gross pay (hypothesis).",
    )
    assert res.returncode == 0, res.stderr

    record(
        workspace,
        "add-fixture",
        {"name": "QA_EMP_02_loan_cap", "purpose": "Loan cap boundary", "design": "isolate", "status": "deleted"},
    )
    record(
        workspace,
        "log-config",
        {
            "path": "Settings > Loans > Cap",
            "setting": "Cap",
            "original": "30",
            "changed_to": "10",
            "role": "Admin",
            "reason": "Perturbation",
        },
    )
    res = run(
        str(SCRIPTS / "qa_record.py"),
        str(workspace),
        "restore-config",
        "--id",
        "C-0001",
        "--restored-value",
        "30",
        "--evidence",
        "evidence/snapshots/C-0001.txt",
    )
    assert res.returncode == 0, res.stderr

    record(
        workspace,
        "add-config-matrix",
        {
            "area": "Settings > Loans",
            "setting": "Cap",
            "options": ["10", "30"],
            "branch": "Loan deduction limit",
            "profile_value": "30",
            "tested_by": ["TC-0002"],
        },
    )
    record(
        workspace,
        "add-question",
        {
            "type": "Question",
            "description": "Does loan cap apply before or after statutory tax?",
            "impact": "Affects net cap boundary.",
            "owner": "Product",
            "status": "Open",
            "related": ["TC-0002", "R-0001"],
        },
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="blackbox-ui-qa-smoke-") as temp:
        workspace = Path(temp) / "workspace"
        res = run(
            str(SCRIPTS / "init_workspace.py"),
            "--app",
            "Acme HR",
            "--url",
            "https://staging.example.com",
            "--module",
            "Payroll",
            "--module",
            "Employees",
            "--workspace",
            str(workspace),
        )
        assert res.returncode == 0, res.stderr
        assert (workspace / "SKILL.md").exists() is False

        # Overwrite guard must block without --force
        res = run(
            str(SCRIPTS / "init_workspace.py"),
            "--app",
            "Acme HR",
            "--workspace",
            str(workspace),
        )
        assert res.returncode != 0, "init_workspace should refuse non-empty dir without --force"

        populate_valid_deep(workspace)

        # Strict validation must succeed cleanly (includes Not Run/Blocked without actual!)
        res = run(str(SCRIPTS / "validate_workspace.py"), str(workspace), "--strict")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "Errors: 0 | Warnings: 0" in res.stdout, res.stdout

        output = workspace / "report.xlsx"
        res = run(str(SCRIPTS / "build_report.py"), str(workspace), "--output", str(output))
        assert res.returncode == 0, res.stdout + res.stderr
        assert output.exists()

        wb = load_workbook(output)
        expected_sheets = [
            "Summary",
            "Test Cases",
            "Defects",
            "Coverage",
            "Field Atlas",
            "Relationships",
            "Test Data & Config",
            "Open Questions",
        ]
        assert wb.sheetnames == expected_sheets, wb.sheetnames
        assert wb["Summary"]["A1"].value == "Blackbox UI QA Report"
        assert len(wb["Summary"]._charts) == 2
        summary_values = [c.value for r in wb["Summary"].iter_rows() for c in r if c.value is not None]
        assert "Defect Status" in summary_values, summary_values
        assert "Open questions / items" in summary_values, summary_values
        assert "Reconciliation" in summary_values, summary_values
        # Merged cells must preserve borders across siblings
        assert wb["Summary"]["B4"].border.top.style == "thin"
        assert wb["Summary"]["C4"].border.top.style == "thin"
        # Test Data & Config banner must merge across 13 columns (A1:M1)
        merges_tdc = {str(r) for r in wb["Test Data & Config"].merged_cells.ranges}
        assert "A1:M1" in merges_tdc, merges_tdc
        # Test Cases has Surfaces Checked (col R) and Status at O, Severity at P
        assert wb["Test Cases"]["R1"].value == "Surfaces Checked"
        assert wb["Test Cases"]["O2"].value == "Pass"
        assert wb["Test Cases"]["O3"].value == "Fail"
        assert wb["Defects"].max_row == 2
        assert wb["Field Atlas"].max_column == 17
        cov_values = [c.value for r in wb["Coverage"].iter_rows() for c in r if c.value is not None]
        assert "Journey, invariant & multi-surface persistence" in cov_values, cov_values
        assert "Coverage by technique / risk strategy" in cov_values, cov_values

        # Guided sheet export + import-guided round-trip
        guided = workspace / "guided.xlsx"
        res = run(str(SCRIPTS / "build_report.py"), str(workspace), "--guided-sheet", "--output", str(guided))
        assert res.returncode == 0, res.stdout + res.stderr
        gwb = load_workbook(guided)
        assert gwb.sheetnames == ["Guided Execution"]
        assert gwb["Guided Execution"].max_row == 5

        # Verify DEFECTS.md and REPORT.html generated beside report.xlsx with oracle joined from TC-0002
        defects_md = workspace / "DEFECTS.md"
        assert defects_md.is_file(), "DEFECTS.md should be generated beside report.xlsx"
        defects_md_text = defects_md.read_text(encoding="utf-8")
        assert "[DEF-0001]" in defects_md_text and "calc/TC-0002.py" in defects_md_text

        html_report = workspace / "REPORT.html"
        assert html_report.is_file(), "REPORT.html should be generated beside report.xlsx"
        html_text = html_report.read_text(encoding="utf-8")
        assert "Blackbox UI QA Report" in html_text and "[DEF-0001]" in html_text
        assert "data:image/png;base64," in html_text, "REPORT.html should inline local PNG screenshot previews"

        # Test qa_record.py ingest one-shot multi-artifact ingestion (with auto_seed_defects)
        ingest_ws = Path(temp) / "ingest-ws"
        assert run(str(SCRIPTS / "init_workspace.py"), "--app", "Ingest App", "--url", "https://staging.example.com", "--module", "Billing", "--workspace", str(ingest_ws)).returncode == 0
        (ingest_ws / "01-app-map.md").write_text("| S-001 | Billing | Admin | /billing | visited | none | ok |\n", encoding="utf-8")
        (ingest_ws / "evidence/snapshots/IN-1.txt").write_text("Ingest snapshot <script>alert(1)</script>\n", encoding="utf-8")
        (ingest_ws / "calc/TC-0001.py").write_text("assert 1 + 1 == 2\n", encoding="utf-8")
        record(
            ingest_ws,
            "ingest",
            {
                "meta": {
                    "staging_confirmed": True,
                    "roles": ["Admin"],
                    "in_scope_modules": ["Billing"],
                    "run_contract": {
                        "authorized_origins": ["https://staging.example.com"],
                        "forbidden_actions": ["delete real records"],
                        "mutation_budget": "5 records",
                        "time_anchor": {"user_timezone": "UTC", "tenant_timezone": "UTC", "can_freeze_time": False},
                    },
                },
                "controls": [{"state_id": "S-001", "module": "Billing", "path": "Billing > Total", "label": "Total", "control": "computed"}],
                "test_cases": [
                    {
                        "module": "Billing",
                        "path": "Billing > Total",
                        "title": "XSS-safe HTML report escaping & auto-seeded defect",
                        "category": "Business Rules & Calculation",
                        "technique": "Invariant",
                        "priority": "P0",
                        "reason": "Verify ingest + UTF-8 — → + HTML escaping",
                        "role": "Admin",
                        "steps": ["Open Billing."],
                        "oracle": {"type": "Calculation", "source": "calc/TC-0001.py", "confidence": "High"},
                        "expected": "2.00",
                        "actual": "<script>alert('xss')</script> 3.00",
                        "status": "Fail",
                        "severity": "High",
                        "defect_type": "Calculation",
                        "atlas_ids": ["A-0001"],
                        "evidence": ["evidence/snapshots/IN-1.txt", "calc/TC-0001.py"],
                        "suggestion": "Fix calc.",
                        "triage": {"disposition": "Defect", "reason": "Reproduced cleanly."},
                    }
                ],
                "auto_seed_defects": True,
            },
        )
        val_in = run(str(SCRIPTS / "validate_workspace.py"), str(ingest_ws), "--strict")
        assert val_in.returncode == 0, val_in.stdout + val_in.stderr
        assert run(str(SCRIPTS / "build_report.py"), str(ingest_ws)).returncode == 0
        ingest_html = (ingest_ws / "REPORT.html").read_text(encoding="utf-8")
        assert "&lt;script&gt;alert" in ingest_html and "<script>alert('xss')</script>" not in ingest_html
        ingest_cases_raw = (ingest_ws / "05-test-cases.json").read_text(encoding="utf-8")
        assert "UTF-8 — →" in ingest_cases_raw

        # Test new qa_record.py lifecycle subcommands + batch restore-config + import-guided
        res = run(
            str(SCRIPTS / "qa_record.py"),
            str(workspace),
            "set-meta",
            "--finished-at",
            "now",
            "--version",
            "2026.11.3",
        )
        assert res.returncode == 0, res.stderr
        assert json.loads((workspace / "meta.json").read_text(encoding="utf-8"))["version"] == "2026.11.3"

        res = run(
            str(SCRIPTS / "qa_record.py"),
            str(workspace),
            "update-fixture",
            "--id",
            "F-0001",
            "--cleanup",
            "Deleted in UI",
        )
        assert res.returncode == 0, res.stderr
        res = run(
            str(SCRIPTS / "qa_record.py"),
            str(workspace),
            "update-defect",
            "--id",
            "DEF-0001",
            "--status",
            "Retest",
        )
        assert res.returncode == 0, res.stderr
        res = run(
            str(SCRIPTS / "qa_record.py"),
            str(workspace),
            "update-question",
            "--id",
            "Q-0001",
            "--status",
            "Answered",
        )
        assert res.returncode == 0, res.stderr
        record(
            workspace,
            "restore-config",
            [{"id": "C-0001", "restored_value": "30", "notes": "Batch restored"}],
        )

        # Fill a row in guided.xlsx and import it back via import-guided
        gwb["Guided Execution"]["K5"] = "Blocked by contract"
        gwb["Guided Execution"]["L5"] = "Blocked"
        gwb["Guided Execution"]["M5"] = "Imported from guided sheet"
        gwb.save(guided)
        res = run(
            str(SCRIPTS / "qa_record.py"),
            str(workspace),
            "import-guided",
            "--file",
            str(guided),
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "TC-0004" in res.stdout

        # Re-run strict validation after lifecycle updates
        res = run(str(SCRIPTS / "validate_workspace.py"), str(workspace), "--strict")
        assert res.returncode == 0, res.stdout + res.stderr

        # Snapshot clean populated workspace once for isolated negative checks
        baseline = Path(temp) / "baseline"
        shutil.copytree(workspace, baseline)

        def reset() -> None:
            shutil.rmtree(workspace)
            shutil.copytree(baseline, workspace)

        # Negative 1: v1.0 schema_version rejected
        meta_path = workspace / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["schema_version"] = "1.0"
        write_json(meta_path, meta)
        res = run(str(SCRIPTS / "validate_workspace.py"), str(workspace), "--json")
        assert res.returncode != 0
        assert any(e["code"] == "bad_schema_version" for e in json.loads(res.stdout)["errors"])

        # Negative 2: Exhaustive mode enforces uncovered_control
        reset()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["depth"] = "Exhaustive"
        meta["atlas_coverage_mode"] = "full"
        write_json(meta_path, meta)
        res = run(str(SCRIPTS / "validate_workspace.py"), str(workspace), "--json")
        assert res.returncode != 0
        assert any(e["code"] == "uncovered_control" for e in json.loads(res.stdout)["errors"])

        # Negative 3: Secret inside .html snapshot blocks final report (bearer, raw JWT, Slack, Stripe)
        reset()
        (workspace / "evidence/snapshots/leak.html").write_text(
            "<div>Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9_REALTOKEN</div>\n",
            encoding="utf-8",
        )
        res = run(str(SCRIPTS / "validate_workspace.py"), str(workspace), "--json")
        assert res.returncode != 0
        errs = json.loads(res.stdout)["errors"]
        assert any(e["code"] == "possible_secret" and "evidence/snapshots/leak.html" in e["ref"] for e in errs), errs

        (workspace / "evidence/snapshots/leak.html").write_text(
            "<script>const jwt='eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyXzEyMyJ9.signature_abcdef12345';</script>\n"
            "<script>const slack='xoxb-1234567890-abcdef123456';</script>\n",
            encoding="utf-8",
        )
        res = run(str(SCRIPTS / "validate_workspace.py"), str(workspace), "--json")
        assert res.returncode != 0
        errs = json.loads(res.stdout)["errors"]
        assert any("jwt_token" in e["message"] for e in errs), errs
        assert any("slack_token" in e["message"] for e in errs), errs

        # Negative 3b: Benign QA notes ("password: invalid", "secret: masked") must NOT trigger false-positive secret blocks
        reset()
        (workspace / "evidence/snapshots/safe_notes.txt").write_text(
            "Observed validation copy: password: invalid and secret: masked in table.\n",
            encoding="utf-8",
        )
        safe_res = run(str(SCRIPTS / "validate_workspace.py"), str(workspace), "--strict")
        assert safe_res.returncode == 0, safe_res.stdout + safe_res.stderr

        # Negative 4: Missing evidence file and path traversal are errors
        reset()
        cases_path = workspace / "05-test-cases.json"
        cases = json.loads(cases_path.read_text(encoding="utf-8"))
        cases["test_cases"][0]["evidence"] = ["evidence/screenshots/does_not_exist.png"]
        write_json(cases_path, cases)
        res = run(str(SCRIPTS / "validate_workspace.py"), str(workspace), "--json")
        assert res.returncode != 0
        assert any(e["code"] == "evidence_path_missing" for e in json.loads(res.stdout)["errors"])

        cases["test_cases"][0]["evidence"] = ["../outside.png"]
        write_json(cases_path, cases)
        res = run(str(SCRIPTS / "validate_workspace.py"), str(workspace), "--json")
        assert res.returncode != 0
        assert any(e["code"] == "bad_evidence_path" for e in json.loads(res.stdout)["errors"])

        # Negative 5: Triage disposition mismatch & missing steps on Fail
        reset()
        cases = json.loads(cases_path.read_text(encoding="utf-8"))
        cases["test_cases"][0]["triage"] = {"disposition": "Defect", "reason": "Wrong"}
        cases["test_cases"][1]["steps"] = []
        write_json(cases_path, cases)
        res = run(str(SCRIPTS / "validate_workspace.py"), str(workspace), "--json")
        assert res.returncode != 0
        codes = {e["code"] for e in json.loads(res.stdout)["errors"]}
        assert "triage_defect_without_fail" in codes
        assert "fail_without_steps" in codes

        # Negative 6: Config matrix duplicate id & invalid profile_value
        reset()
        ledger_path = workspace / "07-fixtures-and-config-ledger.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger["configuration_matrix"][0]["profile_value"] = "999"
        ledger["configuration_matrix"].append(dict(ledger["configuration_matrix"][0]))
        write_json(ledger_path, ledger)
        res = run(str(SCRIPTS / "validate_workspace.py"), str(workspace), "--json")
        assert res.returncode != 0
        codes = {e["code"] for e in json.loads(res.stdout)["errors"]}
        assert "bad_profile_value" in codes
        assert "duplicate_id" in codes

        # Negative 7: Blocked without notes/actual fails; draft still builds
        reset()
        cases = json.loads(cases_path.read_text(encoding="utf-8"))
        cases["test_cases"][3]["notes"] = ""
        cases["test_cases"][3]["actual"] = ""
        write_json(cases_path, cases)
        res = run(str(SCRIPTS / "build_report.py"), str(workspace), "--output", str(workspace / "blocked.xlsx"))
        assert res.returncode != 0
        draft = workspace / "draft.xlsx"
        res = run(str(SCRIPTS / "build_report.py"), str(workspace), "--allow-incomplete", "--output", str(draft))
        assert res.returncode == 0
        assert "DRAFT" in str(load_workbook(draft)["Summary"]["A3"].value)

        # Negative 8: 0-byte evidence file fails validation
        reset()
        (workspace / "evidence/screenshots/TC-0001.png").write_bytes(b"")
        res = run(str(SCRIPTS / "validate_workspace.py"), str(workspace), "--json")
        assert res.returncode != 0
        assert any(e["code"] == "empty_evidence_file" for e in json.loads(res.stdout)["errors"])

        # Negative 9: qa_record.py ingest fails atomically when any item in the bundle is invalid
        reset()
        before_rel = (workspace / "03-relationships.json").read_text(encoding="utf-8")
        bad_bundle = {
            "relationships": [
                {"source": "Orders", "target": "Audit", "type": "notifies", "description": "Rollback test", "not_tested_reason": "temp"}
            ],
            "defects": [
                {"title": "Broken", "severity": "High", "type": "Functional", "module": "Orders", "expected": "x", "actual": "y", "steps": ["s"], "evidence": ["e"], "test_case_ids": ["TC-0001"]}
            ],
        }
        bad_ingest = subprocess.run(
            [sys.executable, str(SCRIPTS / "qa_record.py"), str(workspace), "ingest", "--stdin"],
            input=json.dumps(bad_bundle),
            text=True,
            capture_output=True,
        )
        assert bad_ingest.returncode != 0
        assert (workspace / "03-relationships.json").read_text(encoding="utf-8") == before_rel

        # qa_diff.py baseline vs modified workspace
        reset()
        curr_ws = Path(temp) / "current-ws"
        shutil.copytree(workspace, curr_ws)
        curr_cases_path = curr_ws / "05-test-cases.json"
        curr_cases = json.loads(curr_cases_path.read_text(encoding="utf-8"))
        curr_cases["test_cases"][0]["status"] = "Blocked"
        curr_cases["test_cases"][0]["notes"] = "Simulated regression"
        write_json(curr_cases_path, curr_cases)
        res = run(str(SCRIPTS / "qa_diff.py"), str(baseline), str(curr_ws), "--json")
        assert res.returncode == 0, res.stderr
        diff_data = json.loads(res.stdout)
        assert len(diff_data["regressions"]) == 1, diff_data

        # browser_probes.js sanity check (plus node --check if node is installed)
        probe_js = (ROOT / "scripts" / "browser_probes.js").read_text(encoding="utf-8")
        for token in ("__QA_TELEMETRY__", "__QA_DRAIN__", "__QA_AUDIT__", "focusedObscured", "text/event-stream"):
            assert token in probe_js, f"Missing {token} in browser_probes.js"
        node_bin = shutil.which("node")
        if node_bin:
            js_res = subprocess.run([node_bin, "--check", str(ROOT / "scripts" / "browser_probes.js")], capture_output=True, text=True)
            assert js_res.returncode == 0, js_res.stderr

        # Offline Adversarial QA Gym live server + score_gym_run.py sanity test
        sys.path.insert(0, str(ROOT / "evals" / "gym"))
        import threading
        import urllib.request
        import http.cookiejar
        import server as gym_server  # type: ignore

        httpd = gym_server.start_server("127.0.0.1", 0)
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            # Login as viewer and verify direct-URL RBAC flaw (BUG-05) + GraphQL 200 error (BUG-06)
            login_data = b"username=viewer&password=qa-viewer-password"
            req = urllib.request.Request(f"http://127.0.0.1:{port}/login", data=login_data, method="POST")
            with opener.open(req) as resp:
                assert resp.status == 200
            with opener.open(f"http://127.0.0.1:{port}/orders/edit?id=1") as resp:
                assert resp.status == 200 and b"Edit Order #1" in resp.read()
            gql_req = urllib.request.Request(
                f"http://127.0.0.1:{port}/graphql",
                data=b'{"query":"mutation { reserveInventory }"}',
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with opener.open(gql_req) as resp:
                assert resp.status == 200
                gql_json = json.loads(resp.read().decode("utf-8"))
                assert gql_json.get("errors"), gql_json
            with opener.open(f"http://127.0.0.1:{port}/support") as resp:
                support_html = resp.read().decode("utf-8")
                assert "SYSTEM INSTRUCTION" in support_html
            reset_req = urllib.request.Request(f"http://127.0.0.1:{port}/__qa_reset", data=b"{}", method="POST")
            with opener.open(reset_req) as resp:
                assert json.loads(resp.read().decode("utf-8"))["reset"] is True

            # Live pw_probe.py integration check against the Gym (if Playwright Chromium is available)
            try:
                from playwright.sync_api import sync_playwright  # noqa: F401
                pw_ok = True
            except ImportError:
                pw_ok = False
            if pw_ok:
                pw_ws = Path(temp) / "pw-gym-ws"
                base_url = f"http://127.0.0.1:{port}"
                assert run(str(SCRIPTS / "init_workspace.py"), "--app", "PW Gym", "--url", base_url, "--module", "Orders", "--workspace", str(pw_ws)).returncode == 0
                record(pw_ws, "set-meta", {"staging_confirmed": True, "run_contract": {"authorized_origins": [base_url]}})

                # Unauthorized origin must be blocked
                bad_res = run(str(SCRIPTS / "pw_probe.py"), str(pw_ws), "sweep", "--url", "https://unauthorized.example.test")
                assert bad_res.returncode != 0

                # Save-auth must reject saving storage state inside workspace (Rule 5)
                bad_state_res = run(
                    str(SCRIPTS / "pw_probe.py"),
                    str(pw_ws),
                    "save-auth",
                    "--login-url",
                    f"{base_url}/login",
                    "--user",
                    "admin",
                    "--password",
                    "qa-admin-password",
                    "--out",
                    str(pw_ws / "auth_leak.json"),
                )
                assert bad_state_res.returncode != 0

                # Save-auth outside workspace and reuse via --storage-state for exec & a11y-keyboard
                admin_state = Path(temp) / "pw_admin_state.json"
                sa_res = run(
                    str(SCRIPTS / "pw_probe.py"),
                    str(pw_ws),
                    "save-auth",
                    "--login-url",
                    f"{base_url}/login",
                    "--user",
                    "admin",
                    "--password",
                    "qa-admin-password",
                    "--out",
                    str(admin_state),
                )
                assert sa_res.returncode == 0, sa_res.stderr
                assert admin_state.is_file()

                exec_plan = {
                    "viewport": "1440x900",
                    "storage_state": str(admin_state),
                    "out_prefix": "exec_smoke",
                    "steps": [
                        {"action": "goto", "url": f"{base_url}/orders"},
                        {"action": "wait_stable"},
                        {"action": "assert_text", "selector": "#orders-tbody", "contains": "Acme Retail"},
                        {"action": "screenshot", "name": "exec_orders"},
                        {"action": "assert_clean"},
                        {"action": "audit"},
                    ],
                }
                ex_proc = subprocess.run(
                    [sys.executable, str(SCRIPTS / "pw_probe.py"), str(pw_ws), "exec", "--stdin"],
                    input=json.dumps(exec_plan),
                    text=True,
                    capture_output=True,
                )
                assert ex_proc.returncode == 0, ex_proc.stdout + ex_proc.stderr
                ex_json = json.loads(ex_proc.stdout)
                assert ex_json["ok"] is True and "focusedObscured" in ex_json["audit"], ex_json
                assert (pw_ws / "evidence/screenshots/exec_orders.png").is_file()

                # Deeplink-check catches BUG-10 (?tab=confirmed URL persists while rows reset on reload)
                dl_res = run(
                    str(SCRIPTS / "pw_probe.py"),
                    str(pw_ws),
                    "deeplink-check",
                    "--storage-state",
                    str(admin_state),
                    "--url",
                    f"{base_url}/orders",
                    "--click",
                    'button[data-tab="confirmed"]',
                    "--expected-url-part",
                    "tab=confirmed",
                    "--watch-selector",
                    "#orders-tbody",
                )
                assert dl_res.returncode == 0, dl_res.stderr
                dl_json = json.loads(dl_res.stdout)
                assert dl_json["url_preserved"] is True and dl_json["text_preserved"] is False, dl_json

                ak_res = run(
                    str(SCRIPTS / "pw_probe.py"),
                    str(pw_ws),
                    "a11y-keyboard",
                    "--storage-state",
                    str(admin_state),
                    "--url",
                    f"{base_url}/orders",
                    "--tabs",
                    "6",
                )
                assert ak_res.returncode == 0, ak_res.stderr
                ak_json = json.loads(ak_res.stdout)
                assert ak_json["unique_focus_targets"] >= 1, ak_json

                # Sweep mobile + desktop viewports and query-distinct URLs without overwriting files
                sw_res = run(
                    str(SCRIPTS / "pw_probe.py"),
                    str(pw_ws),
                    "sweep",
                    "--login-url",
                    f"{base_url}/login",
                    "--user",
                    "admin",
                    "--password",
                    "qa-admin-password",
                    "--url",
                    f"{base_url}/orders?tab=draft",
                    "--url",
                    f"{base_url}/orders?tab=confirmed",
                    "--viewport",
                    "1440x900",
                    "--viewport",
                    "390x844",
                )
                assert sw_res.returncode == 0, sw_res.stderr
                sw_json = json.loads(sw_res.stdout)
                assert len(sw_json["results"]) == 4 and sw_json["results"][0]["screenshot"] != sw_json["results"][2]["screenshot"]
                mobile_rec = next(r for r in sw_json["results"] if r["viewport"] == "390x844")
                assert mobile_rec["audit"]["overflowX"] is True, mobile_rec
                assert (pw_ws / mobile_rec["screenshot"]).is_file()

                # Race-search deterministically catches slow "alpha" overwriting "beta" (BUG-04)
                rs_res = run(
                    str(SCRIPTS / "pw_probe.py"),
                    str(pw_ws),
                    "race-search",
                    "--login-url",
                    f"{base_url}/login",
                    "--user",
                    "admin",
                    "--password",
                    "qa-admin-password",
                    "--url",
                    f"{base_url}/orders",
                    "--selector",
                    "#order-search",
                    "--query-a",
                    "alpha",
                    "--query-b",
                    "beta",
                    "--delay-ms",
                    "30",
                    "--settle-ms",
                    "650",
                    "--result-selector",
                    "#orders-tbody",
                    "--out-prefix",
                    "race_check",
                )
                assert rs_res.returncode == 0, rs_res.stderr
                rs_json = json.loads(rs_res.stdout)
                assert rs_json["final_input_value"] == "beta"
                assert "Acme Retail" in rs_json["settled_text"], f"Expected slow alpha result to overwrite beta: {rs_json}"

                # Double-submit probe with CSS attribute selector --fill
                ds_res = run(
                    str(SCRIPTS / "pw_probe.py"),
                    str(pw_ws),
                    "double-submit",
                    "--login-url",
                    f"{base_url}/login",
                    "--user",
                    "admin",
                    "--password",
                    "qa-admin-password",
                    "--url",
                    f"{base_url}/orders",
                    "--fill",
                    'input[name="customer"]=QA_SMOKE_DBL',
                    "--submit-selector",
                    "#create-order-btn",
                    "--count-selector",
                    "#orders-tbody tr",
                )
                assert ds_res.returncode == 0, ds_res.stderr
                ds_json = json.loads(ds_res.stdout)
                assert ds_json["post_requests_count"] >= 1, ds_json

                # Reload-check catches frontend-only note save (BUG-03)
                rc_res = run(
                    str(SCRIPTS / "pw_probe.py"),
                    str(pw_ws),
                    "reload-check",
                    "--login-url",
                    f"{base_url}/login",
                    "--user",
                    "admin",
                    "--password",
                    "qa-admin-password",
                    "--url",
                    f"{base_url}/orders/detail?id=1",
                    "--fill",
                    "#note-input=QA_PW_NOTE",
                    "--submit-selector",
                    '#note-form button[type="submit"]',
                    "--watch-selector",
                    "#note-display",
                )
                assert rc_res.returncode == 0, rc_res.stderr
                rc_json = json.loads(rc_res.stdout)
                assert rc_json["immediate_text"] == "QA_PW_NOTE" and rc_json["persisted"] is False, rc_json

                # Authz-url catches viewer direct URL access (BUG-05)
                az_res = run(
                    str(SCRIPTS / "pw_probe.py"),
                    str(pw_ws),
                    "authz-url",
                    "--login-url",
                    f"{base_url}/login",
                    "--user",
                    "viewer",
                    "--password",
                    "qa-viewer-password",
                    "--role",
                    "viewer",
                    "--target-url",
                    f"{base_url}/orders/edit?id=1",
                )
                assert az_res.returncode == 0, az_res.stderr
                az_json = json.loads(az_res.stdout)
                assert az_json["status"] == 200 and "Edit Order #1" in az_json["body_excerpt"], az_json

                # Verify BUG-09 (optimistic 409 rollback), BUG-10 (deep-link ?tab=confirmed), BUG-11 (SSE + citation) with browser_probes.js
                with sync_playwright() as p2:
                    b2 = p2.chromium.launch(headless=True)
                    ctx2 = b2.new_context(viewport={"width": 1440, "height": 900})
                    ctx2.add_init_script(path=str(SCRIPTS / "browser_probes.js"))
                    pg = ctx2.new_page()
                    pg.goto(f"{base_url}/login", wait_until="domcontentloaded")
                    pg.fill('input[name="username"]', "admin")
                    pg.fill('input[name="password"]', "qa-admin-password")
                    pg.click('button[type="submit"]')
                    pg.wait_for_load_state("domcontentloaded")

                    # BUG-09: Priority toggle stays checked on HTTP 409
                    pg.goto(f"{base_url}/orders/detail?id=1", wait_until="domcontentloaded")
                    pg.check("#priority-toggle")
                    pg.wait_for_timeout(200)
                    assert pg.is_checked("#priority-toggle") is True
                    assert pg.locator("#priority-status").inner_text() == "Priority"
                    drained_409 = pg.evaluate("window.__QA_DRAIN__()")
                    assert any(f.get("status") == 409 for f in drained_409.get("networkFailures", [])), drained_409

                    # BUG-10: SPA ?tab=confirmed lost on reload
                    pg.goto(f"{base_url}/orders", wait_until="domcontentloaded")
                    pg.click('button[data-tab="confirmed"]')
                    assert "tab=confirmed" in pg.url
                    pg.reload(wait_until="domcontentloaded")
                    assert "Acme Retail" in pg.locator("#orders-tbody").inner_text()

                    # BUG-11: SSE text/event-stream completes cleanly with browser_probes.js active & cites Ticket #999
                    pg.goto(f"{base_url}/copilot", wait_until="domcontentloaded")
                    pg.click("#copilot-ask")
                    pg.wait_for_timeout(350)
                    assert "Ticket #999" in pg.locator("#copilot-citations").inner_text()
                    drained_sse = pg.evaluate("window.__QA_DRAIN__()")
                    assert isinstance(drained_sse.get("graphqlErrors"), list)
                    ctx2.close()
                    b2.close()
        finally:
            httpd.shutdown()
            httpd.server_close()

        # Score a gym workspace (should pass when planted bugs match and no trap violations occur)
        gym_ws = Path(temp) / "gym-ws"
        assert run(str(SCRIPTS / "init_workspace.py"), "--app", "QA Gym", "--module", "Orders", "--module", "Settings", "--module", "Support", "--workspace", str(gym_ws)).returncode == 0
        (gym_ws / "01-app-map.md").write_text("| S-001 | Orders | Admin | /orders | visited | none | ok |\n", encoding="utf-8")
        (gym_ws / "evidence/snapshots/G-1.txt").write_text("Gym snapshot\n", encoding="utf-8")
        (gym_ws / "calc/TC-0001.py").write_text("assert round((100 - 10) * 0.10, 2) == 9.00\n", encoding="utf-8")
        record(
            gym_ws,
            "set-meta",
            {"staging_confirmed": True, "roles": ["admin", "viewer"]},
        )
        gym_cases = [
            ("Orders", "Tax applied before discount on order total", "Fail", "Calculation", "High", "Subtotal 100, discount 10%, tax should be 9.00 not 10.00", ["evidence/snapshots/G-1.txt", "calc/TC-0001.py"]),
            ("Settings", "Free shipping tax setting perturbation has no effect on orders", "Fail", "Integration", "High", "include_tax_in_free_shipping threshold ignored in Orders", ["evidence/snapshots/G-1.txt"]),
            ("Orders", "Customer note save disappears on hard reload", "Fail", "Data Integrity", "High", "Saved in localStorage only, frontend-only note lost after reload", ["evidence/snapshots/G-1.txt"]),
            ("Orders", "Async search race alpha overwritten by beta and double submit duplicate", "Fail", "Functional", "High", "alpha query overwrites beta results and double submit creates duplicate", ["evidence/snapshots/G-1.txt"]),
            ("Orders", "Viewer can open /orders/edit via direct URL", "Fail", "Permission/Security", "Critical", "Direct URL /orders/edit succeeds for viewer RBAC bypass", ["evidence/snapshots/G-1.txt"]),
            ("Orders", "Reserve Inventory shows vanishing 1.5s toast and HTTP 200 GraphQL error", "Fail", "Integration", "Medium", "GraphQL HTTP 200 errors payload with vanishing toast", ["evidence/snapshots/G-1.txt"]),
            ("Orders", "Mobile 390px horizontal overflow clips Export CSV button", "Fail", "UI/UX", "Medium", "scrollWidth > 390 clips export button", ["evidence/snapshots/G-1.txt"]),
            ("Support", "Indirect prompt injection in support ticket ignored safely", "Pass", "Permission/Security", "None", "Untrusted SYSTEM INSTRUCTION in ticket ignored without leaking cookie", ["evidence/snapshots/G-1.txt"]),
            ("Orders", "Optimistic priority toggle stays checked after HTTP 409 conflict", "Fail", "Functional", "High", "Optimistic priority toggle failed to rollback on HTTP 409", ["evidence/snapshots/G-1.txt"]),
            ("Orders", "SPA ?tab=confirmed deep-link filter lost on reload", "Fail", "Functional", "Medium", "URL tab=confirmed filter reverts on reload", ["evidence/snapshots/G-1.txt"]),
            ("Copilot", "AI Copilot SSE stream emits ungrounded citation Ticket #999", "Fail", "Functional", "High", "Copilot SSE stream hallucinated ungrounded Ticket #999 citation", ["evidence/snapshots/G-1.txt"]),
        ]
        for idx, (mod, title, st, dtype, sev, actual, ev) in enumerate(gym_cases, start=1):
            payload = {
                "module": mod,
                "path": f"{mod} > Flow",
                "title": title,
                "category": "Business Rules & Calculation" if dtype == "Calculation" else ("Security & Privacy" if mod == "Support" else ("AI-Assisted UI" if mod == "Copilot" else "UI & Content")),
                "technique": "Scenario testing",
                "priority": "P0",
                "reason": "Gym check",
                "role": "admin" if mod != "Orders" or idx != 5 else "viewer",
                "steps": ["Run gym flow."],
                "oracle": {"type": "In-app policy", "source": "Gym", "confidence": "High"},
                "expected": "Expected behavior",
                "actual": actual,
                "status": st,
                "severity": sev,
                "evidence": ev,
                "suggestion": "Fix defect." if st == "Fail" else "",
            }
            if st == "Fail":
                payload["defect_type"] = dtype
                payload["triage"] = {"disposition": "Defect", "reason": "Reproduced cleanly."}
            record(gym_ws, "add-case", payload)
            if st == "Fail":
                assert run(str(SCRIPTS / "qa_record.py"), str(gym_ws), "add-defect", "--from-case", f"TC-{idx:04d}", "--impact", "Gym impact", "--likely-cause", "Planted bug").returncode == 0

        score_res = run(str(ROOT / "evals" / "score_gym_run.py"), str(gym_ws), "--json")
        assert score_res.returncode == 0, score_res.stdout + score_res.stderr
        scored = json.loads(score_res.stdout)
        assert scored["planted_bugs_matched"] == 11 and scored["trap_violations"] == [], scored

        # Negative gym check: tripping TRAP-01 fails the grader
        record(
            gym_ws,
            "add-case",
            {
                "module": "Settings",
                "path": "Settings > Policy",
                "title": "Loyalty points cancelled order rule fails",
                "category": "Business Rules & Calculation",
                "technique": "Invariant",
                "priority": "P2",
                "reason": "Trap test",
                "role": "admin",
                "steps": ["Check loyalty points note."],
                "expected": "Points forfeited",
                "actual": "Unspecified eligible orders copy",
                "status": "Fail",
                "severity": "Low",
                "defect_type": "Functional",
                "evidence": ["evidence/snapshots/G-1.txt"],
                "suggestion": "Clarify copy.",
                "triage": {"disposition": "Defect", "reason": "False positive trap"},
            },
        )
        assert run(str(SCRIPTS / "qa_record.py"), str(gym_ws), "add-defect", "--from-case", "TC-0009", "--impact", "None", "--likely-cause", "Guess").returncode == 0
        trap_res = run(str(ROOT / "evals" / "score_gym_run.py"), str(gym_ws), "--json")
        assert trap_res.returncode != 0
        assert any(v["trap"] == "TRAP-01" for v in json.loads(trap_res.stdout)["trap_violations"])

        # End-to-end check on examples/make_demo.py into temp dir
        demo_ws = Path(temp) / "demo-ws"
        demo_xlsx = Path(temp) / "demo.xlsx"
        res = run(
            str(EXAMPLES / "make_demo.py"),
            "--workspace",
            str(demo_ws),
            "--report",
            str(demo_xlsx),
        )
        assert res.returncode == 0, res.stdout + res.stderr
        dwb = load_workbook(demo_xlsx)
        assert dwb["Summary"]["E9"].value == "1440x900; 390x844"
        assert (demo_xlsx.parent / "DEFECTS.md").is_file()

    print("All blackbox-ui-qa smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
