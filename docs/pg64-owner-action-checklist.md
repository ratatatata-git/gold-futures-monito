# PG64 Owner Action Checklist

This checklist separates owner-provided source evidence from repository implementation work. It does not authorize production promotion.

## What the owner needs to do now

**No immediate code or terminal work is required.** The repository changes are made through PRs; the most useful owner contribution is source verification.

- [ ] Review/merge PR #13 only after its CI checks finish successfully: https://github.com/ratatatata-git/gold-futures-monito/pull/13
- [ ] Confirm the intended source PDFs are the official PG64 bulletins for the dates in the test corpus, and that each PDF is final or preliminary as recorded.
- [ ] For each golden fixture, visually verify the exact page, section header, strike rows, raw cell tokens, and printed TOTAL against the source PDF. Correct any transcription mismatch before using it as expected test data.
- [ ] For any row or column whose meaning is uncertain (especially Open Interest TOTAL semantics and B/A quote markers), mark it unresolved; do not guess.
- [ ] When new PDF dates are added, confirm whether the corpus should include preliminary bulletins, final bulletins, or both, and how revised bulletins should be represented.

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
