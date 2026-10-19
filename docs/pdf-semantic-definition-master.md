# PDF semantic definition master (draft)

## Purpose

This master defines what extracted source tokens mean, how raw forms may be interpreted, and which evidence is required before a value can be treated as resolved. It is deliberately separate from PDF text extraction, semantic validation, publication approval, and market-data analysis.

The current master is **draft-only**. Its existence does not certify any PDF value and does not make PG64 production-ready.

## Responsibilities

1. Layout profile: identifies the bulletin family and version of the source layout. A profile is selected by a structural fingerprint, not a filename alone.
2. Field dictionary: names each semantic field, data type, unit, source meaning, normalization rule, permitted states, and evidence requirements.
3. Raw-value rules: defines handling for source nulls, signs, UNCH, marker suffixes, Unicode dashes, and unknown glyphs without losing the original token.
4. Evidence policy: prevents the same coordinate definition from being both the extraction rule and its only proof.
5. Promotion gate: unresolved, quarantined, ambiguously matched, unassigned, or multiply assigned tokens block promotion.

## Master data contract

The versioned seed master is at data/definitions/pdf-field-master.json. IDs are stable identifiers; labels may change. The master itself has a version and status. Each layout profile has its own lifecycle status and fingerprint.

### Field definition properties

- field_id: stable semantic ID
- data_type / unit: expected type and units
- source_semantics: meaning as supported by the source
- normalization: named, testable transformation; not a free-form guess
- allowed_states: VALUE, SOURCE_NULL, and/or UNRESOLVED
- publishable_when: state allow-list; this does not itself grant publication rights
- evidence_groups_required: evidence classes needed to resolve a cell
- status: DRAFT until reviewed against source headers, legends, and multiple dates

## Interpretation rules for tricky tokens

- Preserve raw text and Unicode code points before any normalization.
- ---- is seeded as a draft source-null marker because it appears in the existing PG62 master. Its scope must be confirmed per field and source revision before promotion.
- UNCH is not globally rewritten to zero. The existing parser's zero mapping is recorded as needing an explicit, reviewed semantic rule.
- B is not assigned an assumed meaning. Keep the marker attached to the raw value and quarantine the interpretation until the official source legend is checked.
- Detached + / - signs are combined with a number only when field identity and geometric association both support the join.
- Numeric type checks do not establish field identity: Volume and Open Interest can both be valid integers even if a column was misassigned.

## Fail-closed profile selection

A future profile selector must match exactly one profile using several independent structural signals, such as bulletin family, required header tokens, page geometry, page-count expectations where stable, and a reviewed header fingerprint. Zero matches or multiple matches stop processing. Null fingerprint fields are intentionally incomplete and must not act as wildcards in a production selector.

## Token coverage invariant

For each source character/token, the downstream ledger must record exactly one disposition:

- CELL: assigned to one known field/cell;
- EXPLICIT_IGNORE_WITH_REASON: intentionally ignored with a documented reason; or
- QUARANTINE: retained for review and blocks promotion.

No token may disappear silently or be assigned twice. Unknown token IDs and references to unknown cells block the run.

## Independent verification

The field master is not an oracle. At least two distinct evidence groups are required, and at least one must be independent of the coordinate/layout mapping. Suitable groups include independent visual review of the rendered source page, a second extraction engine with separately inspected disagreements, semantic invariants such as settlement change against prior settlement, and official source legend review for annotations and special values.

The same coordinate range or the same parser output cannot count as two independent sources. Arithmetic checks are corroboration, not substitutes for row-by-row source review.

## Scope and rollout

1. Validate the JSON contract and stable IDs.
2. Review PG62 field labels, units, and markers against official headings and legends.
3. Add independently reviewed layout fingerprints from multiple dates and versions; do not guess coordinates into this master.
4. Build a token-to-cell assignment ledger and a fail-closed resolver.
5. Validate the master against a small PG62 golden set, then multiple dates, PRELIM/FINAL versions, and edge cases.
6. Keep PG64 diagnostic-only until its separate field dictionary, table structures, and source-specific semantics have passed equivalent gates.
7. Keep publication/data redistribution approval as a separate gate.

## Non-goals

This master does not fetch PDFs, extract glyphs, decide whether a visual review was honestly completed, prove OCR/PDF text is accurate, map all PG64 option contract types, or authorize publication. It is a controlled definition source for the next integration phase.
