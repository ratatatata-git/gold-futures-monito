"""Regression tests for the PG64 diagnostic-to-production boundary.

These tests deliberately protect the existing fail-closed contract:
PG64 audit output is diagnostic evidence, not normalized production history.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from scripts.parse_pg64 import (
    DIAGNOSTIC_SCHEMA,
    VERSION,
    audit,
)


ROOT = Path(__file__).resolve().parent.parent
PG64_DIR = ROOT / "data" / "cme-pg64"
OPTIONS_HISTORY = ROOT / "data" / "cme-gold-options-history.json"


def get_fixture() -> Path:
    pdfs = sorted(PG64_DIR.glob("*.pdf"))
    assert pdfs, f"No PG64 fixture PDFs found in {PG64_DIR}"
    return pdfs[-1]


def test_pg64_diagnostic_schema_is_explicitly_not_production():
    """The parser schema/version must clearly identify the diagnostic stage."""
    assert DIAGNOSTIC_SCHEMA == "pg64.audit.v5"
    assert VERSION.startswith("pg64-gold-v")


def test_audit_output_has_diagnostic_only_contract():
    """An actual fixture audit must retain its fail-closed status."""
    result = audit(get_fixture())

    assert result["diagnostic_schema"] == DIAGNOSTIC_SCHEMA
    assert result["parser_version"] == VERSION
    assert result["production_master_status"] == "BLOCKED_DIAGNOSTIC_ONLY"
    assert result["known_unhandled_risks"], (
        "Diagnostic output must explain why it cannot be promoted."
    )
    assert "candidate_examples" in result
    assert "unresolved_examples" in result
    assert "totals_candidates" in result


def test_diagnostic_audit_does_not_mutate_options_history():
    """Calling audit() must not create or modify the downstream history file."""
    before_exists = OPTIONS_HISTORY.exists()
    before_bytes = OPTIONS_HISTORY.read_bytes() if before_exists else None

    result = audit(get_fixture())

    after_exists = OPTIONS_HISTORY.exists()
    after_bytes = OPTIONS_HISTORY.read_bytes() if after_exists else None

    assert after_exists == before_exists
    assert after_bytes == before_bytes
    assert result["production_master_status"] == "BLOCKED_DIAGNOSTIC_ONLY"


def test_diagnostic_output_is_not_the_options_history_schema():
    """Keep the audit envelope separate from the downstream history format."""
    result = audit(get_fixture())

    assert result["diagnostic_schema"] == "pg64.audit.v5"
    assert result["diagnostic_schema"] != "cme-gold-options-history.v1"
    assert "source" in result
    assert "product_master" in result
    assert "candidate_examples" in result
    assert "production_master_status" in result


def test_audit_cli_only_writes_under_audit_directory(tmp_path):
    """CLI invocation should write its audit JSON only to the configured audit dir."""
    audit_dir = tmp_path / "audit-output"

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "parse_pg64.py"),
            str(get_fixture()),
            "--audit-dir",
            str(audit_dir),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, (
        f"Diagnostic CLI failed.\nstdout:\n{completed.stdout}"
        f"\nstderr:\n{completed.stderr}"
    )
    assert "PG64 AUDIT ONLY:" in completed.stdout
    assert "No production MASTER written" in completed.stdout
    outputs = list(audit_dir.rglob("*.json"))
    assert len(outputs) == 1
    written = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert written["diagnostic_schema"] == DIAGNOSTIC_SCHEMA
    assert written["production_master_status"] == "BLOCKED_DIAGNOSTIC_ONLY"
