#!/usr/bin/env python3
"""Compare two blackbox-ui-qa v2.0 workspaces to surface regressions and coverage deltas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from qa_common import as_text, coverage, load_workspace


def _index_by_key(records: list[dict], fields: tuple[str, ...]) -> dict[tuple[str, ...], dict]:
    out: dict[tuple[str, ...], dict] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        key = tuple(as_text(rec.get(f)).lower() for f in fields)
        out[key] = rec
    return out


def diff_workspaces(baseline_dir: Path, current_dir: Path) -> dict:
    base = load_workspace(baseline_dir)
    curr = load_workspace(current_dir)
    base_cov = coverage(base)
    curr_cov = coverage(curr)

    base_cases = _index_by_key(base.get("test_cases") or [], ("module", "title"))
    curr_cases = _index_by_key(curr.get("test_cases") or [], ("module", "title"))

    regressions = []
    recoveries = []
    status_changes = []
    new_cases = []
    removed_cases = []

    for key, c_case in curr_cases.items():
        c_status = as_text(c_case.get("status"))
        b_case = base_cases.get(key)
        if b_case is None:
            new_cases.append({"id": c_case.get("id"), "module": c_case.get("module"), "title": c_case.get("title"), "status": c_status})
            continue
        b_status = as_text(b_case.get("status"))
        if b_status != c_status:
            entry = {
                "module": c_case.get("module"),
                "title": c_case.get("title"),
                "baseline_id": b_case.get("id"),
                "current_id": c_case.get("id"),
                "from": b_status,
                "to": c_status,
            }
            status_changes.append(entry)
            if b_status == "Pass" and c_status in ("Fail", "Blocked"):
                regressions.append(entry)
            elif b_status == "Fail" and c_status == "Pass":
                recoveries.append(entry)

    for key, b_case in base_cases.items():
        if key not in curr_cases:
            removed_cases.append({"id": b_case.get("id"), "module": b_case.get("module"), "title": b_case.get("title")})

    base_defects = _index_by_key(base.get("defects") or [], ("module", "title"))
    curr_defects = _index_by_key(curr.get("defects") or [], ("module", "title"))

    new_defects = [
        {"id": d.get("id"), "severity": d.get("severity"), "module": d.get("module"), "title": d.get("title")}
        for k, d in curr_defects.items()
        if k not in base_defects
    ]
    resolved_defects = [
        {"id": d.get("id"), "severity": d.get("severity"), "module": d.get("module"), "title": d.get("title")}
        for k, d in base_defects.items()
        if k not in curr_defects or as_text(curr_defects[k].get("status")) in ("Fixed", "Not a Bug", "Won't Fix")
    ]

    return {
        "baseline": str(baseline_dir),
        "current": str(current_dir),
        "deltas": {
            "pass_rate_delta": round(curr_cov["pass_rate"] - base_cov["pass_rate"], 2),
            "controls_executed_pct_delta": round(curr_cov["controls_coverage_pct"] - base_cov["controls_coverage_pct"], 2),
            "relationships_executed_pct_delta": round(
                curr_cov["relationships_coverage_pct"] - base_cov["relationships_coverage_pct"], 2
            ),
            "cases_delta": curr_cov["cases_total"] - base_cov["cases_total"],
            "defects_delta": len(curr.get("defects") or []) - len(base.get("defects") or []),
        },
        "regressions": regressions,
        "recoveries": recoveries,
        "status_changes": status_changes,
        "new_cases": new_cases,
        "removed_cases": removed_cases,
        "new_defects": new_defects,
        "resolved_defects": resolved_defects,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff two blackbox-ui-qa v2.0 workspaces.")
    parser.add_argument("baseline", help="Baseline workspace directory")
    parser.add_argument("current", help="Current workspace directory")
    parser.add_argument("--json", action="store_true", help="Output JSON diff")
    args = parser.parse_args()

    baseline = Path(args.baseline).expanduser().resolve()
    current = Path(args.current).expanduser().resolve()
    for p in (baseline, current):
        if not p.is_dir():
            print(f"Workspace not found: {p}", file=sys.stderr)
            return 1

    result = diff_workspaces(baseline, current)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    d = result["deltas"]
    print(f"Baseline: {baseline}")
    print(f"Current:  {current}")
    print(
        f"Deltas: pass rate {d['pass_rate_delta']:+.1f}% | "
        f"executed control cov {d['controls_executed_pct_delta']:+.1f}% | "
        f"cases {d['cases_delta']:+d} | defects {d['defects_delta']:+d}"
    )
    print(
        f"Regressions: {len(result['regressions'])} | Recoveries: {len(result['recoveries'])} | "
        f"New defects: {len(result['new_defects'])} | Resolved defects: {len(result['resolved_defects'])}"
    )
    for item in result["regressions"]:
        print(f"  [REGRESSION] {item['module']} - {item['title']} ({item['from']} -> {item['to']})")
    for item in result["new_defects"]:
        print(f"  [NEW DEFECT] {item['id']} ({item['severity']}) {item['module']} - {item['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
