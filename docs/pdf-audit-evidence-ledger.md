# PDF audit evidence ledger

**Status:** historical evidence catalog; underlying extraction is not certified production-ready.

The machine-readable ledger is `data/verification/pdf-audit-evidence-ledger.json`. It preserves prior audit observations, source identifiers, methods, results, limitations, and remaining gates so later parser/master changes do not erase the distinction between what was checked and what still needs checking.

## Evidence status meanings

- `REPRODUCIBLE_AUTOMATED`: repository code and a command exist to rerun the stated check. The status is a record of a prior run; rerun it to confirm current results. A smoke test is not a cell-accuracy proof.
- `MANUAL_REVIEW_RECORDED`: prior visual/manual review was recorded, but a complete per-cell worksheet is not preserved as a rerunnable evidence package.
- `CROSSCHECK_RECORDED_NOT_REPRODUCIBLE`: prior cross-engine counts were recorded, but the original exact scanner and environment are not preserved well enough to reproduce them.
- `INCOMPLETE`: the stated validation has not been completed.

The ledger intentionally includes limitations for every evidence item. A recorded result must never be silently upgraded to reproducible merely because the repository now has a similarly named script.

## Recorded scope

### PG62 GC, 2026-10-12 to 2026-10-14

The historical audit records 27 GC contract rows for each of the three dates, including manual comparison of the listed price/volume/open-interest fields and preservation of source forms such as `B`, `----`, `UNCH`, and detached signs. For 2026-10-14, the recorded arithmetic cross-check against 2026-10-13 found zero settlement-change mismatches across 27 contracts. A raw-line/token crosscheck recorded 27 rows, zero unparsed rows, and zero token mismatches.

These are preserved as **recorded manual results**, not as fully reproducible row-by-row fixtures. The live PDF smoke test checks source provenance and parser execution; it does not independently verify every cell.

### PG64, 2026-10-14

The historical visual audit records review of all 70 pages. A separately recorded two-engine scan reported 8,529 PyMuPDF candidates, 8,490 pdfplumber candidates, 8,490 y-coordinate matches, 8,480 normalized token-sequence matches, 10 matched rows with token mismatches, 39 PyMuPDF-only rows, and zero pdfplumber-only rows.

The original scanner and exact dependency/configuration set were not preserved in the repository. These counts are therefore **not reproducible yet**. The follow-up diagnostic script is not treated as a faithful reproduction: its split-sign normalization and greedy y-grouping need correction and tests. Neither page review nor row-count agreement proves every option field or canonical contract key.

## Validation

Run:

```sh
python scripts/validate_pdf_audit_evidence_ledger.py
python -m unittest tests.test_pdf_audit_evidence_ledger -v
```

The validator checks only ledger structure and consistency. It does not open PDFs, re-run extraction, verify the identity of the reviewer, or certify any recorded value. CI may confirm the ledger's structural validity without closing the underlying accuracy gates.

## Open gates and next work

1. Turn PG62's recorded 27-row/day checks into deterministic, rerunnable raw-token reconciliation fixtures tied to the exact PDF hash.
2. Preserve a deterministic PG64 scanner, pinned dependency versions, row grouping, and mismatch reports; test split signs and merged/split rows.
3. Independently reconcile every PG64 row and field against source pages. Quarantine unresolved values; do not infer values from row counts.
4. Resolve `----`, `UNCH`, `B`, detached signs, and structural fingerprints before promoting the semantic master from draft.

This ledger does not replace `docs/pdf-extraction-assurance.md`, the source revision manifest, reconciliation reports, or the semantic master. It connects their current state to the historical audit record.
