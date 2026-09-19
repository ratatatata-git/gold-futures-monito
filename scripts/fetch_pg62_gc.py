#!/usr/bin/env python3
"""
Fetch CME Daily Bulletin PG62 (Metals Futures Products), extract COMEX Gold
Futures (GC FUT), and write normalized JSON.

Stage 2-A:
CME PG62 PDF -> GC rows -> JSON

This intentionally runs server-side (for example in GitHub Actions), not in
the iPhone/browser. Do not put CME credentials in the frontend.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from pypdf import PdfReader

DEFAULT_URL = "https://www.cmegroup.com/daily_bulletin/current/Section62_Metals_Futures_Products.pdf"
MONTHS = r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
CONTRACT_RE = re.compile(rf"^{MONTHS}\d{{2}}$")
DATE_RE = re.compile(r"\b([A-Z][a-z]{2}),\s+([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})\b")

# Example extracted PDF row:
# DEC26 4381.60 4439.80 /4372.20 4424.90 + 25.20 141307 1612 315327 + 1194
ROW_RE = re.compile(
    rf"^(?P<contract>{MONTHS}\d{{2}})\s+"
    rf"(?P<open>\S+)\s+"
    rf"(?P<high>\S+)\s+"
    rf"(?P<low>\S+)\s+"
    rf"(?P<settlement>\S+)\s+"
    rf"(?P<price_sign>[+-]|UNCH)\s*"
    rf"(?P<price_change>\S+)\s+"
    rf"(?P<globex_volume>\S+)\s+"
    rf"(?P<pnt_volume>\S+)\s+"
    rf"(?P<open_interest>\S+)\s+"
    rf"(?P<oi_sign>[+-]|UNCH)\s*"
    rf"(?P<oi_change>\S+)$"
)


def clean_int(value: str) -> int | None:
    value = value.replace(",", "").strip()
    if value in {"----", "UNCH"}:
        return None
    return int(value)


def clean_float(value: str) -> float | None:
    value = value.replace(",", "").strip()
    if value in {"----", "UNCH"}:
        return None
    return float(value)


def signed_number(sign: str, value: str) -> float | int | None:
    if sign == "UNCH":
        return 0
    value = value.replace(",", "").strip()
    if value in {"----", "UNCH"}:
        return None
    number = float(value)
    number = number if "." in value else int(number)
    return -number if sign == "-" else number


def parse_trade_date(text: str) -> str:
    match = DATE_RE.search(text)
    if not match:
        raise ValueError("Could not find bulletin date in PG62 PDF text.")
    month = match.group(2)
    day = int(match.group(3))
    year = int(match.group(4))
    dt = datetime.strptime(f"{day} {month} {year}", "%d %b %Y")
    return dt.strftime("%Y-%m-%d")


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def fetch_pdf(url: str, destination: Path) -> None:
    response = requests.get(
        url,
        timeout=60,
        headers={"User-Agent": "Gold-Futures-Monitor/2.0"},
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "pdf" not in content_type.lower() and not response.content.startswith(b"%PDF"):
        raise ValueError(f"CME response does not look like a PDF: {content_type}")
    destination.write_bytes(response.content)


def parse_gc_rows(text: str, trade_date: str) -> list[dict[str, Any]]:
    lines = [re.sub(r"\s+", " ", line.strip()) for line in text.splitlines()]
    start = next(
        (i for i, line in enumerate(lines) if "GC FUT COMEX GOLD FUTURES" in line),
        None,
    )
    if start is None:
        raise ValueError("Could not find 'GC FUT COMEX GOLD FUTURES' in PG62.")

    rows: list[dict[str, Any]] = []
    for line in lines[start + 1 :]:
        if line.startswith("TOTAL GC FUT"):
            break

        match = ROW_RE.match(line)
        if not match:
            continue

        data = match.groupdict()
        globex_volume = clean_int(data["globex_volume"]) or 0
        pnt_volume = clean_int(data["pnt_volume"]) or 0

        # CME displays two volume columns in PG62. We expose their sum as the
        # contract's total volume, while retaining both source components.
        total_volume = globex_volume + pnt_volume

        oi_change = signed_number(data["oi_sign"], data["oi_change"])
        settlement = clean_float(data["settlement"])

        # Rows with no settlement are retained only if they have OI/volume.
        if settlement is None:
            continue

        rows.append(
            {
                "date": trade_date,
                "contract": data["contract"],
                "settlement": settlement,
                "volume": total_volume,
                "open_interest": clean_int(data["open_interest"]),
                "oi_change": oi_change,
                "is_active": False,
                "source": "CME Daily Bulletin PG62",
                "source_status": "preliminary",
                "volume_globex": globex_volume,
                "volume_pnt_pit": pnt_volume,
            }
        )

    if not rows:
        raise ValueError("GC section found, but no GC contract rows were parsed.")
    return rows


def mark_active(rows: list[dict[str, Any]]) -> None:
    """
    Stage 2-A only: mark the highest-volume GC contract as a provisional
    active contract. This is intentionally labeled provisional because the
    production roll rule should be finalized separately.
    """
    eligible = [r for r in rows if isinstance(r.get("volume"), int)]
    if not eligible:
        return
    active = max(eligible, key=lambda r: r["volume"])
    active["is_active"] = True


def build_output(rows: list[dict[str, Any]], source_url: str) -> dict[str, Any]:
    trade_date = rows[0]["date"]
    return {
        "trade_date": trade_date,
        "product": "GC",
        "exchange": "COMEX",
        "source": "CME Daily Bulletin PG62",
        "source_url": source_url,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_status": "preliminary",
        "active_contract_method": "provisional_highest_volume",
        "contracts": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/cme-gc-latest.json"))
    parser.add_argument("--keep-pdf", action="store_true")
    args = parser.parse_args()

    work_pdf = args.pdf or Path("pg62_current.pdf")

    try:
        if args.pdf:
            if not work_pdf.exists():
                raise FileNotFoundError(work_pdf)
        else:
            fetch_pdf(args.url, work_pdf)

        text = extract_pdf_text(work_pdf)
        trade_date = parse_trade_date(text)
        rows = parse_gc_rows(text, trade_date)
        mark_active(rows)
        output = build_output(rows, args.url)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        active = next((r for r in rows if r["is_active"]), None)
        print(f"OK: {len(rows)} GC contracts, trade date {trade_date}")
        if active:
            print(
                f"Provisional active: {active['contract']} "
                f"(volume {active['volume']:,})"
            )

        if not args.keep_pdf and not args.pdf:
            work_pdf.unlink(missing_ok=True)

        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
