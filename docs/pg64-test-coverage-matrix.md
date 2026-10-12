# PG64 Test Coverage Matrix

Status: inventory of currently reviewed evidence, not a certification of parser correctness. Coverage labels describe explicit assertions in the reviewed tests, not general support for every PDF layout.

## Evidence reviewed

| Evidence | What it currently demonstrates | What it does not demonstrate |
| --- | --- | --- |
| `tests/test_pg64_manual_source_fixture.py` + `tests/fixtures/pg64_2026-10-05_page2_og5_call_total.json` | Four recorded OG5 CALL OCT26 rows; source page/section/status; settlement and Delta raw tokens; fixture-local Globex Volume total of 10 matches; Open Interest/change comparisons are explicitly limited to this fixture | General TOTAL semantics, other products/types/expiries, parser extraction from PDF, malformed/missing values, a deliberate mismatch |
| `tests/test_pg64_high_low_raw_tokens.py` + `tests/fixtures/pg64_2026-10-05_page3_og3_call_high_low.json` | Three recorded OG3 CALL OCT26 rows; distinct Globex and Open Outcry High/Low raw tokens; `----`, signed PT changes, Delta tokens, and `UNCH`/change markers remain preserved | Numeric normalization, B/A meaning, general column geometry, all page layouts, TOTAL reconciliation |
| `scripts/parse_pg64.py` | Diagnostic parser v5.0.9; product/alias identification and audit output; code states it does not emit production MASTER | Production numeric extraction or production options-history output from PG64 |
| `.github/workflows/parse-cme-gold.yml` | Runs PG64 parser in diagnostic mode for stored PG64 PDFs; generated-data commit step stages PG62 futures and options-history files | A dedicated end-to-end test of all PG64 extracted values; proof that each field is correctly assigned |
| CI for PR #9 | “Test PG64 Parser” run #55 completed successfully, run ID `38150227203` | Does not by itself certify full-document correctness or untested behavior |

## Coverage matrix

Legend:
- **Covered (narrow):** explicit assertions exist for the stated fixture only.
- **Partial:** some relevant evidence exists, but the acceptance behavior is not comprehensively tested.
- **Not evidenced:** no corresponding test was identified in the files reviewed for this matrix. This does not prove no test exists elsewhere.

| Area | Current assessment | Evidence / gap |
| --- | --- | --- |
| Source provenance and section identity | Covered (narrow) | Page 2 and page 3 fixture metadata includes PDF path, trade date, bulletin number/status, page, and section |
| Strike row examples | Covered (narrow) | Four page-2 rows and three page-3 rows |
| Settlement Price / Delta raw token retention | Covered (narrow) | Page-2 and page-3 fixtures |
| Separate Globex vs Open Outcry High/Low assignment | Covered (narrow) | Three page-3 rows |
| Literal `----` marker preservation | Covered (narrow) | Page-3 open/volume fields |
| Negative PT-change sign preservation | Covered (narrow) | Page-3 examples |
| Open Interest change marker preservation (`UNCH`, signed values) | Covered (narrow) | Page-2/page-3 examples |
| Numeric normalization contract (raw token + normalized value + status) | Not evidenced | Reviewed source fixtures primarily store raw tokens; no reviewed numeric-extraction implementation |
| Blank vs numeric zero vs malformed token | Not evidenced | No reviewed negative/edge-case fixture asserting these distinctions |
| Coordinate-based extraction across layout variants | Not evidenced | Narrow examples only; no reviewed automated PDF-to-cell extraction tests |
| Unknown product / unresolved CALL-PUT / expiry fail-closed tests | Partial / not evidenced here | Parser design describes fail-closed behavior, but corresponding test file was not located in the reviewed paths |
| Printed TOTAL group identity | Partial | Page-2 fixture has one explicitly labelled section and TOTAL; no cross-group separation test reviewed |
| Volume TOTAL arithmetic | Covered (narrow) | Page-2 fixture only: row sum 10 equals printed total 10 |
| Open Interest TOTAL semantics | Unresolved | Page-2 equality is explicitly fixture-only; do not generalize |
| Deliberately mismatched TOTAL | Not evidenced | No reviewed negative fixture |
| Duplicate/missing row detection | Not evidenced | No reviewed test |
| Full-document corpus run with row/group counts | Not evidenced | Current workflow runs diagnostic audits, but reviewed workflow has no assertions comparing every extracted row to a golden dataset |
| Reprocessing determinism / idempotency | Not evidenced | No reviewed test |
| Production history isolation | Partial | Parser/workflow structure and documentation state diagnostic-only; a direct regression test proving the production history file cannot change was not located in reviewed paths |
| Explicit gate assertion in every fixture test | Needs cleanup | Page-2 test uses a conditional assertion with ambiguous operator grouping; simplify to assert the known nested status directly |

## Prioritized next work

### P0 — Tighten the current tests
1. Simplify the page-2 gate assertion to an unconditional assertion against `fixture["expected_reconciliation"]["production_master_status"]`.
2. Add a deliberately mismatched TOTAL case and assert the result is MISMATCH (or BLOCKED when identity/inputs are unresolved).
3. Add tests that keep blank, literal zero, `----`, malformed, and ambiguous tokens distinct.

### P1 — Verify the source before defining expected normalized values
1. Record the PDF SHA-256 and the header geometry for every layout intended for support.
2. Manually review rows from more than one product/type/expiry and at least one layout edge.
3. Keep TOTAL scope and Open Interest aggregation unresolved until the source supports a clear rule.

### P2 — Implement numeric extraction against approved fixtures
1. Extract by validated coordinates, not token order alone.
2. Preserve raw token, normalized value, and parse status.
3. Quarantine ambiguous/unsupported rows.
4. Add PDF-to-fixture integration tests before full-corpus reconciliation.

### P3 — Full-corpus and safety gate
1. Report row/group counts, rejected/quarantined rows, and all mismatches for each source PDF.
2. Test duplicate/missing rows and deterministic reprocessing.
3. Directly test that PG64 diagnostic runs do not alter production options history.
4. Keep `BLOCKED_DIAGNOSTIC_ONLY` until a separate promotion review.

## Safety invariant

This matrix does not authorize production promotion. PG64 remains `BLOCKED_DIAGNOSTIC_ONLY`; no fixture-local match is evidence that all PDF layouts or TOTAL rules are correct.
