#!/usr/bin/env python3
"""Verify that a local parser artifact is tied to its registered PG62/PG64 PDF.

This checks provenance only. It does not validate extraction accuracy or approve
normal-history promotion/publication.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_DATASETS = {"PG62": "PG62_GC_FUTURES", "PG64": "PG64_GOLD_OPTIONS"}


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON at {path}: {exc}") from exc


def verify(manifest: Any, artifact: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    if manifest.get("processing_status") != "RAW_REGISTERED_LOCAL_ONLY":
        raise ValueError("manifest must be RAW_REGISTERED_LOCAL_ONLY")
    if manifest.get("publication_approved") is not False:
        raise ValueError("manifest publication_approved must be false")
    document = manifest.get("document")
    if not isinstance(document, dict):
        raise ValueError("manifest document must be an object")
    bulletin_type = document.get("bulletin_type")
    if bulletin_type not in EXPECTED_DATASETS:
        raise ValueError("manifest document.bulletin_type must be PG62 or PG64")
    digest = document.get("sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise ValueError("manifest document.sha256 is invalid")
    page_count = document.get("page_count")
    if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 1:
        raise ValueError("manifest document.page_count must be a positive integer")
    bulletin_date = document.get("bulletin_date")
    if not isinstance(bulletin_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", bulletin_date):
        raise ValueError("manifest document.bulletin_date must be YYYY-MM-DD")
    edition = document.get("edition_status")
    if edition not in {"PRELIMINARY", "FINAL", "REVISED", "UNCLASSIFIED", "CONFLICTING_EVIDENCE"}:
        raise ValueError("manifest document.edition_status is invalid")

    if not isinstance(artifact, dict):
        raise ValueError("parser artifact root must be an object")
    if artifact.get("dataset") != EXPECTED_DATASETS[bulletin_type]:
        raise ValueError(f"parser artifact dataset must be {EXPECTED_DATASETS[bulletin_type]}")
    source = artifact.get("source")
    if not isinstance(source, dict) or source.get("sha256") != digest:
        raise ValueError("parser artifact source.sha256 does not match the registered PDF")
    if artifact.get("trade_date") != bulletin_date:
        raise ValueError("parser artifact trade_date does not match manifest bulletin_date")

    parser_page_count = artifact.get("page_count")
    if parser_page_count is not None and parser_page_count != page_count:
        raise ValueError("parser artifact page_count does not match manifest page_count")

    bulletin = artifact.get("bulletin")
    if not isinstance(bulletin, dict):
        raise ValueError("parser artifact bulletin must be an object")
    if bulletin_type == "PG62":
        if bulletin.get("status") != edition:
            raise ValueError("PG62 parser bulletin.status does not match manifest edition_status")
        parser_mode = "GC futures master parser"
        parser_result_status = artifact.get("validation", {}).get("status") if isinstance(artifact.get("validation"), dict) else None
    else:
        candidates = bulletin.get("status_candidates")
        if not isinstance(candidates, list) or candidates != [edition]:
            raise ValueError("PG64 status_candidates must contain exactly the manifest edition_status")
        parser_mode = "diagnostic audit only"
        parser_result_status = artifact.get("production_master_status")

    return {
        "schema_version": 1,
        "check_status": "PROVENANCE_MATCH",
        "bulletin_type": bulletin_type,
        "bulletin_date": bulletin_date,
        "edition_status": edition,
        "sha256": digest,
        "manifest_page_count": page_count,
        "parser_page_count": parser_page_count,
        "dataset": artifact["dataset"],
        "parser_version": artifact.get("parser_version"),
        "parser_mode": parser_mode,
        "parser_result_status": parser_result_status,
        "accuracy_gate": "NOT_EVALUATED",
        "publication_approved": False,
        "note": "Provenance only. Independently reconcile extracted raw values against the source PDF; this result does not approve history promotion or publication.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--artifact", required=True, type=Path, help="local PG62 master or PG64 diagnostic audit JSON")
    parser.add_argument("--output", required=True, type=Path, help="new local JSON output; existing files are never overwritten")
    args = parser.parse_args()
    if args.output.exists():
        print(f"ERROR: refusing to overwrite existing output: {args.output}", file=sys.stderr)
        return 2
    try:
        result = verify(read_json(args.manifest), read_json(args.artifact))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as destination:
            json.dump(result, destination, indent=2, ensure_ascii=False)
            destination.write("\n")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    print(f"PROVENANCE_MATCH: {args.output}")
    print("Accuracy gate: NOT_EVALUATED")
    print("Publication status: NOT APPROVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
