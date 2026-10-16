#!/usr/bin/env python3
"""Fail-closed validator for manually reconciled PG62/PG64 PDF evidence reports.

The report contains independently transcribed source values and parser output.
This tool does not fetch PDFs, extract values, or certify publication rights.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EDITION_STATUSES = {
    "PRELIMINARY", "FINAL", "REVISED", "UNCLASSIFIED", "CONFLICTING_EVIDENCE"
}
BULLETIN_TYPES = {"PG62", "PG64"}


def is_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
        return len(value) == 10
    except ValueError:
        return False


def is_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def inspect_report(report: Any) -> tuple[list[str], dict[str, Any]]:
    """Return blocking issues and a derived summary; never trust a supplied pass flag."""
    issues: list[str] = []
    if not isinstance(report, dict):
        return ["report root must be a JSON object"], {"gate": "BLOCKED"}

    if report.get("schema_version") != 1:
        issues.append("schema_version must be 1")

    document = report.get("document")
    if not isinstance(document, dict):
        issues.append("document must be an object")
        document = {}

    if document.get("bulletin_type") not in BULLETIN_TYPES:
        issues.append("document.bulletin_type must be PG62 or PG64")
    if not is_date(document.get("bulletin_date")):
        issues.append("document.bulletin_date must be YYYY-MM-DD")
    edition = document.get("edition_status")
    if edition not in EDITION_STATUSES:
        issues.append("document.edition_status is invalid")
    if not isinstance(document.get("sha256"), str) or not SHA256_RE.fullmatch(document["sha256"]):
        issues.append("document.sha256 must be a lowercase 64-character SHA-256")
    page_count = document.get("page_count")
    if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 1:
        issues.append("document.page_count must be a positive integer")
        page_count = 0
    if not isinstance(document.get("source_url"), str) or not document["source_url"].strip():
        issues.append("document.source_url is required")
    if not is_timestamp(document.get("retrieved_at")):
        issues.append("document.retrieved_at must be an ISO-8601 timestamp")

    review = report.get("review")
    if not isinstance(review, dict):
        issues.append("review must be an object")
        review = {}
    if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
        issues.append("review.reviewer is required")
    if not is_timestamp(review.get("reviewed_at")):
        issues.append("review.reviewed_at must be an ISO-8601 timestamp")
    if review.get("method") != "independent_manual_pdf":
        issues.append("review.method must be independent_manual_pdf")

    pages = report.get("pages_reviewed")
    if not isinstance(pages, list) or any(
        isinstance(p, bool) or not isinstance(p, int) or p < 1 or p > page_count for p in pages
    ):
        issues.append("pages_reviewed must be a list of valid 1-based page numbers")
        pages = []
    if len(pages) != len(set(pages)):
        issues.append("pages_reviewed must not contain duplicates")
    if page_count and set(pages) != set(range(1, page_count + 1)):
        issues.append("page coverage incomplete: every page must be explicitly reviewed")

    items = report.get("items")
    if not isinstance(items, list) or not items:
        issues.append("items must be a non-empty array")
        items = []

    ids: set[str] = set()
    matches = 0
    mismatches = 0
    unresolved = 0
    for index, item in enumerate(items):
        prefix = f"items[{index}]"
        if not isinstance(item, dict):
            issues.append(f"{prefix} must be an object")
            unresolved += 1
            continue
        item_id = item.get("check_id")
        if not isinstance(item_id, str) or not item_id.strip():
            issues.append(f"{prefix}.check_id is required")
        elif item_id in ids:
            issues.append(f"duplicate check_id: {item_id}")
        else:
            ids.add(item_id)

        page = item.get("page_number")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1 or page > page_count:
            issues.append(f"{prefix}.page_number must be within the document page range")
        if not isinstance(item.get("locator"), str) or not item["locator"].strip():
            issues.append(f"{prefix}.locator must identify a table/row/cell or token location")
        if not isinstance(item.get("field"), str) or not item["field"].strip():
            issues.append(f"{prefix}.field is required")
        if item.get("independently_verified") is not True:
            issues.append(f"{prefix}.independently_verified must be true")
        expected = item.get("expected_raw")
        actual = item.get("extracted_raw")
        if not isinstance(expected, str) or not isinstance(actual, str):
            issues.append(f"{prefix} expected_raw and extracted_raw must be strings")
            unresolved += 1
        elif expected == actual:
            matches += 1
        else:
            mismatches += 1
            issues.append(f"{prefix} raw value mismatch (expected_raw != extracted_raw)")

    if edition != "FINAL":
        issues.append("standard-history gate requires edition_status FINAL")
    if mismatches:
        # Individual mismatch issues already identify the failed checks.
        pass

    summary = {
        "bulletin_type": document.get("bulletin_type"),
        "bulletin_date": document.get("bulletin_date"),
        "edition_status": edition,
        "page_count": page_count,
        "pages_reviewed": len(set(pages)),
        "checks": len(items),
        "matches": matches,
        "mismatches": mismatches,
        "unresolved": unresolved,
        "gate": "PASS" if not issues else "BLOCKED",
        "issues": issues,
    }
    return issues, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="path to a local reconciliation JSON report")
    parser.add_argument("--json", action="store_true", help="print machine-readable summary JSON")
    args = parser.parse_args()

    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read valid JSON report: {exc}", file=sys.stderr)
        return 2

    issues, summary = inspect_report(report)
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(
            f'{summary.get("gate", "BLOCKED")}: {summary.get("bulletin_type", "?")} '
            f'{summary.get("bulletin_date", "?")} | edition={summary.get("edition_status", "?")} | '
            f'pages={summary.get("pages_reviewed", 0)}/{summary.get("page_count", 0)} | '
            f'checks={summary.get("checks", 0)} matches={summary.get("matches", 0)} '
            f'mismatches={summary.get("mismatches", 0)} unresolved={summary.get("unresolved", 0)}'
        )
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
    return 0 if not issues else 1


if __args__ == "__main__":
    raise SystemExit(main())
