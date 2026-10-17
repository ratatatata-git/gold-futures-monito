#!/usr/bin/env python3
"""Create a local, deliberately blocked manual-review worksheet for a PG62/PG64 PDF."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from pypdf import PdfReader

EDITION_CHOICES = ("PRELIMINARY", "FINAL", "REVISED", "UNCLASSIFIED", "CONFLICTING_EVIDENCE")
def is_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    except (ValueError, AttributeError):
        return False


def build_worksheet(
    pdf_path: Path,
    *,
    bulletin_type: str,
    bulletin_date: str,
    edition_status: str,
    source_url: str,
    retrieved_at: str,
) -> dict[str, Any]:
    """Build an incomplete report template; never mark pages or values reviewed."""
    pdf_path = pdf_path.expanduser().resolve()
    if bulletin_type not in {"PG62", "PG64"}:
        raise ValueError("bulletin_type must be PG62 or PG64")
    try:
        if date.fromisoformat(bulletin_date).isoformat() != bulletin_date:
            raise ValueError
    except ValueError as exc:
        raise ValueError("bulletin_date must be a real YYYY-MM-DD date") from exc
    if edition_status not in EDITION_CHOICES:
        raise ValueError(f"edition_status must be one of {', '.join(EDITION_CHOICES)}")
    if not source_url.strip():
        raise ValueError("source_url is required")
    if not is_timestamp(retrieved_at):
        raise ValueError("retrieved_at must be an ISO-8601 timestamp with timezone")
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    reader = PdfReader(str(pdf_path), strict=True)
    if reader.is_encrypted:
        raise ValueError("encrypted PDFs cannot be used to create a worksheet")
    page_count = len(reader.pages)
    if page_count < 1:
        raise ValueError("PDF has no pages")

    return {
        "schema_version": 1,
        "document": {
            "bulletin_type": bulletin_type,
            "bulletin_date": bulletin_date,
            "edition_status": edition_status,
            "sha256": digest,
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
        "items": [
            {
                "check_id": f"{bulletin_type.lower()}-page-{page}-REPLACE",
                "page_number": page,
                "locator": f"Page {page}: replace with exact table / row / cell locator after inspecting the rendered PDF",
                "field": "REPLACE_WITH_FIELD",
                "expected_raw": "",
                "extracted_raw": "",
                "independently_verified": False,
            }
            for page in range(1, page_count + 1)
        ],
        "worksheet_status": "INCOMPLETE_REVIEW_REQUIRED",
        "instructions": [
            "This is a template, not evidence of review or accuracy.",
            "Inspect the rendered source PDF directly; do not copy expected_raw from parser output.",
            "Replace each placeholder item with a specific independently transcribed raw token and its parser raw token.",
            "Add enough distinct checks to cover representative rows, edge cases, and each supported layout; page placeholders alone do not prove row coverage.",
            "Mark every page reviewed only after visual inspection and record reviewer identity and review timestamp.",
            "Run scripts/validate_pdf_reconciliation.py only after completing the review; the untouched template must fail closed.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="local source PDF")
    parser.add_argument("--type", dest="bulletin_type", required=True, choices=("PG62", "PG64"))
    parser.add_argument("--date", dest="bulletin_date", required=True, help="trade date printed in the source, YYYY-MM-DD")
    parser.add_argument("--edition", dest="edition_status", required=True, choices=EDITION_CHOICES,
                        help="edition status verified from the PDF itself, not inferred from the filename")
    parser.add_argument("--source-url", required=True, help="official source page or exact source URL")
    parser.add_argument("--retrieved-at", required=True, help="actual retrieval timestamp, ISO-8601 with timezone")
    parser.add_argument("--output", type=Path, required=True, help="new local JSON path; existing files are never overwritten")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists():
        print(f"ERROR: refusing to overwrite existing worksheet: {output}", file=sys.stderr)
        return 2
    try:
        worksheet = build_worksheet(
            args.pdf,
            bulletin_type=args.bulletin_type,
            bulletin_date=args.bulletin_date,
            edition_status=args.edition_status,
            source_url=args.source_url,
            retrieved_at=args.retrieved_at,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(worksheet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        f"WORKSHEET CREATED (INCOMPLETE): {worksheet['document']['bulletin_type']} "
        f"{worksheet['document']['bulletin_date']} | pages={worksheet['document']['page_count']} "
        f"| sha256={worksheet['document']['sha256']} | output={output}"
    )
    print("No page or value has been marked reviewed; the reconciliation gate must remain BLOCKED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
