#!/usr/bin/env python3
"""Fetch selected FRED macro context series as auditable CSV history.

Uses FRED's public graph CSV endpoint (no API key). Missing observations stay
null; the script does not forward-fill, interpolate, or make trading signals.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "fred"
HISTORY_PATH = DATA_DIR / "gold-macro-context.json"
RAW_DIR = DATA_DIR / "raw"
SOURCE_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SERIES = {
    "DFII10": "Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity, Inflation-Indexed",
    "DGS10": "Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity",
    "DTWEXBGS": "Nominal Broad U.S. Dollar Index",
}
USER_AGENT = "GoldFuturesMonitor/0.1 (read-only data ingestion)"


def parse_csv(payload: bytes, expected_series: tuple[str, ...] = tuple(SERIES)) -> list[dict]:
    try:
        text = payload.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or "observation_date" not in reader.fieldnames:
            raise ValueError("CSV missing observation_date column")
        missing = set(expected_series) - set(reader.fieldnames)
        if missing:
            raise ValueError("CSV missing expected series columns: " + ", ".join(sorted(missing)))
        records = []
        seen = set()
        for row in reader:
            date = (row.get("observation_date") or "").strip()
            if not date:
                raise ValueError("CSV row has empty observation_date")
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError(f"Invalid observation date: {date}") from exc
            if date in seen:
                raise ValueError(f"Duplicate observation date: {date}")
            seen.add(date)
            values = {}
            for series_id in expected_series:
                raw = (row.get(series_id) or "").strip()
                if raw in ("", "."):
                    values[series_id] = None
                else:
                    try:
                        value = float(raw)
                    except ValueError as exc:
                        raise ValueError(f"Invalid {series_id} value on {date}: {raw}") from exc
                    if value != value or value in (float("inf"), float("-inf")):
                        raise ValueError(f"Non-finite {series_id} value on {date}")
                    values[series_id] = value
            records.append({"observation_date": date, "values": values, "raw_values": {
                series_id: (row.get(series_id) or "").strip() for series_id in expected_series
            }})
        if not records:
            raise ValueError("CSV contains no observations")
        return sorted(records, key=lambda row: row["observation_date"])
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError(f"Unable to parse FRED CSV: {exc}") from exc


def load_history(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "series": SERIES, "records": [], "retrievals": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read existing history {path}: {exc}") from exc
    if not isinstance(data.get("records"), list) or not isinstance(data.get("retrievals"), list):
        raise ValueError("Existing FRED history has an invalid schema")
    return data


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def ingest(payload: bytes, history_path: Path = HISTORY_PATH, raw_dir: Path = RAW_DIR,
           retrieved_at: str | None = None) -> dict:
    records = parse_csv(payload)
    digest = hashlib.sha256(payload).hexdigest()
    retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat()
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{digest}.csv"
    if not raw_path.exists():
        atomic_write(raw_path, payload)

    history = load_history(history_path)
    previous = {row["observation_date"]: row for row in history["records"]}
    added = revised = 0
    for parsed in records:
        date = parsed["observation_date"]
        old = previous.get(date)
        record = {
            "observation_date": date,
            "values": parsed["values"],
            "raw_values": parsed["raw_values"],
            "source": "FRED graph CSV",
            "source_url": SOURCE_BASE,
            "retrieved_at": retrieved_at,
            "payload_sha256": digest,
            "raw_archive_path": str(raw_path.relative_to(ROOT)) if raw_path.is_relative_to(ROOT) else str(raw_path),
        }
        if old is None:
            added += 1
        elif old.get("values") != record["values"] or old.get("raw_values") != record["raw_values"]:
            revised += 1
        else:
            # Keep the newest provenance for identical source observations.
            pass
        previous[date] = record

    history["schema_version"] = 1
    history["series"] = SERIES
    history["records"] = [previous[key] for key in sorted(previous)]
    history.setdefault("retrievals", []).append({
        "retrieved_at": retrieved_at,
        "source_url": SOURCE_BASE,
        "payload_sha256": digest,
        "response_rows": len(records),
        "rows_added": added,
        "rows_revised": revised,
        "latest_observation_date": records[-1]["observation_date"],
        "raw_archive_path": str(raw_path.relative_to(ROOT)) if raw_path.is_relative_to(ROOT) else str(raw_path),
    })
    atomic_write(history_path, (json.dumps(history, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return history["retrievals"][-1]


def fetch_payload() -> bytes:
    url = SOURCE_BASE + "?id=" + ",".join(SERIES)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv"})
    try:
        with urlopen(request, timeout=45) as response:
            if response.status != 200:
                raise RuntimeError(f"FRED HTTP {response.status}")
            payload = response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"FRED request failed: {exc}") from exc
    if not payload:
        raise RuntimeError("FRED returned an empty response")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fetch and validate without writing local history")
    args = parser.parse_args()
    try:
        payload = fetch_payload()
        records = parse_csv(payload)
        if args.check:
            print(json.dumps({
                "status": "ok",
                "response_rows": len(records),
                "latest_observation_date": records[-1]["observation_date"],
                "payload_sha256": hashlib.sha256(payload).hexdigest(),
                "series": list(SERIES),
            }, indent=2))
        else:
            print(json.dumps(ingest(payload), indent=2))
        return 0
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
