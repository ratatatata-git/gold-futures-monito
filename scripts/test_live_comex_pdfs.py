#!/usr/bin/env python3
"""Run PG62 and PG64 parsers against official current CME PDFs, locally."""
from __future__ import annotations
import sys
import tempfile
import urllib.request
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
    "PG62": "https://www.cmegroup.com/daily_bulletin/current/Section62_Metals_Futures_Products.pdf",
    "PG64": "https://www.cmegroup.com/daily_bulletin/current/Section64_Metals_Option_Products.pdf",
}
MAX_BYTES = 100 * 1024 * 1024


def download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
        "Referer": "https://www.cmegroup.com/market-data/daily-bulletin.html",
    })
    with urllib.request.urlopen(request, timeout=45) as response:
        content_type = response.headers.get("Content-Type", "")
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError("official PDF exceeded the 100 MiB safety limit")
    if not payload.startswith(b"%PDF-"):
        raise ValueError(f"official source did not return a PDF (Content-Type={content_type!r})")
    target.write_bytes(payload)


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
        "accuracy_review": "NOT_INDEPENDENTLY_RECONCILED", "publication_approved": False,
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
        "accuracy_review": "NOT_INDEPENDENTLY_RECONCILED", "publication_approved": False,
    }


def main() -> int:
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    results = []
    try:
        with tempfile.TemporaryDirectory(prefix="gold-futures-live-pdf-") as temp:
            temp_dir = Path(temp)
            paths = {}
            for kind, url in SOURCES.items():
                path = temp_dir / f"{kind}.pdf"
                download(url, path)
                reader = PdfReader(str(path), strict=True)
                if reader.is_encrypted or len(reader.pages) < 1:
                    raise ValueError(f"{kind} PDF is encrypted or has no pages")
                paths[kind] = path
            results.append(run_pg62(paths["PG62"], retrieved_at))
            results.append(run_pg64(paths["PG64"], retrieved_at))
    except Exception as exc:
        print(f"LIVE PDF SMOKE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("PDFs and intermediate artifacts were held in a temporary directory and removed.", file=sys.stderr)
        return 1
    print("LIVE OFFICIAL CME PDF SMOKE: PASS")
    for result in results:
        print(
            f"{result['type']}: date={result['date']} edition={result['edition']} "
            f"pages={result['pages']} sha256={result['sha256']} "
            f"parser={result['parser_status']} provenance={result['provenance_status']}"
        )
        print(
            f"{result['type']}: accuracy_review={result['accuracy_review']} "
            f"publication_approved={str(result['publication_approved']).lower()}"
        )
    print("Scope: live parser/provenance smoke only; no independent cell-by-cell review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
