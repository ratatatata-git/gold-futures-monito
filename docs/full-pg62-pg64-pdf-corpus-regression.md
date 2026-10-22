# Full PG62 / PG64 repository PDF corpus regression

The CI workflow `.github/workflows/live-comex-pdf-smoke.yml` runs
`scripts/test_repository_pdf_corpus.py` against **every PDF matching the expected
filename pattern in both source directories**:

- `data/cme-pg62/PG62_YYYY-MM-DD.pdf`
- `data/cme-pg64/PG64_YYYY-MM-DD.pdf`

The script does not select only the newest common date. It validates each file's
PDF readability, SHA-256 and page-count provenance, parsed trade date versus
filename date, and parser-specific structural/status gates. PG62 accepts recognized FINAL, PRELIMINARY, or REVISED edition labels, preserves the
edition status in the report, and requires a passing parser validation plus unique
non-empty contract codes. A PRELIMINARY pass is only a parser/structure regression
result; it does not promote that bulletin to FINAL or make it eligible for the normal
production history. PG64 requires a single unambiguous edition-status candidate and a passing
provenance match.

The set of PG62 dates and PG64 dates may differ; the script prints the date range,
count, shared dates, and dates present in only one report type. Missing calendar
dates are not automatically treated as missing bulletins because weekends and
market holidays exist. Any desired completeness policy must use an explicit
expected bulletin calendar rather than assuming daily issuance.

## What a pass does not mean

This is a corpus-wide **parser / structure / provenance regression gate**. It does
not independently certify every extracted source cell. PG64 remains diagnostic;
its provenance match does not approve a production master or prove strike-level
accuracy. Independent source-cell reconciliation and cross-date arithmetic/history
checks remain separate gates.

No generated parser outputs or completed private review worksheets are written by
this CI script.
