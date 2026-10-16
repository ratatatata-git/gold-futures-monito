#!/usr/bin/env python3
"""Compare two locally registered PG62/PG64 revisions and their reconciliation reports.

All inputs and outputs are local. A successful comparison is not publication approval.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from validate_pdf_reconciliation import inspect_report

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON at {path}: {exc}") from exc


def verified_side(manifest_path: Path, report_path: Path, label: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = read_json(manifest_path)
    report = read_json(report_path)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError(f"{label}: manifest schema_version must be 1")
    document = manifest.get("document")
    if not isinstance(document, dict):
        raise ValueError(f"{label}: manifest document must be an object")
    digest = document.get("sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise ValueError(f"{label}: manifest has invalid SHA-256")
    if manifest.get("processing_status") != "RAW_REGISTERED_LOCAL_ONLY":
        raise ValueError(f"{label}: manifest is not RAW_REGISTERED_LOCAL_ONLY")
    if manifest.get("publication_approved") is not False:
        raise ValueError(f"{label}: publication_approved must remain false for this local tool")

    issues, summary = inspect_report(report)
    if issues or summary.get("gate") != "PASS":
        raise ValueError(f"{label}: reconciliation report is blocked: {'; '.join(issues[:5])}")
    report_doc = report.get("document", {})
    pairs = {
        "bulletin_type": document.get("bulletin_type"),
        "bulletin_date": document.get("bulletin_date"),
        "edition_status": document.get("edition_status"),
        "sha256": digest,
        "page_count": document.get("page_count"),
    }
    for field, expected in pairs.items():
        if report_doc.get(field) != expected:
            raise ValueError(f"{label}: manifest/report provenance mismatch for {field}")
    return manifest, report, summary


def item_index(report: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in report["items"]:
        check_id = item["check_id"]
        if check_id in result:
            raise ValueError(f"{label}: duplicate check_id {check_id}")
        result[check_id] = item
    return result


def compare_revisions(old_manifest_path: Path, old_report_path: Path,
                      new_manifest_path: Path, new_report_path: Path) -> dict[str, Any]:
    old_manifest, old_report, old_summary = verified_side(old_manifest_path, old_report_path, "old")
    new_manifest, new_report, new_summary = verified_side(new_manifest_path, new_report_path, "new")
    old_doc = old_manifest["document"]
    new_doc = new_manifest["document"]
    for field in ("bulletin_type", "bulletin_date"):
        if old_doc.get(field) != new_doc.get(field):
            raise ValueError(f"revisions must share {field}")
    if old_doc["sha256"] == new_doc["sha256"]:
        raise ValueError("revision hashes are identical; no source revision to compare")

    old_items = item_index(old_report, "old")
    new_items = item_index(new_report, "new")
    added = sorted(set(new_items) - set(old_items))
    removed = sorted(set(old_items) - set(new_items))
    changed, unchanged = [], []
    for check_id in sorted(set(old_items) & set(new_items)):
        before, after = old_items[check_id], new_items[check_id]
        fields = ("expected_raw", "extracted_raw", "page_number", "locator", "field")
        differences = {field: {"old": before.get(field), "new": after.get(field)}
                       for field in fields if before.get(field) != after.get(field)}
        entry = {"check_id": check_id, "differences": differences}
        (changed if differences else unchanged).append(entry)

    return {
        "schema_version": 1,
        "comparison_status": "DIFF_READY",
        "publication_approved": False,
        "identity": {"bulletin_type": old_doc["bulletin_type"], "bulletin_date": old_doc["bulletin_date"]},
        "old_revision": {"manifest_path": str(old_manifest_path), "sha256": old_doc["sha256"],
                         "edition_status": old_doc["edition_status"], "page_count": old_doc["page_count"],
                         "reconciliation_gate": old_summary["gate"]},
        "new_revision": {"manifest_path": str(new_manifest_path), "sha256": new_doc["sha256"],
                         "edition_status": new_doc["edition_status"], "page_count": new_doc["page_count"],
                         "reconciliation_gate": new_summary["gate"]},
        "summary": {"old_check_count": len(old_items), "new_check_count": len(new_items),
                    "unchanged_count": len(unchanged), "changed_count": len(changed),
                    "added_check_ids": added, "removed_check_ids": removed,
                    "page_count_changed": old_doc["page_count"] != new_doc["page_count"],
                    "edition_status_changed": old_doc["edition_status"] != new_doc["edition_status"]},
        "unchanged": unchanged,
        "changed": changed,
        "note": "Local comparison only. Review changed/added/removed coverage and rights separately; not publication approval.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-manifest", required=True, type=Path)
    parser.add_argument("--old-report", required=True, type=Path)
    parser.add_argument("--new-manifest", required=True, type=Path)
    parser.add_argument("--new-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="new local JSON output; must not already exist")
    args = parser.parse_args()
    if args.output.exists():
        print(f"ERROR: refusing to overwrite existing output: {args.output}", file=sys.stderr)
        return 2
    try:
        result = compare_revisions(args.old_manifest, args.old_report, args.new_manifest, args.new_report)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as destination:
            json.dump(result, destination, indent=2, ensure_ascii=False)
            destination.write("\n")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    print(f"DIFF_READY: {args.output}")
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    print("Publication status: NOT APPROVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
