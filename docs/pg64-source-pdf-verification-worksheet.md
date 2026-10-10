# PG64 Source PDF Verification Worksheet

Status: worksheet only. Values must be transcribed by a reviewer from the rendered source PDF. No values in this document are presumed verified.

## Goal

Capture a small, independently checked sample from the source PDF before implementing numeric extraction or TOTAL reconciliation. Keep the production gate at BLOCKED_DIAGNOSTIC_ONLY until the worksheet is completed, reviewed, and converted into regression fixtures.

## Recommended sample selection

Start with `data/cme-pg64/PG64_2026-10-05.pdf` because the current product-master tests exercise product headers on this fixture. Select at least:

1. One page with a visible main-chain table header and several ordinary strike rows.
2. One page containing a High/Low pair whose values are visually clear.
3. One page containing a printed TOTAL row.
4. If present, one page with a blank cell or a row near a page/layout transition.

Record the actual PDF page number and the printed section/product/type/expiry labels. Do not infer an absent label from adjacent content unless the PDF's layout explicitly establishes that scope.

## A. Source and metadata record

| Item | Reviewer entry |
| --- | --- |
| Repository path | `data/cme-pg64/PG64_2026-10-05.pdf` |
| PDF SHA-256 | To be computed from the exact downloaded fixture |
| PDF page number(s) | To be recorded from the rendered PDF |
| Bulletin number | Transcribe exactly; unresolved if not visible |
| Bulletin status (PRELIMINARY / FINAL / other) | Transcribe exactly; unresolved if ambiguous |
| Trade date printed in source | Transcribe exactly |
| Reviewer / review date | Fill in during review |
| Parser version under comparison | Record exact version |
| PDF layout/header variant | Describe the visible header and any page differences |

## B. Header geometry record

For each distinct layout variant, record the left/right coordinate bounds (or another stable coordinate system) for the visible column headers. Use one coordinate system consistently, for example PDF points measured from the page's left edge.

| Column | Header text as printed | Left bound | Right bound | Notes |
| --- | --- | ---: | ---: | --- |
| Volume | To inspect | | | |
| Open Interest | To inspect | | | |
| Delta | To inspect | | | |
| High/Low | To inspect | | | |
| Settlement Price | To inspect | | | |
| Strike | To inspect | | | |

Do not copy coordinates from one page to another until alignment has been confirmed. Record any rotation, scaling, repeated header, or column movement.

## C. Manually verified row fixture

Create one entry for each selected strike row. Transcribe raw tokens first, then record the intended normalized values. Keep a screenshot/page reference or a short visual locator so another reviewer can reproduce the check.

| Field | Reviewer entry |
| --- | --- |
| PDF page and visual locator | |
| Product label / raw code | |
| Option type as explicitly shown | |
| Expiry/month as explicitly shown | |
| Strike raw token | |
| Volume raw token / expected value | |
| Open Interest raw token / expected value | |
| Delta raw token / expected value | |
| High raw token / expected value | |
| Low raw token / expected value | |
| Settlement Price raw token / expected value | |
| Blank / zero / malformed / ambiguous fields | |
| Does the current parser assign the correct columns? | PASS / FAIL / NOT TESTED |
| Reviewer notes | |

Use separate entries for blank cells, literal zero, negative values, decimals, and High/Low tokens that appear close to adjacent columns. Never record an expected value by copying the parser output; read it independently from the PDF.

## D. TOTAL semantics verification

Complete one entry for every distinct TOTAL layout observed.

| Question | Reviewer entry |
| --- | --- |
| PDF page and section | |
| Exact printed TOTAL label and raw tokens | |
| Product scope explicit in source? | YES / NO / AMBIGUOUS |
| CALL/PUT scope explicit in source? | YES / NO / AMBIGUOUS |
| Expiry scope explicit in source? | YES / NO / AMBIGUOUS |
| Which measures are actually printed as totals? | Transcribe; do not assume |
| Volume total meaning confirmed? | YES / NO / AMBIGUOUS |
| Open Interest total meaning confirmed? | YES / NO / AMBIGUOUS |
| Other aggregation rules stated in source? | |
| Evidence supporting the interpretation | |
| Reviewer conclusion | CONFIRMED / UNRESOLVED |

Do not calculate a reconciliation pass/fail until the scope and semantics of the printed TOTAL are confirmed. If the report does not clearly define a field's total, mark that field NOT_SPECIFIED.

## E. Expected test assertions

Only after manual review, add explicit expected values to automated fixtures for:

- Raw source tokens and normalized values for each selected row.
- Column assignment for all selected numeric fields.
- The exact group identity associated with each TOTAL.
- Which measure(s) can be reconciled for that TOTAL.
- Expected reconciliation result, including a deliberately mismatched fixture.
- Any blank, zero, malformed, or ambiguous cases.

Expected values must be source-derived and reviewed independently. Do not generate expected values from the same parser being tested.

## F. Sign-off gate

- [ ] Source file identity and hash recorded.
- [ ] Every supported header layout has geometry notes.
- [ ] At least 10 rows manually checked, including at least one High/Low pair and one edge case, or document why fewer rows are available.
- [ ] Printed TOTAL scope and measure semantics are confirmed for each layout being implemented.
- [ ] A second pass or independent reviewer confirms the expected values.
- [ ] The checked values have been added as fixtures and tests pass.
- [ ] Diagnostic output still cannot mutate production options history.
- [ ] Production status remains BLOCKED_DIAGNOSTIC_ONLY pending a separate promotion review.

## Important limitation

This worksheet does not claim that the 2026-10-05 PDF has been visually reviewed. It is a structured record for that manual review. Do not mark any item confirmed until the source PDF itself has been opened and inspected.
