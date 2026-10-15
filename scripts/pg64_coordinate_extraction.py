"""Coordinate-banded extraction of PG64 strike-row cells.

This is an implementation-stage extraction primitive, not a production parser.
It retains source tokens and page coordinates and makes no numeric coercions.
"""
from __future__ import annotations

import re
from statistics import median
from typing import Any

# Boundaries follow the printed PG64 GOLD OPTIONS table geometry (612 pt page).
# Each interval is [left, right); unsupported layouts require review.
COLUMN_BOUNDS: tuple[tuple[str, float, float], ...] = (
    ("strike", 0.0, 38.0),
    ("globex_open", 38.0, 70.0),
    ("open_outcry_open", 70.0, 115.0),
    ("globex_high_low", 115.0, 185.0),
    ("open_outcry_high_low", 185.0, 260.0),
    ("open_outcry_close", 260.0, 320.0),
    ("settlement_price", 320.0, 370.0),
    ("pt_change", 370.0, 397.0),
    ("delta", 397.0, 425.0),
    ("exercises", 425.0, 450.0),
    ("open_outcry_volume", 450.0, 480.0),
    ("globex_volume", 480.0, 510.0),
    ("pnt_volume", 510.0, 545.0),
    ("open_interest", 545.0, 565.0),
    ("open_interest_change", 565.0, 612.0),
)
STRIKE_TOKEN = re.compile(r"^\d{2,5}(?:\.\d+)?$")


def _row_groups(words: list[dict[str, Any]], tolerance: float = 2.5):
    """Group words into visual rows, anchored at each group's median y."""
    ordered = sorted(words, key=lambda word: (float(word["top"]), float(word["x0"])))
    groups: list[list[dict[str, Any]]] = []
    for word in ordered:
        y = float(word["top"])
        target = next(
            (
                group
                for group in reversed(groups)
                if abs(y - median(float(item["top"]) for item in group)) < tolerance
            ),
            None,
        )
        if target is None:
            groups.append([word])
        else:
            target.append(word)
    return groups


def extract_strike_rows(page, *, page_number: int | None = None) -> list[dict[str, Any]]:
    """Extract strike rows into coordinate-banded raw cells.

    Only numeric strike anchors >= 1000 are included. Tokens in a cell are
    joined left-to-right. Empty cells remain empty strings; markers such as
    ---- and UNCH remain literal. No values are numerically normalized.
    """
    words = page.extract_words(
        x_tolerance=1,
        y_tolerance=2,
        keep_blank_chars=False,
    )
    extracted: list[dict[str, Any]] = []
    for group in _row_groups(words):
        ordered = sorted(group, key=lambda word: float(word["x0"]))
        strike_words = [
            word for word in ordered
            if 0.0 <= float(word["x0"]) < 38.0
            and STRIKE_TOKEN.fullmatch(str(word["text"]).strip())
            and float(str(word["text"]).replace(",", "")) >= 1000
        ]
        if not strike_words:
            continue

        if len(strike_words) != 1:
            extracted.append({
                "page": page_number,
                "top": round(median(float(word["top"]) for word in group), 3),
                "status": "AMBIGUOUS_MULTIPLE_STRIKES",
                "strike_candidates": [word["text"] for word in strike_words],
                "raw_line": " ".join(str(word["text"]) for word in ordered),
                "cells": None,
            })
            continue

        cells: dict[str, str] = {}
        cell_words: dict[str, list[dict[str, Any]]] = {}
        for name, left, right in COLUMN_BOUNDS:
            selected = [
                word for word in ordered
                if left <= float(word["x0"]) < right
            ]
            cell_words[name] = selected
            cells[name] = " ".join(str(word["text"]) for word in selected).strip()

        extracted.append({
            "page": page_number,
            "top": round(median(float(word["top"]) for word in group), 3),
            "status": "COORDINATE_CANDIDATE",
            "strike": cells["strike"],
            "raw_line": " ".join(str(word["text"]) for word in ordered),
            "cells": cells,
            "cell_coordinates": {
                name: [
                    {
                        "text": str(word["text"]),
                        "x0": round(float(word["x0"]), 3),
                        "x1": round(float(word["x1"]), 3),
                        "top": round(float(word["top"]), 3),
                    }
                    for word in items
                ]
                for name, items in cell_words.items()
            },
        })
    return extracted
