# PDF extraction assurance: token coverage and independent evidence

## Status and scope

This is a **fail-closed assurance contract**, not a claim that PG62/PG64 extraction is accurate. The validator checks a local JSON manifest; it does not extract a PDF, authenticate the source, verify a human review, or approve publication. PG64 remains diagnostic-only until its own accuracy and product/expiry resolution gates pass.

## Required invariants

1. Every character-derived token in the extraction inventory has exactly one disposition:
   - `CELL`: assigned to exactly one named cell;
   - `EXPLICIT_IGNORE`: intentionally excluded with a recorded reason;
   - `QUARANTINE`: unresolved/ambiguous with a recorded reason.
2. Missing token assignments, duplicate assignments, unknown token IDs, duplicate inventory IDs, and dispositions without required fields block the gate.
3. A resolved cell requires at least two distinct evidence groups, and at least one group must be independent of layout assignment: `semantic`, `independent_engine`, or `visual`. Reusing the same coordinate definition for both extraction and validation does not count as independent evidence.
4. `UNRESOLVED` is an explicit state, not a value guessed from context. Unresolved values cannot be marked publishable.
5. Definition selection uses a complete structural fingerprint. Exactly one definition must match. Zero or multiple matches block selection; there is no fallback to a “closest” layout.
6. A passing assurance manifest does not alone mean production-ready. Any quarantined token, independent cell review, semantic validation, source provenance, and publication-rights gates must be considered separately.

## Character-first extraction design

The next extractor revision should use PDF character records (text, glyph origin/bounding box, font size, page and span provenance) as its immutable raw inventory. It should not depend on PyMuPDF/pdfplumber word segmentation for the canonical token inventory.

The tokenizer should group characters using font-size-relative horizontal gaps and baseline/vertical overlap, preserving the source character IDs for every derived token. Keep raw character records and derived tokens; do not destructively normalize the source. Test hyphen-minus, en dash, em dash, Unicode minus, signs, decimal points, thousands separators, `UNCH`, `B`, and `----` separately. Unknown or ambiguous glyphs remain `UNRESOLVED`/quarantined pending source review.

Character-first grouping reduces differences caused by engine-level word boundaries, but does not itself prove the resulting cells are correct. Text may overlap, be clipped, be encoded incorrectly, or have unusual reading order.

## Evidence independence

Evidence is grouped by provenance, not by the number of checks:
- `layout`: header anchors, relative X position, cell geometry;
- `semantic`: arithmetic/contract invariants sourced independently from the assigned coordinate;
- `independent_engine`: separately extracted result, with engine and version recorded;
- `visual`: rendered original page reviewed independently with page/cell locator and reviewer/time.

Two checks derived from the same X-band definition are one evidence group. Totals are supplementary only; they cannot replace row-level evidence because errors can cancel. Independent arithmetic should include, when applicable:
- settlement(t) - settlement(t-1) = price change(t);
- open interest(t) - open interest(t-1) = open-interest change(t).

Do not force an identity when the source explicitly marks a value unavailable or the contract is not comparable; record that exception and keep the item unresolved until its semantics are established.

## Definition fingerprint

A fingerprint should include the bulletin type, known edition status, page geometry, normalized header text/locations, section markers, and table structure. It must not be inferred from the filename alone. Store definition ID, schema version, effective interval, author/reviewer, and change rationale. Changes to column bands, grouping thresholds, exceptions, or token normalization require review and multi-date golden regression tests.

## Validation command

```sh
python scripts/validate_pdf_extraction_assurance.py /secure/local/extraction-assurance.json
python -m unittest discover -s tests -p "test_pdf_extraction_assurance.py" -v
```

The JSON manifest and real source values should stay local unless data rights and publication terms have been explicitly cleared. Public tests use synthetic values only.

## Rollout gates

1. PG62 FINAL: run character-first inventory and token-coverage checks; reconcile all selected GC rows against the rendered original; verify arithmetic identities against independently retained prior-day data.
2. Additional PG62 dates: include PRELIM/FINAL revisions, holiday-adjacent sessions, and expiry-heavy days. Never promote PRELIM as standard history.
3. PG64: only after PG62 behavior is stable, run on representative pages and multiple dates. Include continued tables, multiple-row headers, section transitions, OG/weeklies/serials and expiry mappings. Row extraction accuracy and O-04/O-05 product/expiry resolution are separate gates.
4. Report counts separately: characters, derived tokens, cell assignments, explicit ignores, quarantined tokens, independent visual checks, semantic checks, and unresolved cells. Never report only a single “row count”.
