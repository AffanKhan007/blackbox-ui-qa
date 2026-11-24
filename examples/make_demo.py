#!/usr/bin/env python3
"""Generate a small, fully synthetic deep-ui-qa demo workspace and workbook.

No login, network access or real personal data is involved. The generated
report exercises run contracts, triage, reconciliation, traceability and the
configuration matrix so the output is easy to read and explain.

Run from anywhere:

    python examples/make_demo.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EXAMPLES = Path(__file__).resolve().parent


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=ROOT, text=True, capture_output=True)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def prepare(workspace: Path) -> None:
    if workspace.exists():
        meta_path = workspace / "meta.json"
        is_demo = False
        if meta_path.is_file():
            try:
                is_demo = json.loads(meta_path.read_text(encoding="utf-8")).get("app") == "Demo SaaS"
            except (json.JSONDecodeError, OSError):
                is_demo = False
        if not is_demo:
            raise SystemExit(f"Refusing to overwrite a non-demo folder: {workspace}")
        shutil.rmtree(workspace)

    result = run(
        str(SCRIPTS / "init_workspace.py"),
        "--app",
        "Demo SaaS",
        "--url",
        "https://demo.example.test",
        "--module",
        "Orders",
        "--depth",
        "standard",
        "--workspace",
        str(workspace),
    )
    if result.returncode != 0:
        raise SystemExit(result.stdout + result.stderr)


def populate(workspace: Path) -> None:
    write_json(
        workspace / "meta.json",
        {
            "app": "Demo SaaS",
            "url": "https://demo.example.test",
            "environment": "staging",
            "version": "demo-1",
            "started_at": "2026-11-24T09:00:00Z",
            "finished_at": "2026-11-24T11:00:00Z",
            "depth": "Standard",
            "scope": "Orders + correlated Customers",
            "module": "Orders",
            "in_scope_modules": ["Orders", "Customers"],
            "roles": ["Admin", "Viewer"],
            "host": "demo",
            "browser_tool": "none",
            "viewport": "1280x800",
            "locale": "en-US",
            "timezone": "UTC",
            "staging_confirmed": True,
            "forbidden_actions": ["delete production data", "send email"],
            "limitations": ["Viewer role cannot export"],
            "run_contract": {
                "authorized_origins": ["https://demo.example.test"],
                "allowed_actions": ["read", "create QA_ records", "delete QA_ records"],
                "forbidden_actions": ["delete production data", "send email"],
                "mutation_budget": "5 created records; 1 config change",
                "data_classification": "synthetic test data only",
                "evidence_retention": "retained until handoff",
                "time_anchor": {
                    "clock": "2026-11-24T09:00:00Z",
                    "user_timezone": "UTC",
                    "tenant_timezone": "UTC",
                    "can_freeze_time": False,
                },
                "end_state": "QA_ fixtures deleted; config restored; no outbound messages.",
            },
            "workspace_version": "1.0",
        },
    )

    write_json(
        workspace / "02-field-atlas.json",
        {
            "controls": [
                {
                    "id": "A-0001",
                    "state_id": "S-001",
                    "module": "Orders",
                    "path": "Orders > Detail > Status",
                    "label": "Status",
                    "control": "select",
                    "required": "yes",
                    "default": "Draft",
                    "options": ["Draft", "Confirmed", "Cancelled"],
                    "options_count": 3,
                    "constraints": "Confirmed is terminal",
                    "helper_text": "Changing status updates the list badge.",
                    "depends_on": "Order exists",
                    "affects": "List badge; totals",
                    "saves_how": "On Save",
                    "roles_visible": ["Admin", "Viewer"],
                    "tested_by": ["TC-0001"],
                    "not_tested_reason": "",
                    "notes": "",
                    "evidence": "evidence/snapshots/S-001.txt",
                },
                {
                    "id": "A-0002",
                    "state_id": "S-001",
                    "module": "Orders",
                    "path": "Orders > Detail > Quantity",
                    "label": "Quantity",
                    "control": "number",
                    "required": "yes",
                    "default": "1",
                    "options": [],
                    "options_count": 0,
                    "constraints": "minimum 1, integer",
                    "helper_text": "Quantity must be positive.",
                    "depends_on": "",
                    "affects": "Order total",
                    "saves_how": "On Save",
                    "roles_visible": ["Admin"],
                    "tested_by": ["TC-0002"],
                    "not_tested_reason": "",
                    "notes": "",
                    "evidence": "evidence/snapshots/S-001.txt",
                },
                {
                    "id": "A-0003",
                    "state_id": "S-002",
                    "module": "Customers",
                    "path": "Customers > Summary > Open orders",
                    "label": "Open orders",
                    "control": "computed",
                    "required": "no",
                    "default": "empty",
                    "options": [],
                    "options_count": 0,
                    "constraints": "integer",
                    "helper_text": "",
                    "depends_on": "Order status",
                    "affects": "Customer summary",
                    "saves_how": "Computed",
                    "roles_visible": ["Admin", "Viewer"],
                    "tested_by": ["TC-0005"],
                    "not_tested_reason": "",
                    "notes": "",
                    "evidence": "",
                },
            ]
        },
    )

    write_json(
        workspace / "03-relationships.json",
        {
            "relationships": [
                {
                    "id": "R-0001",
                    "source": "A-0001",
                    "target": "A-0003",
                    "type": "computes",
                    "description": "Confirmed orders are excluded from Open orders.",
                    "evidence": "evidence/snapshots/TC-0001.txt",
                    "confidence": "High",
                    "verified_by": ["TC-0001"],
                    "not_tested_reason": "",
                },
                {
                    "id": "R-0002",
                    "source": "A-0002",
                    "target": "A-0003",
                    "type": "computes",
                    "description": "Quantity changes should recompute the summary total.",
                    "evidence": "",
                    "confidence": "Medium",
                    "verified_by": ["TC-0005"],
                    "not_tested_reason": "",
                },
            ]
        },
    )

    write_text(
        workspace / "03-rules.md",
        "# Demo rules\n\n"
        "- A confirmed order is excluded from the customer's Open orders count.\n"
        "- Quantity must be at least 1.\n"
        "- The Viewer role may read orders but may not export them.\n",
    )
    write_text(
        workspace / "04-scenarios.md",
        "# Demo scenarios\n\n"
        "SC-001 Change an order from Draft to Confirmed and check the customer summary.\n"
        "  End state: order Confirmed; summary decremented; fixture deleted.\n\n"
        "SC-002 Save an order with quantity zero and confirm whether validation blocks it.\n"
        "  End state: invalid order rejected or recorded as a defect; fixture deleted.\n",
    )

    write_json(
        workspace / "05-test-cases.json",
        {
            "test_cases": [
                {
                    "id": "TC-0001",
                    "module": "Orders",
                    "path": "Orders > Detail > Status",
                    "title": "Confirmed order disappears from Open orders",
                    "category": "Cross-Module Ripple",
                    "technique": "Perturbation",
                    "priority": "P1",
                    "reason": "The customer summary is consumed by support and must match order state.",
                    "role": "Admin",
                    "preconditions": "One QA_ order in Draft.",
                    "test_data": "QA_ORDER_01",
                    "steps": ["Open the order.", "Set Status to Confirmed.", "Save.", "Open the customer summary."],
                    "oracle": {
                        "type": "In-app policy + consistency invariant",
                        "source": "03-rules.md and the Open orders definition",
                        "confidence": "High",
                        "families": ["Familiarity", "Product", "World"],
                        "description": "Open orders decreases by one after confirmation.",
                    },
                    "expected": "Open orders decreases from 2 to 1.",
                    "actual": "Open orders decreased from 2 to 1 after reload and on the summary screen.",
                    "status": "Pass",
                    "severity": "None",
                    "defect_type": "",
                    "correlated_modules": ["Customers"],
                    "relationship_ids": ["R-0001"],
                    "atlas_ids": ["A-0001", "A-0003"],
                    "evidence": ["evidence/snapshots/TC-0001.txt", "evidence/network/TC-0001.json"],
                    "suggestion": "",
                    "notes": "",
                    "executed_at": "2026-11-24T10:05:00Z",
                },
                {
                    "id": "TC-0002",
                    "module": "Orders",
                    "path": "Orders > Detail > Quantity",
                    "title": "Quantity zero is accepted on save",
                    "category": "Validation & Boundary",
                    "technique": "Boundary value",
                    "priority": "P0",
                    "reason": "A zero-quantity order can reach downstream totals.",
                    "role": "Admin",
                    "preconditions": "A new QA_ order form.",
                    "test_data": "QA_ORDER_02",
                    "steps": ["Open a new order.", "Set Quantity to 0.", "Click Save."],
                    "oracle": {
                        "type": "In-app policy + world rule",
                        "source": "03-rules.md: quantity must be at least 1",
                        "confidence": "High",
                        "families": ["Claims", "World", "Standards and statutes"],
                        "description": "Saving with quantity zero must be rejected.",
                    },
                    "expected": "Validation error; no order saved.",
                    "actual": "Order saved with quantity 0 and appeared in the list.",
                    "status": "Fail",
                    "severity": "High",
                    "defect_type": "Validation",
                    "correlated_modules": ["Customers"],
                    "relationship_ids": [],
                    "atlas_ids": ["A-0002"],
                    "evidence": ["evidence/snapshots/TC-0002.txt"],
                    "suggestion": "Enforce the minimum server-side and show an inline error.",
                    "notes": "Reproduced twice from a clean form.",
                    "triage": {
                        "disposition": "Defect",
                        "reason": "Reproduced from a clean state and contradicted an independently stated rule.",
                        "evidence": ["evidence/snapshots/TC-0002.txt"],
                    },
                    "executed_at": "2026-11-24T10:20:00Z",
                },
                {
                    "id": "TC-0003",
                    "module": "Orders",
                    "path": "Orders > List > Export",
                    "title": "Viewer export attempt",
                    "category": "Roles & Permissions",
                    "technique": "Permission matrix",
                    "priority": "P2",
                    "reason": "Exports must respect role permissions.",
                    "role": "Viewer",
                    "preconditions": "Signed in as Viewer.",
                    "test_data": "",
                    "steps": ["Open Orders > List.", "Click Export."],
                    "oracle": {
                        "type": "In-app policy",
                        "source": "03-rules.md: Viewer may read but not export",
                        "confidence": "Medium",
                        "families": ["Claims", "Product", "Purpose"],
                        "description": "Export is unavailable to Viewer.",
                    },
                    "expected": "Export action is unavailable or refused.",
                    "actual": "Export control is hidden for Viewer; no server response was observable.",
                    "status": "Blocked",
                    "severity": "None",
                    "defect_type": "",
                    "correlated_modules": [],
                    "relationship_ids": [],
                    "atlas_ids": [],
                    "evidence": ["evidence/snapshots/TC-0003.txt"],
                    "suggestion": "",
                    "notes": "The provided Viewer account cannot reach an export endpoint; server-side enforcement remains unverified.",
                    "triage": {
                        "disposition": "Environment/data",
                        "reason": "Access limitation, not a product defect; server-side behaviour was not observable.",
                        "evidence": ["evidence/snapshots/TC-0003.txt"],
                    },
                    "executed_at": "2026-11-24T10:35:00Z",
                },
                {
                    "id": "TC-0004",
                    "module": "Orders",
                    "path": "Orders > Detail",
                    "title": "Status label differs between detail and list",
                    "category": "UI & Content",
                    "technique": "Differential",
                    "priority": "P3",
                    "reason": "Terminology drift can cause misconfiguration.",
                    "role": "Admin",
                    "preconditions": "An order exists.",
                    "test_data": "QA_ORDER_01",
                    "steps": ["Compare the status label on detail and list."],
                    "oracle": {
                        "type": "Consistency invariant",
                        "source": "Same field should use one label",
                        "confidence": "Medium",
                        "description": "Labels should match.",
                    },
                    "expected": "The same label on both screens.",
                    "actual": "Detail says 'Status'; list says 'State'.",
                    "status": "Observation",
                    "severity": "Low",
                    "defect_type": "UI/UX",
                    "correlated_modules": [],
                    "relationship_ids": [],
                    "atlas_ids": [],
                    "evidence": ["evidence/snapshots/TC-0004.txt"],
                    "suggestion": "Use one label.",
                    "notes": "Cosmetic; not a functional defect.",
                    "triage": {
                        "disposition": "Observation",
                        "reason": "Real but cosmetic difference; no functional oracle contradicted.",
                        "evidence": ["evidence/snapshots/TC-0004.txt"],
                    },
                    "executed_at": "2026-11-24T10:45:00Z",
                },
                {
                    "id": "TC-0005",
                    "module": "Customers",
                    "path": "Customers > Summary > Open orders",
                    "title": "Open orders count matches the order list",
                    "category": "Cross-Module Ripple",
                    "technique": "Metamorphic relation",
                    "priority": "P2",
                    "reason": "The customer summary is used by support and must agree with the order list.",
                    "role": "Viewer",
                    "preconditions": "One confirmed and one draft QA_ order for the customer.",
                    "test_data": "QA_ORDER_01, QA_ORDER_03",
                    "steps": ["Open Customers > Summary.", "Count non-confirmed orders in Orders > List.", "Compare."],
                    "oracle": {
                        "type": "Consistency invariant",
                        "source": "03-rules.md: confirmed orders are excluded",
                        "confidence": "High",
                        "families": ["Familiarity", "Product", "World"],
                        "description": "Open orders equals the count of non-confirmed orders.",
                    },
                    "expected": "Open orders = 1.",
                    "actual": "Open orders = 1 on the summary and after reload.",
                    "status": "Pass",
                    "severity": "None",
                    "defect_type": "",
                    "correlated_modules": ["Orders"],
                    "relationship_ids": ["R-0002"],
                    "atlas_ids": ["A-0003"],
                    "evidence": ["evidence/snapshots/TC-0005.txt"],
                    "suggestion": "",
                    "notes": "",
                    "executed_at": "2026-11-24T10:55:00Z",
                },
            ]
        },
    )

    write_json(
        workspace / "06-defects.json",
        {
            "defects": [
                {
                    "id": "DEF-0001",
                    "title": "Quantity zero is accepted on save",
                    "severity": "High",
                    "type": "Validation",
                    "module": "Orders",
                    "path": "Orders > Detail > Quantity",
                    "test_case_ids": ["TC-0002"],
                    "environment": "staging demo-1, Admin, en-US, UTC",
                    "preconditions": "A new QA_ order form.",
                    "steps": ["Open a new order.", "Set Quantity to 0.", "Click Save."],
                    "expected": "Validation error; no order saved.",
                    "actual": "Order saved with quantity 0.",
                    "evidence": ["evidence/snapshots/TC-0002.txt"],
                    "impact": "Invalid totals can reach the customer summary.",
                    "likely_cause": "Client-side check missing (hypothesis).",
                    "suggestion": "Enforce the minimum server-side and show an inline error.",
                    "workaround": "None; reject the record manually.",
                    "status": "Open",
                    "notes": "",
                    "created_at": "2026-11-24T10:25:00Z",
                }
            ]
        },
    )

    write_json(
        workspace / "07-fixtures-and-config-ledger.json",
        {
            "fixtures": [
                {
                    "id": "F-0001",
                    "name": "QA_ORDER_02_zero_qty",
                    "purpose": "Boundary subject for the quantity minimum",
                    "design": "isolate",
                    "created_via": "Orders > Add",
                    "status": "deleted",
                    "cleanup": "Deleted after the run.",
                    "notes": "Differs from QA_ORDER_01 only in quantity.",
                }
            ],
            "config_changes": [
                {
                    "id": "C-0001",
                    "path": "Settings > Orders > Allow zero quantity",
                    "setting": "Allow zero quantity",
                    "original": "false",
                    "changed_to": "true",
                    "changed_at": "2026-11-24T10:15:00Z",
                    "role": "Admin",
                    "reason": "Perturbation to isolate the validation branch.",
                    "restored": True,
                    "restored_at": "2026-11-24T10:30:00Z",
                    "restored_value": "false",
                    "evidence": "evidence/snapshots/C-0001.txt",
                    "notes": "",
                }
            ],
            "configuration_matrix": [
                {
                    "id": "CFG-0001",
                    "area": "Settings > Orders",
                    "setting": "Allow zero quantity",
                    "options": ["true", "false"],
                    "branch": "Quantity validation on save",
                    "profile_value": "false",
                    "tested_by": ["TC-0002"],
                    "not_tested_reason": "",
                }
            ],
        },
    )

    write_json(
        workspace / "08-open-questions.json",
        {
            "items": [
                {
                    "id": "Q-0001",
                    "type": "Question",
                    "description": "Should a cancelled order also be excluded from Open orders?",
                    "impact": "Affects the summary oracle for cancelled orders.",
                    "owner": "Product owner",
                    "status": "Open",
                    "related": ["R-0001"],
                },
                {
                    "id": "Q-0002",
                    "type": "Limitation",
                    "description": "Viewer server-side export enforcement could not be observed.",
                    "impact": "Permission coverage is partial.",
                    "owner": "QA",
                    "status": "Open",
                    "related": ["TC-0003"],
                },
            ]
        },
    )

    evidence = {
        "evidence/snapshots/S-001.txt": "Synthetic snapshot: Orders detail with Status and Quantity controls.",
        "evidence/snapshots/TC-0001.txt": "Synthetic snapshot: Open orders 2 -> 1 after confirmation; stable after reload.",
        "evidence/network/TC-0001.json": '{"event": "order.updated", "status": "Confirmed"}',
        "evidence/snapshots/TC-0002.txt": "Synthetic snapshot: order saved with quantity 0 and listed in Orders.",
        "evidence/snapshots/TC-0003.txt": "Synthetic snapshot: Export control not present for Viewer role.",
        "evidence/snapshots/TC-0004.txt": "Synthetic snapshot: detail label 'Status'; list label 'State'.",
        "evidence/snapshots/TC-0005.txt": "Synthetic snapshot: Open orders = 1 and matches the order list.",
        "evidence/snapshots/C-0001.txt": "Synthetic snapshot: setting changed to true, then restored to false.",
        "evidence/security/.gitkeep": "Injection-like content would be recorded here as a redacted excerpt.",
        "calc/TC-0001.txt": "Synthetic oracle note: Open orders = count(Status != Confirmed).",
    }
    for relative, text in evidence.items():
        write_text(workspace / relative, text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a synthetic deep-ui-qa demo.")
    parser.add_argument("--workspace", default=str(EXAMPLES / "demo-workspace"), help="Demo workspace folder")
    parser.add_argument("--report", default=str(EXAMPLES / "demo_report.xlsx"), help="Output workbook path")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    report = Path(args.report).expanduser().resolve()

    prepare(workspace)
    populate(workspace)

    result = run(str(SCRIPTS / "validate_workspace.py"), str(workspace))
    if result.returncode != 0:
        raise SystemExit(result.stdout + result.stderr)

    result = run(str(SCRIPTS / "build_report.py"), str(workspace), "--output", str(report))
    if result.returncode != 0:
        raise SystemExit(result.stdout + result.stderr)

    print(f"Demo workspace: {workspace}")
    print(f"Demo report:    {report}")
    print(result.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
