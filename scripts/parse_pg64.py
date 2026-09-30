#!/usr/bin/env python3
"""Parse CME PG64 Gold options bulletins into production MASTER JSON.

RAW -> MASTER only.
No IV / Gamma / GEX / dealer positioning / trading-regime analytics are written.

Design:
- Input: one PDF or all PDFs under data/cme-pg64/
- Output: one MASTER JSON per bulletin under data/pg64/
- Gold sections are discovered semantically; page number never defines meaning.
- Gold Weekly PDF family labels are mapped to official CME product codes via WEEK.
- PDF word coordinates are used for local table extraction.
- TOTAL rows are preserved separately and never parsed as option strikes.
- EOO / Block is preserved separately from the main option table.
- PRELIMINARY and FINAL bulletins are retained independently.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber

try:
    import pypdf
except ImportError:  # pragma: no cover
    pypdf = None

PARSER_VERSION = "pg64-gold-v1.1.0"
SCHEMA_VERSION = "pg64.master.v1"

# Possible CME Product Master codes, not simultaneously listed contracts.
PRODUCT_CODES = {"OG", "OMG", *(f"OG{i}" for i in range(1, 6))}
PRODUCT_CODES |= {f"G{i}{d}" for d in "MTWR" for i in range(1, 6)}
PRODUCT_CODES |= {f"{i}MG" for i in range(1, 6)}
PRODUCT_CODES |= {f"{i}WG" for i in range(1, 6)}
PRODUCT_CODES |= {f"{i}FG" for i in range(1, 6)}

FAMILY_META = {
    "GMW": ("GOLD_WEEKLY", "MONDAY"),
    "GWT": ("GOLD_WEEKLY", "TUESDAY"),
    "GWW": ("GOLD_WEEKLY", "WEDNESDAY"),
    "GWR": ("GOLD_WEEKLY", "THURSDAY"),
    "MMG": ("MICRO_GOLD_WEEKLY", "MONDAY"),
    "WMG": ("MICRO_GOLD_WEEKLY", "WEDNESDAY"),
    "FMG": ("MICRO_GOLD_WEEKLY", "FRIDAY"),
}

# These are validation anchors only. Meaning is discovered from the page/header.
EXPECTED_X = {
    "delta": 411,
    "exercises": 437,
    "pnt_volume": 521,
    "open_interest": 574,
}

EXPIRY_RE = re.compile(r"^(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2}$", re.I)
STRIKE_RE = re.compile(r"^\d{2,5}(?:\.\d+)?$")
NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)$")

GOLD_HEADER_RE = re.compile(
    r"\b(?:OG\d?|OMG|GMW|GWT|GWW|GWR|MMG|WMG|FMG)\b.*\bGOLD\b.*\bOPTION",
    re.I,
)


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return None if value in {"----", "—", "- - - -"} else value


def number(value: str | None):
    value = clean_text(value)
    if value is None:
        return None
    value = value.replace(",", "")
    if not NUMBER_RE.fullmatch(value):
        return None
    try:
        n = float(value)
    except ValueError:
        return None
    return int(n) if n.is_integer() else n


def parse_change(value: str | None):
    value = clean_text(value)
    if value is None:
        return None, None
    u = value.upper()
    if u == "NEW":
        return None, "NEW"
    if u == "UNCH":
        return 0, "UNCH"
    n = number(value)
    return n, None


def parse_bulletin_meta(text: str) -> dict[str, Any]:
    status = None
    head = text[:3000].upper()
    if re.search(r"\bFINAL\b", head):
        status = "FINAL"
    elif re.search(r"\bPRELIMINARY\b", head):
        status = "PRELIMINARY"

    m = re.search(
        r"PG64\s+BULLETIN\s*#\s*(\d+).*?"
        r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s*"
        r"([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})",
        text,
        re.I | re.S,
    )
    if not m:
        m = re.search(
            r"PG64\s+BULLETIN\s*#\s*(\d+).*?"
            r"([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})",
            text,
            re.I | re.S,
        )
    if not m:
        return {
            "bulletin_number": None,
            "trade_date": None,
            "bulletin_status": status,
        }

    month, day, year = m.group(2), int(m.group(3)), int(m.group(4))
    trade_date = datetime.strptime(
        f"{month} {day} {year}", "%b %d %Y"
    ).date().isoformat()
    return {
        "bulletin_number": int(m.group(1)),
        "trade_date": trade_date,
        "bulletin_status": status,
    }


def family_to_code(label: str, week: int | None, direct: str | None):
    if direct:
        return direct if direct in PRODUCT_CODES else None
    if week is None:
        return None
    mapping = {"GMW": "M", "GWT": "T", "GWW": "W", "GWR": "R"}
    if label in mapping:
        code = f"G{week}{mapping[label]}"
    elif label == "MMG":
        code = f"{week}MG"
    elif label == "WMG":
        code = f"{week}WG"
    elif label == "FMG":
        code = f"{week}FG"
    else:
        return None
    return code if code in PRODUCT_CODES else None


def parse_family_header(line: str):
    u = re.sub(r"\s+", " ", line.upper()).strip()
    m = re.match(r"(OG\d?|OMG|GMW|GWT|GWW|GWR|MMG|WMG|FMG)\b", u)
    if not m or "GOLD" not in u or "OPTION" not in u:
        return None

    label = m.group(1)
    week_m = re.search(r"\bWEEK\s*([1-5])\b", u)
    week = int(week_m.group(1)) if week_m else None

    if label == "OG":
        family, weekday = "GOLD_MONTHLY", None
        direct = "OG"
    elif label in {f"OG{i}" for i in range(1, 6)}:
        family, weekday = "GOLD_WEEKLY", "FRIDAY"
        direct = label
    elif label == "OMG":
        family, weekday = "MICRO_GOLD_MONTHLY", None
        direct = "OMG"
    elif label in FAMILY_META:
        family, weekday = FAMILY_META[label]
        direct = None
    else:
        return None

    return {
        "product_family": family,
        "product_family_label": label,
        "product_code": family_to_code(label, week, direct),
        "weekday": weekday,
        "week_number": week,
        "header_raw": line,
    }


def parse_option_type(line: str):
    u = line.upper()
    if re.search(r"\bCALL\b", u):
        return "CALL"
    if re.search(r"\bPUT\b", u):
        return "PUT"
    return None


def value_near_x(words: list[dict[str, Any]], lo: float, hi: float):
    vals = [w["text"] for w in words if lo <= w["x0"] < hi]
    return "".join(vals) if vals else None


def signed_change(words: list[dict[str, Any]]):
    # Price-change column is commonly split into sign and number.
    for w in words:
        t = w["text"].upper()
        if t == "UNCH":
            return 0, "UNCH"
        if t == "NEW":
            return None, "NEW"

    vals = [w["text"] for w in words if 360 <= w["x0"] < 400]
    joined = "".join(vals).replace(" ", "")
    m = re.fullmatch(r"([+-]?)(\d+(?:\.\d+)?)", joined)
    if not m:
        return None, None
    n = float(m.group(2))
    if m.group(1) == "-":
        n = -n
    return (int(n) if n.is_integer() else n), None


def row_groups(page, words: list[dict[str, Any]] | None = None):
    """Return visually aligned rows using the Strike column as anchor.

    The original production parser used a per-strike scan over every word.
    That works, but PG64 pages are large enough that the O(words^2) behavior
    becomes unnecessarily slow. We first cluster words into visual lines and
    then identify strike-anchored lines, preserving the same observed ~0.7pt
    vertical offset behavior.
    """
    if words is None:
        words = page.extract_words(
            x_tolerance=1,
            y_tolerance=2,
            keep_blank_chars=False,
        )

    words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    line_groups: list[list[dict[str, Any]]] = []
    line_tops: list[float] = []

    for word in words:
        if not line_groups or abs(word["top"] - line_tops[-1]) > 1.5:
            line_groups.append([word])
            line_tops.append(word["top"])
        else:
            line_groups[-1].append(word)

    out: list[list[dict[str, Any]]] = []
    for group in line_groups:
        group = sorted(group, key=lambda w: w["x0"])
        line_text = " ".join(w["text"] for w in group).upper()

        # TOTAL rows are retained for separate handling by the caller, but
        # never enter the strike-row candidate path.
        if re.search(r"\bTOTAL(?:S)?\b", line_text):
            out.append(group)
            continue

        strike_words = [
            w for w in group
            if w["x0"] < 35 and STRIKE_RE.fullmatch(w["text"])
        ]
        if strike_words:
            valid = False
            for w in strike_words:
                try:
                    if float(w["text"].replace(",", "")) >= 1000:
                        valid = True
                        break
                except ValueError:
                    pass
            if valid:
                out.append(group)
                continue

        out.append(group)

    return out


def header_validation(words):
    anchors = {}
    for w in words:
        t = w["text"].upper()
        cx = (w["x0"] + w["x1"]) / 2
        if t == "DELTA":
            anchors["delta"] = cx
        elif t in {"EXER", "EXERCISES"}:
            anchors["exercises"] = cx
        elif t == "PNT":
            anchors["pnt_volume"] = cx
        elif t == "INTEREST":
            anchors["open_interest"] = cx

    checks = [abs(x - EXPECTED_X[k]) <= 12 for k, x in anchors.items()]
    return len(checks) >= 3 and sum(checks) >= 3, anchors


def parse_option_row(words: list[dict[str, Any]]):
    words = sorted(words, key=lambda w: w["x0"])
    if not words or not STRIKE_RE.fullmatch(words[0]["text"]):
        return None

    row_text = " ".join(w["text"] for w in words).upper()
    if re.search(r"\bTOTAL\b", row_text):
        return None

    strike = number(words[0]["text"])
    if strike is None or strike < 1000:
        return None

    # PG64 main-table local coordinate bands. These are based on the
    # observed column geometry of the option table; semantic discovery and
    # row identity do not depend on page number.
    bands = {
        "open_outcry_volume": (40, 68),
        "open_range": (68, 108),
        "open_outcry_high_low": (108, 188),
        "globex_high_low": (188, 260),
        "open_outcry_close_range": (260, 310),
        "settlement": (310, 363),
        "price_change": (363, 397),
        "delta": (397, 426),
        "exercises": (426, 452),
        "globex_open": (452, 482),
        "pnt_volume": (482, 512),
        "globex_volume": (512, 546),
        "open_interest": (546, 575),
        "oi_change": (575, 610),
    }

    def cell(name):
        lo, hi = bands[name]
        vals = [w["text"] for w in words if lo <= w["x0"] < hi]
        return "".join(vals) if vals else None

    settlement = number(cell("settlement"))
    price_change, price_change_status = signed_change(words)
    delta = number(cell("delta"))
    exercises = number(cell("exercises"))
    open_outcry_volume = number(cell("open_outcry_volume"))
    pnt_volume = number(cell("pnt_volume"))
    globex_volume = number(cell("globex_volume"))
    open_interest = number(cell("open_interest"))
    oi_change, oi_change_status = parse_change(cell("oi_change"))
    globex_open = number(cell("globex_open"))

    # Preserve range / quote cells as observed strings. "----" becomes null.
    open_range = clean_text(cell("open_range"))
    open_outcry_high_low = clean_text(cell("open_outcry_high_low"))
    globex_high_low = clean_text(cell("globex_high_low"))
    open_outcry_close_range = clean_text(cell("open_outcry_close_range"))

    # Require evidence that this is an option row, while allowing sparse rows.
    if settlement is None and open_interest is None and delta is None and not any(
        isinstance(x, (int, float))
        for x in (open_outcry_volume, pnt_volume, globex_volume, exercises)
    ):
        return None

    return {
        "strike": strike,
        "open_outcry_volume": open_outcry_volume,
        "open_outcry_open_range": open_range,
        "open_outcry_high_low": open_outcry_high_low,
        "globex_high_low": globex_high_low,
        "open_outcry_close_range": open_outcry_close_range,
        "settlement": settlement,
        "price_change": price_change,
        "price_change_status": price_change_status,
        "open_interest": open_interest,
        "oi_change": oi_change,
        "oi_change_status": oi_change_status,
        "delta": delta,
        "exercises": exercises,
        "globex_open": globex_open,
        "pnt_volume": pnt_volume,
        "globex_volume": globex_volume,
        "raw_row": " ".join(w["text"] for w in words),
    }


def parse_total(words, state, page_no):
    raw = " ".join(w["text"] for w in words)
    return {
        **state,
        "page": page_no,
        "total_tokens": [w["text"] for w in words[1:]],
        "raw": raw,
    }


def parse_eoo_block_text(text: str, page_no: int, warnings: list[dict[str, Any]]):
    """Parse the separate OPTIONS EOO'S AND BLOCKS table from page text.

    The EOO/Block table is structurally simpler than the main table and is
    kept separate. Observed rows are typically:
      OG 4300 0 350
    with section headers such as:
      OG CALL COMEX GOLD OPTIONS
      NOV26 CALL
    """
    records = []
    in_section = False
    current_product = None
    current_option_type = None
    current_expiry = None

    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        u = line.upper()
        if not line:
            continue

        if "OPTIONS EOO" in u and "BLOCK" in u:
            in_section = True
            continue
        if not in_section:
            continue

        # Stop when the next metals product begins.
        if re.match(r"^(?:COMEX\s+)?(?:SILVER|COPPER|PLATINUM|PALLADIUM)", u):
            break

        m = re.search(
            r"(OG\d?|OMG|GMW|GWT|GWW|GWR|MMG|WMG|FMG)\s*"
            r"(CALL|PUT)?\s*COMEX GOLD OPTIONS",
            u,
        )
        if not m:
            m = re.search(
                r"COMEX GOLD OPTIONS\s*(OG\d?|OMG|GMW|GWT|GWW|GWR|MMG|WMG|FMG)\s*"
                r"(CALL|PUT)?",
                u,
            )
        if m:
            current_product = m.group(1)
            current_option_type = m.group(2)
            continue

        if current_product:
            exp_m = re.search(
                r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2}\b",
                u,
            )
            if exp_m:
                current_expiry = exp_m.group(0)
                if re.search(r"\bCALL\b", u):
                    current_option_type = "CALL"
                elif re.search(r"\bPUT\b", u):
                    current_option_type = "PUT"
                continue

        if "TOTALS" in u or u.startswith("TOTAL"):
            continue

        m = re.match(
            r"^(OG\d?|OMG|GMW|GWT|GWW|GWR|MMG|WMG|FMG)\s+"
            r"(\d{2,5}(?:\.\d+)?)\s+(.+?)\s+(\d+)\s*$",
            u,
        )
        if not m:
            continue

        product_code = m.group(1)
        strike = number(m.group(2))
        middle = m.group(3).strip()
        block_volume = number(m.group(4))

        # In the observed EOO/Block layout, the middle value is EOO volume
        # when no price is printed. Preserve a numeric price separately only
        # when there are two numeric values in the middle field.
        middle_tokens = middle.split()
        numeric_middle = [number(x) for x in middle_tokens if number(x) is not None]
        price = None
        eoo_volume = None
        if len(numeric_middle) >= 2:
            price = numeric_middle[-2]
            eoo_volume = numeric_middle[-1]
        elif len(numeric_middle) == 1:
            eoo_volume = numeric_middle[0]

        records.append({
            "page": page_no,
            "product_code": product_code,
            "option_type": current_option_type,
            "expiry": current_expiry,
            "strike": strike,
            "price": price,
            "eoo_volume": eoo_volume,
            "block_volume": block_volume,
            "raw": line,
        })

    return records


def fast_gold_pages(pdf_path: Path) -> list[int]:
    if pypdf is None:
        return []
    reader = pypdf.PdfReader(str(pdf_path))
    pages = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        u = text.upper()
        normalized = re.sub(r"\s+", " ", u)
        is_gold = bool(
            GOLD_HEADER_RE.search(normalized)
            or re.search(r"COMEX GOLD OPTIONS\s*(?:OG\d?|OMG)", normalized)
            or re.search(r"GOLD WEEKLY .* OPTION", normalized)
            or re.search(r"MICRO GOLD .* OPTION", normalized)
        )
        is_table = bool(re.search(r"OPEN\s+OUTCRY\s+VOLUME", u)) or ("OPTIONS EOO" in u and "BLOCK" in u)
        if is_gold and is_table:
            pages.append(idx)
    return pages


def parse_pdf(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    ingested_at = datetime.now(timezone.utc).isoformat()

    rows: list[dict[str, Any]] = []
    totals: list[dict[str, Any]] = []
    eoo_block: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    with pdfplumber.open(path) as pdf:
        first_text = "\n".join((p.extract_text() or "") for p in pdf.pages[:3])
        bulletin = parse_bulletin_meta(first_text)

        candidate_pages = fast_gold_pages(path)
        if not candidate_pages:
            # Fallback: pdfplumber semantic scan. This is slower but avoids a
            # hard dependency on pypdf for correctness.
            candidate_pages = []
            for idx, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                u = text.upper()
                normalized = re.sub(r"\s+", " ", u)
                gold_semantic = bool(
                    GOLD_HEADER_RE.search(normalized)
                    or re.search(r"COMEX GOLD OPTIONS\s*(?:OG\d?|OMG)", normalized)
                    or re.search(r"GOLD WEEKLY .* OPTION", normalized)
                    or re.search(r"MICRO GOLD .* OPTION", normalized)
                )
                if gold_semantic and (
                    re.search(r"OPEN\s+OUTCRY\s+VOLUME", u) or ("OPTIONS EOO" in u and "BLOCK" in u)
                ):
                    candidate_pages.append(idx)

        state: dict[str, Any] | None = None

        for idx in candidate_pages:
            page_no = idx + 1
            page = pdf.pages[idx]
            text = page.extract_text() or ""
            words = page.extract_words(
                x_tolerance=1,
                y_tolerance=2,
                keep_blank_chars=False,
            )

            header_ok, anchors = header_validation(words)
            if not header_ok:
                warnings.append({
                    "page": page_no,
                    "type": "header_validation",
                    "anchors": anchors,
                })

            visual_rows = row_groups(page, words)
            eoo_block.extend(parse_eoo_block_text(text, page_no, warnings))

            # A Gold semantic page can contain continuation rows. State is
            # carried only while the page itself remains semantically Gold.
            page_has_gold = bool(
                GOLD_HEADER_RE.search(text)
                or "GOLD OPTIONS" in text.upper()
                or "MICRO GOLD" in text.upper()
                or "GOLD WEEKLY" in text.upper()
            )
            if not page_has_gold:
                state = None
                continue

            current_state = dict(state) if state else None

            for ws in visual_rows:
                if not ws:
                    continue
                line = re.sub(r"\s+", " ", " ".join(w["text"] for w in ws)).strip()
                upper = line.upper()

                fh = parse_family_header(line)
                if fh:
                    current_state = fh
                    current_state["option_type"] = parse_option_type(line)
                    current_state.pop("expiry", None)
                    continue

                ot = parse_option_type(line)
                if ot and current_state:
                    current_state["option_type"] = ot
                    continue

                # Standalone expiry line.
                expiry_words = [w["text"].upper() for w in ws if EXPIRY_RE.fullmatch(w["text"].upper())]
                if current_state and len(ws) <= 3 and expiry_words:
                    current_state["expiry"] = expiry_words[0]
                    continue

                if current_state and upper.startswith("TOTAL"):
                    totals.append(parse_total(ws, current_state, page_no))
                    continue

                if current_state and current_state.get("expiry"):
                    rec = parse_option_row(ws)
                    if rec:
                        rec = {
                            "trade_date": bulletin.get("trade_date"),
                            "bulletin_number": bulletin.get("bulletin_number"),
                            "bulletin_status": bulletin.get("bulletin_status"),
                            "page": page_no,
                            "product_family": current_state.get("product_family"),
                            "product_family_label": current_state.get("product_family_label"),
                            "product_code": current_state.get("product_code"),
                            "weekday": current_state.get("weekday"),
                            "week_number": current_state.get("week_number"),
                            "option_type": current_state.get("option_type"),
                            "expiry": current_state.get("expiry"),
                            **rec,
                        }
                        rows.append(rec)

            state = current_state

    # Validation warnings are source/parser quality warnings, not analytics.
    unknown_codes = sorted({
        r["product_code"] for r in rows
        if r.get("product_code") and r["product_code"] not in PRODUCT_CODES
    })
    if unknown_codes:
        warnings.append({"type": "unknown_product_codes", "codes": unknown_codes})

    unresolved_product_rows = sum(1 for r in rows if not r.get("product_code"))
    if unresolved_product_rows:
        warnings.append({
            "type": "unresolved_product_code_rows",
            "count": unresolved_product_rows,
        })

    if not bulletin.get("trade_date"):
        warnings.append({"type": "missing_trade_date"})

    if not bulletin.get("bulletin_status"):
        warnings.append({"type": "missing_bulletin_status"})

    provenance = {
        "source": "CME Daily Bulletin PG64",
        "source_file": path.name,
        "sha256": sha,
        "parser_version": PARSER_VERSION,
        "ingested_at": ingested_at,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": provenance,
        "bulletin": bulletin,
        "rows": rows,
        "totals": totals,
        "eoo_block": eoo_block,
        "warnings": warnings,
    }


def output_name(data: dict[str, Any], pdf_path: Path) -> str:
    date = data.get("bulletin", {}).get("trade_date")
    status = data.get("bulletin", {}).get("bulletin_status") or "UNKNOWN"
    if date:
        return f"{date}_{status}.json"
    return f"{pdf_path.stem}_{status}.json"


def validate_master(data: dict[str, Any]) -> list[str]:
    errors = []
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version")
    bulletin = data.get("bulletin") or {}
    if not bulletin.get("trade_date"):
        errors.append("missing trade_date")
    if not bulletin.get("bulletin_number"):
        errors.append("missing bulletin_number")
    if bulletin.get("bulletin_status") not in {"PRELIMINARY", "FINAL"}:
        errors.append("invalid bulletin_status")
    if not isinstance(data.get("rows"), list):
        errors.append("rows not list")
    if not isinstance(data.get("totals"), list):
        errors.append("totals not list")
    if not isinstance(data.get("eoo_block"), list):
        errors.append("eoo_block not list")

    required = {
        "trade_date", "bulletin_number", "bulletin_status", "page",
        "product_family", "product_family_label", "product_code",
        "option_type", "expiry", "strike", "settlement", "open_interest",
        "delta", "exercises", "pnt_volume", "globex_volume",
    }
    for i, row in enumerate(data.get("rows", [])):
        missing = sorted(required - set(row))
        if missing:
            errors.append(f"row[{i}] missing: {','.join(missing)}")
            break
        if row.get("product_code") and row["product_code"] not in PRODUCT_CODES:
            errors.append(f"row[{i}] invalid product_code: {row['product_code']}")
            break
        if row.get("option_type") not in {"CALL", "PUT", None}:
            errors.append(f"row[{i}] invalid option_type")
            break
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="?", type=Path)
    ap.add_argument("--input-dir", type=Path, default=Path("data/cme-pg64"))
    ap.add_argument("--output-dir", type=Path, default=Path("data/pg64"))
    ap.add_argument("--keep-existing", action="store_true", default=True,
                    help="Keep existing MASTER JSON files; default behavior.")
    args = ap.parse_args()

    if args.pdf:
        pdf_paths = [args.pdf]
    else:
        pdf_paths = sorted(args.input_dir.glob("*.pdf"))

    if not pdf_paths:
        raise SystemExit(f"No PG64 PDF files found in {args.input_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Found {len(pdf_paths)} PG64 PDF(s)")
    failures = 0
    all_outputs = []

    for pdf_path in pdf_paths:
        print(f"\nParsing: {pdf_path}")
        try:
            data = parse_pdf(pdf_path)
            errors = validate_master(data)
            if errors:
                failures += 1
                print("  VALIDATION ERROR:", "; ".join(errors))
                continue

            filename = output_name(data, pdf_path)
            output_path = args.output_dir / filename
            output_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            all_outputs.append(output_path)

            bulletin = data["bulletin"]
            print(f"  Date:     {bulletin.get('trade_date')}")
            print(f"  Bulletin: {bulletin.get('bulletin_number')}")
            print(f"  Status:   {bulletin.get('bulletin_status')}")
            print(f"  Rows:     {len(data['rows'])}")
            print(f"  Totals:   {len(data['totals'])}")
            print(f"  EOO/Block:{len(data['eoo_block'])}")
            print(f"  Warnings: {len(data['warnings'])}")
            print(f"  Output:   {output_path}")

            products = Counter(r.get("product_code") for r in data["rows"])
            print(f"  Products: {dict(products)}")
        except Exception as exc:
            failures += 1
            print(f"  ERROR: {type(exc).__name__}: {exc}")

    print("\n========================================")
    print("PG64 MASTER generation complete")
    print("========================================")
    print(f"Generated: {len(all_outputs)}")
    print(f"Failures:  {failures}")
    print(f"Output:    {args.output_dir}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
