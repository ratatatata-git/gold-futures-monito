#!/usr/bin/env python3
"""Register a local PG62/PG64 PDF revision without publishing or modifying the source."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

EDITION_STATUSES = {"UNCLASSIFIED", "PRELIMINARY", "FINAL", "REVISED", "CONFLICTING_EVIDENCE"}
BULLETIN_TYPES = {"PG62", "PG64"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_parent(path: Path, bulletin_type: str, bulletin_date: str) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read parent manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("parent manifest must have schema_version 1")
    document = manifest.get("document")
    if not isinstance(document, dict):
        raise ValueError("parent manifest is missing document metadata")
    if document.get("bulletin_type") != bulletin_type or document.get("bulletin_date") != bulletin_date:
        raise ValueError("parent manifest must refer to the same bulletin type and date")
    digest = document.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("parent manifest has an invalid SHA-256")
    return manifest


def build_manifest(
    pdf_path: Path,
    bulletin_type: str,
    bulletin_date: str,
    edition_status: str,
    source_url: str,
    retrieved_at: str,
    parent_manifest_path: Path | None = None,
) -> dict[str, Any]:
    if bulletin_type not in BULLETIN_TYPES:
        raise ValueError("bulletin_type must be PG62 or PG64")
    if edition_status not in EDITION_STATUSES:
        raise ValueError("edition_status is not recognized; do not infer it from filename")
    try:
        parsed_date = datetime.strptime(bulletin_date, "%Y-%m-%d").date()
        if parsed_date.isoformat() != bulletin_date:
            raise ValueError
    except ValueError as exc:
        raise ValueError("bulletin_date must be YYYY-MM-DD") from exc
    if not source_url.strip():
        raise ValueError("source_url is required")
    try:
        datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("retrieved_at must be an ISO-8601 timestamp") from exc
    if not pdf_path.is_file():
        raise ValueError(f"PDF does not exist or is not a regular file: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("input file must have a .pdf extension")

    try:
        reader = PdfReader(str(pdf_path), strict=True)
        if reader.is_encrypted:
            raise ValueError("encrypted PDF cannot be registered without explicit decryption handling")
        page_count = len(reader.pages)
        if page_count < 1:
            raise ValueError("PDF contains no pages")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"PDF parsing failed; source not registered: {exc}") from exc

    digest = sha256_file(pdf_path)
    parent = None
    if parent_manifest_path:
        parent = load_parent(parent_manifest_path, bulletin_type, bulletin_date)
        parent_doc = parent["document"]
        if parent_doc.get("sha256") == digest:
            raise ValueError("current PDF hash matches parent; this is not a new revision")
        parent = {
            "manifest_path": str(parent_manifest_path),
            "sha256": parent_doc["sha256"],
            "edition_status": parent_doc.get("edition_status", "UNCLASSIFIED"),
        }

    return {
        "schema_version": 1,
        "document": {
            "bulletin_type": bulletin_type,
            "bulletin_date": bulletin_date,
            "edition_status": edition_status,
            "original_filename": pdf_path.name,
            "sha256": digest,
            "byte_size": pdf_path.stat().st_size,
            "page_count": page_count,
            "source_url": source_url,
            "retrieved_at": retrieved_at,
            "local_source_path": str(pdf_path.resolve()),
        },
        "revision": {
            "relation": "new_revision_candidate" if parent else "initial_registration",
            "parent": parent,
            "classification_note": "Edition status is user-supplied and must be verified against the source PDF.",
        },
        "processing_status": "RAW_REGISTERED_LOCAL_ONLY",
        "publication_status": "NOT_REVIEWED",
        "publication_approved": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--type", required=True, choices=sorted(BULLETIN_TYPES), dest="bulletin_type")
    parser.add_argument("--date", required=True, dest="bulletin_date", help="bulletin date YYYY-MM-DD")
    parser.add_argument("--edition", required=True, choices=sorted(EDITION_STATUSES))
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--output", required=True, type=Path, help="new local JSON manifest path")
    parser.add_argument("--retrieved-at", help="ISO-8601 timestamp; defaults to current UTC time")
    parser.add_argument("--parent-manifest", type=Path, help="previous manifest for the same bulletin/date")
    args = parser.parse_args()

    if args.output.exists():
        print(f"ERROR: output already exists; refusing to overwrite: {args.output}", file=sys.stderr)
        return 2
    retrieved_at = args.retrieved_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        manifest = build_manifest(
            args.pdf, args.bulletin_type, args.bulletin_date, args.edition,
            args.source_url, retrieved_at, args.parent_manifest,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as destination:
            json.dump(manifest, destination, indent=2, ensure_ascii=False)
            destination.write("\n")
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Registered local manifest: {args.output}")
    print(f"SHA-256: {manifest['document']['sha256']}")
    print(f"Pages: {manifest['document']['page_count']}")
    print("Publication status: NOT_REVIEWED (not approved for publication)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
