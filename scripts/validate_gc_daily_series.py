#!/usr/bin/env python3
"""Validate PG62 GC day-over-day settlement and open-interest identities.

This is a local quality gate, not a source-accuracy or publication-rights approval.
Only FINAL observations are eligible. Missing/ambiguous prior values remain
NOT_CHECKED and prevent an all-clear result.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

FIELDS = {
    "SETTLEMENT_CHANGE": ("settlement", "price_change"),
    "OPEN_INTEREST_CHANGE": ("open_interest", "oi_change"),
}


def decimal_value(row: dict[str, Any], field: str) -> Decimal | None:
    value = row.get(field)
    if isinstance(value, dict):
        if value.get("state") != "VALUE":
            return None
        value = value.get("value")
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if value in {"", "----", "UNCH", "—", "-"}:
            return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def final_observations(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("root must be an object")
    rows = payload.get("observations")
    if not isinstance(rows, list) or not rows:
        raise ValueError("observations must be a non-empty array")
    result = []
    keys = set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"observations[{i}] must be an object")
        if row.get("source_status") not in {"FINAL", "PRELIMINARY"}:
            raise ValueError(f"observations[{i}] has unknown source_status")
        date, contract = row.get("date"), row.get("contract")
        if not isinstance(date, str) or len(date) != 10 or not isinstance(contract, str) or not contract:
            raise ValueError(f"observations[{i}] requires date and contract")
        if row["source_status"] != "FINAL":
            continue
        key = (date, contract)
        if key in keys:
            raise ValueError(f"duplicate FINAL observation for {date} {contract}")
        keys.add(key)
        result.append(row)
    if not result:
        raise ValueError("no FINAL observations available")
    return sorted(result, key=lambda r: (r["date"], r["contract"]))


def inspect_series(payload: Any) -> dict[str, Any]:
    rows = final_observations(payload)
    dates = sorted({row["date"] for row in rows})
    by_key = {(row["date"], row["contract"]): row for row in rows}
    prior_date = {dates[i]: dates[i - 1] if i else None for i in range(len(dates))}
    checks: list[dict[str, Any]] = []
    for row in rows:
        date, contract = row["date"], row["contract"]
        previous = prior_date[date]
        for kind, (level_field, change_field) in FIELDS.items():
            check = {
                "check_id": f"{date}:{contract}:{kind}",
                "date": date,
                "contract": contract,
                "kind": kind,
                "status": "NOT_CHECKED",
                "reason": None,
            }
            if previous is None:
                check["reason"] = "no earlier FINAL bulletin in supplied history"
                checks.append(check)
                continue
            old = by_key.get((previous, contract))
            if old is None:
                check["reason"] = f"contract absent from previous FINAL bulletin {previous}"
                checks.append(check)
                continue
            current_value = decimal_value(row, level_field)
            previous_value = decimal_value(old, level_field)
            reported = decimal_value(row, change_field)
            if current_value is None or previous_value is None or reported is None:
                check["reason"] = "one or more source values are null or unresolved"
                checks.append(check)
                continue
            calculated = current_value - previous_value
            check.update({
                "status": "CHECKED" if calculated == reported else "MISMATCH",
                "previous_date": previous,
                "current_value": str(current_value),
                "previous_value": str(previous_value),
                "calculated_change": str(calculated),
                "reported_change": str(reported),
            })
            if check["status"] == "MISMATCH":
                check["reason"] = "day-over-day arithmetic identity failed"
            checks.append(check)

    mismatches = sum(c["status"] == "MISMATCH" for c in checks)
    unchecked = sum(c["status"] == "NOT_CHECKED" for c in checks)
    checked = sum(c["status"] == "CHECKED" for c in checks)
    gate = "BLOCKED" if mismatches else ("INCOMPLETE" if unchecked else "PASS")
    return {
        "schema_version": 1,
        "dataset": "PG62_GC_FUTURES",
        "gate": gate,
        "final_dates": dates,
        "counts": {"checked": checked, "not_checked": unchecked, "mismatches": mismatches},
        "checks": checks,
        "limitations": [
            "Arithmetic consistency does not prove source extraction accuracy.",
            "Only FINAL rows are checked; PRELIMINARY rows are excluded.",
            "The first available date and contracts without a prior-day row remain NOT_CHECKED.",
            "This report does not approve storage, redistribution, or publication rights."
        ]
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path, help="local PG62 MASTER/history JSON")
    parser.add_argument("--output", type=Path, help="optional local report JSON")
    args = parser.parse_args()
    try:
        payload = json.loads(args.history.read_text(encoding="utf-8"))
        report = inspect_series(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.output.with_suffix(args.output.suffix + ".tmp")
        tmp.write_text(text + "\n", encoding="utf-8")
        tmp.replace(args.output)
    return 0 if report["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
