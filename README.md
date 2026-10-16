# Gold Futures Monitor

Gold Futures Monitor is a staged research and decision-support project for COMEX gold futures/options. It is not an automated trading system.

## Start here

- **[Integrated system specification and AI handoff guide](docs/system-specification.md)** — project purpose, architecture, data contracts, validation gates, analysis, web delivery, production operations, open decisions, and instructions for continuing work in a new chat or with another AI.
- [Project purpose and validation plan](docs/project-purpose-and-validation-plan.md)
- [Data state transitions and date contract](docs/data-state-and-date-contract.md)
- [PG64 master/derived-data architecture](docs/pg64-master-derived-data-architecture.md)
- [COT/FRED data-source and publication review checklist](docs/data-source-publication-review.md)
- [Local dashboard data validation guide](docs/dashboard-data-validation.md)

## Current implementation notes

The repository contains existing PG62/PG64 scripts, workflows, test fixtures, historical JSON artifacts, and a PWA. Their existence does **not** by itself prove production-grade accuracy. Synthetic tests, real-PDF reconciliation, history-update safety, public-URL verification, and publication approval are separate gates.

The older manual-import workflow documented below describes existing behavior, not an unconditional recommendation to publish source PDFs or extracted data.

## Legacy PG62 manual-import flow (review before use)

1. Obtain the official CME Daily Bulletin Metals / PG62 PDF in accordance with applicable access terms.
2. Place it in the configured input location.
3. Run the applicable validation and parsing workflow.
4. Review the extraction report and history diff before accepting any generated data.
5. Confirm edition status, validation status, publication rights, and rollback readiness before publishing.

**Important:** PRELIMINARY and FINAL must be tracked as separate source revisions. Standard history must use only a verified FINAL that passes extraction validation. Do not silently substitute PRELIMINARY when FINAL is missing or fails. If edition status is unknown, classify it as `UNCLASSIFIED` until verified.

CME source PDFs, raw extraction, normalized data, and derived data must not be published until the applicable storage and redistribution rights have been reviewed. Do not store credentials in the repository or bypass provider access controls.
