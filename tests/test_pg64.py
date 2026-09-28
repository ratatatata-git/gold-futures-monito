#!/usr/bin/env python3

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# PG64 parser
PARSER = ROOT / "scripts" / "parse_pg64_v1.py"

# PDF fixtures
FIX = ROOT / "pg64_fixtures"

# Test output
OUT = ROOT / "pg64_tests" / "out"
OUT.mkdir(parents=True, exist_ok=True)


EXPECTED = {
    "21": {
        "bulletin_number": 181,
        "status": "PRELIMINARY",
        "codes": {
            "OG",
            "OG1",
            "OG2",
            "OG3",
            "OG4",
            "OMG",
            "G1R",
            "G1W",
            "G2M",
            "G2T",
            "G3M",
            "G3R",
            "G4M",
            "G4T",
            "G4W",
            "G5W",
            "4WG",
        },
        "unresolved_family": set(),
    },
    "23": {
        "bulletin_number": 183,
        "status": "FINAL",
        "codes": {
            "OG",
            "OG1",
            "OG2",
            "OG3",
            "OG4",
            "OMG",
            "G1M",
            "G2R",
            "G3R",
            "G4M",
            "G4W",
            "G5T",
            "G5W",
            "4FG",
            "4WG",
        },
        "unresolved_family": {
            ("MMG", None),
        },
    },
    "25": {
        "bulletin_number": 185,
        "status": "PRELIMINARY",
        "codes": {
            "OG",
            "OG1",
            "OG2",
            "OG3",
            "OG4",
            "OMG",
            "G1R",
            "G1W",
            "G2R",
            "G3R",
            "G4M",
            "G5T",
            "G5W",
            "4FG",
        },
        "unresolved_family": {
            ("MMG", None),
        },
    },
}


FILES = {
    "21": FIX / "PG64_2026-09-21(1).pdf",
    "23": FIX / "PG64_2026-09-23.pdf",
    "25": FIX / "PG64_2026-09-25.pdf",
}


def run_parser(key):
    """Run PG64 parser and return parsed JSON."""

    out = OUT / f"pg64_{key}.json"

    subprocess.run(
        [
            sys.executable,
            str(PARSER),
            str(FILES[key]),
            "-o",
            str(out),
        ],
        check=True,
    )

    return json.loads(out.read_text(encoding="utf-8"))[0]


def test_parser_exists():
    """The PG64 parser must exist at the expected location."""

    assert PARSER.exists(), f"Parser not found: {PARSER}"


def test_fixture_files_exist():
    """All regression PDF fixtures must exist."""

    for key, path in FILES.items():
        assert path.exists(), f"Fixture {key} not found: {path}"


def test_pg64_regression():
    """Run the complete PG64 v1 regression suite."""

    for key, exp in EXPECTED.items():
        data = run_parser(key)

        # Bulletin metadata
        assert (
            data["bulletin"]["bulletin_number"]
            == exp["bulletin_number"]
        ), key

        assert (
            data["bulletin"]["bulletin_status"]
            == exp["status"]
        ), key

        # Product codes
        codes = {
            r["product_code"]
            for r in data["rows"]
            if r["product_code"]
        }

        assert codes == exp["codes"], (
            key,
            f"missing={exp['codes'] - codes}",
            f"unexpected={codes - exp['codes']}",
        )

        # Unresolved product families
        unresolved = {
            (
                r["product_family_label"],
                r["week_number"],
            )
            for r in data["rows"]
            if r["product_code"] is None
        }

        assert unresolved == exp["unresolved_family"], (
            key,
            unresolved,
        )

        # MASTER invariants
        for r in data["rows"]:
            assert r["option_type"] in {
                "CALL",
                "PUT",
                "UNKNOWN",
                None,
            }

            assert r["strike"] is not None

            assert r["product_family_label"]

        # Every resolved code must be an expected code
        assert all(
            r["product_code"] in exp["codes"]
            or r["product_code"] is None
            for r in data["rows"]
        )

        print(
            f"PASS {key}: "
            f"codes={len(codes)} "
            f"rows={len(data['rows'])} "
            f"totals={len(data['totals'])}"
        )


def test_pg64_all_regressions_pass():
    """
    Explicit smoke test.

    This intentionally calls the main regression test so pytest
    reports the suite as an actual test case.
    """

    test_pg64_regression()
