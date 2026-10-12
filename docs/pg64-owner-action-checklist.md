# PG64 Owner Action Checklist

This checklist separates owner-provided source evidence from repository implementation work. It does not authorize production promotion.

## What the owner needs to do now

**No immediate code or terminal work is required.** The repository changes are made through PRs; the most useful owner contribution is source verification.

- [ ] Check the latest CI results for merged PR #13 and confirm that the fail-closed tests ran successfully: https://github.com/ratatatata-git/gold-futures-monito/pull/13
- [ ] Confirm the intended source PDFs are the official PG64 bulletins for the dates in the test corpus, and that each PDF is final or preliminary as recorded.
- [ ] For each golden fixture, visually verify the exact page, section header, strike rows, raw cell tokens, and printed TOTAL against the source PDF. Correct any transcription mismatch before using it as expected test data.
- [ ] For any row or column whose meaning is uncertain (especially Open Interest TOTAL semantics and B/A quote markers), mark it unresolved; do not guess.
- [x] Include both PRELIMINARY and FINAL bulletins in the validation corpus, as requested by the project owner.
- [ ] When both versions exist for a date, verify each against its own original PDF and record bulletin status/identity separately. Do not assume the two versions should match; document differences as revisions unless a source rule says otherwise.
- [ ] Define how superseded/revised bulletins are represented in downstream history without overwriting provenance.

## What I can continue doing

- Add tests for invalid, missing, ambiguous, and deliberately mismatched values.
- Keep raw source tokens separate from normalized values and parse status.
- Build PDF-to-fixture comparisons only for independently verified source examples.
- Check workflow runs and report their actual outcomes.
- Keep the production gate blocked until a separate review.

## Source-review checklist per fixture

Record the PDF filename and SHA-256, bulletin date/number/status, page, section/product/type/expiry, strike, each relevant raw token, printed TOTAL, verification date, and unresolved questions.

## Safety boundary

The current work is diagnostic/test scaffolding. No owner checkbox or passing fixture automatically enables production writes. The required status remains `BLOCKED_DIAGNOSTIC_ONLY`.
