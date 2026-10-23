#!/usr/bin/env python3
"""Run parser/provenance checks against every PG62 and PG64 PDF checked into the repository.

This is a corpus regression gate, not independent source-cell accuracy certification.
Every PDF discovered in the designated source directory is parsed; no "latest only"
shortcut is used. PG62 and PG64 coverage can differ by date.
"""
from __future__ import annotations

import hashlib
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
DATE_RE = re.compile(r"^(PG62|PG64)_(\d{4}-\d{2}-\d{2})\.pdf$")


def discover(kind: str) -> list[tuple[str, Path]]:
    folder = ROOT / "data" / f"cme-{kind.lower()}"
    if not folder.is_dir():
        raise FileNotFoundError(f"expected repository PDF directory: {folder}")
    found = []
    for path in sorted(folder.iterdir()):
        match = DATE_RE.fullmatch(path.name)
        if match and match.group(1) == kind and path.is_file():
            found.append((match.group(2), path))
    if not found:
        raise FileNotFoundError(f"no {kind} PDFs found under {folder}")
    dates = [date for date, _ in found]
    if len(dates) != len(set(dates)):
        raise ValueError(f"duplicate {kind} source dates discovered")
    return found


def inspect_pdf(kind: str, date: str, path: Path, retrieved_at: str) -> dict:
    reader = PdfReader(str(path), strict=True)
    if reader.is_encrypted or not reader.pages:
        raise ValueError(f"{kind} {date}: encrypted PDF or zero pages")
    page_count = len(reader.pages)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    if kind == "PG62":
        artifact = parse_pg62.parse_pdf(path)
        edition = artifact["bulletin"]["status"]
        if artifact.get("trade_date") != date:
            # Keep the mismatch fail-closed, but expose source evidence in CI logs so
            # operators can distinguish a bad filename from a parser date bug.
            first_page = re.sub(r"\\s+", " ", reader.pages[0].extract_text() or "").strip()
            header_excerpt = first_page[:900]
            bulletin = artifact.get("bulletin", {})
            raise ValueError(
                f"PG62 filename date {date} != parsed trade date {artifact.get('trade_date')}; "
                f"bulletin={bulletin!r}; first_page_excerpt={header_excerpt!r}"
            )
        if edition not in {"FINAL", "PRELIMINARY", "REVISED"}:
            raise ValueError(f"PG62 {date}: unsupported or ambiguous edition status {edition!r}")
        if artifact.get("validation", {}).get("status") != "PASS":
            raise ValueError(f"PG62 {date}: arithmetic/structural validation did not PASS")
        rows = artifact.get("contracts", [])
        contracts = [row.get("contract") for row in rows]
        if not rows or len(contracts) != len(set(contracts)) or any(not c for c in contracts):
            raise ValueError(f"PG62 {date}: no contracts, missing contract code, or duplicate contracts")
        parser_status = artifact["validation"]["status"]
    else:
        artifact = parse_pg64.audit(path)
        if artifact.get("trade_date") != date:
            raise ValueError(f"PG64 filename date {date} != parsed trade date {artifact.get('trade_date')}")
        statuses = artifact["bulletin"]["status_candidates"]
        if len(statuses) != 1:
            raise ValueError(f"PG64 {date}: ambiguous edition status candidates: {statuses!r}")
        edition = statuses[0]
        parser_status = artifact.get("production_master_status", "DIAGNOSTIC_ONLY")

    manifest = register_pdf_revision.build_manifest(
        pdf_path=path,
        bulletin_type=kind,
        bulletin_date=date,
        edition_status=edition,
        source_url=SOURCES[kind],
        retrieved_at=retrieved_at,
    )
    if manifest["document"]["page_count"] != page_count or manifest["document"]["sha256"] != digest:
        raise ValueError(f"{kind} {date}: manifest page count/hash disagrees with PDF")
    provenance = validate_pdf_parser_provenance.verify(manifest, artifact)
    if provenance["check_status"] != "PROVENANCE_MATCH":
        raise ValueError(f"{kind} {date}: provenance gate failed: {provenance}")
    return {
        "type": kind,
        "date": date,
        "edition": edition,
        "pages": page_count,
        "sha256": digest,
        "parser_status": parser_status,
        "provenance_status": provenance["check_status"],
        "contracts": len(artifact.get("contracts", [])) if kind == "PG62" else None,
    }


def main() -> int:
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        cases = [
            (kind, date, path)
            for kind in ("PG62", "PG64")
            for date, path in discover(kind)
        ]
        results = [inspect_pdf(kind, date, path, retrieved_at) for kind, date, path in cases]
    except Exception as exc:
        print(f"REPOSITORY PDF CORPUS REGRESSION: FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    by_type = {kind: [r for r in results if r["type"] == kind] for kind in ("PG62", "PG64")}
    for kind in ("PG62", "PG64"):
        for result in by_type[kind]:
            extra = f" contracts={result['contracts']}" if kind == "PG62" else ""
            print(
                f"{kind} {result['date']}: edition={result['edition']} pages={result['pages']}"
                f"{extra} sha256={result['sha256']} parser={result['parser_status']}"
                f" provenance={result['provenance_status']}"
            )
    pg62_dates = {r["date"] for r in by_type["PG62"]}
    pg64_dates = {r["date"] for r in by_type["PG64"]}
    print(f"PG62 PDFs tested: {len(by_type['PG62'])}; dates={min(pg62_dates)}..{max(pg62_dates)}")
    print(f"PG64 PDFs tested: {len(by_type['PG64'])}; dates={min(pg64_dates)}..{max(pg64_dates)}")
    print(f"Shared dates: {len(pg62_dates & pg64_dates)}; PG62-only dates: {sorted(pg62_dates - pg64_dates)}; PG64-only dates: {sorted(pg64_dates - pg62_dates)}")
    print("REPOSITORY PDF CORPUS REGRESSION: PASS")
    print("Scope: all checked-in PDFs parsed with structural/status/provenance gates. This does NOT certify independent cell-by-cell accuracy, especially for PG64.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
