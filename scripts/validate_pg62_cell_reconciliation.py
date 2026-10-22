#!/usr/bin/env python3
"""Validate full PG62 GC contract-by-field coverage after manual source review."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from validate_pdf_reconciliation import inspect_report

FIELDS = {
    "contract_code", "open", "high", "low", "settlement", "price_change",
    "volume_globex", "volume_pnt_pit", "open_interest", "oi_change",
}
CONTRACT_RE = re.compile(r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\\d{2}$", re.I)


def validate_pg62_coverage(report: Any, expected_contract_count: int = 27) -> tuple[list[str], dict[str, Any]]:
    """Run generic reconciliation checks plus strict PG62 completeness checks."""
    issues, summary = inspect_report(report)
    if not isinstance(report, dict):
        return issues, summary
    doc = report.get("document") if isinstance(report.get("document"), dict) else {}
    if doc.get("bulletin_type") != "PG62":
        issues.append("document.bulletin_type must be PG62")
    if doc.get("edition_status") != "FINAL":
        issues.append("PG62 source must be FINAL")

    items = report.get("items")
    if not isinstance(items, list):
        items = []
    contracts: set[str] = set()
    seen: set[tuple[str, str]] = set()
    fields_by_contract: dict[str, set[str]] = {}
    malformed = 0
    trade_date = doc.get("bulletin_date", "")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            malformed += 1
            continue
        field = item.get("field")
        check_id = item.get("check_id")
        if not isinstance(field, str) or field not in FIELDS:
            issues.append(f"items[{index}].field is not a supported PG62 field")
            malformed += 1
            continue
        prefix = f"pg62-{trade_date}-"
        if not isinstance(check_id, str) or not check_id.startswith(prefix):
            issues.append(f"items[{index}].check_id must start with {prefix}")
            malformed += 1
            continue
        suffix = check_id[len(prefix):]
        expected_suffix = f"-{field}"
        if not suffix.endswith(expected_suffix):
            issues.append(f"items[{index}].check_id field suffix does not match {field}")
            malformed += 1
            continue
        contract = suffix[:-len(expected_suffix)]
        if not CONTRACT_RE.fullmatch(contract):
            issues.append(f"items[{index}].check_id has invalid contract code {contract!r}")
            malformed += 1
            continue
        key = (contract, field)
        if key in seen:
            issues.append(f"duplicate contract-field check: {contract}.{field}")
        seen.add(key)
        contracts.add(contract)
        fields_by_contract.setdefault(contract, set()).add(field)

    if len(contracts) != expected_contract_count:
        issues.append(f"expected {expected_contract_count} unique GC contracts, found {len(contracts)}")
    expected_pairs = {(c, f) for c in contracts for f in FIELDS}
    missing = sorted(expected_pairs - seen)
    if missing:
        issues.append("missing contract-field checks: " + ", ".join(f"{c}.{f}" for c, f in missing))
    unexpected = sorted(seen - expected_pairs)
    if unexpected:
        issues.append("unexpected contract-field checks: " + ", ".join(f"{c}.{f}" for c, f in unexpected))
    expected_total = expected_contract_count * len(FIELDS)
    if len(items) != expected_total:
        issues.append(f"expected exactly {expected_total} cell checks, found {len(items)}")

    checklist = report.get("page_review_checklist")
    page_count = doc.get("page_count")
    if not isinstance(checklist, list):
        issues.append("page_review_checklist is required to prove every page was reviewed")
    elif isinstance(page_count, int) and not isinstance(page_count, bool):
        reviewed_pages = {
            p.get("page_number") for p in checklist
            if isinstance(p, dict) and p.get("reviewed") is True
        }
        listed_pages = {
            p.get("page_number") for p in checklist if isinstance(p, dict)
        }
        expected_pages = set(range(1, page_count + 1))
        if listed_pages != expected_pages or len(checklist) != page_count:
            issues.append("page_review_checklist must contain each PDF page exactly once")
        if reviewed_pages != expected_pages:
            issues.append("page_review_checklist must mark every PDF page reviewed")

    summary.update({
        "unique_contracts": len(contracts),
        "expected_contracts": expected_contract_count,
        "expected_cell_checks": expected_total,
        "malformed_items": malformed,
        "gate": "PASS" if not issues else "BLOCKED",
        "issues": issues,
    })
    return issues, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--expected-contracts", type=int, default=27)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.expected_contracts < 1:
        parser.error("--expected-contracts must be positive")
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read valid JSON report: {exc}", file=sys.stderr)
        return 2
    issues, summary = validate_pg62_coverage(report, args.expected_contracts)
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(
            f'{summary.get("gate", "BLOCKED")}: PG62 {summary.get("bulletin_date", "?")} | '
            f'contracts={summary.get("unique_contracts", 0)}/{args.expected_contracts} | '
            f'checks={summary.get("checks", 0)}/{args.expected_contracts * len(FIELDS)} | '
            f'matches={summary.get("matches", 0)} mismatches={summary.get("mismatches", 0)}'
        )
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
