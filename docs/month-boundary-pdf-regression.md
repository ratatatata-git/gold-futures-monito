# Month-boundary PG62 / PG64 PDF regression window

## Window

The initial month-boundary regression window is **2026-09-29 through 2026-10-09 inclusive**. The checked-in source set is expected to contain both PG62 and PG64 PDFs for each weekday in that interval: September 29–30 and October 1–2 and 5–9 (9 dates, 18 PDFs).

## Automated gate

Run:

```sh
python scripts/test_comex_pdf_date_range.py --start-date 2026-09-29 --end-date 2026-10-09
```

The gate fails closed if either report is missing for a weekday, the parsed bulletin date differs from the filename/date under test, the edition is not FINAL, or parser provenance does not match. It reports each PDF's page count and SHA-256.

This gate intentionally exercises the actual checked-in PDFs, not synthetic fixtures. It covers date availability, document identity, parser execution, and provenance across the September/October boundary.

## Limits and next checks

- A passing smoke test is **not** an independent cell-by-cell accuracy review.
- PG62 still needs independently transcribed source cells and daily arithmetic checks for each date.
- PG64 remains diagnostic: the gate does not certify every option row, strike, volume, open interest, settlement, or canonical key.
- The date range covers weekdays in this specific period; for other windows, account for exchange holidays explicitly rather than assuming every weekday must have a bulletin.
- No extracted market data or completed private review worksheet is committed by this test.
