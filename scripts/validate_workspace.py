#!/usr/bin/env python3
"""Validate a blackbox-ui-qa v2.0 workspace before building the report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from qa_common import configure_utf8_stdio, coverage, load_workspace, validate_workspace


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Validate a blackbox-ui-qa workspace.")
    parser.add_argument("workspace", help="Workspace directory")
    parser.add_argument("--json", action="store_true", help="Print issues and stats as JSON")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    parser.add_argument("--no-secret-scan", action="store_true", help="Skip the credential scan")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        print(f"Workspace not found: {workspace}", file=sys.stderr)
        return 1

    loaded = load_workspace(workspace)
    issues = validate_workspace(loaded, include_secret_scan=not args.no_secret_scan)
    stats = coverage(loaded)

    errors = [issue for issue in issues if issue["level"] == "error"]
    warnings = [issue for issue in issues if issue["level"] == "warning"]

    if args.json:
        print(
            json.dumps(
                {
                    "workspace": str(workspace),
                    "errors": errors,
                    "warnings": warnings,
                    "stats": {
                        "controls": stats["controls_total"],
                        "controls_tested": stats["controls_tested"],
                        "controls_executed": stats["controls_executed"],
                        "relationships": stats["relationships_total"],
                        "relationships_verified": stats["relationships_verified"],
                        "relationships_executed": stats["relationships_executed"],
                        "cases": stats["cases_total"],
                        "status_counts": stats["status_counts"],
                        "defects": len(loaded.get("defects") or []),
                        "defect_status_counts": stats["defect_status_counts"],
                        "open_questions_count": stats["open_questions_count"],
                        "triage_counts": stats["triage_counts"],
                        "reconciliation": stats["reconciliation"],
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"Workspace: {workspace}")
        print(
            f"Controls: {stats['controls_total']} ({stats['controls_executed']} executed, {stats['controls_tested']} linked) | "
            f"Relationships: {stats['relationships_total']} ({stats['relationships_executed']} executed, {stats['relationships_verified']} linked) | "
            f"Cases: {stats['cases_total']} | Defects: {len(loaded.get('defects') or [])} | "
            f"Open questions: {stats['open_questions_count']}"
        )
        rec = stats["reconciliation"]
        print(
            f"Reconciliation ({rec['atlas_coverage_mode']}): {'OK' if rec['ok'] else 'CHECK'} | "
            f"unexplained controls {rec['controls_unexplained']} | "
            f"unexplained relationships {rec['relationships_unexplained']} | "
            f"passes without evidence {rec['passes_without_evidence']} | "
            f"fails without defect {rec['fails_without_defect']} | "
            f"fails without triage {rec['fails_without_triage']} | "
            f"orphan defects {rec['defects_without_cases']} | "
            f"in-scope modules without cases {rec['in_scope_modules_without_cases']}"
        )
        print(f"Errors: {len(errors)} | Warnings: {len(warnings)}")
        if errors:
            print("\nERRORS")
            for issue in errors:
                ref = f" [{issue['ref']}]" if issue.get("ref") else ""
                print(f"- {issue['code']}{ref}: {issue['message']}")
        if warnings:
            print("\nWARNINGS")
            for issue in warnings:
                ref = f" [{issue['ref']}]" if issue.get("ref") else ""
                print(f"- {issue['code']}{ref}: {issue['message']}")
        if not errors and not warnings:
            print("\nNo issues found.")

    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
