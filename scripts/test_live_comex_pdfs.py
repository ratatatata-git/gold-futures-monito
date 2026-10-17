#!/usr/bin/env python3
"""Smoke-test the repository's real CME PG62/PG64 PDFs and verify provenance."""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import parse_pg62
import parse_pg64
import register_pdf_revision
import validate_pdf_parser_provenance

SOURCES = {
    "PG62": "https://www.cmegroup.com/market-data/daily-bulletin.html",
    "PG64": "https://www.cmegroup.com/market-data/daily-bulletin.html",
}
DATE_RE = re.compile(r"^(PG(?:62|64))_(\d{4}-\d{2}-\d{2})\.pdf$")


def find_latest_common_pair() -> tuple[Path, Path]:
    """Choose the newest date with both report types in their designated folders."""
    found: dict[str, dict[str, Path]] = {"PG62": {}, "PG64": {}}
    for kind in ("PG62", "PG64"):
        folder = ROOT / "data" / f"cme-{kind.lower()}"
        if not folder.is_dir():
            raise FileNotFoundError(f"expected repository PDF directory: {folder}")
        for path in folder.iterdir():
            match = DATE_RE.fullmatch(path.name)
            if match and match.group(1) == kind and path.is_file():
                found[kind][match.group(2)] = path
    common_dates = sorted(set(found["PG62"]) & set(found["PG64"]))
    if not common_dates:
        raise FileNotFoundError("no matching PG62/PG64 PDF dates found under data/cme-pg62 and data/cme-pg64")
    date = common_dates[-1]
    return found["PG62"][date], found["PG64"][date]


def run_pg62(pdf: Path, retrieved_at: str) -> dict:
    artifact = parse_pg62.parse_pdf(pdf)
    edition = artifact["bulletin"]["status"]
    manifest = register_pdf_revision.build_manifest(
        pdf_path=pdf, bulletin_type="PG62", bulletin_date=artifact["trade_date"],
        edition_status=edition, source_url=SOURCES["PG62"], retrieved_at=retrieved_at,
    )
    provenance = validate_pdf_parser_provenance.verify(manifest, artifact)
    if artifact.get("validation", {}).get("status") != "PASS":
        raise ValueError("PG62 parser did not report validation PASS")
    if provenance["check_status"] != "PROVENANCE_MATCH":
        raise ValueError("PG62 provenance gate did not pass")
    return {
        "type": "PG62", "date": artifact["trade_date"], "edition": edition,
        "pages": manifest["document"]["page_count"], "sha256": manifest["document"]["sha256"],
        "parser_status": artifact["validation"]["status"], "provenance_status": provenance["check_status"],
    }


def run_pg64(pdf: Path, retrieved_at: str) -> dict:
    artifact = parse_pg64.audit(pdf)
    statuses = artifact["bulletin"]["status_candidates"]
    if len(statuses) != 1:
        raise ValueError(f"PG64 edition status is ambiguous ({len(statuses)} candidates); fail closed")
    edition = statuses[0]
    manifest = register_pdf_revision.build_manifest(
        pdf_path=pdf, bulletin_type="PG64", bulletin_date=artifact["trade_date"],
        edition_status=edition, source_url=SOURCES["PG64"], retrieved_at=retrieved_at,
    )
    provenance = validate_pdf_parser_provenance.verify(manifest, artifact)
    if provenance["check_status"] != "PROVENANCE_MATCH":
        raise ValueError("PG64 provenance gate did not pass")
    return {
        "type": "PG64", "date": artifact["trade_date"], "edition": edition,
        "pages": manifest["document"]["page_count"], "sha256": manifest["document"]["sha256"],
        "parser_status": artifact["production_master_status"], "provenance_status": provenance["check_status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg62-pdf", type=Path, help="optional explicit local PG62 PDF")
    parser.add_argument("--pg64-pdf", type=Path, help="optional explicit local PG64 PDF")
    args = parser.parse_args()
    if bool(args.pg62_pdf) != bool(args.pg64_pdf):
        parser.error("--pg62-pdf and --pg64-pdf must be supplied together")

    if args.pg62_pdf and args.pg64_pdf:
        paths = {"PG62": args.pg62_pdf.expanduser().resolve(), "PG64": args.pg64_pdf.expanduser().resolve()}
    else:
        pg62, pg64 = find_latest_common_pair()
        paths = {"PG62": pg62, "PG64": pg64}

    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        for kind, path in paths.items():
            if not path.is_file() or path.suffix.lower() != ".pdf":
                raise ValueError(f"{kind} input is not an existing PDF file: {path}")
            reader = PdfReader(str(path), strict=True)
            if reader.is_encrypted or len(reader.pages) < 1:
                raise ValueError(f"{kind} PDF is encrypted or has no pages")
        results = [run_pg62(paths["PG62"], retrieved_at), run_pg64(paths["PG64"], retrieved_at)]
    except Exception as exc:
        print(f"REPOSITORY PDF SMOKE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("REAL REPOSITORY CME PDF SMOKE: PASS")
    for result in results:
        print(
            f"{result['type']}: date={result['date']} edition={result['edition']} "
            f"pages={result['pages']} sha256={result['sha256']} "
            f"parser={result['parser_status']} provenance={result['provenance_status']}"
        )
        print(f"{result['type']}: accuracy_review=NOT_INDEPENDENTLY_RECONCILED publication_approved=false")
    print("Scope: real-PDF parser/provenance smoke only; independent cell-by-cell reconciliation is still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
