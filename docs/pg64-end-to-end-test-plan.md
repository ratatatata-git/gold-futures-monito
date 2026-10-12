# PG64 End-to-End Test Plan

Status: planning document. This plan does not certify the parser or any PDF layout as production-ready.

## Purpose

Define the evidence and exit criteria for moving PG64 from diagnostic-only observation to a separately reviewed production candidate. Passing CI for a small fixture is necessary but not sufficient.

**Safety invariant:** keep production status at `BLOCKED_DIAGNOSTIC_ONLY`. No diagnostic output may write to or mutate production options history. Any promotion requires a separate explicit review after this plan's applicable gates pass.

## Current stage

**Stage 2–3: source-specification verification and regression-fixture construction are in progress.**

Existing evidence includes targeted product-header/diagnostic tests and manually transcribed examples:
- Page 2, `OG5 CALL / GOLD OPTIONS / OCT26`: four strike rows and a printed TOTAL, fixture-local comparisons only.
- Page 3, `OG3 CALL / GOLD OPTIONS / OCT26`: three rows preserving separate Globex/Open Outcry High/Low tokens, `----`, `UNCH`, signs, and Delta tokens.

These examples are narrow. They do not prove correctness across the document, all layouts, or general TOTAL semantics. CI results must be checked per run; a merged PR alone is not evidence that every relevant workflow passed.

## Stages and exit criteria

### Stage 1 — Scope, isolation, and baseline
- [ ] Record the parser version, workflow entry points, expected artifacts, and production write paths.
- [ ] Demonstrate tests can run without modifying production history.
- [ ] Confirm diagnostic output and production history have a hard separation.
- [ ] Record the baseline CI runs and their exact results.

**Exit:** reproducible baseline and verified fail-closed boundary.

### Stage 2 — Source PDF and layout specification
- [ ] Identify each supported PDF/header/layout variant and its source-file identity/hash.
- [ ] Record header text and column geometry for each variant; do not reuse coordinates without verification.
- [ ] Independently transcribe rows spanning ordinary values, decimal values, negative changes, literal zero, blank/marker tokens, and ambiguous/layout-edge cases where present.
- [ ] Record product/code, CALL/PUT, expiry, strike, page and section identity explicitly.
- [ ] Mark unresolved semantics as unresolved instead of guessing.

**Exit:** reviewed source specification for the layouts and fields intended for implementation. The worksheet's proposed 10-row minimum is a starting threshold, not proof of complete coverage.

### Stage 3 — Golden fixtures and unit-level regression tests
- [ ] Keep raw source tokens separate from normalized values and statuses.
- [ ] Cover each supported column, including separate Globex and Open Outcry High/Low fields.
- [ ] Test `----`, blank cells, literal zero, `UNCH`, `NEW`, B/A suffixes, signs, decimals, malformed values, and ambiguous cells as observed in the supported sources.
- [ ] Include deliberately invalid or mismatched fixtures and assert they fail closed.
- [ ] For every fixture, retain provenance and independent visual-review notes.
- [ ] Fix tests so the diagnostic-only gate is asserted unconditionally.

**Exit:** fixtures are independently source-derived; tests cover supported normalization and explicit rejection cases.

### Stage 4 — Parser implementation and unit tests
- [ ] Implement extraction only for source layouts supported by Stage 2.
- [ ] Preserve raw token, normalized value, and parse status separately.
- [ ] Never coerce blank/marker/ambiguous values to zero.
- [ ] Verify column assignment and numeric normalization against the golden fixtures.
- [ ] Reject or quarantine unsupported layouts and malformed rows; do not silently guess.

**Exit:** all unit tests pass, including negative tests, with no unresolved value silently accepted.

### Stage 5 — Full-document integration and reconciliation
- [ ] Run the candidate parser against the full selected PDF corpus and every supported layout.
- [ ] Compare output with independently prepared expected records, not parser-generated expectations.
- [ ] Check row counts, group identity, duplicate/missing rows, page transitions, and error/quarantine counts.
- [ ] Reconcile only fields whose printed TOTAL scope and semantics are independently confirmed.
- [ ] Test a deliberately mismatched TOTAL and confirm the result is flagged.
- [ ] Treat unconfirmed Open Interest or other TOTAL semantics as `NOT_SPECIFIED`/unresolved, not a pass.

**Exit:** documented corpus-level comparison with all differences explained or quarantined; no unexplained mismatches.

### Stage 6 — Workflow, regression, and safety validation
- [ ] Run the relevant CI workflows on the proposed branch and record links/statuses.
- [ ] Verify repeated runs are deterministic and do not introduce unintended history changes.
- [ ] Verify diagnostic failures stop or quarantine the affected data rather than writing partial production output.
- [ ] Verify existing history and unrelated artifacts remain unchanged.
- [ ] Review permissions, triggers, artifact paths, and failure behavior.

**Exit:** all required CI checks pass and the isolation/fail-closed tests are demonstrated.

### Stage 7 — Promotion review (separate decision)
- [ ] Review source coverage, fixture provenance, unresolved cases, integration differences, and CI evidence.
- [ ] Review data-write/migration/rollback behavior separately.
- [ ] Explicitly approve or reject promotion; do not infer approval from merged test PRs.
- [ ] Until approval, retain `BLOCKED_DIAGNOSTIC_ONLY`.

**Exit:** explicit recorded decision by the project owner/reviewer. This plan itself does not authorize promotion.

## Required evidence report

For each stage, record: status (`NOT_STARTED`, `IN_PROGRESS`, `PASS`, `BLOCKED`), commit/PR, source PDF hashes, test command/workflow run URL, counts of tested/accepted/rejected/quarantined rows, known limitations, and reviewer.

Do not report a stage as PASS merely because a fixture exists or a PR merged. Use PASS only when its stated exit criteria have evidence.

## Immediate next actions

1. Confirm the latest fixture PR's required CI result and record the exact run.
2. Complete source/layout review with a compact coverage matrix before adding many more isolated fixtures.
3. Add fixtures for verified edge cases and deliberate rejection/mismatch cases.
4. Only then implement or extend numeric normalization against the reviewed fixtures.
