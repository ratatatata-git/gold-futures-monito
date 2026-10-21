# PG62 historical audit regression checks

This regression suite makes a subset of the recorded PG62 GC audit repeatable against the exact checked-in source PDFs for 2026-10-12, 2026-10-13, and 2026-10-14.

Run:

```sh
python -m unittest discover -s tests -p "test_pg62_historical_audit.py" -v
```

The suite pins each source PDF by SHA-256, checks eight-page source identity, FINAL/date metadata, 27 unique GC contract rows, four TOTAL-row anchors, and the settlement-change arithmetic for all 27 contracts between 2026-10-13 and 2026-10-14. A mismatch or source revision causes a failure instead of silently accepting a changed input.

## What this proves—and what it does not

- It makes source identity, parser behavior, row count, TOTAL reconciliation, and the recorded settlement-change arithmetic repeatable.
- It does **not** independently verify every raw cell against a human-transcribed source fixture. Parser output and arithmetic can agree while a value is assigned to the wrong column.
- The raw-line assertion only confirms that the contract token is present in the parser's retained row text; it is not a full token-to-cell audit.
- The historical manual review for all 27 rows per date remains classified as recorded manual evidence until the exact per-cell worksheet is preserved and compared by an independent check.
- PG64 row/field accuracy remains a separate open gate.

The test uses real repository PDFs as allowed for local verification. It does not generate or commit extracted daily market-history output.
