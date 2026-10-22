#!/usr/bin/env python3
"""Create a local PG62 cell-by-cell worksheet with parser output separated from manual expected values."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader

FIELDS = (
    "contract_code",
    "open",
    "high",
    "low",
    "settlement",
    "price_change",
    "volume_globex",
    "volume_pnt_pit",
    "open_interest",
    "oi_change",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def is_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    except (ValueError, AttributeError):
        return False


def build_worksheet(
    parsed: dict[str, Any],
    *,
    source_sha256: str,
    page_count: int,
    source_url: str,
    retrieved_at: str,
) -> dict[str, Any]:
    """Build a fail-closed template; expected_raw is always blank and never copied from extraction."""
    if parsed.get("dataset") != "PG62_GC_FUTURES":
        raise ValueError("parsed dataset must be PG62_GC_FUTURES")
    trade_date = parsed.get("trade_date")
    if not isinstance(trade_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date):
        raise ValueError("parsed trade_date must be YYYY-MM-DD")
    try:
        datetime.strptime(trade_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("parsed trade_date must be a real date") from exc
    if parsed.get("bulletin", {}).get("status") != "FINAL":
        raise ValueError("cell reconciliation worksheet requires a FINAL PG62 bulletin")
    if not SHA256_RE.fullmatch(source_sha256):
        raise ValueError("source_sha256 must be lowercase SHA-256")
    if parsed.get("source", {}).get("sha256") != source_sha256:
        raise ValueError("PDF SHA-256 does not match parsed JSON source.sha256")
    if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 1:
        raise ValueError("page_count must be a positive integer")
    if not isinstance(source_url, str) or not source_url.strip():
        raise ValueError("source_url is required")
    if not is_timestamp(retrieved_at):
        raise ValueError("retrieved_at must be an ISO-8601 timestamp with timezone")
    rows = parsed.get("contracts")
    if not isinstance(rows, list) or not rows:
        raise ValueError("parsed contracts must be a non-empty list")

    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for row in rows:
        contract = row.get("contract")
        if not isinstance(contract, str) or not contract.strip():
            raise ValueError("every parsed row needs a contract code")
        if contract in seen:
            raise ValueError(f"duplicate parsed contract: {contract}")
        seen.add(contract)
        source = row.get("source")
        if not isinstance(source, dict):
            raise ValueError(f"{contract}: source locator is missing")
        page = source.get("page")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1 or page > page_count:
            raise ValueError(f"{contract}: source page is outside the PDF")
        for field in FIELDS:
            if field == "contract_code":
                extracted_raw = contract
            else:
                cell = row.get(field)
                if not isinstance(cell, dict) or not isinstance(cell.get("raw"), str):
                    raise ValueError(f"{contract}.{field}: parsed raw token is missing")
                extracted_raw = cell["raw"]
            check_id = f"pg62-{trade_date}-{contract}-{field}"
            items.append({
                "check_id": check_id,
                "page_number": page,
                "locator": f"GC FUTURES row {contract}, source cell {field}",
                "field": field,
                "expected_raw": "",
                "extracted_raw": extracted_raw,
                "independently_verified": False,
            })

    return {
        "schema_version": 1,
        "document": {
            "bulletin_type": "PG62",
            "bulletin_date": trade_date,
            "edition_status": "FINAL",
            "sha256": source_sha256,
            "page_count": page_count,
            "source_url": source_url,
            "retrieved_at": retrieved_at,
        },
        "review": {
            "reviewer": "",
            "reviewed_at": "",
            "method": "independent_manual_pdf",
        },
        "pages_reviewed": [],
        "page_review_checklist": [
            {
                "page_number": page,
                "reviewed": False,
                "review_notes": "",
                "layout_or_table_variants": "",
            }
            for page in range(1, page_count + 1)
        ],
        "items": items,
        "worksheet_status": "INCOMPLETE_REVIEW_REQUIRED",
        "instructions": [
            "This worksheet is deliberately blocked until independently reviewed.",
            "Render and inspect the original PDF. Enter expected_raw from the source PDF itself; never copy it from extracted_raw.",
            "For high and low, transcribe the two values separately into their respective expected_raw fields; preserve source markers and signs.",
            "Mark independently_verified true only after direct source inspection and record reviewer identity, timestamp, and all reviewed pages.",
            "Run scripts/validate_pdf_reconciliation.py after completing review. The untouched worksheet must fail closed.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("parsed_json", type=Path, help="JSON output from scripts/parse_pg62.py")
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--retrieved-at", required=True, help="actual retrieval timestamp with timezone")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists():
        print(f"ERROR: refusing to overwrite existing worksheet: {output}", file=sys.stderr)
        return 2
    try:
        pdf_path = args.pdf.expanduser().resolve()
        parsed = json.loads(args.parsed_json.read_text(encoding="utf-8"))
        pdf_bytes = pdf_path.read_bytes()
        digest = hashlib.sha256(pdf_bytes).hexdigest()
        reader = PdfReader(str(pdf_path), strict=True)
        if reader.is_encrypted:
            raise ValueError("encrypted PDF is not supported")
        worksheet = build_worksheet(
            parsed,
            source_sha256=digest,
            page_count=len(reader.pages),
            source_url=args.source_url,
            retrieved_at=args.retrieved_at,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(worksheet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"WORKSHEET CREATED (INCOMPLETE): {len(worksheet['items'])} cell checks; {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
