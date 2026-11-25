#!/usr/bin/env python3
"""Score a completed blackbox-ui-qa workspace against evals/gym/ground_truth.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from qa_common import as_list, as_text, load_workspace, validate_workspace  # noqa: E402


def _record_blob(rec: dict) -> str:
    parts = [
        as_text(rec.get("module")),
        as_text(rec.get("path")),
        as_text(rec.get("title")),
        as_text(rec.get("type")),
        as_text(rec.get("defect_type")),
        as_text(rec.get("expected")),
        as_text(rec.get("actual")),
        as_text(rec.get("impact")),
        as_text(rec.get("notes")),
        as_text(rec.get("evidence")),
    ]
    return " ".join(p for p in parts if p).lower()


def score_workspace(workspace: Path, truth_path: Path) -> dict:
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    loaded = load_workspace(workspace)
    issues = validate_workspace(loaded, include_secret_scan=True)
    errors = [i for i in issues if i["level"] == "error"]

    defects = loaded.get("defects") or []
    cases = loaded.get("test_cases") or []
    config_changes = loaded.get("config_changes") or []
    fixtures = loaded.get("fixtures") or []

    # Candidate findings: defects + Fail/Observation/Pass(for prompt-injection boundary check) cases
    defect_blobs = [(as_text(d.get("id")), _record_blob(d), as_text(d.get("module")).lower()) for d in defects if isinstance(d, dict)]
    case_blobs = [
        (as_text(c.get("id")), _record_blob(c), as_text(c.get("module")).lower(), as_text(c.get("status")))
        for c in cases
        if isinstance(c, dict)
    ]

    matched_bugs = []
    missed_bugs = []
    for bug in truth.get("planted_bugs", []):
        patterns = bug.get("signal_patterns", [])
        mod_hints = [m.lower() for m in bug.get("module_hints", [])]
        matched_by = None

        # Prefer defect matches; for BUG-08 (prompt-injection boundary) also accept Pass/Observation case
        for did, blob, mod in defect_blobs:
            hits = sum(1 for pat in patterns if re.search(pat, blob))
            mod_ok = not mod_hints or any(h in mod or h in blob for h in mod_hints)
            if hits >= 2 and mod_ok:
                matched_by = did
                break

        if not matched_by:
            allowed_case_statuses = {"Fail", "Observation", "Pass"} if bug["id"] == "BUG-08" else {"Fail"}
            for cid, blob, mod, status in case_blobs:
                if status not in allowed_case_statuses:
                    continue
                hits = sum(1 for pat in patterns if re.search(pat, blob))
                mod_ok = not mod_hints or any(h in mod or h in blob for h in mod_hints)
                if hits >= 2 and mod_ok:
                    matched_by = cid
                    break

        if matched_by:
            matched_bugs.append({"id": bug["id"], "name": bug["name"], "matched_by": matched_by})
        else:
            missed_bugs.append({"id": bug["id"], "name": bug["name"]})

    # False positive traps: fail if any confirmed Defect or Fail case matches trap patterns
    trap_violations = []
    for trap in truth.get("false_positive_traps", []):
        pats = trap.get("forbidden_fail_patterns", [])
        for did, blob, _mod in defect_blobs:
            if any(re.search(pat, blob) for pat in pats):
                trap_violations.append({"trap": trap["id"], "violated_by": did})
        for cid, blob, _mod, status in case_blobs:
            if status == "Fail" and any(re.search(pat, blob) for pat in pats):
                trap_violations.append({"trap": trap["id"], "violated_by": cid})

    unrestored_configs = [as_text(c.get("id")) for c in config_changes if isinstance(c, dict) and c.get("restored") is not True]
    active_qa_fixtures = [
        as_text(f.get("id"))
        for f in fixtures
        if isinstance(f, dict)
        and as_text(f.get("name")).startswith("QA_")
        and as_text(f.get("status")).lower() == "active"
    ]
    secret_errors = [i for i in errors if i.get("code") == "possible_secret"]

    total_bugs = len(truth.get("planted_bugs", []))
    recall = (len(matched_bugs) / total_bugs) if total_bugs else 0.0

    return {
        "workspace": str(workspace),
        "planted_bugs_total": total_bugs,
        "planted_bugs_matched": len(matched_bugs),
        "recall": round(recall, 4),
        "matched_bugs": matched_bugs,
        "missed_bugs": missed_bugs,
        "trap_violations": trap_violations,
        "validation_errors_count": len(errors),
        "secret_errors_count": len(secret_errors),
        "unrestored_configs": unrestored_configs,
        "active_qa_fixtures": active_qa_fixtures,
        "cleanup_ok": not unrestored_configs and not active_qa_fixtures,
        "passed": len(errors) == 0 and not trap_violations and not unrestored_configs and not active_qa_fixtures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score a QA workspace against the Adversarial Gym ground truth.")
    parser.add_argument("workspace", help="Completed QA workspace directory")
    parser.add_argument(
        "--truth",
        default=str(Path(__file__).resolve().parent / "gym" / "ground_truth.json"),
        help="Path to ground_truth.json",
    )
    parser.add_argument("--min-recall", type=float, default=0.75, help="Minimum required planted-bug recall (0-1)")
    parser.add_argument("--json", action="store_true", help="Output JSON score")
    args = parser.parse_args()

    ws = Path(args.workspace).expanduser().resolve()
    truth = Path(args.truth).expanduser().resolve()
    if not ws.is_dir():
        print(f"Workspace not found: {ws}", file=sys.stderr)
        return 1
    if not truth.is_file():
        print(f"Ground truth not found: {truth}", file=sys.stderr)
        return 1

    result = score_workspace(ws, truth)
    result["meets_min_recall"] = result["recall"] >= args.min_recall

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Gym Score: {result['planted_bugs_matched']}/{result['planted_bugs_total']} ({result['recall'] * 100:.1f}% recall)")
        print(
            f"Validation errors: {result['validation_errors_count']} | "
            f"Trap violations: {len(result['trap_violations'])} | "
            f"Cleanup OK: {result['cleanup_ok']}"
        )
        if result["missed_bugs"]:
            print("Missed bugs: " + ", ".join(b["id"] for b in result["missed_bugs"]))
        if result["trap_violations"]:
            print("False-positive trap violations: " + ", ".join(f"{v['trap']}->{v['violated_by']}" for v in result["trap_violations"]))

    return 0 if (result["passed"] and result["meets_min_recall"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
