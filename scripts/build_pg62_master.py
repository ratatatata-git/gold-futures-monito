#!/usr/bin/env python3
"""
Build canonical daily MASTER from the validated PG62 parser.

The parser is responsible for PDF interpretation and validation.
This module is responsible for canonical MASTER persistence only.

Fail-closed:
- parser exception -> no MASTER
- validation status != PASS -> no MASTER
- parser error state -> no MASTER
- existing artifact is never overwritten
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Import the existing parser from the same repository.
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import parse_pg62_v5 as parser


MASTER_VERSION = "pg62.master.daily.v5"


def contains_parser_error(value):
    """Recursively detect any PARSER_ERROR state."""
    if isinstance(value, dict):
        if value.get("state") == "PARSER_ERROR":
            return True
        return any(contains_parser_error(v) for v in value.values())

    if isinstance(value, list):
        return any(contains_parser_error(v) for v in value)

    return False


def build_master(pdf_path: Path, output_root: Path) -> Path:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Parser performs the actual PDF interpretation and fail-closed validation.
    data = parser.parse_pdf(pdf_path)

    # Defensive checks at the MASTER boundary.
    if data.get("validation", {}).get("status") != "PASS":
        raise ValueError(
            "Parser returned data without validation.status == PASS; "
            "MASTER generation refused."
        )

    if contains_parser_error(data):
        raise ValueError(
            "PARSER_ERROR exists somewhere in parsed data; "
            "MASTER generation refused."
        )

    if data.get("dataset") != "PG62_GC_FUTURES":
        raise ValueError(
            f"Unexpected dataset: {data.get('dataset')!r}"
        )

    trade_date = data.get("trade_date")
    bulletin = data.get("bulletin", {})

    if not trade_date:
        raise ValueError("Missing trade_date")

    if bulletin.get("status") not in {"FINAL", "PRELIMINARY"}:
        raise ValueError(
            f"Invalid bulletin status: {bulletin.get('status')!r}"
        )

    contracts = data.get("contracts", [])

    if len(contracts) < 20:
        raise ValueError(
            f"Implausibly small contract count: {len(contracts)}"
        )

    # Canonical MASTER metadata.
    data["master"] = {
        "master_version": MASTER_VERSION,
        "status": "VALIDATED",
        "source_observation": True,
        "derived_analysis": False,
    }

    # Keep the existing parser's source/version/provenance fields intact.
    # Add explicit build metadata without changing observed values.
    data["build"] = {
        "builder_version": MASTER_VERSION,
        "parser_version": data.get("parser_version"),
        "source_sha256": data.get("source", {}).get("sha256"),
    }

    output_path = (
        output_root
        / trade_date[:4]
        / trade_date[5:7]
        / f"{trade_date}_{bulletin['status']}.json"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Immutable MASTER policy.
    if output_path.exists():
        existing = json.loads(
            output_path.read_text(encoding="utf-8")
        )

        existing_sha = (
            existing.get("source", {})
            .get("sha256")
        )

        current_sha = (
            data.get("source", {})
            .get("sha256")
        )

        existing_parser = existing.get("parser_version")
        current_parser = data.get("parser_version")

        if (
            existing_sha == current_sha
            and existing_parser == current_parser
        ):
            print(f"UNCHANGED: {output_path}")
            return output_path

        raise RuntimeError(
            "Refusing to overwrite existing MASTER.\n"
            f"Path: {output_path}\n"
            f"Existing SHA256: {existing_sha}\n"
            f"Current SHA256:  {current_sha}\n"
            f"Existing parser: {existing_parser}\n"
            f"Current parser:  {current_parser}"
        )

    # Atomic write.
    tmp_path = output_path.with_suffix(".json.tmp")

    tmp_path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    tmp_path.replace(output_path)

    print(
        "PG62 MASTER CREATED: "
        f"{output_path} "
        f"rows={len(contracts)} "
        f"status={bulletin['status']}"
    )

    return output_path


def main():
    ap = argparse.ArgumentParser(
        description="Build canonical PG62 daily MASTER"
    )

    ap.add_argument(
        "pdf",
        type=Path,
        help="PG62 PDF",
    )

    ap.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "data" / "master" / "pg62",
        help="Canonical MASTER root",
    )

    args = ap.parse_args()

    try:
        build_master(
            args.pdf,
            args.output_root,
        )
    except Exception as exc:
        print(
            f"MASTER BUILD FAILED: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()
