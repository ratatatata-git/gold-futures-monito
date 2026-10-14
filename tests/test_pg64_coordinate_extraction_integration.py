"""Integration checks for coordinate-banded raw-cell extraction from a real PG64 PDF."""
from pathlib import Path

import pdfplumber
import pytest

from scripts.pg64_coordinate_extraction import extract_strike_rows


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PDF = ROOT / "data" / "cme-pg64" / "PG64_2026-10-05.pdf"


@pytest.fixture(scope="module")
def source_pages():
    if not SOURCE_PDF.exists():
        pytest.skip("Repository source PDF is not present in this checkout")
    with pdfplumber.open(SOURCE_PDF) as pdf:
        # Materialize the two pages while the PDF handle is open.
        yield [extract_strike_rows(pdf.pages[index], page_number=index + 1)
               for index in (1, 2)]


def test_real_pdf_page_2_extracts_og5_call_raw_cells(source_pages):
    rows = source_pages[0]
    candidates = [
        row for row in rows
        if row.get("status") == "COORDINATE_CANDIDATE"
        and row["cells"]["strike"] == "4100"
        and row["cells"]["settlement_price"] == "121.20"
        and row["cells"]["delta"] == ".6111"
    ]

    assert len(candidates) == 1
    cells = candidates[0]["cells"]
    assert cells["globex_volume"] == "1"
    assert cells["open_interest"] == "1"
    assert cells["open_interest_change"] == "+ 1"
    assert candidates[0]["page"] == 2


def test_real_pdf_page_3_preserves_markers_and_separates_high_low_cells(source_pages):
    rows = source_pages[1]
    candidates = [
        row for row in rows
        if row.get("status") == "COORDINATE_CANDIDATE"
        and row["cells"]["strike"] == "4550"
        and row["cells"]["settlement_price"] == "1.60"
        and row["cells"]["delta"] == ".0187"
    ]

    assert len(candidates) == 1
    cells = candidates[0]["cells"]
    assert cells["globex_open"] == "----"
    assert cells["open_outcry_open"] == "----"
    assert cells["globex_high_low"] == "2.60B/1.70A"
    assert cells["open_outcry_high_low"] == "2.60B/1.70A"
    assert cells["pt_change"] == "- 0.80"
    assert cells["globex_volume"] == "----"
    assert cells["open_interest"] == "18"
    assert cells["open_interest_change"] == "UNCH"
    assert candidates[0]["page"] == 3
