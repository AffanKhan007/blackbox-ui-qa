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
    ATLAS_COVERAGE_MODES,
    CATEGORIES,
    CONFIDENCES,
    CONTROLS,
    DEFECT_STATUSES,
    DEFECT_TYPES,
    DEPTHS,
    EXECUTION_MODES,
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
    merge_meta_patch,
    now_iso,
    read_json,
    write_json_atomic,
)


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
    cfg_ids = {as_text(x) for x in as_list(case.get("config_matrix_ids")) if as_text(x)}

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

    if cfg_ids:
        ledger_path = workspace / "07-fixtures-and-config-ledger.json"
        ledger_doc = _load_doc(ledger_path, {"fixtures": [], "config_changes": [], "configuration_matrix": []})
        changed = False
        for entry in ledger_doc["configuration_matrix"]:
            if isinstance(entry, dict) and as_text(entry.get("id")) in cfg_ids:
                updated = _append_unique(entry.get("tested_by"), case_id)
                if updated != entry.get("tested_by"):
                    entry["tested_by"] = updated
                    changed = True
        if changed:
            write_json_atomic(ledger_path, ledger_doc)


def _prepare_controls(existing: list[dict], items: list[dict]) -> tuple[list[dict], list[str]]:
    added_ids = []
    existing_ids = {as_text(r.get("id")) for r in existing if isinstance(r, dict)}
    out = list(existing)
    for raw in items:
        item = dict(raw)
        for req in ("module", "path", "label", "control"):
            if not as_text(item.get(req)):
                raise SystemExit(f"ERROR: Control is missing required '{req}'.")
        _validate_enum(as_text(item.get("control")), CONTROLS, "control")
        cid = as_text(item.get("id")) or _next_id(out, "A")
        if cid in existing_ids:
            raise SystemExit(f"ERROR: Duplicate control id '{cid}'.")
        item["id"] = cid
        existing_ids.add(cid)
        out.append(item)
        added_ids.append(cid)
    return out, added_ids


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

    doc["controls"], added_ids = _prepare_controls(doc["controls"], items)
    write_json_atomic(path, doc)
    return added_ids


def _prepare_relationships(existing: list[dict], items: list[dict]) -> tuple[list[dict], list[str]]:
    added_ids: list[str] = []
    existing_ids = {as_text(r.get("id")) for r in existing if isinstance(r, dict)}
    out = list(existing)
    for raw in items:
        item = dict(raw)
        for req in ("source", "target", "type", "description"):
            if not as_text(item.get(req)):
                raise SystemExit(f"ERROR: Relationship is missing required '{req}'.")
        _validate_enum(as_text(item.get("type")), REL_TYPES, "relationship type")
        _validate_enum(as_text(item.get("confidence")), CONFIDENCES, "confidence")
        rid = as_text(item.get("id")) or _next_id(out, "R")
        if rid in existing_ids:
            raise SystemExit(f"ERROR: Duplicate relationship id '{rid}'.")
        item["id"] = rid
        existing_ids.add(rid)
        out.append(item)
        added_ids.append(rid)
    return out, added_ids


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

    doc["relationships"], added_ids = _prepare_relationships(doc["relationships"], items)
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


def _prepare_cases(existing: list[dict], items: list[dict]) -> tuple[list[dict], list[str], list[dict]]:
    added_ids: list[str] = []
    added_cases: list[dict] = []
    existing_ids = {as_text(r.get("id")) for r in existing if isinstance(r, dict)}
    out = list(existing)
    for raw in items:
        item = dict(raw)
        _validate_case_fields(item)
        tcid = as_text(item.get("id")) or _next_id(out, "TC")
        if tcid in existing_ids:
            raise SystemExit(f"ERROR: Duplicate test case id '{tcid}'.")
        item["id"] = tcid
        if as_text(item.get("status")) in ("Pass", "Fail") and not as_text(item.get("executed_at")):
            item["executed_at"] = now_iso()
        existing_ids.add(tcid)
        out.append(item)
        added_cases.append(item)
        added_ids.append(tcid)
    return out, added_ids, added_cases


def cmd_add_cases(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "05-test-cases.json"
    doc = _load_doc(path, {"test_cases": []})
    items = _read_batch_payload(args)
    if items is None:
        oracle = None
        if args.oracle_type or args.oracle_source or args.oracle_description or args.oracle_family:
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
            "config_matrix_ids": args.config_matrix_id or [],
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

    doc["test_cases"], added_ids, added_cases = _prepare_cases(doc["test_cases"], items)
    write_json_atomic(path, doc)
    for item in added_cases:
        _sync_case_links(workspace, item)
    return added_ids


def cmd_update_case(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "05-test-cases.json"
    doc = _load_doc(path, {"test_cases": []})
    by_id = {as_text(c.get("id")): c for c in doc["test_cases"] if isinstance(c, dict) and as_text(c.get("id"))}

    patches = _read_batch_payload(args)
    updated_targets: list[dict] = []
    if patches is not None:
        for patch in patches:
            cid = as_text(patch.get("id")) or as_text(args.id)
            if not cid:
                raise SystemExit("ERROR: update-case JSON payload requires 'id' (or --id).")
            target = by_id.get(cid)
            if target is None:
                raise SystemExit(f"ERROR: Test case '{cid}' not found.")
            target.update(patch)
            target["id"] = cid
            _validate_case_fields(target)
            updated_targets.append(target)
    else:
        if not args.id:
            raise SystemExit("ERROR: update-case requires --id when not using --stdin/--file.")
        target = by_id.get(args.id)
        if target is None:
            raise SystemExit(f"ERROR: Test case '{args.id}' not found.")
        if args.status:
            target["status"] = args.status
        if args.expected is not None:
            target["expected"] = args.expected
        if args.actual is not None:
            target["actual"] = args.actual
        if args.severity:
            target["severity"] = args.severity
        if args.defect_type:
            target["defect_type"] = args.defect_type
        if args.step:
            target["steps"] = list(args.step)
        if args.atlas_id:
            target["atlas_ids"] = list(args.atlas_id)
        if args.relationship_id:
            target["relationship_ids"] = list(args.relationship_id)
        if args.config_matrix_id:
            target["config_matrix_ids"] = list(args.config_matrix_id)
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
        if args.oracle_type or args.oracle_source or args.oracle_description or args.oracle_family:
            oracle = target.get("oracle") if isinstance(target.get("oracle"), dict) else {}
            if args.oracle_type:
                oracle["type"] = args.oracle_type
            if args.oracle_source:
                oracle["source"] = args.oracle_source
            if args.oracle_confidence:
                oracle["confidence"] = args.oracle_confidence
            if args.oracle_family:
                oracle["families"] = list(args.oracle_family)
            if args.oracle_description:
                oracle["description"] = args.oracle_description
            target["oracle"] = oracle
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
        updated_targets.append(target)

    write_json_atomic(path, doc)
    for target in updated_targets:
        _sync_case_links(workspace, target)
    return [as_text(t.get("id")) for t in updated_targets]


def _prepare_defects(
    existing: list[dict],
    items: list[dict],
    cases_by_id: dict[str, dict] | None = None,
) -> tuple[list[dict], list[str]]:
    added_ids: list[str] = []
    existing_ids = {as_text(r.get("id")) for r in existing if isinstance(r, dict)}
    out = list(existing)
    for raw in items:
        raw_dict = dict(raw)
        from_case = as_text(raw_dict.get("from_case"))
        if from_case:
            src = (cases_by_id or {}).get(from_case)
            if src is None:
                raise SystemExit(f"ERROR: Source test case '{from_case}' not found for defect.")
            item = _seed_defect_from_case(raw_dict, src)
        else:
            item = raw_dict
        for req in ("title", "severity", "type", "module", "expected", "actual", "suggestion"):
            if not as_text(item.get(req)):
                raise SystemExit(f"ERROR: Defect is missing required '{req}'.")
        if not as_list(item.get("steps")) or not as_list(item.get("evidence")) or not as_list(item.get("test_case_ids")):
            raise SystemExit("ERROR: Defect requires non-empty 'steps', 'evidence', and 'test_case_ids'.")
        _validate_enum(as_text(item.get("severity")), SEVERITIES, "severity")
        _validate_enum(as_text(item.get("type")), DEFECT_TYPES, "defect type")
        _validate_enum(as_text(item.get("status") or "Open"), DEFECT_STATUSES, "defect status")
        did = as_text(item.get("id")) or _next_id(out, "DEF")
        if did in existing_ids:
            raise SystemExit(f"ERROR: Duplicate defect id '{did}'.")
        item["id"] = did
        item.setdefault("status", "Open")
        item.setdefault("created_at", now_iso())
        existing_ids.add(did)
        out.append(item)
        added_ids.append(did)
    return out, added_ids


def cmd_add_defects(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "06-defects.json"
    doc = _load_doc(path, {"defects": []})
    items = _read_batch_payload(args)
    cases_by_id: dict[str, dict] | None = None
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
    elif any(isinstance(raw, dict) and raw.get("from_case") for raw in items):
        cases_doc = _load_doc(workspace / "05-test-cases.json", {"test_cases": []})
        cases_by_id = {
            as_text(c.get("id")): c for c in cases_doc["test_cases"] if isinstance(c, dict) and as_text(c.get("id"))
        }

    doc["defects"], added_ids = _prepare_defects(doc["defects"], items, cases_by_id=cases_by_id)
    write_json_atomic(path, doc)
    return added_ids


def _prepare_fixtures(existing: list[dict], items: list[dict]) -> tuple[list[dict], list[str]]:
    added_ids: list[str] = []
    existing_ids = {as_text(r.get("id")) for r in existing if isinstance(r, dict)}
    out = list(existing)
    for raw in items:
        item = dict(raw)
        for req in ("name", "purpose"):
            if not as_text(item.get(req)):
                raise SystemExit(f"ERROR: Fixture is missing required '{req}'.")
        if item.get("design"):
            _validate_enum(as_text(item.get("design")), FIXTURE_DESIGNS, "fixture design")
        fid = as_text(item.get("id")) or _next_id(out, "F")
        if fid in existing_ids:
            raise SystemExit(f"ERROR: Duplicate fixture id '{fid}'.")
        item["id"] = fid
        existing_ids.add(fid)
        out.append(item)
        added_ids.append(fid)
    return out, added_ids


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
    doc["fixtures"], added_ids = _prepare_fixtures(doc["fixtures"], items)
    write_json_atomic(path, doc)
    return added_ids


def _prepare_config_changes(existing: list[dict], items: list[dict]) -> tuple[list[dict], list[str]]:
    added_ids: list[str] = []
    existing_ids = {as_text(r.get("id")) for r in existing if isinstance(r, dict)}
    out = list(existing)
    for raw in items:
        item = dict(raw)
        for req in ("path", "original", "changed_to"):
            if not as_text(item.get(req)):
                raise SystemExit(f"ERROR: Config change is missing required '{req}'.")
        cid = as_text(item.get("id")) or _next_id(out, "C")
        if cid in existing_ids:
            raise SystemExit(f"ERROR: Duplicate config change id '{cid}'.")
        item["id"] = cid
        item.setdefault("restored", False)
        item.setdefault("changed_at", now_iso())
        existing_ids.add(cid)
        out.append(item)
        added_ids.append(cid)
    return out, added_ids


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
    doc["config_changes"], added_ids = _prepare_config_changes(doc["config_changes"], items)
    write_json_atomic(path, doc)
    return added_ids


def _prepare_config_restores(existing: list[dict], items: list[dict], *, default_id: str = "") -> list[str]:
    by_id = {as_text(c.get("id")): c for c in existing if isinstance(c, dict) and as_text(c.get("id"))}
    restored_ids: list[str] = []
    for raw in items:
        cid = as_text(raw.get("id")) or default_id
        if not cid:
            raise SystemExit("ERROR: restore-config entry requires 'id'.")
        target = by_id.get(cid)
        if target is None:
            raise SystemExit(f"ERROR: Config change '{cid}' not found.")
        target["restored"] = True
        target["restored_at"] = as_text(raw.get("restored_at")) or now_iso()
        target["restored_value"] = as_text(raw.get("restored_value")) or target.get("original", "")
        if raw.get("evidence"):
            target["evidence"] = raw["evidence"]
        if raw.get("notes"):
            target["notes"] = raw["notes"]
        restored_ids.append(cid)
    return restored_ids


def cmd_restore_config(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "07-fixtures-and-config-ledger.json"
    doc = _load_doc(path, {"fixtures": [], "config_changes": [], "configuration_matrix": []})

    items = _read_batch_payload(args)
    if items is None:
        if not args.id:
            raise SystemExit("ERROR: restore-config requires --id when not using --stdin/--file.")
        items = [
            {
                "id": args.id,
                "restored_value": args.restored_value,
                "restored_at": args.restored_at,
                "evidence": args.evidence,
                "notes": args.notes,
            }
        ]

    restored_ids = _prepare_config_restores(doc["config_changes"], items, default_id=as_text(args.id))
    write_json_atomic(path, doc)
    return restored_ids


def _prepare_config_matrix(existing: list[dict], items: list[dict]) -> tuple[list[dict], list[str]]:
    added_ids: list[str] = []
    existing_ids = {as_text(r.get("id")) for r in existing if isinstance(r, dict)}
    out = list(existing)
    for raw in items:
        item = dict(raw)
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
        mid = as_text(item.get("id")) or _next_id(out, "CFG")
        if mid in existing_ids:
            raise SystemExit(f"ERROR: Duplicate configuration matrix id '{mid}'.")
        item["id"] = mid
        existing_ids.add(mid)
        out.append(item)
        added_ids.append(mid)
    return out, added_ids


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
    doc["configuration_matrix"], added_ids = _prepare_config_matrix(doc["configuration_matrix"], items)
    write_json_atomic(path, doc)
    return added_ids


def _prepare_questions(existing: list[dict], items: list[dict]) -> tuple[list[dict], list[str]]:
    added_ids: list[str] = []
    existing_ids = {as_text(r.get("id")) for r in existing if isinstance(r, dict)}
    out = list(existing)
    for raw in items:
        item = dict(raw)
        for req in ("type", "description"):
            if not as_text(item.get(req)):
                raise SystemExit(f"ERROR: Question is missing required '{req}'.")
        _validate_enum(as_text(item.get("type")), QUESTION_TYPES, "question type")
        _validate_enum(as_text(item.get("status") or "Open"), QUESTION_STATUSES, "question status")
        qid = as_text(item.get("id")) or _next_id(out, "Q")
        if qid in existing_ids:
            raise SystemExit(f"ERROR: Duplicate question id '{qid}'.")
        item["id"] = qid
        item.setdefault("status", "Open")
        existing_ids.add(qid)
        out.append(item)
        added_ids.append(qid)
    return out, added_ids


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
    doc["items"], added_ids = _prepare_questions(doc["items"], items)
    write_json_atomic(path, doc)
    return added_ids


def cmd_set_meta(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "meta.json"
    doc = _load_doc(path, {})
    patches = _read_batch_payload(args)
    if patches is not None:
        if len(patches) != 1:
            raise SystemExit("ERROR: set-meta expects a single JSON object.")
        doc = merge_meta_patch(doc, patches[0])
    else:
        if args.staging_confirmed:
            doc["staging_confirmed"] = args.staging_confirmed == "true"
        if args.version is not None:
            doc["version"] = args.version
        if args.scope is not None:
            doc["scope"] = args.scope
        if args.in_scope_module:
            doc["in_scope_modules"] = list(args.in_scope_module)
            if args.scope is None:
                doc["scope"] = ", ".join(args.in_scope_module)
        if args.depth:
            _validate_enum(args.depth, DEPTHS, "depth")
            doc["depth"] = args.depth
        if args.execution_mode:
            _validate_enum(args.execution_mode, EXECUTION_MODES, "execution_mode")
            doc["execution_mode"] = args.execution_mode
        if args.atlas_coverage_mode:
            _validate_enum(args.atlas_coverage_mode, ATLAS_COVERAGE_MODES, "atlas_coverage_mode")
            doc["atlas_coverage_mode"] = args.atlas_coverage_mode
        if args.role:
            doc["roles"] = list(args.role)
        if args.host is not None:
            doc["host"] = args.host
        if args.browser_tool is not None:
            doc["browser_tool"] = args.browser_tool
        if args.locale is not None:
            doc["locale"] = args.locale
        if args.finished_at is not None:
            doc["finished_at"] = now_iso() if args.finished_at == "now" else args.finished_at
        if args.limitation:
            doc["limitations"] = list(args.limitation)
        if args.capability:
            caps = doc.get("capabilities") if isinstance(doc.get("capabilities"), dict) else {}
            for entry in args.capability:
                if "=" not in entry:
                    raise SystemExit(f"ERROR: --capability must be key=true|false, got '{entry}'.")
                k, v = entry.split("=", 1)
                caps[k.strip()] = v.strip().lower() == "true"
            doc["capabilities"] = caps
        rc = doc.get("run_contract") if isinstance(doc.get("run_contract"), dict) else {}
        rc_changed = False
        if args.authorized_origin:
            rc["authorized_origins"] = list(args.authorized_origin)
            rc_changed = True
        if args.allowed_action:
            rc["allowed_actions"] = list(args.allowed_action)
            rc_changed = True
        if args.forbidden_action:
            rc["forbidden_actions"] = list(args.forbidden_action)
            rc_changed = True
        if args.mutation_budget is not None:
            rc["mutation_budget"] = args.mutation_budget
            rc_changed = True
        if args.end_state is not None:
            rc["end_state"] = args.end_state
            rc_changed = True
        if rc_changed:
            doc["run_contract"] = rc

    write_json_atomic(path, doc)
    return ["meta.json"]


def cmd_update_defect(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "06-defects.json"
    doc = _load_doc(path, {"defects": []})
    by_id = {as_text(d.get("id")): d for d in doc["defects"] if isinstance(d, dict) and as_text(d.get("id"))}
    patches = _read_batch_payload(args)
    updated: list[str] = []
    if patches is not None:
        for patch in patches:
            did = as_text(patch.get("id")) or as_text(args.id)
            if not did:
                raise SystemExit("ERROR: update-defect JSON payload requires 'id'.")
            target = by_id.get(did)
            if target is None:
                raise SystemExit(f"ERROR: Defect '{did}' not found.")
            target.update(patch)
            target["id"] = did
            _validate_enum(as_text(target.get("severity")), SEVERITIES, "severity")
            _validate_enum(as_text(target.get("type")), DEFECT_TYPES, "defect type")
            _validate_enum(as_text(target.get("status") or "Open"), DEFECT_STATUSES, "defect status")
            updated.append(did)
    else:
        if not args.id:
            raise SystemExit("ERROR: update-defect requires --id when not using --stdin/--file.")
        target = by_id.get(args.id)
        if target is None:
            raise SystemExit(f"ERROR: Defect '{args.id}' not found.")
        if args.status:
            _validate_enum(args.status, DEFECT_STATUSES, "defect status")
            target["status"] = args.status
        if args.severity:
            _validate_enum(args.severity, SEVERITIES, "severity")
            target["severity"] = args.severity
        if args.notes is not None:
            target["notes"] = args.notes
        if args.workaround is not None:
            target["workaround"] = args.workaround
        if args.impact is not None:
            target["impact"] = args.impact
        if args.likely_cause is not None:
            target["likely_cause"] = args.likely_cause
        if args.suggestion is not None:
            target["suggestion"] = args.suggestion
        updated.append(args.id)

    write_json_atomic(path, doc)
    return updated


def cmd_update_fixture(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "07-fixtures-and-config-ledger.json"
    doc = _load_doc(path, {"fixtures": [], "config_changes": [], "configuration_matrix": []})
    by_id = {as_text(f.get("id")): f for f in doc["fixtures"] if isinstance(f, dict) and as_text(f.get("id"))}
    patches = _read_batch_payload(args)
    updated: list[str] = []
    if patches is not None:
        for patch in patches:
            fid = as_text(patch.get("id")) or as_text(args.id)
            if not fid:
                raise SystemExit("ERROR: update-fixture JSON payload requires 'id'.")
            target = by_id.get(fid)
            if target is None:
                raise SystemExit(f"ERROR: Fixture '{fid}' not found.")
            target.update(patch)
            target["id"] = fid
            if target.get("design"):
                _validate_enum(as_text(target.get("design")), FIXTURE_DESIGNS, "fixture design")
            updated.append(fid)
    else:
        if not args.id:
            raise SystemExit("ERROR: update-fixture requires --id when not using --stdin/--file.")
        target = by_id.get(args.id)
        if target is None:
            raise SystemExit(f"ERROR: Fixture '{args.id}' not found.")
        if args.status is not None:
            target["status"] = args.status
        if args.cleanup is not None:
            target["cleanup"] = args.cleanup
        if args.notes is not None:
            target["notes"] = args.notes
        if args.purpose is not None:
            target["purpose"] = args.purpose
        if args.design:
            _validate_enum(args.design, FIXTURE_DESIGNS, "fixture design")
            target["design"] = args.design
        updated.append(args.id)

    write_json_atomic(path, doc)
    return updated


def cmd_update_question(workspace: Path, args: argparse.Namespace) -> list[str]:
    path = workspace / "08-open-questions.json"
    doc = _load_doc(path, {"items": []})
    by_id = {as_text(q.get("id")): q for q in doc["items"] if isinstance(q, dict) and as_text(q.get("id"))}
    patches = _read_batch_payload(args)
    updated: list[str] = []
    if patches is not None:
        for patch in patches:
            qid = as_text(patch.get("id")) or as_text(args.id)
            if not qid:
                raise SystemExit("ERROR: update-question JSON payload requires 'id'.")
            target = by_id.get(qid)
            if target is None:
                raise SystemExit(f"ERROR: Question '{qid}' not found.")
            target.update(patch)
            target["id"] = qid
            _validate_enum(as_text(target.get("type")), QUESTION_TYPES, "question type")
            _validate_enum(as_text(target.get("status") or "Open"), QUESTION_STATUSES, "question status")
            updated.append(qid)
    else:
        if not args.id:
            raise SystemExit("ERROR: update-question requires --id when not using --stdin/--file.")
        target = by_id.get(args.id)
        if target is None:
            raise SystemExit(f"ERROR: Question '{args.id}' not found.")
        if args.status:
            _validate_enum(args.status, QUESTION_STATUSES, "question status")
            target["status"] = args.status
        if args.impact is not None:
            target["impact"] = args.impact
        if args.owner is not None:
            target["owner"] = args.owner
        if args.description is not None:
            target["description"] = args.description
        if args.related:
            target["related"] = list(args.related)
        updated.append(args.id)

    write_json_atomic(path, doc)
    return updated


def cmd_import_guided(workspace: Path, args: argparse.Namespace) -> list[str]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise SystemExit(f"ERROR: openpyxl is required for import-guided: {exc}")

    xlsx_path = Path(args.file).expanduser().resolve()
    if not xlsx_path.is_file():
        raise SystemExit(f"ERROR: Guided workbook not found: {xlsx_path}")

    wb = load_workbook(xlsx_path, data_only=True)
    ws = wb["Guided Execution"] if "Guided Execution" in wb.sheetnames else wb.active
    headers = [as_text(cell.value) for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    col_map = {name: idx for idx, name in enumerate(headers) if name}

    id_col = col_map.get("Case ID", 0)
    actual_col = col_map.get("Observed Actual Result (Fill In)", 10)
    status_col = col_map.get("Status (Fill In)", 11)
    notes_col = col_map.get("Tester Notes / Error Text", 12)

    cases_path = workspace / "05-test-cases.json"
    doc = _load_doc(cases_path, {"test_cases": []})
    by_id = {as_text(c.get("id")): c for c in doc["test_cases"] if isinstance(c, dict) and as_text(c.get("id"))}

    updated_ids: list[str] = []
    updated_cases: list[dict] = []
    stamp = now_iso()

    for row in ws.iter_rows(min_row=2, values_only=True):
        cid = as_text(row[id_col] if id_col < len(row) else "")
        if not cid:
            continue
        status = as_text(row[status_col] if status_col < len(row) else "")
        actual = as_text(row[actual_col] if actual_col < len(row) else "")
        notes = as_text(row[notes_col] if notes_col < len(row) else "")
        if not status and not actual and not notes:
            continue

        target = by_id.get(cid)
        if target is None:
            raise SystemExit(f"ERROR: Guided sheet Case ID '{cid}' not found in 05-test-cases.json.")
        if status:
            _validate_enum(status, STATUSES, "status")
            target["status"] = status
            if status in ("Pass", "Fail") and not target.get("executed_at"):
                target["executed_at"] = stamp
        if actual:
            target["actual"] = actual
        if notes:
            target["notes"] = notes
        _validate_case_fields(target)
        updated_ids.append(cid)
        updated_cases.append(target)

    if updated_ids:
        write_json_atomic(cases_path, doc)
        for tc in updated_cases:
            _sync_case_links(workspace, tc)
    return updated_ids


def _seed_defect_from_case(raw: dict, src: dict) -> dict:
    cid = as_text(src.get("id"))
    return {
        "id": raw.get("id", ""),
        "title": raw.get("title") or src.get("title", ""),
        "severity": raw.get("severity") or src.get("severity", ""),
        "type": raw.get("type") or src.get("defect_type", ""),
        "module": raw.get("module") or src.get("module", ""),
        "path": raw.get("path") or src.get("path", ""),
        "test_case_ids": raw.get("test_case_ids") or [cid],
        "environment": raw.get("environment", ""),
        "preconditions": raw.get("preconditions") or src.get("preconditions", ""),
        "steps": raw.get("steps") or src.get("steps", []),
        "expected": raw.get("expected") or src.get("expected", ""),
        "actual": raw.get("actual") or src.get("actual", ""),
        "evidence": raw.get("evidence") or src.get("evidence", []),
        "impact": raw.get("impact", ""),
        "likely_cause": raw.get("likely_cause", ""),
        "suggestion": raw.get("suggestion") or src.get("suggestion", ""),
        "workaround": raw.get("workaround", ""),
        "status": raw.get("status") or "Open",
        "notes": raw.get("notes") or src.get("notes", ""),
        "created_at": raw.get("created_at") or now_iso(),
    }


def _sync_links_in_memory(
    case: dict,
    controls: list[dict],
    relationships: list[dict],
    config_matrix: list[dict],
) -> tuple[bool, bool, bool]:
    case_id = as_text(case.get("id"))
    atlas_ids = {as_text(x) for x in as_list(case.get("atlas_ids")) if as_text(x)}
    rel_ids = {as_text(x) for x in as_list(case.get("relationship_ids")) if as_text(x)}
    cfg_ids = {as_text(x) for x in as_list(case.get("config_matrix_ids")) if as_text(x)}
    c_changed = r_changed = m_changed = False

    if atlas_ids:
        for ctrl in controls:
            if isinstance(ctrl, dict) and as_text(ctrl.get("id")) in atlas_ids:
                updated = _append_unique(ctrl.get("tested_by"), case_id)
                if updated != ctrl.get("tested_by"):
                    ctrl["tested_by"] = updated
                    c_changed = True
    if rel_ids:
        for rel in relationships:
            if isinstance(rel, dict) and as_text(rel.get("id")) in rel_ids:
                updated = _append_unique(rel.get("verified_by"), case_id)
                if updated != rel.get("verified_by"):
                    rel["verified_by"] = updated
                    r_changed = True
    if cfg_ids:
        for entry in config_matrix:
            if isinstance(entry, dict) and as_text(entry.get("id")) in cfg_ids:
                updated = _append_unique(entry.get("tested_by"), case_id)
                if updated != entry.get("tested_by"):
                    entry["tested_by"] = updated
                    m_changed = True
    return c_changed, r_changed, m_changed


def cmd_ingest(workspace: Path, args: argparse.Namespace) -> list[str]:
    """Atomically ingest a multi-artifact JSON bundle into workspace files in one call."""
    bundles = _read_batch_payload(args)
    if not bundles or len(bundles) != 1:
        raise SystemExit("ERROR: ingest expects a single JSON object via --stdin or --file.")
    bundle = bundles[0]

    meta_path = workspace / "meta.json"
    atlas_path = workspace / "02-field-atlas.json"
    rel_path = workspace / "03-relationships.json"
    cases_path = workspace / "05-test-cases.json"
    defects_path = workspace / "06-defects.json"
    ledger_path = workspace / "07-fixtures-and-config-ledger.json"
    questions_path = workspace / "08-open-questions.json"

    meta_doc = _load_doc(meta_path, {})
    atlas_doc = _load_doc(atlas_path, {"controls": []})
    rel_doc = _load_doc(rel_path, {"relationships": []})
    cases_doc = _load_doc(cases_path, {"test_cases": []})
    defects_doc = _load_doc(defects_path, {"defects": []})
    ledger_doc = _load_doc(ledger_path, {"fixtures": [], "config_changes": [], "configuration_matrix": []})
    questions_doc = _load_doc(questions_path, {"items": []})

    summary_ids: list[str] = []
    dirty_meta = dirty_atlas = dirty_rel = dirty_cases = dirty_defects = dirty_ledger = dirty_questions = False

    if isinstance(bundle.get("meta"), dict):
        meta_doc = merge_meta_patch(meta_doc, bundle["meta"])
        dirty_meta = True
        summary_ids.append("meta.json")

    if bundle.get("controls"):
        atlas_doc["controls"], cids = _prepare_controls(atlas_doc["controls"], as_list(bundle["controls"]))
        dirty_atlas = True
        summary_ids.extend(cids)

    if bundle.get("relationships"):
        rel_doc["relationships"], rids = _prepare_relationships(
            rel_doc["relationships"], as_list(bundle["relationships"])
        )
        dirty_rel = True
        summary_ids.extend(rids)

    if bundle.get("configuration_matrix"):
        ledger_doc["configuration_matrix"], mids = _prepare_config_matrix(
            ledger_doc["configuration_matrix"], as_list(bundle["configuration_matrix"])
        )
        dirty_ledger = True
        summary_ids.extend(mids)

    added_cases: list[dict] = []
    if bundle.get("test_cases"):
        cases_doc["test_cases"], tcids, added_cases = _prepare_cases(
            cases_doc["test_cases"], as_list(bundle["test_cases"])
        )
        dirty_cases = True
        summary_ids.extend(tcids)

    cases_by_id = {as_text(c.get("id")): c for c in cases_doc["test_cases"] if isinstance(c, dict) and as_text(c.get("id"))}
    defect_items = list(as_list(bundle.get("defects")))
    if bundle.get("auto_seed_defects"):
        already_linked = {
            as_text(tid)
            for d in defects_doc["defects"]
            if isinstance(d, dict)
            for tid in as_list(d.get("test_case_ids"))
        } | {
            as_text(tid)
            for d in defect_items
            if isinstance(d, dict)
            for tid in as_list(d.get("test_case_ids"))
        } | {as_text(d.get("from_case")) for d in defect_items if isinstance(d, dict) and d.get("from_case")}
        for tc in added_cases:
            if as_text(tc.get("status")) == "Fail" and as_text(tc.get("id")) not in already_linked:
                defect_items.append({"from_case": as_text(tc.get("id"))})

    if defect_items:
        defects_doc["defects"], dids = _prepare_defects(
            defects_doc["defects"], defect_items, cases_by_id=cases_by_id
        )
        dirty_defects = True
        summary_ids.extend(dids)

    if bundle.get("fixtures"):
        ledger_doc["fixtures"], fids = _prepare_fixtures(
            ledger_doc["fixtures"], as_list(bundle["fixtures"])
        )
        dirty_ledger = True
        summary_ids.extend(fids)

    if bundle.get("config_changes"):
        ledger_doc["config_changes"], cids = _prepare_config_changes(
            ledger_doc["config_changes"], as_list(bundle["config_changes"])
        )
        dirty_ledger = True
        summary_ids.extend(cids)

    if bundle.get("config_restores"):
        restored_cids = _prepare_config_restores(
            ledger_doc["config_changes"], as_list(bundle["config_restores"])
        )
        dirty_ledger = True
        summary_ids.extend(restored_cids)

    if bundle.get("questions"):
        questions_doc["items"], qids = _prepare_questions(
            questions_doc["items"], as_list(bundle["questions"])
        )
        dirty_questions = True
        summary_ids.extend(qids)

    for tc in added_cases:
        c_ch, r_ch, m_ch = _sync_links_in_memory(
            tc, atlas_doc["controls"], rel_doc["relationships"], ledger_doc["configuration_matrix"]
        )
        dirty_atlas = dirty_atlas or c_ch
        dirty_rel = dirty_rel or r_ch
        dirty_ledger = dirty_ledger or m_ch

    if dirty_meta:
        write_json_atomic(meta_path, meta_doc)
    if dirty_atlas:
        write_json_atomic(atlas_path, atlas_doc)
    if dirty_rel:
        write_json_atomic(rel_path, rel_doc)
    if dirty_cases:
        write_json_atomic(cases_path, cases_doc)
    if dirty_defects:
        write_json_atomic(defects_path, defects_doc)
    if dirty_ledger:
        write_json_atomic(ledger_path, ledger_doc)
    if dirty_questions:
        write_json_atomic(questions_path, questions_doc)
    return summary_ids


def _add_batch_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--stdin", action="store_true", help="Read a JSON object or array from stdin")
    p.add_argument("--file", default="", help="Read a JSON object or array from a file")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Atomically record items in a blackbox-ui-qa v2.0 workspace.")
    parser.add_argument("workspace", help="Workspace directory")
    sub = parser.add_subparsers(dest="command", required=True)

    p_meta = sub.add_parser("set-meta", help="Update meta.json intake, capabilities, or completion fields")
    _add_batch_flags(p_meta)
    p_meta.add_argument("--staging-confirmed", choices=["true", "false"], default="")
    p_meta.add_argument("--version", default=None)
    p_meta.add_argument("--scope", default=None)
    p_meta.add_argument("--in-scope-module", action="append")
    p_meta.add_argument("--depth", default="")
    p_meta.add_argument("--execution-mode", default="")
    p_meta.add_argument("--atlas-coverage-mode", default="")
    p_meta.add_argument("--role", action="append")
    p_meta.add_argument("--host", default=None)
    p_meta.add_argument("--browser-tool", default=None)
    p_meta.add_argument("--locale", default=None)
    p_meta.add_argument("--finished-at", default=None, help="ISO timestamp or 'now'")
    p_meta.add_argument("--limitation", action="append")
    p_meta.add_argument("--capability", action="append", help="key=true|false")
    p_meta.add_argument("--authorized-origin", action="append")
    p_meta.add_argument("--allowed-action", action="append")
    p_meta.add_argument("--forbidden-action", action="append")
    p_meta.add_argument("--mutation-budget", default=None)
    p_meta.add_argument("--end-state", default=None)

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
    p_case.add_argument("--config-matrix-id", action="append")
    p_case.add_argument("--surface", action="append")
    p_case.add_argument("--evidence", action="append")
    p_case.add_argument("--suggestion", default="")
    p_case.add_argument("--notes", default="")
    p_case.add_argument("--triage-disposition", default="")
    p_case.add_argument("--triage-reason", default="")
    p_case.add_argument("--triage-evidence", action="append")
    p_case.add_argument("--executed-at", default="")

    p_ucase = sub.add_parser("update-case", help="Update execution result of one or more existing test cases")
    _add_batch_flags(p_ucase)
    p_ucase.add_argument("--id", default="")
    p_ucase.add_argument("--status", default="")
    p_ucase.add_argument("--expected", default=None)
    p_ucase.add_argument("--actual", default=None)
    p_ucase.add_argument("--severity", default="")
    p_ucase.add_argument("--defect-type", default="")
    p_ucase.add_argument("--step", action="append")
    p_ucase.add_argument("--atlas-id", action="append")
    p_ucase.add_argument("--relationship-id", action="append")
    p_ucase.add_argument("--config-matrix-id", action="append")
    p_ucase.add_argument("--oracle-type", default="")
    p_ucase.add_argument("--oracle-source", default="")
    p_ucase.add_argument("--oracle-confidence", default="")
    p_ucase.add_argument("--oracle-family", action="append")
    p_ucase.add_argument("--oracle-description", default="")
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

    p_udef = sub.add_parser("update-defect", help="Update an existing defect in 06-defects.json")
    _add_batch_flags(p_udef)
    p_udef.add_argument("--id", default="")
    p_udef.add_argument("--status", default="")
    p_udef.add_argument("--severity", default="")
    p_udef.add_argument("--impact", default=None)
    p_udef.add_argument("--likely-cause", default=None)
    p_udef.add_argument("--suggestion", default=None)
    p_udef.add_argument("--workaround", default=None)
    p_udef.add_argument("--notes", default=None)

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

    p_ufix = sub.add_parser("update-fixture", help="Update fixture lifecycle status or cleanup notes")
    _add_batch_flags(p_ufix)
    p_ufix.add_argument("--id", default="")
    p_ufix.add_argument("--status", default=None)
    p_ufix.add_argument("--cleanup", default=None)
    p_ufix.add_argument("--notes", default=None)
    p_ufix.add_argument("--purpose", default=None)
    p_ufix.add_argument("--design", default="")

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

    p_rcfg = sub.add_parser("restore-config", help="Mark one or more logged config changes as restored")
    _add_batch_flags(p_rcfg)
    p_rcfg.add_argument("--id", default="")
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

    p_uq = sub.add_parser("update-question", help="Update status or details of an open question")
    _add_batch_flags(p_uq)
    p_uq.add_argument("--id", default="")
    p_uq.add_argument("--status", default="")
    p_uq.add_argument("--impact", default=None)
    p_uq.add_argument("--owner", default=None)
    p_uq.add_argument("--description", default=None)
    p_uq.add_argument("--related", action="append")

    p_ig = sub.add_parser("import-guided", help="Import human-filled Guided_Execution_*.xlsx results")
    p_ig.add_argument("--file", required=True, help="Path to filled Guided_Execution_*.xlsx")

    p_ing = sub.add_parser("ingest", help="Atomically ingest a multi-artifact JSON bundle in one call")
    _add_batch_flags(p_ing)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        print(f"ERROR: Workspace not found: {workspace}", file=sys.stderr)
        return 1

    dispatch = {
        "set-meta": cmd_set_meta,
        "add-control": cmd_add_controls,
        "add-relationship": cmd_add_relationships,
        "add-case": cmd_add_cases,
        "update-case": cmd_update_case,
        "add-defect": cmd_add_defects,
        "update-defect": cmd_update_defect,
        "add-fixture": cmd_add_fixtures,
        "update-fixture": cmd_update_fixture,
        "log-config": cmd_log_config,
        "restore-config": cmd_restore_config,
        "add-config-matrix": cmd_add_config_matrix,
        "add-question": cmd_add_questions,
        "update-question": cmd_update_question,
        "import-guided": cmd_import_guided,
        "ingest": cmd_ingest,
    }
    ids = dispatch[args.command](workspace, args)
    print(json.dumps({"ok": True, "command": args.command, "ids": ids}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
