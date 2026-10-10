# PG64 Data Handoff and Production Gate

## Purpose

This document defines the boundary between the current PG64 diagnostic audit and any future normalized Gold Options dataset. It is a review contract, not authorization to enable production output.

**Current state: `BLOCKED_DIAGNOSTIC_ONLY`.** Keep this state until every applicable gate below is implemented, tested, and reviewed.

## Current pipeline (verified)

- `scripts/parse_pg64.py` reads a PG64 PDF and writes an audit JSON under `data/audit/pg64/<trade_date>/`.
- The audit records source-file SHA-256, bulletin metadata candidates, product-header resolutions, candidate strike rows, candidate TOTAL rows, unresolved-state examples, and known limitations.
- The parser explicitly prints that no production MASTER is written.
- `.github/workflows/parse-cme-gold.yml` runs PG62 production parsing and PG64 diagnostic audits. The commit step adds only `data/cme-gc-history.json` and `data/cme-gold-options-history.json`; PG64 audit JSON is not the downstream options-history dataset.
- A successful Actions run means the workflow steps completed. It does **not** mean PG64 options data is complete or production-ready.

## Handoff boundary

Until a dedicated PG64 production parser and validation suite exist:

1. Treat `data/audit/pg64/**` as diagnostic evidence only.
2. Do not consume candidate strike rows or candidate TOTAL rows as complete market data.
3. Do not infer missing option type or expiry from delta, neighboring rows, product-master defaults, or historical observations.
4. Do not promote PG64 audit output into `data/cme-gold-options-history.json`.
5. Preserve the fail-closed production status.

## Proposed normalized row contract (future implementation)

Every production contract observation must be a source-backed row with, at minimum:

| Field | Requirement |
| --- | --- |
| `trade_date` | Resolved bulletin trade date; source status/version must be retained separately |
| `bulletin_number` | Source bulletin identifier |
| `bulletin_status` | Explicitly resolved status such as PRELIMINARY or FINAL; ambiguous status blocks promotion |
| `source_file` / `source_sha256` | Exact input PDF identity |
| `product_code` | Canonical product code with traceable raw source code and alias rule |
| `option_type` | Explicit source-backed CALL or PUT; never inferred from delta |
| `contract_month` | Explicitly resolved source expiry/month |
| `strike` | Parsed numeric strike, preserving raw source token for audit |
| `volume`, `open_interest`, `delta`, `high`, `low`, `settlement_price` | Parsed numeric values from validated column geometry; missing/ambiguous cells must not silently become zero |
| `parser_version` / `schema_version` | Reproducibility and downstream compatibility |

The eventual schema may add fields, but field names, units, null semantics, and revision handling must be versioned before downstream consumers rely on it. The existing diagnostic schema is not this production contract.

## Production gate checklist

All gates are mandatory; a passing subset is not sufficient.

### 1. Source and metadata integrity

- [ ] Trade date, bulletin number, and bulletin status resolve unambiguously from the PDF.
- [ ] Source PDF hash and parser/schema versions are recorded for every output.
- [ ] PRELIMINARY and FINAL observations are retained and linked; a FINAL revision does not erase source history.
- [ ] Duplicate inputs and repeated workflow runs are idempotent.

### 2. Product and contract identity

- [ ] Every production row resolves to a current canonical product using source evidence and an auditable alias rule.
- [ ] Unknown and noncurrent product-header counts are both zero for the candidate production output.
- [ ] Every row has an explicit CALL/PUT type and expiry/month. No unresolved candidate state can enter production.
- [ ] Product-master data is never used to invent source facts absent from the PDF.

### 3. Numeric extraction and reconciliation

- [ ] PDF column geometry is validated against the actual table headers.
- [ ] Overlapping or split High/Low cells have deterministic, fixture-tested reconstruction.
- [ ] Numeric parsing distinguishes blank, zero, malformed, and ambiguous values.
- [ ] Every product/type/expiry group reconciles to its printed TOTAL using documented rules and tolerances.
- [ ] Any mismatch, missing mandatory field, or unparsed relevant row blocks promotion and produces an actionable diagnostic.

### 4. Regression and independent verification

- [ ] Tests cover each available dated fixture, product aliases, month/year boundaries, source revisions, and malformed/ambiguous rows.
- [ ] Expected row counts and numeric values are checked against independently verified PDF examples, not only parser-generated expectations.
- [ ] Tests prove that diagnostic output cannot be mistaken for the production schema and cannot change production history.
- [ ] A full-history replay completes with zero unexplained reconciliation failures.
- [ ] A reviewer approves the schema, reconciliation policy, and sample rows before promotion.

### 5. Controlled promotion

- [ ] Production output is written to a separate, explicitly versioned PG64 dataset.
- [ ] Downstream consumers are tested against that schema before they are switched over.
- [ ] Promotion is an explicit reviewed change; successful CI alone never unlocks the gate.
- [ ] Until all boxes above are checked and reviewed, output remains `BLOCKED_DIAGNOSTIC_ONLY`.

## Next implementation sequence

1. Add tests for the future handoff boundary: confirm diagnostic JSON is not the production options-history schema and does not alter options history.
2. Specify exact numeric columns, units, null semantics, and expiry/TOTAL reconciliation rules from the source PDF layout.
3. Implement numeric row extraction behind a separate diagnostic/test path; compare sample rows with manually verified PDF values.
4. Add per-expiry reconciliation and full-fixture regression checks.
5. Only after the checks and independent review pass, propose a separate production-promotion change.

**This document does not change parser behavior or the production gate.**
