#!/usr/bin/env python3
"""Validate independently sourced PDF value identities using exact decimal arithmetic."""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

IDENTITIES = {
    "SETTLEMENT_CHANGE": ("current_settlement", "previous_settlement", "reported_change"),
    "OPEN_INTEREST_CHANGE": ("current_open_interest", "previous_open_interest", "reported_change"),
}


def inspect_identities(records: Any) -> dict[str, Any]:
    issues: list[str] = []
    checked = 0
    not_applicable = 0
    unresolved = 0
    if not isinstance(records, list) or not records:
        return {"gate": "BLOCKED", "issues": ["identities must be a non-empty array"]}
    ids: set[str] = set()
    for i, record in enumerate(records):
        prefix = f"identities[{i}]"
        if not isinstance(record, dict):
            issues.append(f"{prefix} must be an object")
            continue
        record_id = record.get("check_id")
        if not isinstance(record_id, str) or not record_id.strip():
            issues.append(f"{prefix}.check_id is required")
        elif record_id in ids:
            issues.append(f"duplicate check_id: {record_id}")
        else:
            ids.add(record_id)
        kind = record.get("kind")
        if kind not in IDENTITIES:
            issues.append(f"{prefix}.kind must be one of {sorted(IDENTITIES)}")
            continue
        status = record.get("status")
        if status == "NOT_APPLICABLE":
            if not isinstance(record.get("reason"), str) or not record["reason"].strip():
                issues.append(f"{prefix}.reason is required for NOT_APPLICABLE")
            else:
                not_applicable += 1
            continue
        if status == "UNRESOLVED":
            unresolved += 1
            issues.append(f"{prefix} identity is UNRESOLVED; promotion is blocked")
            continue
        if status != "CHECKED":
            issues.append(f"{prefix}.status must be CHECKED, NOT_APPLICABLE, or UNRESOLVED")
            continue
        values = {key: record.get(key) for key in IDENTITIES[kind]}
        parsed: dict[str, Decimal] = {}
        for key, value in values.items():
            if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
                issues.append(f"{prefix}.{key} must be a decimal string or integer")
                continue
            try:
                parsed[key] = Decimal(str(value).replace(",", ""))
            except InvalidOperation:
                issues.append(f"{prefix}.{key} is not a valid decimal")
        if len(parsed) != 3:
            continue
        if not all(v.is_finite() for v in parsed.values()):
            issues.append(f"{prefix} values must be finite")
            continue
        current_key, previous_key, change_key = IDENTITIES[kind]
        calculated = parsed[current_key] - parsed[previous_key]
        if calculated != parsed[change_key]:
            issues.append(
                f"{prefix} identity mismatch: {current_key} - {previous_key} = "
                f"{calculated}, but {change_key} = {parsed[change_key]}"
            )
        else:
            checked += 1
    return {
        "gate": "PASS" if not issues else "BLOCKED",
        "checked": checked,
        "not_applicable": not_applicable,
        "unresolved": unresolved,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="local JSON with independently sourced identity records")
    args = parser.parse_args()
    try:
        payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read valid JSON: {exc}", file=sys.stderr)
        return 2
    result = inspect_identities(payload.get("identities") if isinstance(payload, dict) else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
