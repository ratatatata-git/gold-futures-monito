# 実PDFライブスモークテスト

`scripts/test_live_comex_pdfs.py` downloads the official current CME PG62 and PG64 PDF endpoints into a temporary directory and runs the existing parsers plus the local source-provenance gate.

## Run locally

```sh
python -m pip install -r pg64-requirements.txt
python scripts/test_live_comex_pdfs.py
```

The same test can be started manually from GitHub Actions using **Live Official CME PDF Smoke Test** (`workflow_dispatch`). It is intentionally not run on every pull request because it depends on an external live endpoint.

## Data handling and interpretation

- Source URLs are the official CME current bulletin endpoints for Section 62 and Section 64.
- PDF files and intermediate parser outputs are held only in a temporary directory and removed when the process exits.
- The script prints a compact result (date, edition, page count, SHA-256, parser status and provenance status), not the extracted contract/option values.
- PG62 must pass its built-in structural and TOTAL reconciliation checks.
- PG64 must have a single unambiguous edition status; its parser output remains diagnostic-only.
- A successful run verifies that the current real PDFs can be downloaded, parsed, and tied to matching local source manifests. It is not independent cell-by-cell reconciliation, a complete page-review record, a redistribution-rights decision, or publication approval.
- The endpoint may change between runs. Keep the printed hashes and test time in a private operational log if audit continuity is required; do not commit PDFs or data-bearing artifacts to this repository while redistribution terms remain unresolved.

Phase 2 remains incomplete until the actual PDFs are reviewed page-by-page and independently transcribed raw tokens are reconciled against parser outputs.
