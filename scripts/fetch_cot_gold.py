#!/usr/bin/env python3
"""Fetch COMEX Gold CFTC Disaggregated Futures-Only COT history.

The script stores the exact API response by SHA-256 and maintains an
idempotent JSON history keyed by report date, contract market code, and market
name. It does not calculate net positioning or infer trader intent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "cot"
HISTORY_PATH = DATA_DIR / "gold-disaggregated-futures-only.json"
RAW_DIR = DATA_DIR / "raw"
DATASET_ID = "72hh-3qpy"  # CFTC Disaggregated - Futures Only
CONTRACT_MARKET_CODE = "088691"  # COMEX Gold; validate returned market names too.
SOURCE_BASE = f"https://publicreporting.cftc.gov/resource/{DATASET_ID}.json"
USER_AGENT = "Gold-Futures-Monitor/1.0 (CFTC COT history ingestion)"
LIMIT = 50000


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def source_url() -> str:
    query = {
        "$where": f"cftc_contract_market_code='{CONTRACT_MARKET_CODE}'",
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$limit": str(LIMIT),
    }
    return f"{SOURCE_BASE}?{urlencode(query)}"


def fetch_payload(url: str, timeout: int = 45) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"CFTC API request failed: {exc}") from exc
    if not payload:
        raise RuntimeError("CFTC API returned an empty response.")
    return payload


def validate_records(payload: bytes) -> list[dict[str, Any]]:
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("CFTC API response is not valid JSON.") from exc
    if not isinstance(decoded, list) or not decoded:
        raise ValueError("CFTC API returned no rows; refusing to replace history.")
    required = {
        "report_date_as_yyyy_mm_dd",
        "cftc_contract_market_code",
        "market_and_exchange_names",
        "open_interest_all",
    }
    records: list[dict[str, Any]] = []
    for index, row in enumerate(decoded):
        if not isinstance(row, dict) or not required.issubset(row):
            raise ValueError(f"CFTC row {index} is missing required identity/data fields.")
        if row["cftc_contract_market_code"] != CONTRACT_MARKET_CODE:
            raise ValueError(f"Unexpected contract market code in row {index}.")
        market_name = str(row["market_and_exchange_names"]).upper()
        if "GOLD" not in market_name or "COMMODITY EXCHANGE" not in market_name:
            raise ValueError(f"Unexpected market name in row {index}: {market_name!r}")
        date_value = str(row["report_date_as_yyyy_mm_dd"])[:10]
        try:
            datetime.strptime(date_value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"Invalid COT report date in row {index}: {date_value!r}") from exc
        # Preserve the original API row and all source tokens without coercion.
        records.append(row)
    keys = [record_key(row) for row in records]
    if len(keys) != len(set(keys)):
        raise ValueError("CFTC response contains duplicate report-date/market keys.")
    return records


def record_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row["report_date_as_yyyy_mm_dd"])[:10],
        str(row["cftc_contract_market_code"]),
        str(row["market_and_exchange_names"]),
    )


def load_history(path: Path = HISTORY_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": 1,
            "source": "CFTC Public Reporting Environment",
            "dataset_id": DATASET_ID,
            "report_type": "Disaggregated Futures Only",
            "contract_market_code": CONTRACT_MARKET_CODE,
            "records": [],
            "snapshots": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Existing history cannot be read safely: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError("Existing COT history has an unsupported structure.")
    return data


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def ingest(payload: bytes, retrieved_at: str, history_path: Path = HISTORY_PATH,
           raw_dir: Path = RAW_DIR) -> dict[str, Any]:
    incoming = validate_records(payload)
    digest = hashlib.sha256(payload).hexdigest()
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{digest}.json"
    if not raw_path.exists():
        raw_path.write_bytes(payload)

    history = load_history(history_path)
    existing: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in history["records"]:
        if not isinstance(row, dict):
            raise ValueError("Existing COT history contains a malformed record.")
        existing[record_key(row)] = row

    added = 0
    revised = 0
    for row in incoming:
        key = record_key(row)
        previous = existing.get(key)
        if previous is None:
            added += 1
        elif previous != row:
            revised += 1
        # Upsert allows official corrections to be reflected while the raw
        # snapshot archive preserves the exact earlier source response.
        existing[key] = row

    history["records"] = [
        existing[key] for key in sorted(existing, key=lambda item: item[0])
    ]
    history.setdefault("snapshots", []).append({
        "retrieved_at": retrieved_at,
        "source_url": source_url(),
        "sha256": digest,
        "raw_archive": str(raw_path.relative_to(ROOT)) if raw_path.is_relative_to(ROOT) else str(raw_path),
        "rows_in_response": len(incoming),
        "rows_added": added,
        "rows_revised": revised,
    })
    history["last_retrieved_at"] = retrieved_at
    history["last_source_sha256"] = digest
    atomic_write_json(history_path, history)
    return {
        "response_rows": len(incoming),
        "latest_report_date": max(str(row["report_date_as_yyyy_mm_dd"])[:10] for row in incoming),
        "history_rows": len(history["records"]),
        "rows_added": added,
        "rows_revised": revised,
        "sha256": digest,
        "history_path": str(history_path),
        "raw_archive": str(raw_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=45, help="HTTP timeout in seconds")
    args = parser.parse_args()
    retrieved_at = utc_now()
    url = source_url()
    try:
        payload = fetch_payload(url, timeout=args.timeout)
        result = ingest(payload, retrieved_at)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
