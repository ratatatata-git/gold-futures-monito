#!/usr/bin/env python3
"""Run real-PDF parser/provenance smoke checks over the 2026 month boundary."""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from test_live_comex_pdfs import run_pg62, run_pg64


def dates_between(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("end date must be on or after start date")
    dates: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2026-09-29", help="inclusive YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-10-09", help="inclusive YYYY-MM-DD")
    args = parser.parse_args()
    try:
        start, end = date.fromisoformat(args.start_date), date.fromisoformat(args.end_date)
        dates = dates_between(start, end)
        if not dates:
            raise ValueError("range contains no weekdays")
        retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        results: list[dict] = []
        for day in dates:
            stamp = day.isoformat()
            paths = {
                "PG62": ROOT / "data" / "cme-pg62" / f"PG62_{stamp}.pdf",
                "PG64": ROOT / "data" / "cme-pg64" / f"PG64_{stamp}.pdf",
            }
            for kind, path in paths.items():
                if not path.is_file():
                    raise FileNotFoundError(f"missing expected {kind} source for {stamp}: {path.relative_to(ROOT)}")
            pg62 = run_pg62(paths["PG62"], retrieved_at)
            pg64 = run_pg64(paths["PG64"], retrieved_at)
            for result in (pg62, pg64):
                if result["date"] != stamp:
                    raise ValueError(f"{result['type']} filename/date mismatch: expected {stamp}, got {result['date']}")
                if result["edition"] != "FINAL":
                    raise ValueError(f"{result['type']} {stamp} edition is {result['edition']}, not FINAL")
                if result["provenance_status"] != "PROVENANCE_MATCH":
                    raise ValueError(f"{result['type']} {stamp} provenance did not match")
                results.append(result)
    except Exception as exc:
        print(f"MONTH-BOUNDARY PDF RANGE TEST FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"MONTH-BOUNDARY PDF RANGE TEST: PASS ({len(dates)} dates, {len(results)} PDFs)")
    for result in results:
        print(
            f"{result['type']} date={result['date']} edition={result['edition']} "
            f"pages={result['pages']} sha256={result['sha256']} "
            f"parser={result['parser_status']} provenance={result['provenance_status']} "
            "accuracy_review=NOT_INDEPENDENTLY_RECONCILED"
        )
    print("Scope: date coverage, FINAL/date identity, parser smoke and provenance only; not cell-by-cell accuracy certification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
