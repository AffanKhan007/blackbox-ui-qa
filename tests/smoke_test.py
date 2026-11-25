#!/usr/bin/env python3
"""End-to-end smoke test suite for blackbox-ui-qa v2.0 scripts and demo generator."""

from __future__ import annotations

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

    for rel, content in {
        "evidence/screenshots/TC-0001.png": "png\n",
        "evidence/screenshots/TC-0002.png": "png\n",
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

        # Guided sheet export
        guided = workspace / "guided.xlsx"
        res = run(str(SCRIPTS / "build_report.py"), str(workspace), "--guided-sheet", "--output", str(guided))
        assert res.returncode == 0, res.stdout + res.stderr
        gwb = load_workbook(guided)
        assert gwb.sheetnames == ["Guided Execution"]
        assert gwb["Guided Execution"].max_row == 5

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

        # Negative 3: Secret inside .html snapshot blocks final report
        reset()
        (workspace / "evidence/snapshots/leak.html").write_text(
            "<div>Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9_REALTOKEN</div>\n",
            encoding="utf-8",
        )
        res = run(str(SCRIPTS / "validate_workspace.py"), str(workspace), "--json")
        assert res.returncode != 0
        errs = json.loads(res.stdout)["errors"]
        assert any(e["code"] == "possible_secret" and "evidence/snapshots/leak.html" in e["ref"] for e in errs), errs

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

    print("All v2.0 smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
