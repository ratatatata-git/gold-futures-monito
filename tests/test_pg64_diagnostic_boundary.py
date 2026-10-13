"""Regression test for the PG64 diagnostic-only CLI output boundary."""
import json
from pathlib import Path

from scripts import parse_pg64


def test_cli_writes_audit_json_only_under_configured_audit_dir(
    monkeypatch, tmp_path, capsys
):
    audit_dir = tmp_path / "isolated-audit"
    source_pdf = tmp_path / "source.pdf"
    source_pdf.write_bytes(b"placeholder; audit is mocked below")

    diagnostic_result = {
        "diagnostic_schema": "pg64.audit.v5",
        "parser_version": parse_pg64.VERSION,
        "dataset": "PG64_GOLD_OPTIONS",
        "trade_date": "2026-10-01",
        "bulletin": {
            "number": 189,
            "status_candidates": ["FINAL"],
        },
        "source": {"file": source_pdf.name, "sha256": "test-hash"},
        "production_master_status": "BLOCKED_DIAGNOSTIC_ONLY",
        "pages": [],
        "pages_with_main_chain_header": [2],
        "product_headers_seen": 1,
        "known_product_headers": 1,
        "unknown_product_headers": 0,
        "candidate_strike_rows": 4,
        "candidate_total_rows": 1,
        "unresolved_state_rows": 0,
    }

    def fake_audit(path, product_master_path, alias_master_path):
        assert path == source_pdf
        return diagnostic_result

    monkeypatch.setattr(parse_pg64, "audit", fake_audit)
    monkeypatch.setattr(
        "sys.argv",
        [
            "parse_pg64.py",
            str(source_pdf),
            "--audit-dir",
            str(audit_dir),
        ],
    )

    parse_pg64.main()

    expected_output = (
        audit_dir / "2026-10-01" / "2026-10-01_FINAL_AUDIT.json"
    )
    assert expected_output.is_file()
    saved = json.loads(expected_output.read_text(encoding="utf-8"))
    assert saved["production_master_status"] == "BLOCKED_DIAGNOSTIC_ONLY"
    assert saved["dataset"] == "PG64_GOLD_OPTIONS"

    # The CLI may create only the configured diagnostic output in this isolated
    # invocation; it must not create history or MASTER files alongside it.
    created_files = {
        p.relative_to(tmp_path)
        for p in tmp_path.rglob("*")
        if p.is_file() and p != source_pdf
    }
    assert created_files == {
        Path("isolated-audit/2026-10-01/2026-10-01_FINAL_AUDIT.json")
    }

    output = capsys.readouterr().out
    assert "PG64 AUDIT ONLY:" in output
    assert "No production MASTER written" in output
    assert "Production gate: BLOCKED_DIAGNOSTIC_ONLY" in output
