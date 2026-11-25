#!/usr/bin/env python3
"""Generate a synthetic blackbox-ui-qa v2.0 demo workspace and Excel workbook.

Uses qa_record.py and build_report.py so the demo validates end-to-end against
the live v2.0 schema with zero login, network access, or personal data.
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


def run(*args: str, stdin_data: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        input=stdin_data,
        text=True,
        capture_output=True,
    )


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
        "--module",
        "Customers",
        "--depth",
        "deep",
        "--workspace",
        str(workspace),
    )
    if result.returncode != 0:
        raise SystemExit(result.stdout + result.stderr)


def record_batch(workspace: Path, subcommand: str, payload: list[dict] | dict) -> None:
    res = run(
        str(SCRIPTS / "qa_record.py"),
        str(workspace),
        subcommand,
        "--stdin",
        stdin_data=json.dumps(payload),
    )
    if res.returncode != 0:
        raise SystemExit(f"{subcommand} failed:\n{res.stdout}\n{res.stderr}")


def populate(workspace: Path) -> None:
    write_json(
        workspace / "meta.json",
        {
            "schema_version": "2.0",
            "app": "Demo SaaS",
            "url": "https://demo.example.test",
            "environment": "staging",
            "staging_confirmed": True,
            "version": "demo-2.0",
            "scope": "Orders + correlated Customers",
            "in_scope_modules": ["Orders", "Customers"],
            "depth": "Deep",
            "execution_mode": "browser",
            "atlas_coverage_mode": "risk-targeted",
            "roles": ["Admin", "Viewer"],
            "host": "demo",
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
            "viewports": ["1440x900", "390x844"],
            "locale": "en-US",
            "started_at": "2026-11-24T09:00:00Z",
            "finished_at": "2026-11-24T11:00:00Z",
            "limitations": ["Viewer role cannot reach CSV export endpoint"],
            "run_contract": {
                "authorized_origins": ["https://demo.example.test"],
                "allowed_actions": ["read", "create QA_ records", "delete QA_ records"],
                "forbidden_actions": ["delete non-QA records", "send email"],
                "direct_url_authz_checks": True,
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
        },
    )

    write_text(
        workspace / "01-app-map.md",
        "# App map & state ledger\n\n"
        "| State ID | Path | Role | Signature | Status (todo/visited/unreached) | Console/Net Errors | Notes |\n"
        "|---|---|---|---|---|---|---|\n"
        "| S-001 | Orders > Detail | Admin | /orders/detail | visited | none | Demo state |\n"
        "| S-002 | Customers > Summary | Admin, Viewer | /customers | visited | none | Demo state |\n",
    )
    write_text(
        workspace / "03-rules.md",
        "# Demo rules\n\n"
        "- RULE-001 IF Order.status == Confirmed THEN excluded from Customer Open orders.\n"
        "- RULE-002 IF Order.quantity < 1 THEN save is rejected.\n"
        "- RULE-003 IF Role == Viewer THEN Export is denied.\n",
    )
    write_text(
        workspace / "04-scenarios.md",
        "# Demo scenarios\n\n"
        "SC-001 Confirm a Draft order and verify Customer Open orders across reload & list.\n"
        "  End state: order Confirmed; summary decremented; QA_ fixture deleted.\n",
    )

    evidence = {
        "evidence/snapshots/S-001.txt": "Synthetic snapshot: Orders detail with Status and Quantity controls.",
        "evidence/snapshots/TC-0001.txt": "Synthetic snapshot: Open orders 2 -> 1 after confirmation; stable after reload.",
        "evidence/network/TC-0001.json": '{"event": "order.updated", "status": "Confirmed"}',
        "evidence/snapshots/TC-0002.txt": "Synthetic snapshot: order saved with quantity 0 and listed in Orders.",
        "evidence/snapshots/TC-0003.txt": "Synthetic snapshot: Export control hidden for Viewer role.",
        "evidence/snapshots/TC-0004.txt": "Synthetic snapshot: detail label 'Status'; list label 'State'.",
        "evidence/snapshots/TC-0005.txt": "Synthetic snapshot: Open orders = 1 and matches the order list.",
        "evidence/snapshots/C-0001.txt": "Synthetic snapshot: setting toggled true -> false and restored.",
        "calc/TC-0001.py": "open_orders = sum(1 for o in orders if o['status'] != 'Confirmed')\nassert open_orders == 1\n",
        "calc/TC-0005.py": "subtotal = 100.00\ntax = round(subtotal * 0.10, 2)\nassert subtotal + tax == 110.00\n",
    }
    for relative, text in evidence.items():
        write_text(workspace / relative, text)

    record_batch(
        workspace,
        "add-control",
        [
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
                "constraints": "Confirmed is terminal",
                "helper_text": "Confirmed orders leave Open orders.",
                "affects": "Customer summary; totals",
                "roles_visible": ["Admin", "Viewer"],
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
                "constraints": "minimum 1, integer",
                "affects": "Order total",
                "roles_visible": ["Admin"],
            },
            {
                "id": "A-0003",
                "state_id": "S-002",
                "module": "Customers",
                "path": "Customers > Summary > Open orders",
                "label": "Open orders",
                "control": "computed",
                "depends_on": "Order status",
                "roles_visible": ["Admin", "Viewer"],
            },
        ],
    )

    record_batch(
        workspace,
        "add-relationship",
        [
            {
                "id": "R-0001",
                "source": "Orders > Detail > Status",
                "target": "Customers > Summary > Open orders",
                "type": "computes",
                "description": "Confirmed orders are excluded from Open orders.",
                "evidence": "Perturbation: confirming QA_ORDER_01 decremented Open orders 2 -> 1.",
                "confidence": "High",
            },
            {
                "id": "R-0002",
                "source": "Orders > Detail > Quantity",
                "target": "Customers > Summary > Open total",
                "type": "computes",
                "description": "Order total recalculates with tax on quantity update.",
                "evidence": "calc/TC-0005.py",
                "confidence": "High",
            },
        ],
    )

    record_batch(
        workspace,
        "add-case",
        [
            {
                "id": "TC-0001",
                "module": "Orders",
                "path": "Orders > Detail > Status",
                "title": "Confirmed order decrements Customer Open orders across reload",
                "category": "Cross-Module Ripple",
                "technique": "Cross-surface consistency",
                "priority": "P1",
                "reason": "Support relies on Open orders matching live order status.",
                "role": "Admin",
                "preconditions": "One QA_ order in Draft.",
                "test_data": "QA_ORDER_01",
                "steps": ["Open QA_ORDER_01.", "Set Status to Confirmed.", "Save & hard reload.", "Open Customers > Summary."],
                "oracle": {
                    "type": "Consistency invariant",
                    "source": "03-rules.md RULE-001; calc/TC-0001.py",
                    "confidence": "High",
                    "description": "Open orders decreases by 1 after confirmation.",
                },
                "expected": "Open orders decreases from 2 to 1.",
                "actual": "Open orders decreased from 2 to 1 immediately, after reload, and on summary.",
                "status": "Pass",
                "severity": "None",
                "surfaces_checked": ["immediate", "reload", "summary", "network"],
                "correlated_modules": ["Customers"],
                "relationship_ids": ["R-0001"],
                "atlas_ids": ["A-0001", "A-0003"],
                "evidence": ["evidence/snapshots/TC-0001.txt", "evidence/network/TC-0001.json", "calc/TC-0001.py"],
                "executed_at": "2026-11-24T10:05:00Z",
            },
            {
                "id": "TC-0002",
                "module": "Orders",
                "path": "Orders > Detail > Quantity",
                "title": "Quantity zero is accepted on order save",
                "category": "Validation & Boundary",
                "technique": "Boundary value analysis",
                "priority": "P0",
                "reason": "Zero-quantity orders corrupt downstream totals and fulfillment.",
                "role": "Admin",
                "preconditions": "New QA_ order form.",
                "test_data": "QA_ORDER_02",
                "steps": ["Open a new order.", "Set Quantity to 0.", "Click Save and reload."],
                "oracle": {
                    "type": "In-app policy",
                    "source": "03-rules.md RULE-002",
                    "confidence": "High",
                    "description": "Saving quantity 0 must fail validation.",
                },
                "expected": "Inline validation error; order not saved.",
                "actual": "Order saved with quantity 0 and persisted after reload.",
                "status": "Fail",
                "severity": "High",
                "defect_type": "Validation",
                "surfaces_checked": ["immediate", "reload", "list"],
                "correlated_modules": ["Customers"],
                "atlas_ids": ["A-0002"],
                "evidence": ["evidence/snapshots/TC-0002.txt"],
                "suggestion": "Enforce minimum >= 1 server-side and display inline error.",
                "notes": "Reproduced twice from clean state.",
                "triage": {
                    "disposition": "Defect",
                    "reason": "Reproduced cleanly; contradicts explicit minimum >= 1 rule.",
                    "evidence": ["evidence/snapshots/TC-0002.txt"],
                },
                "executed_at": "2026-11-24T10:20:00Z",
            },
            {
                "id": "TC-0003",
                "module": "Orders",
                "path": "Orders > List > Export",
                "title": "Viewer export permission enforcement",
                "category": "Roles & Permissions",
                "technique": "Permission matrix",
                "priority": "P2",
                "reason": "Exports must respect role boundaries.",
                "role": "Viewer",
                "preconditions": "Signed in as Viewer.",
                "steps": ["Open Orders > List.", "Locate Export button."],
                "oracle": {
                    "type": "In-app policy",
                    "source": "03-rules.md RULE-003",
                    "confidence": "Medium",
                },
                "expected": "Export action denied.",
                "actual": "Export control hidden in UI; server endpoint behavior unverified.",
                "status": "Blocked",
                "severity": "None",
                "evidence": ["evidence/snapshots/TC-0003.txt"],
                "notes": "No export route exposed to Viewer; server check unverified.",
                "triage": {
                    "disposition": "Environment/data",
                    "reason": "UI hides button; no UI-generated export URL available to probe.",
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
                "reason": "Terminology drift causes user confusion.",
                "role": "Admin",
                "steps": ["Compare Status label on detail and list views."],
                "oracle": {
                    "type": "Consistency invariant",
                    "source": "Same field should share one label",
                    "confidence": "Medium",
                },
                "expected": "Same label on both screens.",
                "actual": "Detail says 'Status'; list header says 'State'.",
                "status": "Observation",
                "severity": "Low",
                "defect_type": "UI/UX",
                "evidence": ["evidence/snapshots/TC-0004.txt"],
                "notes": "Cosmetic terminology mismatch.",
                "triage": {
                    "disposition": "Observation",
                    "reason": "Real terminology drift; no functional failure.",
                    "evidence": ["evidence/snapshots/TC-0004.txt"],
                },
                "executed_at": "2026-11-24T10:45:00Z",
            },
            {
                "id": "TC-0005",
                "module": "Customers",
                "path": "Customers > Summary > Open total",
                "title": "Customer Open total matches line qty * price + 10% tax",
                "category": "Business Rules & Calculation",
                "technique": "Invariant",
                "priority": "P1",
                "reason": "Billing summary relies on accurate order tax calculation.",
                "role": "Viewer",
                "preconditions": "QA_ORDER_03 qty 2 at 50.00.",
                "steps": ["Open Customers > Summary.", "Inspect Open total."],
                "oracle": {
                    "type": "Calculation",
                    "source": "calc/TC-0005.py",
                    "confidence": "High",
                },
                "expected": "110.00",
                "actual": "110.00 after reload and on summary.",
                "status": "Pass",
                "severity": "None",
                "surfaces_checked": ["immediate", "reload", "summary"],
                "correlated_modules": ["Orders"],
                "relationship_ids": ["R-0002"],
                "atlas_ids": ["A-0003"],
                "evidence": ["evidence/snapshots/TC-0005.txt", "calc/TC-0005.py"],
                "executed_at": "2026-11-24T10:55:00Z",
            },
        ],
    )

    res = run(
        str(SCRIPTS / "qa_record.py"),
        str(workspace),
        "add-defect",
        "--from-case",
        "TC-0002",
        "--environment",
        "staging demo-2.0, Admin, en-US, UTC",
        "--impact",
        "Invalid zero-qty orders persist and distort customer totals.",
        "--likely-cause",
        "Missing server-side minimum validation (hypothesis).",
        "--workaround",
        "Manually delete invalid orders.",
    )
    if res.returncode != 0:
        raise SystemExit(res.stdout + res.stderr)

    record_batch(
        workspace,
        "add-fixture",
        [
            {
                "id": "F-0001",
                "name": "QA_ORDER_02_zero_qty",
                "purpose": "Boundary isolate for quantity minimum",
                "design": "isolate",
                "created_via": "Orders > Add",
                "status": "deleted",
                "cleanup": "Deleted after run.",
            }
        ],
    )
    record_batch(
        workspace,
        "log-config",
        [
            {
                "id": "C-0001",
                "path": "Settings > Orders > Allow zero quantity",
                "setting": "Allow zero quantity",
                "original": "false",
                "changed_to": "true",
                "changed_at": "2026-11-24T10:15:00Z",
                "role": "Admin",
                "reason": "Perturbation to isolate validation branch.",
                "restored": True,
                "restored_at": "2026-11-24T10:30:00Z",
                "restored_value": "false",
                "evidence": "evidence/snapshots/C-0001.txt",
            }
        ],
    )
    record_batch(
        workspace,
        "add-config-matrix",
        [
            {
                "id": "CFG-0001",
                "area": "Settings > Orders",
                "setting": "Allow zero quantity",
                "options": ["true", "false"],
                "branch": "Quantity validation on save",
                "profile_value": "false",
                "tested_by": ["TC-0002"],
            }
        ],
    )
    record_batch(
        workspace,
        "add-question",
        [
            {
                "id": "Q-0001",
                "type": "Question",
                "description": "Should Cancelled orders also leave Customer Open orders?",
                "impact": "Defines summary oracle for cancelled orders.",
                "owner": "Product owner",
                "status": "Open",
                "related": ["R-0001"],
            },
            {
                "id": "Q-0002",
                "type": "Limitation",
                "description": "Viewer server-side export enforcement unverified.",
                "impact": "Partial permission coverage.",
                "owner": "QA",
                "status": "Open",
                "related": ["TC-0003"],
            },
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a synthetic blackbox-ui-qa v2.0 demo.")
    parser.add_argument("--workspace", default=str(EXAMPLES / "demo-workspace"), help="Demo workspace folder")
    parser.add_argument("--report", default=str(EXAMPLES / "demo_report.xlsx"), help="Output workbook path")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    report = Path(args.report).expanduser().resolve()

    prepare(workspace)
    populate(workspace)

    result = run(str(SCRIPTS / "validate_workspace.py"), str(workspace), "--strict")
    if result.returncode != 0:
        raise SystemExit(result.stdout + result.stderr)

    result = run(str(SCRIPTS / "build_report.py"), str(workspace), "--output", str(report), "--force")
    if result.returncode != 0:
        raise SystemExit(result.stdout + result.stderr)

    print(f"Demo workspace: {workspace}")
    print(f"Demo report:    {report}")
    print(result.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
