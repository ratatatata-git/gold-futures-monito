# FRED macro context ingestion — MVP

## Scope

This manual ingestion retrieves three FRED series that provide macro context for gold research:

- `DFII10`: 10-year inflation-indexed Treasury yield (real-yield proxy).
- `DGS10`: 10-year Treasury constant-maturity yield.
- `DTWEXBGS`: nominal broad U.S. dollar index.

Source series and definitions: [FRED](https://fred.stlouisfed.org/). The script uses the public FRED graph CSV endpoint and does not require an API key. Confirm endpoint availability and applicable terms before relying on it operationally.

## Run

From repository root, Python 3.9+:

```sh
python scripts/fetch_fred_context.py --check
python scripts/fetch_fred_context.py
python -m unittest discover -s tests -p "test_fred_context.py" -v
```

The first command fetches and validates current CSV without writing the history file. The second archives the exact response and upserts the cumulative history.

## Data contract

- Raw CSV bytes are archived under `data/fred/raw/<sha256>.csv`.
- Normalized observations are stored in `data/fred/gold-macro-context.json`.
- Each observation carries its observation date, parsed values, original raw values, retrieval timestamp, source URL, payload SHA-256, and raw archive path.
- Missing values (empty or `.`) remain `null`; there is no forward-fill or interpolation.
- Duplicate dates and missing expected columns fail closed.
- Re-running the same payload adds no duplicate observations. A changed value updates the current observation and the earlier raw payload remains archived. Retrieval attempts are appended to a manifest.
- FRED observation dates are not retrieval timestamps. Series have different calendars and may be revised; the record is an observed source snapshot, not proof that the value was available to the market at that time.

## Boundaries

This is research context, not a trading signal. No correlation, causal claim, composite score, or forecast is calculated. Do not commit the generated history/raw files to the public repository until the data publication and redistribution terms have been reviewed. The live CI smoke test validates reachability and shape in a temporary runner only; it does not persist data into the repository.
