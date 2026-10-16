# CFTC Gold COT ingestion — MVP

## Scope

This first ingestion uses the CFTC Public Reporting Environment's **Disaggregated Futures Only** dataset (72hh-3qpy) and filters to contract market code 088691 for the COMEX Gold market. It deliberately does not mix futures-only positions with the futures-and-options-combined report.

Official references:

- Dataset: https://publicreporting.cftc.gov/w/72hh-3qpy
- CFTC COT overview and API guidance: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- CFTC explanatory notes: https://www.cftc.gov/MarketReports/CommitmentsofTraders/ExplanatoryNotes/index.htm

COT report dates represent positions as of Tuesday; publication is normally Friday. Keep the report date separate from the local retrieval timestamp.

## Run manually

From the repository root, with Python 3.9 or newer:

\`\`\`bash
python scripts/fetch_cot_gold.py
\`\`\`

The script makes one read-only request to the official CFTC API. It requires no API token for ordinary low-volume use. It fails closed if the response is empty, malformed, has the wrong market code, or does not identify the expected COMEX Gold market.

## Outputs

- data/cot/gold-disaggregated-futures-only.json — cumulative history, sorted by report date. The original API row is retained without numeric coercion.
- data/cot/raw/<sha256>.json — exact API response bytes, addressed by SHA-256. A repeated identical response reuses the same archive file.
- Each history snapshot records retrieval time, source URL, payload hash, response row count, rows added, and rows revised.

History is upserted by report date + CFTC contract market code + market name. Re-running the same response does not duplicate observations. If the CFTC revises an existing observation, the current history is updated and the previous raw payload remains archived. The JSON snapshot manifest records each retrieval attempt.

## Offline tests

\`\`\`bash
python -m unittest tests.test_cot_ingestion -v
\`\`\`

Tests cover empty/wrong-market responses, duplicate keys, idempotent re-ingestion, and corrected source rows. They do not prove that the live CFTC API is reachable or that the market-code filter is current; perform a live run and reconcile the newest row against the CFTC website before relying on the resulting history.

## Explicitly not included yet

- GitHub Actions scheduling
- Dashboard display
- Derived net-position calculations or COT-index scoring
- FRED ingestion
- Rights/publication review for redistributing the resulting data
