#!/usr/bin/env python3
"""Atomic incremental JSON recorder for blackbox-ui-qa v2.0 workspaces.

Supports both single-record CLI flags and batch JSON input (--stdin or --file)
to eliminate PowerShell escaping traps and reduce hand-editing of large JSON files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from qa_common import (
    CATEGORIES,
    CONFIDENCES,
    CONTROLS,
    DEFECT_STATUSES,
    DEFECT_TYPES,
    FIXTURE_DESIGNS,
    ORACLE_FAMILIES,
    PRIORITIES,
    QUESTION_STATUSES,
    QUESTION_TYPES,
    REL_TYPES,
    SEVERITIES,
    STATUSES,
    TRIAGE_DISPOSITIONS,
    as_list,
    as_text,
    now_iso,
    read_json,
    write_json_atomic,
)

PREFIX_MAP = {
    "control": ("02-field-atlas.json", "controls", "A"),
    "relationship": ("03-relationships.json", "relationships", "R"),
    "case": ("05-test-cases.json", "test_cases", "TC"),
    "defect": ("06-defects.json", "defects", "DEF"),
    "fixture": ("07-fixtures-and-config-ledger.json", "fixtures", "F"),
    "config_change": ("07-fixtures-and-config-ledger.json", "config_changes", "C"),
    "config_matrix": ("07-fixtures-and-config-ledger.json", "configuration_matrix", "CFG"),
    "question": ("08-open-questions.json", "items", "Q"),
}


def _load_doc(path: Path, default_data: dict) -> dict:
    if not path.exists():
        return dict(default_data)
    data, err = read_json(path)
    if err:
        raise SystemExit(f"ERROR: {err}")
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: {path.name} must contain a JSON object.")
    for key, val in default_data.items():
        data.setdefault(key, list(val) if isinstance(val, list) else val)
    return data


def _next_id(records: list[dict], prefix: str) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    max_num = 0
    for rec in records:
        if not isinstance(rec, dict):
            continue
        match = pattern.match(as_text(rec.get("id")))
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"{prefix}-{max_num + 1:04d}"


def _read_batch_payload(args: argparse.Namespace) -> list[dict] | None:
    raw = None
    if getattr(args, "stdin", False):
        raw = sys.stdin.read()
    elif getattr(args, "file", ""):
        raw = Path(args.file).expanduser().read_text(encoding="utf-8")
    if raw is None:
        return None
    if not raw.strip():
        raise SystemExit("ERROR: Empty JSON input.")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: Invalid JSON payload: {exc}")
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
        return parsed
    raise SystemExit("ERROR: JSON input must be an object or a list of objects.")


def _validate_enum(value: str, allowed: list[str], name: str) -> None:
    if value and value not in allowed:
        raise SystemExit(f"ERROR: Invalid {name} '{value}'. Allowed: {', '.join(allowed)}")


def _append_unique(items: list, value: str) -> list:
    cleaned = [as_text(x) for x in as_list(items) if as_text(x)]
    if value and value not in cleaned:
        cleaned.append(value)
    return cleaned


def _sync_case_links(workspace: Path, case: dict) -> None:
    case_id = as_text(case.get("id"))
    atlas_ids = {as_text(x) for x in as_list(case.get("atlas_ids")) if as_text(x)}
    rel_ids = {as_text(x) for x in as_list(case.get("relationship_ids")) if as_text(x)}

    if atlas_ids:
        atlas_path = workspace / "02-field-atlas.json"
        atlas_doc = _load_doc(atlas_path, {"controls": []})
        changed = False
        for ctrl in atlas_doc["controls"]:
            if isinstance(ctrl, dict) and as_text(ctrl.get("id")) in atlas_ids:
                updated = _append_unique(ctrl.get("tested_by"), case_id)
                if updated != ctrl.get("tested_by"):
                    ctrl["tested_by"] = updated
                    changed = True
        if changed:
            write_json_atomic(atlas_path, atlas_doc)

    if rel_ids:
        rel_path = workspace / "03-relationships.json"
        rel_doc = _load_doc(rel_path, {"relationships": []})
        changed = False
        for rel in rel_doc["relationships"]:
            if isinstance(rel, dict) and as_text(rel.get("id")) in rel_ids:
                updated = _append_unique(rel.get("verified_by"), case_id)
                if updated != rel.get("verified_by"):
                    rel["verified_by"] = updated
                    changed = True
        if changed:
            write_json_atomic(rel_path, rel_doc)


def cmd_add_controls(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "02-field-atlas.json"
    doc = _load_doc(path, {"controls": []})
    items = _read_batch_payload(args)
    if items is None:
        items = [
            {
                "id": args.id or "",
                "state_id": args.state_id,
                "module": args.module,
                "path": args.path,
                "label": args.label,
                "control": args.control,
                "required": args.required,
                "default": args.default,
                "options": args.option or [],
                "constraints": args.constraints,
                "helper_text": args.helper_text,
                "depends_on": args.depends_on,
                "affects": args.affects,
                "roles_visible": args.role or [],
                "tested_by": args.tested_by or [],
                "not_tested_reason": args.not_tested_reason,
                "notes": args.notes,
            }
        ]

    added_ids = []
    existing_ids = {as_text(r.get("id")) for r in doc["controls"] if isinstance(r, dict)}
    for item in items:
        for req in ("module", "path", "label", "control"):
            if not as_text(item.get(req)):
                raise SystemExit(f"ERROR: Control is missing required '{req}'.")
        _validate_enum(as_text(item.get("control")), CONTROLS, "control")
        cid = as_text(item.get("id")) or _next_id(doc["controls"], "A")
        if cid in existing_ids:
            raise SystemExit(f"ERROR: Duplicate control id '{cid}'.")
        item["id"] = cid
        existing_ids.add(cid)
        doc["controls"].append(item)
        added_ids.append(cid)
    write_json_atomic(path, doc)
    return added_ids


def cmd_add_relationships(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "03-relationships.json"
    doc = _load_doc(path, {"relationships": []})
    items = _read_batch_payload(args)
    if items is None:
        items = [
            {
                "id": args.id or "",
                "source": args.source,
                "target": args.target,
                "type": args.type,
                "description": args.description,
                "evidence": args.evidence,
                "confidence": args.confidence,
                "verified_by": args.verified_by or [],
                "not_tested_reason": args.not_tested_reason,
            }
        ]

    added_ids = []
    existing_ids = {as_text(r.get("id")) for r in doc["relationships"] if isinstance(r, dict)}
    for item in items:
        for req in ("source", "target", "type", "description"):
            if not as_text(item.get(req)):
                raise SystemExit(f"ERROR: Relationship is missing required '{req}'.")
        _validate_enum(as_text(item.get("type")), REL_TYPES, "relationship type")
        _validate_enum(as_text(item.get("confidence")), CONFIDENCES, "confidence")
        rid = as_text(item.get("id")) or _next_id(doc["relationships"], "R")
        if rid in existing_ids:
            raise SystemExit(f"ERROR: Duplicate relationship id '{rid}'.")
        item["id"] = rid
        existing_ids.add(rid)
        doc["relationships"].append(item)
        added_ids.append(rid)
    write_json_atomic(path, doc)
    return added_ids


def _validate_case_fields(item: dict) -> None:
    for req in ("module", "path", "title", "status", "expected"):
        if not as_text(item.get(req)):
            raise SystemExit(f"ERROR: Test case is missing required '{req}'.")
    _validate_enum(as_text(item.get("status")), STATUSES, "status")
    _validate_enum(as_text(item.get("category")), CATEGORIES, "category")
    _validate_enum(as_text(item.get("priority")), PRIORITIES, "priority")
    _validate_enum(as_text(item.get("severity")), SEVERITIES, "severity")
    _validate_enum(as_text(item.get("defect_type")), DEFECT_TYPES, "defect_type")
    oracle = item.get("oracle")
    if isinstance(oracle, dict):
        for fam in as_list(oracle.get("families")):
            _validate_enum(as_text(fam), ORACLE_FAMILIES, "oracle family")
    triage = item.get("triage")
    if isinstance(triage, dict) and triage.get("disposition"):
        _validate_enum(as_text(triage.get("disposition")), TRIAGE_DISPOSITIONS, "triage disposition")


def cmd_add_cases(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "05-test-cases.json"
    doc = _load_doc(path, {"test_cases": []})
    items = _read_batch_payload(args)
    if items is None:
        oracle = None
        if args.oracle_type or args.oracle_source or args.oracle_description:
            oracle = {
                "type": args.oracle_type,
                "source": args.oracle_source,
                "confidence": args.oracle_confidence,
                "families": args.oracle_family or [],
                "description": args.oracle_description,
            }
        triage = None
        if args.triage_disposition or args.triage_reason:
            triage = {
                "disposition": args.triage_disposition,
                "reason": args.triage_reason,
                "evidence": args.triage_evidence or [],
            }
        item: dict[str, Any] = {
            "id": args.id or "",
            "module": args.module,
            "path": args.path,
            "title": args.title,
            "category": args.category,
            "technique": args.technique,
            "priority": args.priority,
            "reason": args.reason,
            "role": args.role,
            "preconditions": args.preconditions,
            "test_data": args.test_data,
            "steps": args.step or [],
            "expected": args.expected,
            "actual": args.actual,
            "status": args.status,
            "severity": args.severity,
            "defect_type": args.defect_type,
            "correlated_modules": args.correlated_module or [],
            "relationship_ids": args.relationship_id or [],
            "atlas_ids": args.atlas_id or [],
            "surfaces_checked": args.surface or [],
            "evidence": args.evidence or [],
            "suggestion": args.suggestion,
            "notes": args.notes,
            "executed_at": args.executed_at or (now_iso() if args.status in ("Pass", "Fail") else ""),
        }
        if oracle:
            item["oracle"] = oracle
        if triage:
            item["triage"] = triage
        items = [item]

    added_ids = []
    existing_ids = {as_text(r.get("id")) for r in doc["test_cases"] if isinstance(r, dict)}
    for item in items:
        _validate_case_fields(item)
        tcid = as_text(item.get("id")) or _next_id(doc["test_cases"], "TC")
        if tcid in existing_ids:
            raise SystemExit(f"ERROR: Duplicate test case id '{tcid}'.")
        item["id"] = tcid
        existing_ids.add(tcid)
        doc["test_cases"].append(item)
        added_ids.append(tcid)
    write_json_atomic(path, doc)
    for item in items:
        _sync_case_links(workspace, item)
    return added_ids


def cmd_update_case(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "05-test-cases.json"
    doc = _load_doc(path, {"test_cases": []})
    target = next((c for c in doc["test_cases"] if isinstance(c, dict) and as_text(c.get("id")) == args.id), None)
    if target is None:
        raise SystemExit(f"ERROR: Test case '{args.id}' not found.")

    patch = _read_batch_payload(args)
    if patch is not None:
        if len(patch) != 1:
            raise SystemExit("ERROR: update-case expects a single JSON object.")
        target.update(patch[0])
        target["id"] = args.id
    else:
        if args.status:
            target["status"] = args.status
        if args.actual is not None:
            target["actual"] = args.actual
        if args.severity:
            target["severity"] = args.severity
        if args.defect_type:
            target["defect_type"] = args.defect_type
        if args.evidence:
            target["evidence"] = list(args.evidence)
        if args.surface:
            target["surfaces_checked"] = list(args.surface)
        if args.suggestion is not None:
            target["suggestion"] = args.suggestion
        if args.notes is not None:
            target["notes"] = args.notes
        if args.executed_at is not None:
            target["executed_at"] = args.executed_at
        elif args.status in ("Pass", "Fail") and not target.get("executed_at"):
            target["executed_at"] = now_iso()
        if args.triage_disposition or args.triage_reason:
            triage = target.get("triage") if isinstance(target.get("triage"), dict) else {}
            if args.triage_disposition:
                triage["disposition"] = args.triage_disposition
            if args.triage_reason:
                triage["reason"] = args.triage_reason
            if args.triage_evidence:
                triage["evidence"] = list(args.triage_evidence)
            target["triage"] = triage

    _validate_case_fields(target)
    write_json_atomic(path, doc)
    _sync_case_links(workspace, target)
    return [args.id]


def cmd_add_defects(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "06-defects.json"
    doc = _load_doc(path, {"defects": []})
    items = _read_batch_payload(args)
    if items is None:
        if args.from_case:
            cases_doc = _load_doc(workspace / "05-test-cases.json", {"test_cases": []})
            src = next(
                (c for c in cases_doc["test_cases"] if isinstance(c, dict) and as_text(c.get("id")) == args.from_case),
                None,
            )
            if src is None:
                raise SystemExit(f"ERROR: Source test case '{args.from_case}' not found.")
            items = [
                {
                    "id": args.id or "",
                    "title": args.title or src.get("title", ""),
                    "severity": args.severity or src.get("severity", ""),
                    "type": args.type or src.get("defect_type", ""),
                    "module": args.module or src.get("module", ""),
                    "path": args.path or src.get("path", ""),
                    "test_case_ids": args.test_case_id or [args.from_case],
                    "environment": args.environment,
                    "preconditions": args.preconditions or src.get("preconditions", ""),
                    "steps": args.step or src.get("steps", []),
                    "expected": args.expected or src.get("expected", ""),
                    "actual": args.actual or src.get("actual", ""),
                    "evidence": args.evidence or src.get("evidence", []),
                    "impact": args.impact,
                    "likely_cause": args.likely_cause,
                    "suggestion": args.suggestion or src.get("suggestion", ""),
                    "workaround": args.workaround,
                    "status": args.status or "Open",
                    "notes": args.notes or src.get("notes", ""),
                    "created_at": now_iso(),
                }
            ]
        else:
            items = [
                {
                    "id": args.id or "",
                    "title": args.title,
                    "severity": args.severity,
                    "type": args.type,
                    "module": args.module,
                    "path": args.path,
                    "test_case_ids": args.test_case_id or [],
                    "environment": args.environment,
                    "preconditions": args.preconditions,
                    "steps": args.step or [],
                    "expected": args.expected,
                    "actual": args.actual,
                    "evidence": args.evidence or [],
                    "impact": args.impact,
                    "likely_cause": args.likely_cause,
                    "suggestion": args.suggestion,
                    "workaround": args.workaround,
                    "status": args.status or "Open",
                    "notes": args.notes,
                    "created_at": now_iso(),
                }
            ]

    added_ids = []
    existing_ids = {as_text(r.get("id")) for r in doc["defects"] if isinstance(r, dict)}
    for item in items:
        for req in ("title", "severity", "type", "module", "expected", "actual", "suggestion"):
            if not as_text(item.get(req)):
                raise SystemExit(f"ERROR: Defect is missing required '{req}'.")
        if not as_list(item.get("steps")):
            raise SystemExit("ERROR: Defect is missing required 'steps'.")
        if not as_list(item.get("evidence")):
            raise SystemExit("ERROR: Defect is missing required 'evidence'.")
        if not as_list(item.get("test_case_ids")):
            raise SystemExit("ERROR: Defect is missing required 'test_case_ids'.")
        _validate_enum(as_text(item.get("severity")), SEVERITIES, "severity")
        _validate_enum(as_text(item.get("type")), DEFECT_TYPES, "defect type")
        _validate_enum(as_text(item.get("status") or "Open"), DEFECT_STATUSES, "defect status")
        did = as_text(item.get("id")) or _next_id(doc["defects"], "DEF")
        if did in existing_ids:
            raise SystemExit(f"ERROR: Duplicate defect id '{did}'.")
        item["id"] = did
        item.setdefault("status", "Open")
        item.setdefault("created_at", now_iso())
        existing_ids.add(did)
        doc["defects"].append(item)
        added_ids.append(did)
    write_json_atomic(path, doc)
    return added_ids


def cmd_add_fixtures(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "07-fixtures-and-config-ledger.json"
    doc = _load_doc(path, {"fixtures": [], "config_changes": [], "configuration_matrix": []})
    items = _read_batch_payload(args)
    if items is None:
        items = [
            {
                "id": args.id or "",
                "name": args.name,
                "purpose": args.purpose,
                "design": args.design,
                "created_via": args.created_via,
                "status": args.status or "active",
                "cleanup": args.cleanup,
                "notes": args.notes,
            }
        ]
    added_ids = []
    existing_ids = {as_text(r.get("id")) for r in doc["fixtures"] if isinstance(r, dict)}
    for item in items:
        for req in ("name", "purpose"):
            if not as_text(item.get(req)):
                raise SystemExit(f"ERROR: Fixture is missing required '{req}'.")
        if item.get("design"):
            _validate_enum(as_text(item.get("design")), FIXTURE_DESIGNS, "fixture design")
        fid = as_text(item.get("id")) or _next_id(doc["fixtures"], "F")
        if fid in existing_ids:
            raise SystemExit(f"ERROR: Duplicate fixture id '{fid}'.")
        item["id"] = fid
        existing_ids.add(fid)
        doc["fixtures"].append(item)
        added_ids.append(fid)
    write_json_atomic(path, doc)
    return added_ids


def cmd_log_config(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "07-fixtures-and-config-ledger.json"
    doc = _load_doc(path, {"fixtures": [], "config_changes": [], "configuration_matrix": []})
    items = _read_batch_payload(args)
    if items is None:
        items = [
            {
                "id": args.id or "",
                "path": args.path,
                "setting": args.setting,
                "original": args.original,
                "changed_to": args.changed_to,
                "changed_at": args.changed_at or now_iso(),
                "role": args.role,
                "reason": args.reason,
                "restored": False,
                "restored_at": "",
                "restored_value": "",
                "evidence": args.evidence,
                "notes": args.notes,
            }
        ]
    added_ids = []
    existing_ids = {as_text(r.get("id")) for r in doc["config_changes"] if isinstance(r, dict)}
    for item in items:
        for req in ("path", "original", "changed_to"):
            if not as_text(item.get(req)):
                raise SystemExit(f"ERROR: Config change is missing required '{req}'.")
        cid = as_text(item.get("id")) or _next_id(doc["config_changes"], "C")
        if cid in existing_ids:
            raise SystemExit(f"ERROR: Duplicate config change id '{cid}'.")
        item["id"] = cid
        item.setdefault("restored", False)
        item.setdefault("changed_at", now_iso())
        existing_ids.add(cid)
        doc["config_changes"].append(item)
        added_ids.append(cid)
    write_json_atomic(path, doc)
    return added_ids


def cmd_restore_config(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "07-fixtures-and-config-ledger.json"
    doc = _load_doc(path, {"fixtures": [], "config_changes": [], "configuration_matrix": []})
    target = next((c for c in doc["config_changes"] if isinstance(c, dict) and as_text(c.get("id")) == args.id), None)
    if target is None:
        raise SystemExit(f"ERROR: Config change '{args.id}' not found.")
    target["restored"] = True
    target["restored_at"] = args.restored_at or now_iso()
    target["restored_value"] = args.restored_value or target.get("original", "")
    if args.evidence:
        target["evidence"] = args.evidence
    if args.notes:
        target["notes"] = args.notes
    write_json_atomic(path, doc)
    return [args.id]


def cmd_add_config_matrix(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "07-fixtures-and-config-ledger.json"
    doc = _load_doc(path, {"fixtures": [], "config_changes": [], "configuration_matrix": []})
    items = _read_batch_payload(args)
    if items is None:
        items = [
            {
                "id": args.id or "",
                "area": args.area,
                "setting": args.setting,
                "options": args.option or [],
                "branch": args.branch,
                "profile_value": args.profile_value,
                "tested_by": args.tested_by or [],
                "not_tested_reason": args.not_tested_reason,
            }
        ]
    added_ids = []
    existing_ids = {as_text(r.get("id")) for r in doc["configuration_matrix"] if isinstance(r, dict)}
    for item in items:
        for req in ("area", "setting", "branch", "profile_value"):
            if not as_text(item.get(req)):
                raise SystemExit(f"ERROR: Configuration matrix entry is missing required '{req}'.")
        opts = [as_text(o) for o in as_list(item.get("options")) if as_text(o)]
        if not opts:
            raise SystemExit("ERROR: Configuration matrix entry must provide non-empty 'options'.")
        if as_text(item.get("profile_value")) not in opts:
            raise SystemExit(
                f"ERROR: profile_value '{item.get('profile_value')}' is not in options {opts}."
            )
        mid = as_text(item.get("id")) or _next_id(doc["configuration_matrix"], "CFG")
        if mid in existing_ids:
            raise SystemExit(f"ERROR: Duplicate configuration matrix id '{mid}'.")
        item["id"] = mid
        existing_ids.add(mid)
        doc["configuration_matrix"].append(item)
        added_ids.append(mid)
    write_json_atomic(path, doc)
    return added_ids


def cmd_add_questions(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "08-open-questions.json"
    doc = _load_doc(path, {"items": []})
    items = _read_batch_payload(args)
    if items is None:
        items = [
            {
                "id": args.id or "",
                "type": args.type,
                "description": args.description,
                "impact": args.impact,
                "owner": args.owner,
                "status": args.status or "Open",
                "related": args.related or [],
            }
        ]
    added_ids = []
    existing_ids = {as_text(r.get("id")) for r in doc["items"] if isinstance(r, dict)}
    for item in items:
        for req in ("type", "description"):
            if not as_text(item.get(req)):
                raise SystemExit(f"ERROR: Question is missing required '{req}'.")
        _validate_enum(as_text(item.get("type")), QUESTION_TYPES, "question type")
        _validate_enum(as_text(item.get("status") or "Open"), QUESTION_STATUSES, "question status")
        qid = as_text(item.get("id")) or _next_id(doc["items"], "Q")
        if qid in existing_ids:
            raise SystemExit(f"ERROR: Duplicate question id '{qid}'.")
        item["id"] = qid
        item.setdefault("status", "Open")
        existing_ids.add(qid)
        doc["items"].append(item)
        added_ids.append(qid)
    write_json_atomic(path, doc)
    return added_ids


def _add_batch_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--stdin", action="store_true", help="Read a JSON object or array from stdin")
    p.add_argument("--file", default="", help="Read a JSON object or array from a file")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Atomically record items in a blackbox-ui-qa v2.0 workspace.")
    parser.add_argument("workspace", help="Workspace directory")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ctrl = sub.add_parser("add-control", help="Add one or more controls to 02-field-atlas.json")
    _add_batch_flags(p_ctrl)
    p_ctrl.add_argument("--id", default="")
    p_ctrl.add_argument("--state-id", default="")
    p_ctrl.add_argument("--module", default="")
    p_ctrl.add_argument("--path", default="")
    p_ctrl.add_argument("--label", default="")
    p_ctrl.add_argument("--control", default="")
    p_ctrl.add_argument("--required", default="")
    p_ctrl.add_argument("--default", default="")
    p_ctrl.add_argument("--option", action="append")
    p_ctrl.add_argument("--constraints", default="")
    p_ctrl.add_argument("--helper-text", default="")
    p_ctrl.add_argument("--depends-on", default="")
    p_ctrl.add_argument("--affects", default="")
    p_ctrl.add_argument("--role", action="append")
    p_ctrl.add_argument("--tested-by", action="append")
    p_ctrl.add_argument("--not-tested-reason", default="")
    p_ctrl.add_argument("--notes", default="")

    p_rel = sub.add_parser("add-relationship", help="Add one or more relationships to 03-relationships.json")
    _add_batch_flags(p_rel)
    p_rel.add_argument("--id", default="")
    p_rel.add_argument("--source", default="")
    p_rel.add_argument("--target", default="")
    p_rel.add_argument("--type", default="")
    p_rel.add_argument("--description", default="")
    p_rel.add_argument("--evidence", default="")
    p_rel.add_argument("--confidence", default="Medium")
    p_rel.add_argument("--verified-by", action="append")
    p_rel.add_argument("--not-tested-reason", default="")

    p_case = sub.add_parser("add-case", help="Add one or more test cases to 05-test-cases.json")
    _add_batch_flags(p_case)
    p_case.add_argument("--id", default="")
    p_case.add_argument("--module", default="")
    p_case.add_argument("--path", default="")
    p_case.add_argument("--title", default="")
    p_case.add_argument("--category", default="")
    p_case.add_argument("--technique", default="")
    p_case.add_argument("--priority", default="P1")
    p_case.add_argument("--reason", default="")
    p_case.add_argument("--role", default="")
    p_case.add_argument("--preconditions", default="")
    p_case.add_argument("--test-data", default="")
    p_case.add_argument("--step", action="append")
    p_case.add_argument("--oracle-type", default="")
    p_case.add_argument("--oracle-source", default="")
    p_case.add_argument("--oracle-confidence", default="High")
    p_case.add_argument("--oracle-family", action="append")
    p_case.add_argument("--oracle-description", default="")
    p_case.add_argument("--expected", default="")
    p_case.add_argument("--actual", default="")
    p_case.add_argument("--status", default="Not Run")
    p_case.add_argument("--severity", default="None")
    p_case.add_argument("--defect-type", default="")
    p_case.add_argument("--correlated-module", action="append")
    p_case.add_argument("--relationship-id", action="append")
    p_case.add_argument("--atlas-id", action="append")
    p_case.add_argument("--surface", action="append")
    p_case.add_argument("--evidence", action="append")
    p_case.add_argument("--suggestion", default="")
    p_case.add_argument("--notes", default="")
    p_case.add_argument("--triage-disposition", default="")
    p_case.add_argument("--triage-reason", default="")
    p_case.add_argument("--triage-evidence", action="append")
    p_case.add_argument("--executed-at", default="")

    p_ucase = sub.add_parser("update-case", help="Update execution result of an existing test case")
    _add_batch_flags(p_ucase)
    p_ucase.add_argument("--id", required=True)
    p_ucase.add_argument("--status", default="")
    p_ucase.add_argument("--actual", default=None)
    p_ucase.add_argument("--severity", default="")
    p_ucase.add_argument("--defect-type", default="")
    p_ucase.add_argument("--evidence", action="append")
    p_ucase.add_argument("--surface", action="append")
    p_ucase.add_argument("--suggestion", default=None)
    p_ucase.add_argument("--notes", default=None)
    p_ucase.add_argument("--triage-disposition", default="")
    p_ucase.add_argument("--triage-reason", default="")
    p_ucase.add_argument("--triage-evidence", action="append")
    p_ucase.add_argument("--executed-at", default=None)

    p_def = sub.add_parser("add-defect", help="Add a defect (optionally seeded with --from-case)")
    _add_batch_flags(p_def)
    p_def.add_argument("--id", default="")
    p_def.add_argument("--from-case", default="", help="Seed fields from an existing test case ID")
    p_def.add_argument("--title", default="")
    p_def.add_argument("--severity", default="")
    p_def.add_argument("--type", default="")
    p_def.add_argument("--module", default="")
    p_def.add_argument("--path", default="")
    p_def.add_argument("--test-case-id", action="append")
    p_def.add_argument("--environment", default="")
    p_def.add_argument("--preconditions", default="")
    p_def.add_argument("--step", action="append")
    p_def.add_argument("--expected", default="")
    p_def.add_argument("--actual", default="")
    p_def.add_argument("--evidence", action="append")
    p_def.add_argument("--impact", default="")
    p_def.add_argument("--likely-cause", default="")
    p_def.add_argument("--suggestion", default="")
    p_def.add_argument("--workaround", default="")
    p_def.add_argument("--status", default="Open")
    p_def.add_argument("--notes", default="")

    p_fix = sub.add_parser("add-fixture", help="Add one or more fixtures to 07-fixtures-and-config-ledger.json")
    _add_batch_flags(p_fix)
    p_fix.add_argument("--id", default="")
    p_fix.add_argument("--name", default="")
    p_fix.add_argument("--purpose", default="")
    p_fix.add_argument("--design", default="stacked")
    p_fix.add_argument("--created-via", default="")
    p_fix.add_argument("--status", default="active")
    p_fix.add_argument("--cleanup", default="")
    p_fix.add_argument("--notes", default="")

    p_cfg = sub.add_parser("log-config", help="Log a config change before mutating settings")
    _add_batch_flags(p_cfg)
    p_cfg.add_argument("--id", default="")
    p_cfg.add_argument("--path", default="")
    p_cfg.add_argument("--setting", default="")
    p_cfg.add_argument("--original", default="")
    p_cfg.add_argument("--changed-to", default="")
    p_cfg.add_argument("--changed-at", default="")
    p_cfg.add_argument("--role", default="")
    p_cfg.add_argument("--reason", default="")
    p_cfg.add_argument("--evidence", default="")
    p_cfg.add_argument("--notes", default="")

    p_rcfg = sub.add_parser("restore-config", help="Mark a logged config change as restored")
    p_rcfg.add_argument("--id", required=True)
    p_rcfg.add_argument("--restored-value", default="")
    p_rcfg.add_argument("--restored-at", default="")
    p_rcfg.add_argument("--evidence", default="")
    p_rcfg.add_argument("--notes", default="")

    p_mat = sub.add_parser("add-config-matrix", help="Add entries to configuration_matrix")
    _add_batch_flags(p_mat)
    p_mat.add_argument("--id", default="")
    p_mat.add_argument("--area", default="")
    p_mat.add_argument("--setting", default="")
    p_mat.add_argument("--option", action="append")
    p_mat.add_argument("--branch", default="")
    p_mat.add_argument("--profile-value", default="")
    p_mat.add_argument("--tested-by", action="append")
    p_mat.add_argument("--not-tested-reason", default="")

    p_q = sub.add_parser("add-question", help="Add items to 08-open-questions.json")
    _add_batch_flags(p_q)
    p_q.add_argument("--id", default="")
    p_q.add_argument("--type", default="Question")
    p_q.add_argument("--description", default="")
    p_q.add_argument("--impact", default="")
    p_q.add_argument("--owner", default="")
    p_q.add_argument("--status", default="Open")
    p_q.add_argument("--related", action="append")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        print(f"ERROR: Workspace not found: {workspace}", file=sys.stderr)
        return 1

    dispatch = {
        "add-control": cmd_add_controls,
        "add-relationship": cmd_add_relationships,
        "add-case": cmd_add_cases,
        "update-case": cmd_update_case,
        "add-defect": cmd_add_defects,
        "add-fixture": cmd_add_fixtures,
        "log-config": cmd_log_config,
        "restore-config": cmd_restore_config,
        "add-config-matrix": cmd_add_config_matrix,
        "add-question": cmd_add_questions,
    }
    ids = dispatch[args.command](workspace, args)
    print(json.dumps({"ok": True, "command": args.command, "ids": ids}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
