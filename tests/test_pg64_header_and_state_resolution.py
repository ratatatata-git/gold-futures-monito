"""Fail-closed tests for PG64 header variants and candidate row identity.

These unit tests validate header recognition and row-state gating only. They do
not claim PDF coordinate extraction or full-document layout support.
"""
import pytest

from scripts.parse_pg64 import (
    PRODUCT_HEADER,
    _is_unresolved_candidate_state,
    normalize_header_code,
)


@pytest.mark.parametrize(
    ("header", "expected_code"),
    [
        ("OG CALL COMEX GOLD OPTIONS", "OG"),
        ("OG5 PUT GOLD OPTIONS", "OG5"),
        ("GMW MON GOLD WEEKLY MONDAY OPTION Week1", "GMW"),
        ("OG3 CALL GOLD OPTION", "OG3"),
    ],
)
def test_product_header_variants_capture_display_code(header, expected_code):
    match = PRODUCT_HEADER.match(header)
    assert match is not None
    assert normalize_header_code(match.group("code")) == expected_code


@pytest.mark.parametrize(
    ("product", "expiry", "option_type"),
    [
        (None, "OCT26", "CALL"),
        ({"status": "UNKNOWN_PRODUCT"}, "OCT26", "CALL"),
        ({"status": "KNOWN_PRODUCT"}, None, "CALL"),
        ({"status": "KNOWN_PRODUCT"}, "", "CALL"),
        ({"status": "KNOWN_PRODUCT"}, "OCT26", None),
        ({"status": "KNOWN_PRODUCT"}, "OCT26", "call"),
        ({"status": "KNOWN_PRODUCT"}, "OCT26", "OTHER"),
    ],
)
def test_unresolved_identity_never_passes_candidate_state_gate(
    product, expiry, option_type
):
    assert _is_unresolved_candidate_state(product, expiry, option_type) is True


@pytest.mark.parametrize("option_type", ["CALL", "PUT"])
def test_known_product_with_expiry_and_explicit_option_type_is_resolved(option_type):
    product = {"status": "KNOWN_PRODUCT"}
    assert _is_unresolved_candidate_state(product, "OCT26", option_type) is False
