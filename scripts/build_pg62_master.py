from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import parse_pg62_v5 as parser


MASTER_VERSION = "pg62.master.daily.v5"


def contains_parser_error(value):
    if isinstance(value, dict):
        if value.get("state") == "PARSER_ERROR":
            return True

        return any(
            contains_parser_error(v)
            for v in value.values()
        )

    if isinstance(value, list):
        return any(
            contains_parser_error(v)
            for v in value
        )

    return False


def build_master(
    pdf_path: Path,
    output_root: Path,
    allow_parser_upgrade: bool = False,
) -> Path:

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF not found: {pdf_path}"
        )

    # ------------------------------------------------------------
    # 1. Parse source PDF with current parser
    # ------------------------------------------------------------

    data = parser.parse_pdf(pdf_path)

    # ------------------------------------------------------------
    # 2. Fail closed on validation
    # ------------------------------------------------------------

    if data.get("validation", {}).get("status") != "PASS":
        raise ValueError(
            "Parser returned data without validation.status == PASS; "
            "MASTER generation refused."
        )

    # ------------------------------------------------------------
    # 3. Never allow PARSER_ERROR into MASTER
    # ------------------------------------------------------------

    if contains_parser_error(data):
        raise ValueError(
            "PARSER_ERROR exists somewhere in parsed data; "
            "MASTER generation refused."
        )

    # ------------------------------------------------------------
    # 4. Validate dataset
    # ------------------------------------------------------------

    if data.get("dataset") != "PG62_GC_FUTURES":
        raise ValueError(
            f"Unexpected dataset: {data.get('dataset')!r}"
        )

    trade_date = data.get("trade_date")

    if not trade_date:
        raise ValueError("Missing trade_date")

    bulletin = data.get("bulletin", {})

    if bulletin.get("status") not in {
        "FINAL",
        "PRELIMINARY",
    }:
        raise ValueError(
            f"Invalid bulletin status: "
            f"{bulletin.get('status')!r}"
        )

    contracts = data.get("contracts", [])

    if len(contracts) < 20:
        raise ValueError(
            f"Implausibly small contract count: "
            f"{len(contracts)}"
        )

    # ------------------------------------------------------------
    # 5. MASTER metadata
    # ------------------------------------------------------------

    data["master"] = {
        "master_version": MASTER_VERSION,
        "status": "VALIDATED",
        "source_observation": True,
        "derived_analysis": False,
    }

    current_parser_version = data.get("parser_version")
    current_source_sha = data.get("source", {}).get("sha256")

    data["build"] = {
        "builder_version": MASTER_VERSION,
        "parser_version": current_parser_version,
        "source_sha256": current_source_sha,
    }

    # ------------------------------------------------------------
    # 6. Determine canonical output path
    # ------------------------------------------------------------

    output_path = (
        output_root
        / trade_date[:4]
        / trade_date[5:7]
        / f"{trade_date}_{bulletin['status']}.json"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ------------------------------------------------------------
    # 7. Existing MASTER handling
    #
    #    Case A:
    #      same PDF SHA + same parser
    #      -> unchanged / idempotent
    #
    #    Case B:
    #      same PDF SHA + newer parser
    #      -> allowed only with --allow-parser-upgrade
    #
    #    Case C:
    #      different PDF SHA
    #      -> NEVER overwrite
    # ------------------------------------------------------------

    if output_path.exists():

        existing = json.loads(
            output_path.read_text(
                encoding="utf-8"
            )
        )

        existing_sha = (
            existing
            .get("source", {})
            .get("sha256")
        )

        existing_parser = (
            existing.get("parser_version")
        )

        # --------------------------------------------------------
        # Case A: identical source + identical parser
        # --------------------------------------------------------

        if (
            existing_sha == current_source_sha
            and existing_parser == current_parser_version
        ):
            print(
                f"UNCHANGED: {output_path}"
            )
            return output_path

        # --------------------------------------------------------
        # Case B: identical source + parser upgrade
        # --------------------------------------------------------

        if (
            existing_sha == current_source_sha
            and existing_parser != current_parser_version
        ):

            if not allow_parser_upgrade:
                raise RuntimeError(
                    "Refusing to overwrite existing MASTER.\n"
                    "Same source PDF, but parser version changed.\n"
                    f"Path: {output_path}\n"
                    f"Source SHA256: {current_source_sha}\n"
                    f"Existing parser: {existing_parser}\n"
                    f"Current parser:  {current_parser_version}\n"
                    "Re-run with --allow-parser-upgrade "
                    "to intentionally rebuild this MASTER."
                )

            print(
                "PARSER UPGRADE REBUILD: "
                f"{output_path}"
            )

            print(
                f"  Existing parser: {existing_parser}"
            )

            print(
                f"  Current parser:  {current_parser_version}"
            )

            print(
                f"  Source SHA256:   {current_source_sha}"
            )

            data["build"]["rebuild"] = {
                "type": "PARSER_UPGRADE",
                "previous_parser_version": existing_parser,
                "new_parser_version": current_parser_version,
                "source_sha256_unchanged": True,
            }

        # --------------------------------------------------------
        # Case C: different source PDF
        # --------------------------------------------------------

        elif existing_sha != current_source_sha:
            raise RuntimeError(
                "Refusing to overwrite existing MASTER.\n"
                "The source PDF SHA256 is different.\n"
                f"Path: {output_path}\n"
                f"Existing SHA256: {existing_sha}\n"
                f"Current SHA256:  {current_source_sha}\n"
                f"Existing parser: {existing_parser}\n"
                f"Current parser:  {current_parser_version}"
            )

    # ------------------------------------------------------------
    # 8. Atomic write
    # ------------------------------------------------------------

    tmp_path = output_path.with_suffix(
        ".json.tmp"
    )

    tmp_path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    tmp_path.replace(output_path)

    # ------------------------------------------------------------
    # 9. Result
    # ------------------------------------------------------------

    print(
        "PG62 MASTER CREATED: "
        f"{output_path} "
        f"rows={len(contracts)} "
        f"status={bulletin['status']}"
    )

    return output_path


def main():

    ap = argparse.ArgumentParser(
        description=(
            "Build canonical PG62 daily MASTER"
        )
    )

    ap.add_argument(
        "pdf",
        type=Path,
        help="PG62 PDF",
    )

    ap.add_argument(
        "--output-root",
        type=Path,
        default=(
            ROOT
            / "data"
            / "master"
            / "pg62"
        ),
        help="Canonical MASTER root",
    )

    ap.add_argument(
        "--allow-parser-upgrade",
        action="store_true",
        help=(
            "Allow rebuilding an existing MASTER "
            "when the source PDF SHA256 is identical "
            "but the parser version has changed. "
            "Different source PDFs are never overwritten."
        ),
    )

    args = ap.parse_args()

    try:

        build_master(
            pdf_path=args.pdf,
            output_root=args.output_root,
            allow_parser_upgrade=(
                args.allow_parser_upgrade
            ),
        )

    except Exception as exc:

        print(
            f"MASTER BUILD FAILED: {exc}",
            file=sys.stderr,
        )

        raise SystemExit(2)


if __name__ == "__main__":
    main()
