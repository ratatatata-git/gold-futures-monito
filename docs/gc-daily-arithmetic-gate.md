# PG62 GC daily arithmetic gate

This local gate checks two identities for the same contract across consecutive
FINAL bulletin dates:

- `settlement(t) - settlement(t-1) == price_change(t)`
- `open_interest(t) - open_interest(t-1) == oi_change(t)`

It is intentionally separate from parser provenance, source-image review, the
semantic field master, and publication approval.

## Run locally

```sh
python scripts/validate_gc_daily_series.py path/to/local-gc-history.json --output path/to/local-report.json
```

The input must contain an `observations` array with `date`, `contract`,
`source_status`, `settlement`, `price_change`, `open_interest`, and
`oi_change`. Values may be scalars or semantic cells with `state=VALUE`
and `value`.

## Gate meanings

- `PASS`: every applicable identity was checked and matched.
- `INCOMPLETE`: no mismatch was found, but one or more checks could not be
  made (first date, absent prior contract, null/unresolved value). This is not
  an approval and must not be reported as PASS.
- `BLOCKED`: at least one arithmetic mismatch or malformed/duplicate input.

PRELIMINARY observations are excluded and never serve as the prior FINAL.
The preceding date means the previous distinct FINAL bulletin date present in
the supplied history; production orchestration must ensure the supplied history
has no missing bulletin dates before treating this as a consecutive-day check.

## Limits

Arithmetic catches inconsistencies between adjacent values, but a wrong value
repeated across dates can pass. Continue original-PDF visual sampling and an
external-source cross-check. This script does not connect or approve the draft
semantic field master, certify extraction accuracy, or grant data rights.
