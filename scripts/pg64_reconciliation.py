"""Small, fail-closed helpers for explicitly additive PG64 integer fields.

These helpers are not wired into production history generation. Callers must
first establish that a field's printed TOTAL is additive for the specific
source section. Unknown tokens never become zero.
"""

from __future__ import annotations

import re
from typing import Iterable

_INTEGER_TOKEN = re.compile(r"^[+-]?\s*\d+$")


def parse_integer_token(raw_token: str | None) -> int | None:
    """Parse an explicit integer token; return None for blank/marker/ambiguous text."""
    if raw_token is None:
        return None
    token = raw_token.strip()
    if not token or token == "----" or not _INTEGER_TOKEN.fullmatch(token):
        return None
    return int(token.replace(" ", ""))


def reconcile_integer_total(
    row_tokens: Iterable[str | None],
    printed_total_token: str | None,
) -> dict[str, object]:
    """Compare a row sum with a printed TOTAL, failing closed on any unresolved token.

    This arithmetic helper must only be used after the caller verifies that the
    measure is additive and the rows belong to the exact TOTAL scope.
    """
    raw_rows = list(row_tokens)
    parsed_rows = [parse_integer_token(token) for token in raw_rows]
    parsed_total = parse_integer_token(printed_total_token)

    if parsed_total is None or any(value is None for value in parsed_rows):
        return {
            "status": "UNRESOLVED",
            "row_sum": None,
            "printed_total": parsed_total,
            "unresolved_row_indices": [
                index for index, value in enumerate(parsed_rows) if value is None
            ],
        }

    row_sum = sum(value for value in parsed_rows if value is not None)
    return {
        "status": "MATCH" if row_sum == parsed_total else "MISMATCH",
        "row_sum": row_sum,
        "printed_total": parsed_total,
        "unresolved_row_indices": [],
    }
