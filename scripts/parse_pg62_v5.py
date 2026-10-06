#!/usr/bin/env python3
"""PG62 Gold Futures -> fail-closed daily MASTER prototype (v5.0.1).

This implementation deliberately scopes itself to the GC futures table.

Responsibilities:
- Reconstruct the GC futures table from the PDF.
- Preserve source cell state/raw text.
- Distinguish VALUE / SOURCE_NULL / EMPTY / PARSER_ERROR.
- Correctly handle one-sided H/L source cells such as "4378.00B".
- Validate against TOTAL GC FUT.
- Refuse MASTER generation when structural or reconciliation checks fail.

No trading analysis or derived trading signals are produced here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber


PARSER_VERSION = "pg62-gold-v5.0.1"
SCHEMA_VERSION = "pg62.master.daily.v5"

CONTRACT_RE = re.compile(
    r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})$",
    re.I,
)

GC_HEADER_RE = re.compile(
    r"\bGC\s+FUT\s+COMEX\s+GOLD\s+FUTURES\b",
    re.I,
)

NUMBER_RE = re.compile(
    r"^[+-]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)$"
)

NULL_TOKENS = {
    "----",
    "---",
    "--",
    "-",
    "—",
    "–",
}

HILO_INDICATORS = set("ABPRN")

# These are validated against the current PG62 table geometry.
# They are fallback extraction bands, not a substitute for header validation.
BANDS = {
    "contract": (0, 70),
    "open": (70, 180),
    "high_low": (180, 280),
    "settlement": (280, 310),
    "price_change": (310, 365),
    "volume_globex": (365, 455),
    "volume_pnt_pit": (455, 520),
    "open_interest": (520, 565),
    "oi_change": (565, 620),
}


def sha256(path: Path) -> str:
    """Return SHA256 of the source PDF."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def words_by_line(page):
    """Group PDF words into source table lines."""
    words = page.extract_words(
        x_tolerance=1,
        y_tolerance=2,
        keep_blank_chars=False,
    )

    lines = []

    for word in sorted(
        words,
        key=lambda z: (z["top"], z["x0"]),
    ):
        target = next(
            (
                group
                for group in reversed(lines)
                if abs(word["top"] - group["top"]) < 2.5
            ),
            None,
        )

        if target is None:
            lines.append(
                {
                    "top": word["top"],
                    "words": [word],
                }
            )
        else:
            target["words"].append(word)
            target["top"] = sum(
                item["top"] for item in target["words"]
            ) / len(target["words"])

    for group in lines:
        group["words"].sort(key=lambda z: z["x0"])

    return lines


def text_of(words):
    """Reconstruct a readable source line."""
    return " ".join(
        str(word.get("text", "")).strip()
        for word in sorted(words, key=lambda z: z["x0"])
    ).strip()


def cell_words(words, key):
    """Return words whose center x-coordinate belongs to a source column."""
    lo, hi = BANDS[key]

    return [
        word
        for word in words
        if lo <= (word["x0"] + word["x1"]) / 2 < hi
    ]


def raw_cell(words, key):
    """Return raw text and selected PDF words for one source column."""
    selected = cell_words(words, key)

    raw = "".join(
        str(word["text"]).strip()
        for word in selected
    ).strip()

    return raw, selected


def parse_decimal(raw: str):
    """Parse a normal numeric source cell."""
    value = raw.replace(",", "").strip()

    if not value or value.upper() in NULL_TOKENS:
        return None

    if not NUMBER_RE.fullmatch(value):
        return None

    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def parse_signed(raw: str):
    """Parse source fields that may contain +/-, UNCH or NEW."""
    value = re.sub(r"\s+", "", raw).upper()

    if value in {"", *NULL_TOKENS, "NEW"}:
        return None

    if value == "UNCH":
        return Decimal("0")

    if value.startswith("+"):
        value = value[1:]

    return parse_decimal(value)


def state(raw: str, parsed):
    """Return a source-observation state for a single cell."""
    value = raw.strip()
    upper = value.upper()

    if not value:
        return {
            "state": "EMPTY",
            "raw": value,
            "value": None,
        }

    if upper in NULL_TOKENS:
        return {
            "state": "SOURCE_NULL",
            "raw": value,
            "value": None,
        }

    if parsed is None:
        return {
            "state": "PARSER_ERROR",
            "raw": value,
            "value": None,
        }

    return {
        "state": "VALUE",
        "raw": value,
        "value": format(parsed, "f"),
    }


def split_hilo(raw: str):
    """Split a PG62 H/L source cell into independent source components.

    Examples
    --------
    4405.25/4338.00
        -> ("4405.25", "4338.00")

    4439.00B/4372.75A
        -> ("4439.00B", "4372.75A")

    4378.00B
        -> ("4378.00B", "")

    ----/864.80A
        -> ("----", "864.80A")

    87.70B/----
        -> ("87.70B", "----")

    ----
        -> ("----", "----")
    """
    value = re.sub(r"\s+", "", raw).upper()

    if not value:
        return "", ""

    if value in NULL_TOKENS:
        return value, value

    parts = value.split("/")

    if len(parts) == 1:
        return parts[0], ""

    if len(parts) != 2:
        raise ValueError(
            f"Malformed H/L source cell: {raw!r}"
        )

    return parts[0], parts[1]


def parse_hilo_component(raw: str):
    """Parse one independent H/L component.

    The trailing CME source indicator B/A/P/R/N is metadata and is
    removed only for numeric parsing. The original raw component is
    preserved separately by state().
    """
    value = raw.strip().upper()

    if not value or value in NULL_TOKENS:
        return None

    numeric = re.sub(
        r"[ABPRN]$",
        "",
        value,
    )

    return parse_decimal(numeric)


def parse_hilo(raw: str):
    """Parse H/L and return independent raw/value information."""
    high_raw, low_raw = split_hilo(raw)

    high_value = parse_hilo_component(high_raw)
    low_value = parse_hilo_component(low_raw)

    high_state = state(high_raw, high_value)
    low_state = state(low_raw, low_value)

    return high_state, low_state


def contract_from(words):
    """Extract contract month from the contract column."""
    for word in cell_words(words, "contract"):
        value = str(word["text"]).upper()

        if CONTRACT_RE.fullmatch(value):
            return value

    return None


def meta_from(pdf_text: str):
    """Extract PG62 bulletin metadata from source PDF text."""
    statuses = set(
        re.findall(
            r"\b(FINAL|PRELIMINARY)\b",
            pdf_text[:12000],
            re.I,
        )
    )

    statuses = {status.upper() for status in statuses}

    if len(statuses) != 1:
        raise ValueError(
            "PG62 status missing or ambiguous: "
            f"{sorted(statuses)}"
        )

    match = re.search(
        r"PG62\s+BULLETIN\s*#\s*(\d+)\s*@?\s+"
        r"METAL FUTURES PRODUCTS\s+"
        r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+"
        r"([A-Z][a-z]{2})\s+"
        r"(\d{1,2}),\s*(\d{4})",
        pdf_text,
        re.I,
    )

    if not match:
        raise ValueError(
            "Could not identify PG62 bulletin number/date"
        )

    trade_date = datetime.strptime(
        f"{match.group(2)} "
        f"{match.group(3)} "
        f"{match.group(4)}",
        "%b %d %Y",
    ).date().isoformat()

    return {
        "number": int(match.group(1)),
        "trade_date": trade_date,
        "status": next(iter(statuses)),
    }


def parse_pdf(path: Path):
    """Parse and validate one PG62 PDF.

    This function never creates a MASTER file itself.
    MASTER persistence is handled by build_pg62_master.py.
    """
    digest = sha256(path)

    with pdfplumber.open(path) as pdf:
        all_text = "\n".join(
            page.extract_text() or ""
            for page in pdf.pages
        )

        meta = meta_from(all_text)

        rows = []
        totals = []

        target_seen = False
        target_done = False

        pages_with_rows = set()
        geometry = []

        for page_number, page in enumerate(
            pdf.pages,
            1,
        ):
            for group in words_by_line(page):
                words = group["words"]
                line = text_of(words)
                upper = line.upper()

                # Discover the target GC futures section.
                if GC_HEADER_RE.search(upper):
                    target_seen = True
                    continue

                if not target_seen or target_done:
                    continue

                # Source TOTAL row terminates the target table.
                if re.match(
                    r"^TOTAL\s+GC\s+FUT\b",
                    upper,
                ):
                    values = []

                    for key in (
                        "volume_globex",
                        "volume_pnt_pit",
                        "open_interest",
                        "oi_change",
                    ):
                        raw, _ = raw_cell(words, key)

                        if key == "oi_change":
                            parsed = parse_signed(raw)
                        else:
                            parsed = parse_decimal(raw)

                        values.append(
                            {
                                "field": key,
                                **state(raw, parsed),
                            }
                        )

                    totals.append(
                        {
                            "page": page_number,
                            "raw_line": line,
                            "cells": values,
                        }
                    )

                    target_done = True
                    continue

                contract = contract_from(words)

                if not contract:
                    continue

                def get(
                    key,
                    parser=parse_decimal,
                ):
                    raw, selected = raw_cell(words, key)

                    return (
                        state(raw, parser(raw)),
                        selected,
                    )

                # Normal numeric/source fields.
                open_state, _ = get("open")

                settlement_state, _ = get(
                    "settlement"
                )

                price_change_state, _ = get(
                    "price_change",
                    parse_signed,
                )

                volume_globex_state, _ = get(
                    "volume_globex"
                )

                volume_pnt_pit_state, _ = get(
                    "volume_pnt_pit"
                )

                open_interest_state, _ = get(
                    "open_interest"
                )

                oi_change_state, _ = get(
                    "oi_change",
                    parse_signed,
                )

                # H/L is handled as TWO independent source cells.
                hilo_raw, _ = raw_cell(
                    words,
                    "high_low",
                )

                high_state, low_state = parse_hilo(
                    hilo_raw
                )

                source_fields = (
                    open_state,
                    settlement_state,
                    price_change_state,
                    volume_globex_state,
                    volume_pnt_pit_state,
                    open_interest_state,
                    oi_change_state,
                )

                # H/L is allowed to contain EMPTY / SOURCE_NULL on one
                # side. It is not part of the minimum ordinary-field
                # completeness test because one-sided H/L is valid CME
                # source structure.
                observed_count = sum(
                    field["state"] in {
                        "VALUE",
                        "SOURCE_NULL",
                    }
                    for field in source_fields
                )

                if observed_count < 5:
                    raise ValueError(
                        "Unrecognized GC contract row "
                        f"{contract} on page {page_number}: "
                        f"{line}"
                    )

                rec = {
                    "contract": contract,
                    "open": open_state,
                    "high": high_state,
                    "low": low_state,
                    "settlement": settlement_state,
                    "price_change": price_change_state,
                    "volume_globex": volume_globex_state,
                    "volume_pnt_pit": volume_pnt_pit_state,
                    "open_interest": open_interest_state,
                    "oi_change": oi_change_state,
                    "source": {
                        "page": page_number,
                        "raw_line": line,
                        "top": round(
                            group["top"],
                            3,
                        ),
                    },
                }

                # No parser errors are allowed in MASTER-bound fields.
                #
                # H/L is included independently so a malformed H/L
                # component still fails closed, while a legitimate
                # one-sided H/L does not.
                for field in (
                    "open",
                    "high",
                    "low",
                    "settlement",
                    "price_change",
                    "volume_globex",
                    "volume_pnt_pit",
                    "open_interest",
                    "oi_change",
                ):
                    if rec[field]["state"] == "PARSER_ERROR":
                        raise ValueError(
                            "PARSER_ERROR "
                            f"{contract}.{field} "
                            f"page {page_number}: "
                            f"{rec[field]['raw']!r}; "
                            f"line={line}"
                        )

                # Numeric volume/OI fields cannot be negative.
                for field in (
                    "volume_globex",
                    "volume_pnt_pit",
                    "open_interest",
                ):
                    if (
                        rec[field]["state"] == "VALUE"
                        and Decimal(
                            rec[field]["value"]
                        ) < 0
                    ):
                        raise ValueError(
                            f"Negative {field} for "
                            f"{contract}: "
                            f"{rec[field]['value']}"
                        )

                # H/L relationship is checked only when both sides
                # are actually numeric.
                high_value = (
                    Decimal(high_state["value"])
                    if high_state["state"] == "VALUE"
                    else None
                )

                low_value = (
                    Decimal(low_state["value"])
                    if low_state["state"] == "VALUE"
                    else None
                )

                if (
                    high_value is not None
                    and low_value is not None
                    and high_value < low_value
                ):
                    raise ValueError(
                        f"high<low for {contract}: "
                        f"{hilo_raw!r}"
                    )

                rows.append(rec)
                pages_with_rows.add(page_number)

                contract_words = cell_words(
                    words,
                    "contract",
                )

                if contract_words:
                    geometry.append(
                        {
                            "page": page_number,
                            "contract_x": round(
                                min(
                                    word["x0"]
                                    for word in contract_words
                                ),
                                2,
                            ),
                            "row_top": round(
                                group["top"],
                                3,
                            ),
                        }
                    )

        if not target_seen:
            raise ValueError(
                "GC FUT COMEX GOLD FUTURES section not found"
            )

        if not target_done or len(totals) != 1:
            raise ValueError(
                "Missing/ambiguous TOTAL GC FUT; "
                "refusing MASTER"
            )

        if len(rows) < 20:
            raise ValueError(
                "Implausibly incomplete GC table: "
                f"{len(rows)} rows; refusing MASTER"
            )

        contracts = [
            row["contract"]
            for row in rows
        ]

        if len(contracts) != len(set(contracts)):
            raise ValueError(
                "Duplicate contract month in GC table"
            )

        total_map = {
            item["field"]: item
            for item in totals[0]["cells"]
        }

        checks = []

        for field in (
            "volume_globex",
            "volume_pnt_pit",
            "open_interest",
            "oi_change",
        ):
            parsed_values = [
                row[field]
                for row in rows
            ]

            known = [
                item
                for item in parsed_values
                if item["state"] == "VALUE"
            ]

            if not known:
                continue

            aggregate = sum(
                (
                    Decimal(item["value"])
                    for item in known
                ),
                Decimal(0),
            )

            source_total = total_map[field]

            if source_total["state"] != "VALUE":
                raise ValueError(
                    f"TOTAL {field} is not numeric; "
                    "cannot reconcile"
                )

            expected = Decimal(
                source_total["value"]
            )

            check = {
                "field": field,
                "parsed_sum_of_numeric_cells": format(
                    aggregate,
                    "f",
                ),
                "source_total": format(
                    expected,
                    "f",
                ),
                "numeric_cells": len(known),
                "source_null_cells_excluded": sum(
                    item["state"] == "SOURCE_NULL"
                    for item in parsed_values
                ),
                "empty_cells_excluded": sum(
                    item["state"] == "EMPTY"
                    for item in parsed_values
                ),
                "pass": aggregate == expected,
            }

            checks.append(check)

            if aggregate != expected:
                raise ValueError(
                    "TOTAL reconciliation failed "
                    f"for {field}: "
                    f"parsed={aggregate}, "
                    f"source={expected}"
                )

        if len(checks) < 3:
            raise ValueError(
                "Insufficient independent TOTAL "
                "reconciliation checks"
            )

        return {
            "schema_version": SCHEMA_VERSION,
            "parser_version": PARSER_VERSION,
            "dataset": "PG62_GC_FUTURES",
            "trade_date": meta["trade_date"],
            "bulletin": {
                "number": meta["number"],
                "status": meta["status"],
            },
            "semantics": (
                "Source-observed facts only. "
                "Derived total volume, active contract, "
                "indicators and analysis are excluded."
            ),
            "source": {
                "file": path.name,
                "sha256": digest,
                "ingested_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            },
            "validation": {
                "contract_rows": len(rows),
                "pages_with_rows": sorted(
                    pages_with_rows
                ),
                "total_reconciliation": checks,
                "status": "PASS",
            },
            "contracts": rows,
            "source_total": totals[0],
        }


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "pdf",
        type=Path,
    )

    ap.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "data/master/pg62"
        ),
    )

    args = ap.parse_args()

    try:
        data = parse_pdf(args.pdf)

    except Exception as exc:
        print(
            f"FAIL-CLOSED: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    out = (
        args.output_dir
        / data["trade_date"]
        / (
            f"{data['trade_date']}_"
            f"{data['bulletin']['status']}.json"
        )
    )

    out.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if out.exists():
        old = json.loads(
            out.read_text(
                encoding="utf-8"
            )
        )

        if (
            old.get("source", {}).get("sha256")
            == data["source"]["sha256"]
            and old.get("parser_version")
            == PARSER_VERSION
        ):
            print(
                f"SKIP unchanged: {out}"
            )
            return

        raise SystemExit(
            "Refusing to overwrite existing MASTER: "
            f"{out}; use versioned path/archive"
        )

    tmp = out.with_suffix(
        out.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    tmp.replace(out)

    print(
        "PG62 MASTER PASS: "
        f"{out} "
        f"rows={len(data['contracts'])} "
        f"totals={len(data['validation']['total_reconciliation'])}"
    )


if __name__ == "__main__":
    main()
