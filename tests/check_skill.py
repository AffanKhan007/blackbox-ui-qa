#!/usr/bin/env python3
"""Integrity checks for the blackbox-ui-qa v2.0 skill package."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> int:
    skill_path = ROOT / "SKILL.md"
    if not skill_path.exists():
        fail("SKILL.md is missing")

    text = skill_path.read_text(encoding="utf-8")
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    if not match:
        fail("SKILL.md must start with YAML frontmatter delimited by ---")

    frontmatter = match.group(1)
    name_match = re.search(r"^name:\s*(.+?)\s*$", frontmatter, re.MULTILINE)
    description_match = re.search(r"^description:\s*(.+?)\s*$", frontmatter, re.MULTILINE)
    version_match = re.search(r'^\s*version:\s*"?([0-9]+\.[0-9]+\.[0-9]+)"?\s*$', frontmatter, re.MULTILINE)
    if not name_match:
        fail("frontmatter is missing 'name'")
    if not description_match:
        fail("frontmatter is missing 'description'")
    if not version_match:
        fail("frontmatter is missing metadata.version")

    name = name_match.group(1).strip()
    description = description_match.group(1).strip()
    version = version_match.group(1).strip()

    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        fail(f"invalid skill name '{name}' (use lowercase kebab-case)")
    if name != ROOT.name:
        fail(f"skill name '{name}' does not match directory name '{ROOT.name}'")
    if not (1 <= len(description) <= 1024):
        fail(f"description length is {len(description)}; must be 1-1024 characters")

    # Version parity across SKILL.md, README.md, CHANGELOG.md, and evals/evals.json
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog_text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    evals_data = json.loads((ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))

    if f"version-{version}-" not in readme_text:
        fail(f"README.md badge does not match SKILL.md version '{version}'")
    if f"## [{version}]" not in changelog_text:
        fail(f"CHANGELOG.md does not contain release heading for '{version}'")
    if evals_data.get("version") != version:
        fail(f"evals/evals.json version '{evals_data.get('version')}' does not match '{version}'")

    for entry in evals_data.get("evals") or []:
        for key in ("id", "archetype", "prompt", "expected_output", "must_catch", "must_not_hallucinate"):
            if not entry.get(key):
                fail(f"eval entry {entry.get('id')} is missing '{key}'")

    lines = text.count("\n") + 1
    if lines > 500:
        fail(f"SKILL.md is {lines} lines; must remain concise (<500 lines).")
    print(f"SKILL.md v{version}: {lines} lines, description {len(description)} chars.")

    # Reference link checks
    referenced = set(re.findall(r"references/[A-Za-z0-9_.-]+\.md", text))
    if not referenced:
        fail("SKILL.md does not reference any reference files")
    for relative in sorted(referenced):
        if not (ROOT / relative).exists():
            fail(f"referenced file does not exist: {relative}")
    for path in sorted((ROOT / "references").glob("*.md")):
        relative = f"references/{path.name}"
        if relative not in referenced:
            fail(f"reference file is not mentioned in SKILL.md: {relative}")

    # Cross-reference checks inside references/*.md (skip workspace artifact filenames)
    workspace_md = {"00-scope.md", "00-progress.md", "01-app-map.md", "03-rules.md", "04-scenarios.md"}
    for ref_file in sorted((ROOT / "references").glob("*.md")):
        ref_text = ref_file.read_text(encoding="utf-8")
        for target in re.findall(r"`([0-9]{2}-[a-z0-9-]+\.md)`|\]\(([0-9]{2}-[a-z0-9-]+\.md)\)", ref_text):
            fname = target[0] or target[1]
            if fname in workspace_md:
                continue
            if not (ROOT / "references" / fname).exists():
                fail(f"{ref_file.name} references non-existent file '{fname}'")

    for relative in sorted(set(re.findall(r"scripts/[A-Za-z0-9_.-]+\.(?:py|js)", text))):
        if not (ROOT / relative).exists():
            fail(f"referenced script does not exist: {relative}")

    for required in [
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "install.sh",
        "install.ps1",
        "requirements.txt",
        "scripts/browser_probes.js",
        "scripts/qa_diff.py",
        "evals/gym/server.py",
        "evals/gym/ground_truth.json",
        "evals/score_gym_run.py",
    ]:
        if not (ROOT / required).exists():
            fail(f"missing repository file: {required}")

    install_sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    install_ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
    if "*.js" not in install_sh:
        fail("install.sh must copy scripts/*.js")
    if "*.js" not in install_ps1:
        fail("install.ps1 must copy scripts\\*.js")

    print(f"References: {len(referenced)} linked files; {len(evals_data.get('evals') or [])} behavioral evals.")
    print("Skill package checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
