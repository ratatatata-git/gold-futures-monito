#!/usr/bin/env python3
"""Validate locally generated COT/FRED JSON against the dashboard's data contract.

This tool is read-only. Missing files are reported as skipped so it can be run
before data generation; pass --require-files to make missing files an error.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COT_PATH = ROOT / "data/cot/gold-disaggregated-futures-only.json"
FRED_PATH = ROOT / "data/fred/gold-macro-context.json"
FRED_SERIES = ("DFII10", "DGS10", "DTWEXBGS")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def valid_date(value: Any) -> bool:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path.relative_to(ROOT)}: cannot read valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)}: root must be a JSON object")
    return value


def validate_cot(path: Path = COT_PATH) -> int:
    data = read_json(path)
    records = data.get("records")
    if data.get("schema_version") != 1:
        raise ValueError("COT schema_version must be 1")
    if not isinstance(records, list) or not records:
        raise ValueError("COT records must be a non-empty array")
    dates = []
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            raise ValueError(f"COT records[{index}] must be an object")
        date = str(row.get("report_date_as_yyyy_mm_dd", ""))[:10]
        if not valid_date(date):
            raise ValueError(f"COT records[{index}] has an invalid report date")
        if row.get("cftc_contract_market_code") != "088691":
            raise ValueError(f"COT records[{index}] has unexpected contract market code")
        market = str(row.get("market_and_exchange_names", "")).upper()
        if "GOLD" not in market or "COMMODITY EXCHANGE" not in market:
            raise ValueError(f"COT records[{index}] is not identified as COMEX Gold")
        for field in ("m_money_positions_long_all", "m_money_positions_short_all"):
            value = row.get(field)
            if value is None or value == "":
                continue
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"COT records[{index}].{field} is not numeric") from exc
            if not math.isfinite(number):
                raise ValueError(f"COT records[{index}].{field} is not finite")
        dates.append(date)
    if dates != sorted(dates):
        raise ValueError("COT records must be sorted by report date")
    return len(records)


def validate_fred(path: Path = FRED_PATH) -> int:
    data = read_json(path)
    records = data.get("records")
    if data.get("schema_version") != 1:
        raise ValueError("FRED schema_version must be 1")
    if not isinstance(records, list) or not records:
        raise ValueError("FRED records must be a non-empty array")
    dates = []
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            raise ValueError(f"FRED records[{index}] must be an object")
        date = row.get("observation_date")
        if not valid_date(date):
            raise ValueError(f"FRED records[{index}] has an invalid observation date")
        values = row.get("values")
        raw_values = row.get("raw_values")
        if not isinstance(values, dict) or not isinstance(raw_values, dict):
            raise ValueError(f"FRED records[{index}] must contain values and raw_values objects")
        for series in FRED_SERIES:
            if series not in values or series not in raw_values:
                raise ValueError(f"FRED records[{index}] is missing {series}")
            value = values[series]
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f"FRED records[{index}].values.{series} must be finite numeric or null")
            if not isinstance(raw_values[series], str):
                raise ValueError(f"FRED records[{index}].raw_values.{series} must be a string")
        dates.append(date)
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValueError("FRED records must be sorted by unique observation date")
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-files", action="store_true",
                        help="fail if either generated history file is missing")
    args = parser.parse_args()
    errors = []
    skipped = []
    for label, path, validator in (
        ("COT", COT_PATH, validate_cot),
        ("FRED", FRED_PATH, validate_fred),
    ):
        if not path.exists():
            message = f"{label}: not present ({path.relative_to(ROOT)})"
            if args.require_files:
                errors.append(message)
            else:
                skipped.append(message)
            continue
        try:
            count = validator(path)
            print(f"OK {label}: {count} records ({path.relative_to(ROOT)})")
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
    for message in skipped:
        print(f"SKIP {message}")
    for message in errors:
        print(f"ERROR {message}", file=sys.stderr)
    if errors:
        return 1
    if skipped:
        print("Validation incomplete: generate local data or pass --require-files for a strict check.")
    else:
        print("All dashboard data files passed validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
