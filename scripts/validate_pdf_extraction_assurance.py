#!/usr/bin/env python3
"""Fail-closed checks for PDF token coverage, evidence independence, and definition selection.

This module validates an extraction-assurance manifest; it does not extract PDF
content or certify that a human-provided visual review is truthful. Synthetic
fixtures only should be committed to the public repository.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DISPOSITIONS = {"CELL", "EXPLICIT_IGNORE", "QUARANTINE"}
EVIDENCE_GROUPS = {"layout", "semantic", "independent_engine", "visual"}
INDEPENDENT_CORROBORATION = {"semantic", "independent_engine", "visual"}


def validate_assignment_coverage(tokens: Any, assignments: Any) -> list[str]:
    """Every observed token must be assigned exactly once or explicitly dispositioned."""
    issues: list[str] = []
    if not isinstance(tokens, list):
        return ["tokens must be an array"]
    if not isinstance(assignments, list):
        return ["assignments must be an array"]

    token_ids: list[str] = []
    for i, token in enumerate(tokens):
        if not isinstance(token, dict) or not isinstance(token.get("token_id"), str) or not token["token_id"].strip():
            issues.append(f"tokens[{i}].token_id is required")
            continue
        token_ids.append(token["token_id"])
    if len(token_ids) != len(set(token_ids)):
        issues.append("token inventory contains duplicate token_id values")
    known = set(token_ids)
    assigned: dict[str, int] = {}
    for i, item in enumerate(assignments):
        prefix = f"assignments[{i}]"
        if not isinstance(item, dict):
            issues.append(f"{prefix} must be an object")
            continue
        token_id = item.get("token_id")
        if not isinstance(token_id, str) or not token_id.strip():
            issues.append(f"{prefix}.token_id is required")
            continue
        if token_id not in known:
            issues.append(f"{prefix} references unknown token_id {token_id}")
        assigned[token_id] = assigned.get(token_id, 0) + 1
        disposition = item.get("disposition")
        if disposition not in DISPOSITIONS:
            issues.append(f"{prefix}.disposition must be one of {sorted(DISPOSITIONS)}")
        if disposition == "CELL":
            if not isinstance(item.get("cell_id"), str) or not item["cell_id"].strip():
                issues.append(f"{prefix}.cell_id is required for CELL")
            if item.get("reason") not in (None, ""):
                issues.append(f"{prefix}.reason must be omitted for CELL")
        elif disposition in {"EXPLICIT_IGNORE", "QUARANTINE"}:
            if not isinstance(item.get("reason"), str) or not item["reason"].strip():
                issues.append(f"{prefix}.reason is required for {disposition}")
            if item.get("cell_id") not in (None, ""):
                issues.append(f"{prefix}.cell_id must be omitted for {disposition}")
            if disposition == "QUARANTINE":
                issues.append(f"{prefix} token {token_id} is quarantined; promotion is blocked")
    for token_id in token_ids:
        count = assigned.get(token_id, 0)
        if count == 0:
            issues.append(f"token {token_id} is unassigned")
        elif count > 1:
            issues.append(f"token {token_id} is assigned {count} times")
    return issues


def validate_cell_evidence(cells: Any) -> list[str]:
    """Require >=2 distinct grounds and at least one corroboration independent of layout."""
    issues: list[str] = []
    if not isinstance(cells, list) or not cells:
        return ["cells must be a non-empty array"]
    seen: set[str] = set()
    for i, cell in enumerate(cells):
        prefix = f"cells[{i}]"
        if not isinstance(cell, dict):
            issues.append(f"{prefix} must be an object")
            continue
        cell_id = cell.get("cell_id")
        if not isinstance(cell_id, str) or not cell_id.strip():
            issues.append(f"{prefix}.cell_id is required")
        elif cell_id in seen:
            issues.append(f"duplicate cell_id: {cell_id}")
        else:
            seen.add(cell_id)
        if cell.get("value_status") not in {"RESOLVED", "UNRESOLVED"}:
            issues.append(f"{prefix}.value_status must be RESOLVED or UNRESOLVED")
        evidence = cell.get("evidence")
        if not isinstance(evidence, list):
            issues.append(f"{prefix}.evidence must be an array")
            continue
        groups: set[str] = set()
        for j, item in enumerate(evidence):
            ep = f"{prefix}.evidence[{j}]"
            if not isinstance(item, dict):
                issues.append(f"{ep} must be an object")
                continue
            group = item.get("group")
            if group not in EVIDENCE_GROUPS:
                issues.append(f"{ep}.group must be one of {sorted(EVIDENCE_GROUPS)}")
            else:
                groups.add(group)
            if not isinstance(item.get("reference"), str) or not item["reference"].strip():
                issues.append(f"{ep}.reference is required")
            if not isinstance(item.get("result"), str) or not item["result"].strip():
                issues.append(f"{ep}.result is required")
        if len(groups) < 2:
            issues.append(f"{prefix} needs at least two distinct evidence groups")
        if not groups.intersection(INDEPENDENT_CORROBORATION):
            issues.append(f"{prefix} needs independent corroboration beyond layout evidence")
        if cell.get("value_status") == "UNRESOLVED" and cell.get("publishable") is True:
            issues.append(f"{prefix} UNRESOLVED values cannot be publishable")
        if cell.get("value_status") == "RESOLVED" and cell.get("publishable") is True:
            if len(groups) < 2 or not groups.intersection(INDEPENDENT_CORROBORATION):
                issues.append(f"{prefix} publishable value lacks independent evidence")
    return issues


def select_definition(fingerprint: Any, definitions: Any) -> tuple[str | None, list[str]]:
    """Select exactly one definition by a complete structural fingerprint; fail closed."""
    issues: list[str] = []
    if not isinstance(fingerprint, dict) or not fingerprint:
        return None, ["document fingerprint must be a non-empty object"]
    if not isinstance(definitions, list):
        return None, ["definitions must be an array"]
    matches: list[str] = []
    for i, definition in enumerate(definitions):
        if not isinstance(definition, dict):
            issues.append(f"definitions[{i}] must be an object")
            continue
        definition_id = definition.get("definition_id")
        expected = definition.get("fingerprint")
        if not isinstance(definition_id, str) or not definition_id.strip():
            issues.append(f"definitions[{i}].definition_id is required")
            continue
        if not isinstance(expected, dict) or not expected:
            issues.append(f"definitions[{i}].fingerprint must be a non-empty object")
            continue
        if expected == fingerprint:
            matches.append(definition_id)
    if len(matches) == 0:
        issues.append("definition selection matched zero definitions; fail closed")
        return None, issues
    if len(matches) > 1:
        issues.append(f"definition selection matched multiple definitions: {matches}; fail closed")
        return None, issues
    return matches[0], issues


def inspect_manifest(manifest: Any) -> dict[str, Any]:
    issues: list[str] = []
    if not isinstance(manifest, dict):
        return {"gate": "BLOCKED", "issues": ["manifest root must be an object"]}
    if manifest.get("schema_version") != 1:
        issues.append("schema_version must be 1")
    source = manifest.get("source")
    if not isinstance(source, dict):
        issues.append("source must be an object")
        source = {}
    if not isinstance(source.get("sha256"), str) or not SHA256_RE.fullmatch(source["sha256"]):
        issues.append("source.sha256 must be a lowercase 64-character SHA-256")
    if isinstance(source.get("page_count"), bool) or not isinstance(source.get("page_count"), int) or source["page_count"] < 1:
        issues.append("source.page_count must be a positive integer")

    selected, selection_issues = select_definition(manifest.get("fingerprint"), manifest.get("definitions"))
    issues.extend(selection_issues)
    tokens = manifest.get("tokens")
    assignments = manifest.get("assignments")
    issues.extend(validate_assignment_coverage(tokens, assignments))
    cells = manifest.get("cells")
    issues.extend(validate_cell_evidence(cells))

    if isinstance(cells, list):
        cell_ids = {
            cell.get("cell_id") for cell in cells
            if isinstance(cell, dict) and isinstance(cell.get("cell_id"), str)
        }
        if isinstance(assignments, list):
            for i, item in enumerate(assignments):
                if isinstance(item, dict) and item.get("disposition") == "CELL":
                    if item.get("cell_id") not in cell_ids:
                        issues.append(f"assignments[{i}] references cell_id absent from cells: {item.get('cell_id')}")

    return {
        "gate": "PASS" if not issues else "BLOCKED",
        "selected_definition": selected,
        "token_count": len(tokens) if isinstance(tokens, list) else 0,
        "assignment_count": len(assignments) if isinstance(assignments, list) else 0,
        "cell_count": len(cells) if isinstance(cells, list) else 0,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="path to a local extraction-assurance JSON manifest")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read valid JSON manifest: {exc}", file=sys.stderr)
        return 2
    summary = inspect_manifest(manifest)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
