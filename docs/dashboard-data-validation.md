# Validate locally generated dashboard data

The COT and FRED panels read generated JSON files, but the ingestion scripts intentionally do not commit them. After reviewing applicable publication terms, generate the files locally:

```sh
python scripts/fetch_cot_gold.py
python scripts/fetch_fred_context.py
python scripts/validate_dashboard_data.py --require-files
python -m unittest discover -s tests -p "test_dashboard_data_contract.py" -v
```

The validator is read-only. It checks the data contract expected by the dashboard: schema version, non-empty records, date format and ordering, COMEX Gold contract identity, Managed Money fields when present, and all three FRED series with finite numeric values or explicit nulls. It does not fetch data, change files, publish files, or assess redistribution rights.

Without `--require-files`, missing generated files are reported as skipped. With the flag, missing files fail validation. A passing result confirms structural compatibility only; it does not verify that the source data is current, economically correct, legally cleared for publication, or suitable as a trading signal.
