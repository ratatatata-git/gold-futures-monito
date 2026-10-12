# PG64 Source Corpus Inventory

Status: inventory of locally available source PDFs, not a complete PRELIMINARY/FINAL comparison and not a parser certification.

## Purpose and handling

This inventory records the filenames, printed bulletin identity/status, and SHA-256 of PG64 PDFs available in the working corpus on 2026-10-13. Filenames are not authoritative for bulletin date or status: read the first-page header and verify the hash. Exact-hash duplicates are listed separately so they are not counted as independent source evidence.

A PRELIMINARY and a FINAL bulletin must each be verified against its own original PDF. Do not assume the versions should match, and do not use a filename alone to infer the report date. This inventory does not establish which dates have both versions.

## Available files

| Local filename | Printed bulletin date | Bulletin | Printed status | SHA-256 | Inventory note |
|---|---|---:|---|---|---|
| `PG64_2026-09-23(2).pdf` | 2026-09-23 | 183@ | FINAL | `05eb40daaaad9c28a96274faf38c4ebfe5174aa5155a11f4372f9d0b315ffe1f` | FINAL source present; corresponding PRELIMINARY not identified in this inventory |
| `PG64_2026-09-29.pdf` | 2026-09-29 | 187@ | PRELIMINARY | `0aa6f11ca1d107964527c365570e14852f5b3e995734d0d1c77c05bbb0d35f53` | PRELIMINARY source present; corresponding FINAL not identified |
| `PG64_2026-09-30.pdf` | 2026-09-30 | 188@ | PRELIMINARY | `c70a235c4070b05643a775380d700581026704ec27b6df89de463d6869aec7bb` | PRELIMINARY source present; corresponding FINAL not identified |
| `PG64_2026-10-01.pdf` | 2026-10-01 | 189@ | PRELIMINARY | `2a6c51f88ea88ebd33ae2c3a1a12106f2af88c7473523b47cd76f4ec86990dbe` | PRELIMINARY source present |
| `PG64_2026-10-02(1).pdf` | 2026-10-01 | 189@ | FINAL | `a5b4985db086071d7afc8dea011ad471b14d6da1c09a9088db8b5157620be005` | Filename date differs from printed bulletin date |
| `PG64_2026-10-02.pdf` | 2026-10-01 | 189@ | FINAL | `a5b4985db086071d7afc8dea011ad471b14d6da1c09a9088db8b5157620be005` | Exact SHA-256 duplicate of `PG64_2026-10-02(1).pdf`; one source artifact, not two independent versions |
| `PG64_2026-10-05(1).pdf` | 2026-10-05 | 191@ | PRELIMINARY | `29531afc68caa350e9ead38a3813d7d370075b5acb6a22a280ce910fdba37760` | PRELIMINARY source present; corresponding FINAL not identified |
| `PG64_2026-10-05.pdf` | 2026-10-05 | 191@ | PRELIMINARY | `29531afc68caa350e9ead38a3813d7d370075b5acb6a22a280ce910fdba37760` | Exact SHA-256 duplicate of `PG64_2026-10-05(1).pdf`; one source artifact, not two independent versions |

## Current coverage finding

- The available set includes both statuses overall: FINAL for printed dates 2026-09-23 and 2026-10-01; PRELIMINARY for printed dates 2026-09-29, 2026-09-30, 2026-10-01, and 2026-10-05.
- The only same-printed-date PRELIMINARY/FINAL pair identified here is 2026-10-01 (bulletin 189@). The files have different SHA-256 values and should be compared as separate revisions.
- This set does **not** contain an identified FINAL version for 2026-10-05, the date of the existing manually transcribed page-2/page-3 fixtures. Do not call the 2026-10-05 fixture a PRELIMINARY-vs-FINAL test until that FINAL source is obtained and independently reviewed.
- The inventory is based on the locally available files and their first-page printed headers. It does not prove that no other official versions exist elsewhere.

## Next validation steps

1. Compare the 2026-10-01 PRELIMINARY and FINAL PDFs by their own hashes and printed identities.
2. Create separate per-version expected records; then record differences as revision deltas without erasing source provenance.
3. Obtain the 2026-10-05 FINAL PDF before extending the existing 2026-10-05 fixtures into a two-version comparison.
4. Visually verify each selected page, section, strike, raw token, and printed TOTAL against each original PDF.
5. Keep uncertain TOTAL semantics and B/A marker meanings unresolved until source evidence establishes their meaning.

## Safety invariant

This is source-inventory documentation only. It does not authorize production writes or promotion. PG64 remains `BLOCKED_DIAGNOSTIC_ONLY`.
