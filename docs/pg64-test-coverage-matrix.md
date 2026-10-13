# PG64 Test Coverage Matrix

Status: inventory of reviewed evidence, not a certification of parser correctness. Coverage labels describe explicit assertions in the reviewed tests, not general support for every PDF layout.

## Evidence reviewed

| Evidence | What it currently demonstrates | What it does not demonstrate |
| --- | --- | --- |
| `tests/test_pg64_manual_source_fixture.py` + `tests/fixtures/pg64_2026-10-05_page2_og5_call_total.json` | Four recorded OG5 CALL OCT26 rows; source page/section/status; settlement and Delta raw tokens; fixture-local Globex Volume total of 10 matches; Open Interest/change comparisons explicitly limited to this fixture | General TOTAL semantics, other products/types/expiries, parser extraction from PDF, malformed/missing values |
| `tests/test_pg64_high_low_raw_tokens.py` + `tests/fixtures/pg64_2026-10-05_page3_og3_call_high_low.json` | Three recorded OG3 CALL OCT26 rows; distinct Globex and Open Outcry High/Low raw tokens; `----`, signed PT changes, Delta tokens, and `UNCH`/change markers preserved | Numeric normalization, B/A meaning, general column geometry, all page layouts, TOTAL reconciliation |
| `scripts/pg64_reconciliation.py` + `tests/test_pg64_reconciliation.py` | Explicit integer tokens, literal zero and signed values, unresolved blanks/markers/malformed tokens, MATCH/MISMATCH, unresolved TOTAL, and empty-row fail-closed behavior | Whether any particular PG64 field is additive or which rows belong to a printed TOTAL scope |
| `tests/test_pg64_diagnostic_boundary.py` | CLI output is written under the configured audit directory; emitted audit retains `BLOCKED_DIAGNOSTIC_ONLY`; no other files are created by the isolated CLI invocation | Full PDF audit correctness; whether unrelated workflow steps or PG62 code alter production history |
| `scripts/parse_pg64.py` | Diagnostic parser v5.0.9; product/alias identification and audit output; CLI explicitly reports that it does not write a production MASTER | Production numeric extraction or production options-history output from PG64 |
| `.github/workflows/parse-cme-gold.yml` | Runs PG64 parser in diagnostic mode for stored PG64 PDFs; generated-data commit step stages PG62 futures and options-history files | A dedicated end-to-end test of every PG64 extracted value or proof that each field is correctly assigned |

## Coverage matrix

Legend:
- **Covered (narrow):** explicit assertions exist for the stated behavior only.
- **Partial:** some relevant evidence exists, but the acceptance behavior is not comprehensively tested.
- **Not evidenced:** no corresponding test was identified in the reviewed files. This does not prove no test exists elsewhere.

| Area | Current assessment | Evidence / gap |
| --- | --- | --- |
| Source provenance and section identity | Covered (narrow) | Page 2 and page 3 fixture metadata includes PDF path, trade date, bulletin number/status, page, and section |
| Strike row examples | Covered (narrow) | Four page-2 rows and three page-3 rows |
| Settlement Price / Delta raw token retention | Covered (narrow) | Page-2 and page-3 fixtures |
| Separate Globex vs Open Outcry High/Low assignment | Covered (narrow) | Three page-3 rows |
| Literal `----` marker preservation | Covered (narrow) | Page-3 open/volume fields |
| Negative PT-change sign preservation | Covered (narrow) | Page-3 examples |
| Open Interest change marker preservation (`UNCH`, signed values) | Covered (narrow) | Page-2/page-3 examples |
| Integer token parsing: raw integer, zero, signs | Covered (narrow) | Isolated helper tests; not wired into PDF cell extraction |
| Blank vs numeric zero vs marker/malformed token | Covered (narrow) | Helper tests keep these distinct; not a complete token-normalization contract |
| Numeric normalization contract (raw token + normalized value + status) | Partial | Integer helper exists; general field-specific normalization is not implemented |
| Coordinate-based extraction across layout variants | Not evidenced | Narrow examples only; no reviewed automated PDF-to-cell extraction tests |
| Unknown product / unresolved CALL-PUT / expiry fail-closed tests | Partial / not evidenced here | Parser design describes fail-closed behavior; coverage still needs a systematic test inventory |
| Printed TOTAL group identity | Partial | Page-2 fixture has one explicitly labelled section and TOTAL; no cross-group separation test reviewed |
| Volume TOTAL arithmetic | Covered (narrow) | Page-2 fixture only: row sum 10 equals printed total 10 |
| Open Interest TOTAL semantics | Unresolved | Page-2 equality is explicitly fixture-only; do not generalize |
| Deliberately mismatched TOTAL | Covered (helper only) | Isolated helper returns MISMATCH for a deliberately wrong total; no PDF-section integration test |
| Duplicate/missing row detection | Not evidenced | No reviewed test |
| Full-document corpus run with row/group counts | Not evidenced | Workflow runs diagnostic audits, but no reviewed assertions compare every extracted row to an independent golden dataset |
| Reprocessing determinism / idempotency | Not evidenced | No reviewed test |
| Production history isolation | Partial | New CLI boundary test verifies audit output path and no additional files in isolation; full workflow still stages PG62 production history outputs |
| Diagnostic gate in manual fixtures | Covered (narrow) | Page-2 test asserts the fixture's nested gate status unconditionally; page-3 test also asserts diagnostic-only status |

## Operational source-version policy

- Prefer a FINAL bulletin when one is available.
- If FINAL is not yet available or cannot be retrieved, retain and use the available PRELIMINARY bulletin rather than blocking collection.
- Record the PDF's printed bulletin date, status, and SHA-256 so the source version remains traceable.
- If both versions exist, preserve their provenance separately. PRELIMINARY-vs-FINAL diffing is not a required routine task; do not discard a usable source or delay unrelated parser testing solely to compare versions.
- Never infer status from the filename or download time alone; read the PDF's printed status.

## Prioritized next work

### P0 — Source-backed fixture quality
1. Independently verify source page, section, strike, column header, raw token, and printed TOTAL before promoting any manual fixture to a golden expectation.
2. Add fixture cases for independently verified layouts and observed edge tokens.
3. Keep Open Interest and other TOTAL semantics unresolved unless the source establishes the arithmetic scope.

### P1 — Parser implementation against approved fixtures
1. Extract by validated coordinates, not token order alone.
2. Preserve raw token, normalized value, and parse status separately.
3. Quarantine ambiguous/unsupported rows; never silently coerce them to zero.
4. Add PDF-to-fixture integration tests before full-corpus reconciliation.

### P2 — Full-corpus and safety gate
1. Report row/group counts, rejected/quarantined rows, and all mismatches for each source PDF.
2. Test duplicate/missing rows and deterministic reprocessing.
3. Extend the production-isolation test to the actual workflow boundary where feasible.
4. Keep `BLOCKED_DIAGNOSTIC_ONLY` until a separate promotion review.

## Safety invariant

This matrix does not authorize production promotion. PG64 remains `BLOCKED_DIAGNOSTIC_ONLY`; no fixture-local match is evidence that all PDF layouts or TOTAL rules are correct.
