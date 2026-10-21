#!/usr/bin/env python3
"""Validate the structure and evidence-status discipline of the PDF audit ledger.

This validates the ledger contract only. It does not reopen PDFs or certify the
accuracy of any historical audit result.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "data" / "verification" / "pdf-audit-evidence-ledger.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_BLOB_RE = re.compile(r"^[0-9a-f]{40}$")
STATUSES = {
    "REPRODUCIBLE_AUTOMATED",
    "MANUAL_REVIEW_RECORDED",
    "CROSSCHECK_RECORDED_NOT_REPRODUCIBLE",
    "INCOMPLETE",
}
BULLETIN_TYPES = {"PG62", "PG64"}


def validate_ledger(data: Any) -> list[str]:
    """Return all structural/consistency errors; never trust a self-reported PASS."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["ledger root must be a JSON object"]
    if data.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    if not isinstance(data.get("ledger_version"), str) or not data["ledger_version"].strip():
        errors.append("ledger_version is required")
    if not isinstance(data.get("sources"), list) or not data["sources"]:
        errors.append("sources must be a non-empty array")
        sources = []
    else:
        sources = data["sources"]

    source_ids: set[str] = set()
    for i, source in enumerate(sources):
        prefix = f"sources[{i}]"
        if not isinstance(source, dict):
            errors.append(f"{prefix} must be an object")
            continue
        sid = source.get("source_id")
        if not isinstance(sid, str) or not sid.strip():
            errors.append(f"{prefix}.source_id is required")
        elif sid in source_ids:
            errors.append(f"duplicate source_id: {sid}")
        else:
            source_ids.add(sid)
        if source.get("bulletin_type") not in BULLETIN_TYPES:
            errors.append(f"{prefix}.bulletin_type must be PG62 or PG64")
        date = source.get("bulletin_date")
        if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            errors.append(f"{prefix}.bulletin_date must use YYYY-MM-DD")
        if source.get("edition_status") not in {"PRELIMINARY", "FINAL", "REVISED", "UNCLASSIFIED", "CONFLICTING_EVIDENCE"}:
            errors.append(f"{prefix}.edition_status is invalid")
        path = source.get("repository_path")
        if not isinstance(path, str) or not path.startswith("data/cme-pg") or ".." in Path(path).parts:
            errors.append(f"{prefix}.repository_path must point inside data/cme-pg*")
        digest = source.get("sha256")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            errors.append(f"{prefix}.sha256 must be a lowercase 64-character SHA-256")
        if "git_blob_sha1" in source and (
            not isinstance(source["git_blob_sha1"], str) or not GIT_BLOB_RE.fullmatch(source["git_blob_sha1"])
        ):
            errors.append(f"{prefix}.git_blob_sha1 must be a 40-character lowercase Git object ID")
        page_count = source.get("page_count")
        if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 1:
            errors.append(f"{prefix}.page_count must be a positive integer")

    evidence = data.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("evidence must be a non-empty array")
        evidence = []
    evidence_ids: set[str] = set()
    for i, item in enumerate(evidence):
        prefix = f"evidence[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        eid = item.get("evidence_id")
        if not isinstance(eid, str) or not eid.strip():
            errors.append(f"{prefix}.evidence_id is required")
        elif eid in evidence_ids:
            errors.append(f"duplicate evidence_id: {eid}")
        else:
            evidence_ids.add(eid)
        status = item.get("status")
        if status not in STATUSES:
            errors.append(f"{prefix}.status is invalid")
        refs = item.get("source_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{prefix}.source_ids must be a non-empty array")
        else:
            for ref in refs:
                if ref not in source_ids:
                    errors.append(f"{prefix} references unknown source_id: {ref}")
        for required in ("scope", "method", "result", "limitations"):
            if required not in item:
                errors.append(f"{prefix}.{required} is required")
        if not isinstance(item.get("limitations"), list) or not item["limitations"]:
            errors.append(f"{prefix}.limitations must be a non-empty array")
        if status == "REPRODUCIBLE_AUTOMATED":
            if not isinstance(item.get("command"), str) or not item["command"].strip():
                errors.append(f"{prefix}: reproducible evidence requires a command")
            artifacts = item.get("artifact_paths")
            if not isinstance(artifacts, list) or not artifacts or any(not isinstance(p, str) or not p.strip() for p in artifacts):
                errors.append(f"{prefix}: reproducible evidence requires artifact_paths")
        elif "command" in item and status == "INCOMPLETE":
            errors.append(f"{prefix}: incomplete evidence must not advertise a passing/reproducible command")

    if not isinstance(data.get("open_gates"), list) or not data["open_gates"]:
        errors.append("open_gates must be a non-empty array")
    else:
        gate_ids: set[str] = set()
        for i, gate in enumerate(data["open_gates"]):
            prefix = f"open_gates[{i}]"
            if not isinstance(gate, dict):
                errors.append(f"{prefix} must be an object")
                continue
            gid = gate.get("gate_id")
            if not isinstance(gid, str) or not gid.strip():
                errors.append(f"{prefix}.gate_id is required")
            elif gid in gate_ids:
                errors.append(f"duplicate gate_id: {gid}")
            else:
                gate_ids.add(gid)
            if gate.get("status") not in {"OPEN", "CLOSED"}:
                errors.append(f"{prefix}.status must be OPEN or CLOSED")
            if not isinstance(gate.get("required_to_close"), str) or not gate["required_to_close"].strip():
                errors.append(f"{prefix}.required_to_close is required")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", nargs="?", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args()
    try:
        data = json.loads(args.ledger.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"BLOCKED: cannot read valid JSON ledger: {exc}", file=sys.stderr)
        return 2
    errors = validate_ledger(data)
    if errors:
        print("BLOCKED: PDF audit evidence ledger has structural errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"PASS: ledger structure valid ({len(data['sources'])} sources, {len(data['evidence'])} evidence records, {len(data['open_gates'])} open gates)")
    print("NOTE: structural validity does not certify the underlying PDF extraction or historical audit results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
