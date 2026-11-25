#!/usr/bin/env python3
"""Create a blackbox-ui-qa v2.0 workspace with required artifacts and folders."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from qa_common import SCHEMA_VERSION, now_iso, slugify

SCOPE_TEMPLATE = """# QA scope & domain rules

Workspace metadata and the run contract live in `meta.json`. Keep this file strictly for user-provided rules, business context, and raw scope notes so nothing is duplicated.

## Objective

<!-- 1–2 sentences: what decision will this QA run support? -->

## Rules & specifications provided by the user

<!-- Claims to verify against the live app, never assumed proof. -->

## Notes & domain context

<!-- Environment caveats, regulatory region/year, prior incident pointers to probe. -->
"""

PROGRESS_TEMPLATE = """# Execution checkpoint

Stage: 1 — Rapid Map & Surface Sweep
Modules complete: none
Modules in progress: none
Open blockers: none
Next action: Complete intake in meta.json, verify login, and map navigation tree in 01-app-map.md.
Last updated: {started}

## Stage checkpoints

| Stage | Status | Notes |
|---|---|---|
| 1. Rapid Map & Surface Sweep | in progress |  |
| 2. Deep Model & Risk Execution | todo |  |
| 3. Second-Look Charters, Report & Cleanup | todo |  |
"""

APP_MAP_TEMPLATE = """# App map & state ledger

A state is anything that alters visible UI or interaction rules: route, active tab/subtab, open modal/drawer, selection toolbar, role, or canvas mode.

Signature format: `URL | active tab/mode | open overlay | role | selection/label hash`.

## Navigation tree

```
App
├── Module
│   ├── Tab / View
│   │   └── Sub-tab / Overlay
└── ...
```

## States

| State ID | Path | Role | Signature | Status (todo/visited/unreached) | Console/Net Errors | Notes |
|---|---|---|---|---|---|---|
| S-001 |  |  |  | todo |  |  |

## Unreached

| Path | Reason | What would be needed |
|---|---|---|
|  |  |  |

## Discovery sweeps

- [ ] Menu, top-bar, user-menu & command-palette reconciliation
- [ ] Role menu diff (across all provided roles)
- [ ] Passive surface sweep (console errors, HTTP >=400, broken images, overflow)
"""

RULES_TEMPLATE = """# Business rules & state machines

One rule per line as IF/THEN with source and confidence. Record entity state machines below.

## Rules

| ID | Rule (IF ... THEN ...) | Source | Confidence | Probed by | Notes |
|---|---|---|---|---|---|
| RULE-001 |  |  |  |  |  |

## Entity state machines

```
Entity: Draft -> Submitted -> Approved -> Locked (expected illegal: Approved -> Edit)
```

## Oracle conflicts

| Rule(s) | Conflict | Question for user (mirror in 08-open-questions.json) |
|---|---|---|
|  |  |  |
"""

SCENARIOS_TEMPLATE = """# Cross-module scenarios & charters

High-yield scenarios combine ≥2 modules, push boundaries/reversals/races, and define an end state.

```
SC-001  "<short name>"
  Entities:  QA_... (stacked / isolate / control)
  Config:    <settings active>
  Path:      <steps across modules>
  Oracle:    <calc/ script or rule>
  Expected:  <parallel expected outcome>
  End state: <record state, downstream totals, cleanup state>
```

## Scenarios & gap-hunt charters

| ID / Charter | Scope / Lens | Risk | Oracle | Status |
|---|---|---|---|---|
| SC-001 |  |  |  | todo |
"""

CALC_README = """# Independent calculations

Every calculation test in Deep/Exhaustive runs needs an expected value computed outside the app.

- One script per scenario or case: `calc/TC-0031.py`, `calc/SC-021.py`.
- Print inputs, formula, rounding mode, and expected result with exact UI precision.
- Reference the script or its `.txt`/`.json` output in `evidence` and `oracle.source`.
- Never import app code or call app APIs to derive expected results.
"""


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a blackbox-ui-qa v2.0 workspace.")
    parser.add_argument("--app", required=True, help="Application name")
    parser.add_argument("--url", default="", help="Application URL")
    parser.add_argument("--module", action="append", default=[], help="In-scope module (repeatable)")
    parser.add_argument(
        "--depth",
        default="deep",
        choices=["quick", "standard", "deep", "exhaustive"],
        help="QA depth (default: deep)",
    )
    parser.add_argument(
        "--mode",
        default="browser",
        choices=["browser", "guided"],
        help="Execution mode (default: browser)",
    )
    parser.add_argument(
        "--atlas-mode",
        default="",
        choices=["", "sampled", "risk-targeted", "full"],
        help="Override atlas coverage mode",
    )
    parser.add_argument("--workspace", default="", help="Workspace path (default: qa-<app>-<timestamp>)")
    parser.add_argument("--force", action="store_true", help="Write into an existing non-empty workspace")
    args = parser.parse_args()

    started = now_iso()
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    if args.workspace:
        workspace = Path(args.workspace).expanduser().resolve()
    else:
        workspace = (Path.cwd() / f"qa-{slugify(args.app)}-{stamp}").resolve()

    if workspace.exists() and any(workspace.iterdir()) and not args.force:
        print(f"Refusing to overwrite non-empty workspace: {workspace}", file=sys.stderr)
        print("Use --force or choose another --workspace.", file=sys.stderr)
        return 1

    workspace.mkdir(parents=True, exist_ok=True)
    for folder in (
        "evidence/screenshots",
        "evidence/snapshots",
        "evidence/network",
        "evidence/console",
        "evidence/outputs",
        "evidence/security",
        "calc",
    ):
        (workspace / folder).mkdir(parents=True, exist_ok=True)

    modules = [m.strip() for m in args.module if m.strip()]
    depth_cap = args.depth.capitalize()
    atlas_mode = args.atlas_mode or (
        "sampled" if args.depth == "quick" else ("full" if args.depth == "exhaustive" else "risk-targeted")
    )
    scope = ", ".join(modules) if modules else "Whole application"

    meta = {
        "schema_version": SCHEMA_VERSION,
        "app": args.app,
        "url": args.url,
        "environment": "staging",
        "staging_confirmed": False,
        "version": "",
        "scope": scope,
        "in_scope_modules": modules,
        "depth": depth_cap,
        "execution_mode": args.mode,
        "atlas_coverage_mode": atlas_mode,
        "roles": [],
        "host": "",
        "browser_tool": "none" if args.mode == "guided" else "",
        "capabilities": {
            "dom_snapshot": False,
            "screenshot": False,
            "console": False,
            "network": False,
            "js_eval": False,
            "multiple_contexts": False,
            "downloads": False,
            "iframes": False,
            "can_freeze_time": False,
        },
        "viewports": ["1440x900", "390x844"],
        "locale": "",
        "started_at": started,
        "finished_at": "",
        "limitations": [],
        "run_contract": {
            "authorized_origins": [args.url] if args.url else [],
            "allowed_actions": ["read-only recon"],
            "forbidden_actions": [],
            "direct_url_authz_checks": True,
            "mutation_budget": "",
            "data_classification": "synthetic test data only",
            "evidence_retention": "retain workspace until handoff",
            "time_anchor": {
                "clock": started,
                "user_timezone": "",
                "tenant_timezone": "",
                "can_freeze_time": False,
            },
            "end_state": "All QA_ fixtures deleted or archived; config restored; no outbound messages.",
        },
    }
    write_json(workspace / "meta.json", meta)
    write_text(workspace / "00-scope.md", SCOPE_TEMPLATE)
    write_text(workspace / "00-progress.md", PROGRESS_TEMPLATE.format(started=started))
    write_text(workspace / "01-app-map.md", APP_MAP_TEMPLATE)
    write_json(workspace / "02-field-atlas.json", {"controls": []})
    write_json(workspace / "03-relationships.json", {"relationships": []})
    write_text(workspace / "03-rules.md", RULES_TEMPLATE)
    write_text(workspace / "04-scenarios.md", SCENARIOS_TEMPLATE)
    write_json(workspace / "05-test-cases.json", {"test_cases": []})
    write_json(workspace / "06-defects.json", {"defects": []})
    write_json(
        workspace / "07-fixtures-and-config-ledger.json",
        {"fixtures": [], "config_changes": [], "configuration_matrix": []},
    )
    write_json(workspace / "08-open-questions.json", {"items": []})
    write_text(workspace / "calc" / "README.md", CALC_README)

    print(f"Workspace created: {workspace}")
    print("Next: confirm staging & run_contract in meta.json, then start Stage 1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
