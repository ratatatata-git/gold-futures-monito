# Data source and publication review — COT / FRED

Status: **open review checklist; not legal advice and not publication approval**.

This repository is public and the dashboard is hosted publicly. A source being free to access does not automatically mean its full history, raw payloads, or derived dataset may be republished from this repository.

## FRED macro context series

Review the official series page and the current FRED Services Terms of Use before publishing a generated history file.

| Series | Source shown by FRED | Current review note | Status for public redistribution |
|---|---|---|---|
| `DFII10` | Board of Governors of the Federal Reserve System, via FRED | The series page shows a “data in this graph are copyrighted” notice; its tags include “Public Domain: Citation Requested”. Confirm whether this distinction affects the intended raw-data/file redistribution and follow the series notes. | **Unresolved — do not treat this note as permission** |
| `DGS10` | Board of Governors of the Federal Reserve System, via FRED | The series page shows a “data in this graph are copyrighted” notice; the series tags indicate “Public Domain: Citation Requested”. Confirm current terms and attribution requirements for the exact use. | **Unresolved — do not treat this note as permission** |
| `DTWEXBGS` | Board of Governors of the Federal Reserve System, via FRED | The series page shows a “data in this graph are copyrighted” notice. Confirm the current series tags/notes and any applicable restrictions before redistribution. | **Unresolved — do not treat this note as permission** |

Official references:
- [FRED Services Terms of Use](https://fred.stlouisfed.org/legal/)
- [DFII10 series notes and tags](https://fred.stlouisfed.org/series/DFII10)
- [DGS10 series notes and tags](https://fred.stlouisfed.org/series/DGS10)
- [DTWEXBGS series notes and tags](https://fred.stlouisfed.org/series/DTWEXBGS)

The dashboard now provides series links and a source attribution line. Attribution is good practice, but **attribution alone does not grant redistribution rights**. FRED explains that series can be third-party-owned and that the original data provider’s restrictions still apply. Re-check the live pages before any public deployment because notices and terms can change.

## CFTC COT

- Official CFTC COT reports are available for public download and use according to the CFTC's data page: [Data at CFTC](https://www.cftc.gov/data).
- Report description and publication cadence: [About the COT Reports](https://www.cftc.gov/MarketReports/CommitmentsofTraders/AbouttheCOTReports/index.htm).
- Keep the source attribution and report-date semantics in the UI.
- Before adding raw snapshots or cumulative history to the public repository, document the exact source endpoint, access method, attribution, and any applicable terms. Do not infer that every downstream format or source wrapper has identical terms.

## Release gate before adding generated data files

- [ ] Confirm each series' current copyright/status tag and notes at the source.
- [ ] Confirm public-hosting and redistribution permissions for raw and normalized data.
- [ ] Preserve source attribution and required copyright notices.
- [ ] Decide whether the data files will be public, locally generated only, or served from a private source.
- [ ] Do not commit raw snapshots or generated history while any relevant permission is unresolved.
- [ ] Re-run ingestion and UI checks against a locally generated file before deploying.

For personal local research, keep the generated data in the local working tree and do not commit it. This document records review tasks; it does not certify that any dataset is cleared for public redistribution.
