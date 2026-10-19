#!/usr/bin/env python3
"""Validate the structural contract of the PDF semantic definition master."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

FIELD_TYPES = {"string", "decimal_string", "signed_decimal_string", "integer_string", "signed_integer_string"}
STATES = {"VALUE", "SOURCE_NULL", "UNRESOLVED"}


def validate(master: Any) -> dict[str, Any]:
    issues: list[str] = []
    if not isinstance(master, dict):
        return {"gate": "BLOCKED", "issues": ["master must be a JSON object"]}
    if master.get("schema_version") != 1:
        issues.append("schema_version must be 1")
    if not isinstance(master.get("master_id"), str) or not master["master_id"].strip():
        issues.append("master_id is required")
    if not isinstance(master.get("master_version"), str) or not master["master_version"].strip():
        issues.append("master_version is required")
    if master.get("status") not in {"DRAFT_NOT_FOR_PRODUCTION", "REVIEWED", "APPROVED"}:
        issues.append("status must be DRAFT_NOT_FOR_PRODUCTION, REVIEWED, or APPROVED")

    for collection_name, id_key in (("layout_profiles", "profile_id"), ("field_definitions", "field_id"),
                                    ("raw_value_rules", "rule_id"), ("normalization_rules", "rule_id")):
        items = master.get(collection_name)
        if not isinstance(items, list):
            issues.append(f"{collection_name} must be an array")
            continue
        seen: set[str] = set()
        for i, item in enumerate(items):
            prefix = f"{collection_name}[{i}]"
            if not isinstance(item, dict):
                issues.append(f"{prefix} must be an object")
                continue
            item_id = item.get(id_key)
            if not isinstance(item_id, str) or not item_id.strip():
                issues.append(f"{prefix}.{id_key} is required")
            elif item_id in seen:
                issues.append(f"duplicate {id_key}: {item_id}")
            else:
                seen.add(item_id)
            if collection_name == "field_definitions":
                if item.get("data_type") not in FIELD_TYPES:
                    issues.append(f"{prefix}.data_type is unsupported")
                if not isinstance(item.get("allowed_states"), list) or not item["allowed_states"]:
                    issues.append(f"{prefix}.allowed_states must be a non-empty array")
                elif any(state not in STATES for state in item["allowed_states"]):
                    issues.append(f"{prefix}.allowed_states contains an unknown state")
                if not isinstance(item.get("publishable_when"), list):
                    issues.append(f"{prefix}.publishable_when must be an array")
                elif any(state not in (item.get("allowed_states") or []) for state in item["publishable_when"]):
                    issues.append(f"{prefix}.publishable_when contains a state not allowed by the field")
                if item.get("status") not in {"DRAFT", "REVIEWED", "APPROVED"}:
                    issues.append(f"{prefix}.status is invalid")
            elif collection_name == "layout_profiles":
                if item.get("status") not in {"DRAFT_UNVERIFIED", "DIAGNOSTIC_ONLY", "REVIEWED", "APPROVED"}:
                    issues.append(f"{prefix}.status is invalid")
                if not isinstance(item.get("fingerprint"), dict):
                    issues.append(f"{prefix}.fingerprint must be an object")
            elif collection_name in {"raw_value_rules", "normalization_rules"}:
                if item.get("status") not in {"DRAFT", "UNRESOLVED", "APPROVED_PRINCIPLE", "REVIEWED", "APPROVED"}:
                    issues.append(f"{prefix}.status is invalid")

    policy = master.get("evidence_policy")
    if not isinstance(policy, dict):
        issues.append("evidence_policy is required")
    else:
        if policy.get("minimum_distinct_evidence_groups_per_cell", 0) < 2:
            issues.append("minimum_distinct_evidence_groups_per_cell must be at least 2")
        if policy.get("layout_definition_alone_is_independent_evidence") is not False:
            issues.append("layout_definition_alone_is_independent_evidence must be false")
        if policy.get("quarantine_blocks_promotion") is not True:
            issues.append("quarantine_blocks_promotion must be true")
        expected = {"CELL", "EXPLICIT_IGNORE_WITH_REASON", "QUARANTINE"}
        if set(policy.get("all_tokens_must_have_exactly_one_disposition", [])) != expected:
            issues.append("token disposition policy must cover CELL, EXPLICIT_IGNORE_WITH_REASON, and QUARANTINE")

    for profile in master.get("layout_profiles", []) if isinstance(master.get("layout_profiles"), list) else []:
        if isinstance(profile, dict) and profile.get("status") == "APPROVED":
            fp = profile.get("fingerprint", {})
            if not isinstance(fp, dict) or not fp.get("required_header_tokens") or not fp.get("header_fingerprint_sha256"):
                issues.append(f"approved profile {profile.get('profile_id')} has incomplete fingerprint")
            if not fp.get("page_size_profile") or fp.get("page_count") is None:
                issues.append(f"approved profile {profile.get('profile_id')} lacks page geometry/count evidence")

    return {"gate": "PASS" if not issues else "BLOCKED", "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("master", nargs="?", type=Path,
                        default=Path("data/definitions/pdf-field-master.json"))
    args = parser.parse_args()
    try:
        master = json.loads(args.master.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read master JSON: {exc}", file=sys.stderr)
        return 2
    result = validate(master)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
