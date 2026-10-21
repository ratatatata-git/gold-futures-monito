# PG62 independent cell reconciliation worksheet

This command creates a local-only, fail-closed review template from a pinned source PDF and a PG62 parser JSON result. It creates one review item per contract and source field: contract code, open, high, low, settlement, price change, Globex volume, PNT/Pit volume, open interest, and OI change.

Example (run locally; use the actual retrieval time):

```sh
python scripts/parse_pg62.py data/cme-pg62/PG62_2026-10-14.pdf --output-dir /secure/local-review/parsed
python scripts/create_pg62_cell_reconciliation.py \
  data/cme-pg62/PG62_2026-10-14.pdf \
  /secure/local-review/parsed/2026-10-14/2026-10-14_FINAL.json \
  --source-url "https://www.cmegroup.com/market-data/daily-bulletin.html" \
  --retrieved-at "REPLACE_WITH_ACTUAL_TIMESTAMP" \
  --output /secure/local-review/pg62-2026-10-14-cell-review.json
python scripts/validate_pdf_reconciliation.py /secure/local-review/pg62-2026-10-14-cell-review.json
```

The worksheet binds the PDF SHA-256 to the parser JSON, checks the FINAL edition and row/page locators, and records the parser's extracted raw token in `extracted_raw`. Crucially, every `expected_raw` is blank and every `independently_verified` flag is false. A reviewer must render the original PDF and transcribe each expected token directly from the source. Do not copy expected values from parser output or the master JSON. The untouched template must fail validation.

For high and low, the parser retains one combined high/low source token; the reviewer enters that same combined token as `expected_raw` for both fields after inspecting the original cell. This checks the source token, while the separate semantic regression test checks how the parser interprets its components.

This worksheet does not claim any cells have already been independently reviewed. It is a tool to make that review systematic and auditable. Keep PDFs, parsed JSON, and completed review reports in the intended private/local storage.
