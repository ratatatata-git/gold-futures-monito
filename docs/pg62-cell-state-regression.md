# PG62 per-cell state regression

Run alongside the historical PDF audit:

```sh
python -m unittest discover -s tests -p "test_pg62_cell_state_regression.py" -v
```

The suite re-parses the exact three PG62 PDFs pinned by `test_pg62_historical_audit.py` and checks state/value consistency for seven scalar fields across all 81 contract/date rows. It uses a small test-side interpretation of raw tokens instead of calling the parser's state/number conversion helpers. It also checks that high and low retain the same source high/low token and that numeric values agree with the corresponding slash-delimited component.

This is a **semantic regression guard**, not independent proof that a token was assigned to the correct PDF column. It consumes the parser's emitted `raw` cell text; a wrong column boundary can still produce a self-consistent result. The next stronger gate is a separately transcribed expected-cell fixture tied to source page and row, followed by an assertion against parser output. Do not label this test as cell-by-cell source certification.

The fixture is deliberately not generated from parser output at test runtime: the test interprets each emitted raw token independently. Source PDFs are identified by the SHA-256 pins in the historical audit test.
