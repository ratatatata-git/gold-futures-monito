# PG64 Numeric Extraction and TOTAL Reconciliation Rules (Draft)

Status: design contract only. No production numeric extraction is implemented by this document. The production gate must remain BLOCKED_DIAGNOSTIC_ONLY.

## 1. Scope and source-backed column inventory

The current diagnostic parser identifies main-chain pages using the presence of these header tokens:

- VOLUME
- INTEREST (the visible header context includes Open Interest)
- DELTA
- HIGH/LOW
- SETT.PRICE

This is only a page-detection heuristic. It does not prove that individual values have been assigned to the correct columns. Before implementing numeric extraction, inspect representative PDFs visually and record the actual header coordinates, token boundaries, and row geometry for each supported layout.

### Proposed row fields

| Field | Parsing rule | Null / ambiguity policy |
| --- | --- | --- |
| volume | Parse only from the Volume column under the validated header geometry | Blank remains null; malformed or ambiguous token blocks the row |
| open_interest | Parse only from the Open Interest column | Same; do not borrow adjacent values |
| delta | Parse only from Delta column; retain source token and normalized numeric value | Never use delta to infer CALL/PUT or expiry |
| high | Parse the High component of the High/Low column pair | If pair reconstruction is uncertain, both source tokens and row are flagged; do not shift values |
| low | Parse the Low component of the High/Low column pair | Same as High |
| settlement_price | Parse only from Settlement Price column | Blank remains null; do not substitute High/Low or a neighboring token |

Every parsed field should retain its raw token, normalized value, and parse status (PARSED, BLANK, MALFORMED, or AMBIGUOUS). Numeric zero is a valid value and must remain distinct from blank. Never convert missing or malformed values to zero.

The production row identity must be established independently from numeric parsing: trade date, bulletin number/status, source file hash, canonical product, explicit CALL/PUT, expiry/month, and strike. If any identity field is unresolved, the row cannot enter production reconciliation.

## 2. High/Low pair handling

High/Low is a paired field and must not be reconstructed by simply taking the next two numeric tokens. PDF text extraction can interleave tokens from adjacent columns or split a cell.

Required implementation behavior:

1. Use word/cell coordinates relative to a validated header template, not token order alone.
2. Support only layouts demonstrated by source fixtures.
3. Preserve the raw line and token coordinates used for each reconstruction.
4. If a token can plausibly belong to more than one column, mark the row AMBIGUOUS and fail the production candidate batch.
5. Add fixtures for ordinary rows, blank High or Low, split/overlapping tokens, and page-boundary/layout variation before enabling this field.

Do not publish a reconstructed High/Low value until independent visual review agrees with the source PDF.

## 3. TOTAL row identity and grouping

The current diagnostic parser stores a TOTAL candidate's page and the product/type/expiry state active when the line is encountered. These are candidates, not proof of correct grouping.

A future production TOTAL must be associated with exactly one fully resolved group:

(trade_date, bulletin_number, bulletin_status, canonical_product_code, option_type, expiry)

Rules:

- The group identity must be source-backed. Do not carry CALL/PUT or expiry into a group if the PDF has not explicitly established it.
- A TOTAL row with missing, conflicting, or ambiguous group identity is an error, not a wildcard total.
- Do not combine CALL and PUT totals, different expiries, different products, or PRELIMINARY and FINAL bulletins.
- Repeated rows or repeated PDFs must not be silently counted twice.
- If a source layout prints a total at a different hierarchy, document and test that hierarchy explicitly before using it.

## 4. Reconciliation metrics

Reconcile only measures that the PDF explicitly prints as totals and whose aggregation semantics are confirmed from the source layout.

Initial policy:

- Volume: sum eligible option rows in the exact TOTAL group and compare with the printed total when that total is present and its meaning is verified.
- Open interest: do not assume it is additive across strike rows. Confirm the CME report's TOTAL semantics for each supported layout before defining an arithmetic comparison.
- Delta, High, Low, Settlement Price, and Strike: do not sum these to reconcile a TOTAL. They are not additive measures. Any report-specific aggregate must be separately documented and independently verified.
- Never manufacture a missing TOTAL, infer a TOTAL from another group, or use a rounded/estimated value as the expected value.

The exact set of fields reconciled must be declared per source-layout version. Until the source TOTAL semantics have been verified against representative PDFs, the implementation must report reconciliation as NOT_SPECIFIED rather than claim a pass.

### Comparison rules after semantics are verified

- Parse the printed total and each contributing row with the same numeric grammar and units.
- Use exact integer equality for count fields such as volume, unless the source explicitly defines a different unit.
- For decimal fields, define the source precision and a field-specific tolerance before tests are written; never choose tolerance after observing a mismatch.
- Missing, malformed, ambiguous, or identity-unresolved contributing rows make the group reconciliation BLOCKED, not PASS.
- Emit an auditable result per group: expected value, calculated value, difference, row count, excluded/blocked row count, rule version, and status (PASS, MISMATCH, BLOCKED, or NOT_SPECIFIED).
- A mismatch or blocked group blocks promotion of the entire bulletin candidate. Do not publish a partial history as if complete.

## 5. Required test matrix

Before production promotion, tests must cover:

- Every currently available PG64 PDF fixture, with explicit expected group/row counts.
- A small set of manually checked rows for each supported layout, including raw source tokens and expected numeric values.
- Positive and negative numbers, decimals, commas, blanks, literal zero, malformed tokens, and adjacent-column overlap.
- High/Low pair reconstruction and layout changes across pages.
- TOTAL rows with missing product, option type, or expiry state.
- Group separation across product, CALL/PUT, expiry, trade date, and bulletin status.
- Exact reconciliation success, one-unit mismatch, duplicate row, missing row, and blocked/ambiguous row.
- Idempotent reprocessing of the same source PDF.
- Proof that diagnostic runs do not mutate data/cme-gold-options-history.json.

## 6. Acceptance criteria

The numeric extraction implementation may advance from experimental to production-candidate only when:

1. Source layout and TOTAL semantics are documented from the actual PDFs.
2. All production rows have complete source-backed identity.
3. Every supported numeric field is parsed or explicitly rejected; there are no silent defaults.
4. Every required group has a specified reconciliation rule and no unexplained mismatch.
5. The full fixture suite passes and independently reviewed sample rows match the PDF.
6. Output is written to a separate, versioned PG64 dataset and is reviewed before any downstream switch.

Until all criteria are met, keep BLOCKED_DIAGNOSTIC_ONLY.

## 7. Open source-verification questions

These cannot be safely decided from the current diagnostic parser alone:

- Which exact numeric measures the PG64 printed TOTAL summarizes for each report section.
- Whether Open Interest is shown as a group total, a repeated snapshot, or another report-specific aggregate.
- Whether TOTAL rows are always scoped by product + option type + expiry, or if any supported layout uses a different hierarchy.
- The allowed decimal precision and any report-defined rounding behavior.
- Whether all currently stored PDF fixtures cover every relevant column geometry.

These questions require visual inspection of representative source PDFs and manually verified expected values. Do not resolve them by assumption.
