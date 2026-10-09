#!/usr/bin/env python3
"""
PG64 product-master integration tests.
This test verifies that the current diagnostic parser:
    PDF
      -> PG64 display code
      -> PG64 alias master
      -> canonical product master
resolves observed Gold option products without guessing.
The existing legacy regression test is intentionally kept separate.
"""
from __future__ import annotations
from pathlib import Path
import pytest
from scripts.parse_pg64 import (
    DEFAULT_ALIAS_MASTER,
    DEFAULT_PRODUCT_MASTER,
    audit,
    load_alias_master,
    load_product_master,
)
# ============================================================
# Paths
# ============================================================
ROOT = Path(__file__).resolve().parent.parent
PG64_DIR = ROOT / "data" / "cme-pg64"
PRODUCT_MASTER = ROOT / DEFAULT_PRODUCT_MASTER
ALIAS_MASTER = ROOT / DEFAULT_ALIAS_MASTER
# ============================================================
# Expected month-boundary fixtures
# ============================================================
EXPECTED_FIXTURES = {
    "2026-09-29",
    "2026-09-30",
    "2026-10-01",
    "2026-10-02",
    "2026-10-05",
}
# ============================================================
# Helpers
# ============================================================
def get_pg64_files() -> list[Path]:
    """Return all PG64 PDFs in the production data directory."""
    if not PG64_DIR.exists():
        raise AssertionError(
            f"PG64 data directory not found: {PG64_DIR}"
        )
    files = sorted(PG64_DIR.glob("*.pdf"))
    if not files:
        raise AssertionError(
            f"No PG64 PDF files found in: {PG64_DIR}"
        )
    return files
def get_fixture_dates(files: list[Path]) -> set[str]:
    """
    Extract YYYY-MM-DD from PG64 filenames.
    The parser itself remains responsible for the authoritative
    trade date from the PDF bulletin.
    """
    dates: set[str] = set()
    for path in files:
        match = __import__("re").search(
            r"(\d{4}-\d{2}-\d{2})",
            path.name,
        )
        if match:
            dates.add(match.group(1))
    return dates
def run_audit(pdf_path: Path) -> dict:
    """Run the current product-master-driven parser directly."""
    return audit(
        pdf_path,
        product_master_path=PRODUCT_MASTER,
        alias_master_path=ALIAS_MASTER,
    )
# ============================================================
# Master-file tests
# ============================================================
def test_product_master_files_exist():
    """Both production product-master files must exist."""
    assert PRODUCT_MASTER.exists(), (
        f"Canonical product master not found: "
        f"{PRODUCT_MASTER}"
    )
    assert ALIAS_MASTER.exists(), (
        f"PG64 alias master not found: "
        f"{ALIAS_MASTER}"
    )
def test_product_master_structure():
    """
    Product masters must load successfully and contain the
    expected current universe.
    """
    products = load_product_master(PRODUCT_MASTER)
    aliases = load_alias_master(ALIAS_MASTER)
    assert products, "Canonical product master is empty."
    assert aliases, "PG64 alias master is empty."
    # Current master created for this project:
    # 117 canonical products and 117 PG64 alias rules.
    assert len(products) == 117, (
        "Unexpected canonical product count: "
        f"{len(products)}; expected 117."
    )
    assert len(aliases) == 117, (
        "Unexpected PG64 alias rule count: "
        f"{len(aliases)}; expected 117."
    )
    # Core Gold products used by the current PG64 files.
    for code in {
        "OG",
        "OG1",
        "OG2",
        "OG3",
        "OG4",
        "OG5",
        "OMG",
    }:
        assert code in {
            row["pg64_display_code"].upper()
            for row in aliases.values()
        }, (
            f"Expected PG64 alias not found: {code}"
        )
# ============================================================
# Fixture availability
# ============================================================
def test_month_boundary_fixtures_exist():
    """
    The five month-boundary PDFs used to validate the product
    master must be present in the repository data directory.
    """
    files = get_pg64_files()
    dates = get_fixture_dates(files)
    missing = EXPECTED_FIXTURES - dates
    assert not missing, (
        "Required PG64 month-boundary fixtures are missing: "
        f"{sorted(missing)}"
    )
# ============================================================
# Product resolution regression test
# ============================================================
def test_all_pg64_pdfs_have_no_unknown_products():
    """
    Every PG64 PDF currently stored in data/cme-pg64 must pass
    product-master resolution.
    UNKNOWN_PRODUCT is a hard failure.
    The parser must never silently invent a canonical product
    code when the PDF product cannot be resolved.
    """
    files = get_pg64_files()
    print()
    print("=" * 78)
    print("PG64 PRODUCT MASTER REGRESSION TEST")
    print("=" * 78)
    print(f"Directory       : {PG64_DIR}")
    print(f"PDF count       : {len(files)}")
    print(f"Product master  : {PRODUCT_MASTER}")
    print(f"Alias master    : {ALIAS_MASTER}")
    print()
    failures: list[str] = []
    for pdf_path in files:
        data = run_audit(pdf_path)
        unknown_count = data["unknown_product_headers"]
        noncurrent_count = data["noncurrent_product_headers"]
        known_count = data["known_product_headers"]
        header_count = data["product_headers_seen"]
        print("-" * 78)
        print(f"PDF             : {pdf_path.name}")
        print(f"Trade date      : {data['trade_date']}")
        print(f"Product headers : {header_count}")
        print(f"Known products  : {known_count}")
        print(f"Unknown         : {unknown_count}")
        print(f"Non-current     : {noncurrent_count}")
        print(
            f"Production gate : "
            f"{data['production_master_status']}"
        )
        if unknown_count:
            print("UNKNOWN PRODUCT EXAMPLES:")
            for item in data["unknown_product_examples"][:10]:
                print(f"  {item}")
            failures.append(
                f"{pdf_path.name}: "
                f"{unknown_count} UNKNOWN_PRODUCT"
            )
        if noncurrent_count:
            failures.append(
                f"{pdf_path.name}: "
                f"{noncurrent_count} "
                f"PRODUCT_MASTER_NONCURRENT"
            )
        assert header_count > 0, (
            f"No Gold option product headers detected: "
            f"{pdf_path.name}"
        )
        assert known_count > 0, (
            f"No known Gold option product headers resolved: "
            f"{pdf_path.name}"
        )
        assert unknown_count == 0, (
            f"UNKNOWN_PRODUCT detected in "
            f"{pdf_path.name}: "
            f"{data['unknown_product_examples'][:10]}"
        )
        assert noncurrent_count == 0, (
            f"Non-current product master entry detected in "
            f"{pdf_path.name}"
        )
        assert (
            data["production_master_status"]
            == "BLOCKED_DIAGNOSTIC_ONLY"
        ), (
            "Product resolution passed, but production gate "
            "returned an unexpected status: "
            f"{data['production_master_status']} "
            f"for {pdf_path.name}"
        )
    print()
    print("=" * 78)
    if failures:
        print("PRODUCT MASTER FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
    print("=" * 78)
    assert not failures, (
        "PG64 product-master regression failures: "
        f"{failures}"
    )
# ============================================================
# OG5-specific regression test
# ============================================================
def test_og5_is_resolved_when_present():
    """
    OG5 is an important month-boundary regression case.
    If the 2026-10-05 PDF is present, the parser must observe
    OG5 and resolve it through the alias/product masters.
    CALL/PUT remains source-derived and is not inferred here.
    """
    candidates = [
        path
        for path in get_pg64_files()
        if "2026-10-05" in path.name
    ]
    if not candidates:
        pytest.fail(
            "2026-10-05 PG64 fixture not found."
        )
    pdf_path = candidates[0]
    data = run_audit(pdf_path)
    og5_headers = [
        item
        for item in data["product_headers"]
        if item["resolution"].get(
            "raw_product_code"
        ) == "OG5"
    ]
    assert og5_headers, (
        "OG5 was not observed in the 2026-10-05 PG64 PDF."
    )
    for item in og5_headers:
        resolution = item["resolution"]
        assert resolution["status"] == "KNOWN_PRODUCT", (
            "OG5 was observed but not resolved as "
            f"KNOWN_PRODUCT: {resolution}"
        )
        assert resolution["canonical_product_code"] == "OG5", (
            "OG5 did not resolve to canonical product OG5: "
            f"{resolution}"
        )
        assert resolution["product_family"], (
            "OG5 resolution is missing product_family: "
            f"{resolution}"
        )
        assert resolution["mapping_basis"], (
            "OG5 resolution is missing mapping_basis: "
            f"{resolution}"
        )
# ============================================================
# No silent fallback test
# ============================================================
def test_unknown_alias_does_not_fallback_to_direct_product():
    """
    The resolver must not silently fall back from WeekN to a
    direct alias.
    This protects against accidentally mapping a weekly product
    to a monthly/direct product when the week information is
    missing or unresolved.
    """
    from scripts.parse_pg64 import ProductResolver
    resolver = ProductResolver(
        product_master_path=PRODUCT_MASTER,
        alias_master_path=ALIAS_MASTER,
    )
    result = resolver.resolve(
        "GMW",
        "GMW MON GOLD WEEKLY MONDAY OPTION",
        page=1,
        top=1.0,
    )
    assert result["status"] == "UNKNOWN_PRODUCT", (
        "Weekly product without WeekN unexpectedly resolved: "
        f"{result}"
    )
    assert result["canonical_product_code"] is None, (
        "Unknown weekly product must not receive a guessed "
        f"canonical product code: {result}"
    )

# ============================================================
# Candidate-state regression test
# ============================================================
def test_unspecified_option_type_is_unresolved():
    """A candidate without explicit CALL/PUT must remain unresolved."""
    from scripts.parse_pg64 import _is_unresolved_candidate_state

    known_product = {"status": "KNOWN_PRODUCT"}
    assert not _is_unresolved_candidate_state(
        known_product,
        "OGZ6",
        "CALL",
    )
    assert not _is_unresolved_candidate_state(
        known_product,
        "OGZ6",
        "PUT",
    )
    assert _is_unresolved_candidate_state(
        known_product,
        "OGZ6",
        "UNSPECIFIED",
    )

