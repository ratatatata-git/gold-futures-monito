# PG64 2026-10-01 PRELIMINARY vs FINAL: First-Pass Diff

Status: automated text-extraction comparison; **not yet visually verified**. This is a triage report, not a golden fixture and not a parser correctness claim.

## Source identity

| Version | Local file | Printed bulletin date | Bulletin | Status | SHA-256 |
|---|---|---|---|---|---|
| PRELIMINARY | `PG64_2026-10-01.pdf` | 2026-10-01 | 189@ | PRELIMINARY | `2a6c51f88ea88ebd33ae2c3a1a12106f2af88c7473523b47cd76f4ec86990dbe` |
| FINAL | `PG64_2026-10-02(1).pdf` | 2026-10-01 | 189@ | FINAL | `a5b4985db086071d7afc8dea011ad471b14d6da1c09a9088db8b5157620be005` |

The FINAL file's local filename contains 2026-10-02, but its printed bulletin date is 2026-10-01. A second local file, `PG64_2026-10-02.pdf`, has the same SHA-256 as the FINAL file above and is an exact duplicate.

## Method

- Extracted text from both PDFs with `pdftotext -layout`.
- Compared the 65 extracted page texts after normalizing only the status word (`PRELIMINARY` / `FINAL`).
- Whitespace/layout differences can still produce false positives; repeated strike rows and column alignment require visual confirmation.
- No numeric field is automatically classified as a confirmed revision in this report.

## First-pass result

Text differences were found on pages:
`4, 22, 23, 24, 26, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 51, 52, 54, 55, 56, 57, 63, 64`.

This is 26 of 65 pages. Some differences are spacing or row-order/extraction artifacts; others appear to be changed numeric tokens or row presence. Do not treat the count as 26 pages of confirmed data revisions.

## Candidate differences requiring visual review

These are examples surfaced by text extraction, not approved expected values:

| Page | Extracted candidate | Why it needs review |
|---:|---|---|
| 4 | Strike 4575: one token appears as `4` in PRELIMINARY and `----` in FINAL in the extracted row | Confirm the column and whether the PDF truly changes the raw cell |
| 22 | DEC26 strikes 1500 and 2475, plus 2525: one extracted field appears numeric in PRELIMINARY and `----` in FINAL | Confirm exact column placement and raw glyphs |
| 23 | Strike 4375: extracted trailing fields differ (`536 + 2` vs `534 UNCH`) | Potential position/change revision; verify all columns visually |
| 24 | Strike 5000: extracted trailing fields differ (`11712 + 68` vs `11812 + 168`) | Potential open-interest/change revision; confirm field boundaries |
| 26 | Printed TOTAL line changes from extracted `309876 - 531` to `309974 - 433`; nearby strike 3050 has a numeric token vs `----` in one field | Do not infer TOTAL semantics; verify page layout and printed totals |
| 34 | Strike 6500 and section TOTAL differ in extracted trailing fields | Verify exact column identity and arithmetic scope before interpreting |
| 35–46 | Many rows differ, including row order/presence and numeric tokens | Dense pages have substantial layout/order noise; compare targeted sections visually rather than accepting a line diff |
| 63–64 | Numerous row spacing/ordering differences in extracted text | Likely mixed layout/extraction noise and possible source differences; require visual inspection |

## Required verification before golden fixtures

For each candidate selected for a fixture, a reviewer must confirm against both original PDFs:
1. Page number and section/product/type/expiry.
2. Strike row identity, including duplicate strike values if present.
3. Exact raw token and column header for each changed cell.
4. Printed TOTAL text and its group/scope, without assuming what it sums.
5. Whether the difference is a genuine revision, a layout-only change, or an extraction artifact.

Only after that review should per-version expected records be committed. Keep each version's PDF hash and status in its own provenance record.

## Next step

Start with a small sample where extracted values are relatively easy to isolate (pages 23, 24, and 26), then expand to other layout regions only after visual confirmation. The 2026-10-05 FINAL remains unlocated in the available corpus; this report does not replace that missing source.

## Safety

No parser behavior or production history is changed by this report. PG64 remains `BLOCKED_DIAGNOSTIC_ONLY`.
