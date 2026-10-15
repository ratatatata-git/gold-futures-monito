# PG64 Testing Philosophy, Results, and Goals

Status: working agreement and evidence inventory. This document summarizes the current test approach and next steps; it is not a parser certification or production-promotion approval.

## 1. Purpose and current boundary

The PG64 Gold Options parser is in a diagnostic-only stage. Its job is to preserve evidence and expose candidate structure, unresolved states, and reconciliation risks so they can be tested. It is not yet an approved source for production options history.

**Required gate:** `BLOCKED_DIAGNOSTIC_ONLY`.

- Do not write a production PG64 MASTER or production options-history data from this parser.
- Do not promote the parser or alter production history without a separate, explicit review.
- Make changes on branches and through pull requests; do not bypass review by committing directly to `main`.
- A passing unit test or a matching fixture-local TOTAL is evidence for that narrow case only, not proof of full-document correctness.

## 2. Testing philosophy

### 2.1 Source evidence comes first

Every golden expectation must be independently checked against the source PDF. Keep the original PDF and record its printed bulletin date, bulletin number, printed status, filename, and SHA-256. Record page, section/header, product, option type, expiry, strike, column, raw token, and any printed TOTAL relevant to the assertion.

Never infer FINAL/PRELIMINARY from the filename or download time; inspect the status printed inside the PDF.

### 2.2 Prefer FINAL, but do not block collection

- Use FINAL when it is available and retrievable.
- If FINAL is not yet available or cannot be retrieved, retain and use PRELIMINARY rather than blocking collection.
- If both exist, preserve each source and its provenance separately.
- Routine PRELIMINARY-vs-FINAL diffing is not a priority. Do not delay unrelated tests just to compare versions.

### 2.3 Preserve evidence; do not guess

For each field, distinguish:
1. raw source token;
2. normalized value, if conversion is valid;
3. parse status / reason.

Keep literal zero distinct from blank, `----`, `UNCH`, malformed text, and missing cells. Never coerce unresolved input to zero. Do not infer CALL/PUT, expiry, product identity, or B/A meaning from nearby fields or expected arithmetic. Ambiguous or unsupported rows must remain unresolved/quarantined.

### 2.4 Fail closed on identity and arithmetic

Unknown products, missing expiry, and missing/invalid CALL/PUT must not pass the resolved-row gate. TOTAL reconciliation is only valid when the source establishes the measure and the exact row/group scope are additive. A helper's arithmetic result does not establish the semantics of a particular printed TOTAL.

### 2.5 Separate unit, fixture, and end-to-end evidence

- **Unit tests** check isolated parsing or safety functions.
- **Source fixtures** lock manually transcribed values for a specific PDF page and section.
- **PDF-to-fixture integration tests** must exercise actual extraction against independently verified source expectations.
- **Corpus tests** must report coverage and unresolved cases across all pages and groups.
- **Workflow-boundary tests** must establish that diagnostic work cannot unexpectedly change production outputs.

Passing one layer does not imply the next layer is covered.

## 3. Current tests and results

The following CI results were observed for the repository's PG64 test workflow:

| PR / CI run | Result | Evidence and limits |
| --- | --- | --- |
| PR #18 / run #68 | Success | CLI diagnostic boundary test: configured audit output, `BLOCKED_DIAGNOSTIC_ONLY`, and no additional files in the isolated invocation. Does not prove full workflow isolation. |
| PR #19 / run #71 | Success | Header-pattern and unresolved candidate identity unit tests. Does not test PDF cell extraction. |
| PR #20 / run #74 | Success | Existing word-line grouping function tested with synthetic coordinate samples, including left-to-right ordering, vertical jitter, and separation of rows. Does not certify extraction against a real CME PDF. |

PR links:
- https://github.com/ratatatata-git/gold-futures-monito/pull/18
- https://github.com/ratatatata-git/gold-futures-monito/pull/19
- https://github.com/ratatatata-git/gold-futures-monito/pull/20

These are observed test outcomes, not a claim that every test or every historical commit has been re-run at the time this document is read.

### 3.1 Existing source-backed examples

- Page 2 fixture for the 2026-10-05 PRELIMINARY bulletin: four OG5 CALL / GOLD OPTIONS / OCT26 rows. Fixture-local Globex Volume sums to the printed total of 10. Open Interest and Open Interest-change matches are explicitly fixture-only and must not be generalized.
- Page 3 fixture for the same bulletin: three OG3 CALL / GOLD OPTIONS / OCT26 rows, preserving Globex versus Open Outcry High/Low raw tokens, `----`, signed PT changes, `UNCH`, and Delta tokens.
- Integer reconciliation helper tests cover explicit integers, zero, signed values, blanks, `----`, `UNCH`, malformed numeric tokens, MATCH/MISMATCH, unresolved totals, and empty input.

These fixtures are narrow manually transcribed examples. They do not demonstrate comprehensive automated extraction from the PDF.

### 3.2 Coverage gaps that remain

- Coordinate-based extraction validated against real PDF cells and multiple layout variants.
- Full raw-token → normalized-value → parse-status behavior for each supported column type.
- Blank versus zero versus `----` versus `UNCH` across actual extracted PDF cells.
- Reliable section/expiry grouping and TOTAL scope identification.
- Duplicate/missing row detection and explicit handling of quarantined rows.
- Full-corpus row/group counts and comparison to independently verified expectations.
- Deterministic/idempotent reprocessing.
- Isolation at the actual workflow boundary, including confirmation that PG62 production outputs are not confused with PG64 diagnostic outputs.
- TOTAL semantics for fields beyond any narrowly verified source case.

See also [PG64 Test Coverage Matrix](pg64-test-coverage-matrix.md) for the more granular evidence inventory.

## 4. Goals and acceptance path

### P0 — Source-backed fixture integrity

1. Independently verify each existing fixture against its original PDF: page, section, product/type/expiry, strike, column heading, exact raw token, and relevant printed TOTAL.
2. Record source filename, printed bulletin identity/status, and SHA-256 alongside fixture provenance.
3. Add only source-verified cases to the golden test set.
4. Leave unresolved any unclear cell or TOTAL scope; do not create expectations from parser output alone.

**Exit condition:** each fixture used as a golden expectation has auditable source provenance and independent visual verification, or is clearly labelled provisional and excluded from certification claims.

### P1 — Extraction correctness against approved fixtures

1. Add PDF-to-fixture integration tests that run the actual extraction code on the source PDF.
2. Validate coordinate/column assignment, not just token order or synthetic line grouping.
3. Compare extracted raw tokens against approved fixture tokens before testing normalization.
4. Normalize by field type while retaining raw token and explicit parse status.
5. Test real examples of zero, blanks, `----`, `UNCH`, signed values, malformed tokens, and missing cells.
6. Keep unresolved or ambiguous rows visible in audit output; never silently discard or coerce them.

**Exit condition:** approved fixture rows and raw tokens match the PDF extraction exactly for the covered pages, and any unsupported case fails closed with a visible reason.

### P2 — Grouping, totals, and full-corpus audit

1. Identify each product/type/expiry section and its exact printed TOTAL scope.
2. Test duplicate/missing rows, section boundaries, and TOTAL rows that are missing, empty, unresolved, or deliberately mismatched.
3. Reconcile only fields whose additive semantics and row scope have been established from the source.
4. Run every available source PDF through the diagnostic parser and report page count, section/group count, row count, unresolved/quarantined rows, and mismatches.
5. Test repeat processing for deterministic output and idempotency.

**Exit condition:** the corpus report accounts for all pages/groups and explicitly lists every unresolved or mismatched item; no unexplained row loss is hidden by a successful aggregate.

### P3 — Workflow safety and any future promotion review

1. Extend safety tests to the real workflow boundary where feasible.
2. Confirm diagnostic output locations and production outputs remain separate.
3. Review failure handling, provenance retention, reproducibility, fixture approval, and known limitations.
4. Keep the gate blocked until a separate explicit promotion review approves all required evidence.

**Exit condition:** a documented review decision explicitly authorizes or rejects promotion. Passing CI alone is never authorization.

## 5. Manual review protocol

No routine manual review is required merely because a unit test or synthetic coordinate test was added.

When visual verification is needed, the request must be actionable and specific:
- exact PDF filename and SHA-256;
- printed bulletin date, number, and status;
- PDF page number;
- section/product/type/expiry;
- strike row(s);
- exact column heading(s) and raw cell(s) to inspect;
- printed TOTAL and the scope being checked;
- whether the value is an expected fixture, a discrepancy, or unresolved evidence.

Do not ask the owner to compare entire PRELIMINARY and FINAL PDFs unless a specific issue makes that comparison necessary.

## 6. Non-goals and prohibited shortcuts

- Do not treat filename or download timestamp as bulletin status.
- Do not infer missing source facts from product-master metadata, strike order, delta, nearby cells, or a TOTAL.
- Do not generalize one fixture's TOTAL match to other products, expiries, or fields.
- Do not call synthetic-coordinate tests end-to-end PDF validation.
- Do not mark all layouts supported based on a few examples.
- Do not promote PG64 or alter production history without explicit review.

## 7. Next immediate work

1. Keep PR #20's passing synthetic grouping tests as a narrow regression layer.
2. Build the first real PDF-to-fixture integration test from an independently verified source page.
3. Use that test to expose coordinate/column assignment errors before adding broad normalization.
4. Update the coverage matrix as each new capability gains direct evidence.
5. Request owner visual review only for exact unresolved source cells that materially block fixture approval.

**Invariant:** PG64 remains `BLOCKED_DIAGNOSTIC_ONLY` until the separate promotion review.