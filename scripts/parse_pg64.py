#!/usr/bin/env python3
"""Parse CME PG64 Metals Options Bulletin for Gold options.

Uses PDF word coordinates (pdfplumber) rather than plain-text extraction because
CME's PDF columns can be reordered/concatenated by normal PDF text extraction.

Output keeps CME-observed fields separate from later model-derived Gamma fields.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pdfplumber

DATE_RE = re.compile(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})\b")
EXPIRY_RE = re.compile(r"^[A-Z]{3}\d{2}$")
NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")
STRIKE_RE = re.compile(r"^\d+(?:\.\d+)?$")

# Product headers that belong to Gold.  OG* are the standard Gold option
# families; OMG/WMG are Micro Gold; GWW/GWR are weekly Gold families seen in
# this bulletin.  Additional GOLD-labelled headers are accepted dynamically.
KNOWN_GOLD_CODES = {
    "OG", "OG1", "OG2", "OG3", "OG4", "OMG", "WMG", "GWW", "GWR", "GWT",
    "G1R", "G5W",
}


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse_number(s: str) -> float | int | None:
    s = s.strip()
    if not NUMBER_RE.fullmatch(s):
        return None
    v = float(s)
    return int(v) if v.is_integer() else v


def signed_change(words: list[dict[str, Any]]) -> int | float | None | str:
    # CME prints change as separate '+'/'-' and numeric words, or UNCH/NEW.
    for w in words:
        t = w["text"].upper()
        if t == "UNCH":
            return 0
        if t == "NEW":
            return "NEW"
    # Usually the price-change field is around x=366-395.
    vals: list[str] = []
    for w in words:
        if 360 <= w["x0"] < 400:
            vals.append(w["text"])
    joined = "".join(vals).replace(" ", "")
    m = re.fullmatch(r"([+-]?)(\d+(?:\.\d+)?)", joined)
    if m:
        n = float(m.group(2))
        if m.group(1) == "-": n = -n
        return int(n) if n.is_integer() else n
    return None


def value_near_x(words, lo, hi):
    candidates = [w for w in words if lo <= w["x0"] < hi]
    if not candidates:
        return None
    # There should normally be exactly one value. If '+' and number are split,
    # join them for the price-change column.
    return "".join(w["text"] for w in candidates)


def parse_row(words: list[dict[str, Any]], product_code: str, option_type: str, expiry: str):
    words = sorted(words, key=lambda w: w["x0"])
    if not words:
        return None
    first = words[0]["text"]
    if not STRIKE_RE.fullmatch(first):
        return None
    strike = parse_number(first)
    if strike is None:
        return None

    # CME's stable x-columns on PG64:
    # settlement ~342, price change ~366-395, delta ~402,
    # exercises ~430, volume columns ~456/486/516, OI ~552-560,
    # OI change ~566-595.
    settlement_s = value_near_x(words, 335, 365)
    if settlement_s in (None, "----"):
        settlement = None
    else:
        settlement = parse_number(settlement_s)

    delta_s = value_near_x(words, 399, 428)
    delta = None if delta_s in (None, "----") else parse_number(delta_s)

    # Three volume columns: Open Outcry, Globex, PNT.
    volumes = []
    for lo, hi in ((448, 480), (480, 510), (510, 545)):
        s = value_near_x(words, lo, hi)
        if s and s != "----":
            n = parse_number(s)
            if n is not None:
                volumes.append(n)
    volume_open_outcry = volumes[0] if len(volumes) > 0 else None
    volume_globex = volumes[1] if len(volumes) > 1 else None
    volume_pnt = volumes[2] if len(volumes) > 2 else None
    volume_parts = [v for v in (volume_open_outcry, volume_globex, volume_pnt) if isinstance(v, (int, float))]
    volume = sum(volume_parts) if volume_parts else None

    oi_s = value_near_x(words, 545, 565)
    oi = None if oi_s in (None, "----") else parse_number(oi_s)

    oi_change_s = value_near_x(words, 565, 610)
    if oi_change_s is None:
        oi_change = None
    elif "UNCH" in oi_change_s.upper():
        oi_change = 0
    elif "NEW" in oi_change_s.upper():
        oi_change = "NEW"
    else:
        oi_change = parse_number(oi_change_s)

    # Require at least OI or settlement to avoid accidentally parsing headers.
    if settlement is None and oi is None and delta is None:
        return None

    return {
        "product_code": product_code,
        "option_type": option_type,
        "expiry": expiry,
        "strike": strike,
        "settlement": settlement,
        "price_change": signed_change(words),
        "delta": delta,
        "volume": volume,
        "volume_open_outcry": volume_open_outcry,
        "volume_globex": volume_globex,
        "volume_pnt": volume_pnt,
        "open_interest": oi,
        "oi_change": oi_change,
    }


def row_groups(page):
    """Return visually aligned rows using the Strike column as the anchor.

    CME places the Strike text about 0.7pt below the other cells. Grouping by
    rounded y-coordinates can therefore accidentally merge adjacent strikes.
    """
    words = page.extract_words(x_tolerance=1, y_tolerance=2, keep_blank_chars=False)
    strikes = [w for w in words if w["x0"] < 35 and STRIKE_RE.fullmatch(w["text"]) and float(w["text"]) >= 1000]
    data_rows = []
    used = set()
    for sw in strikes:
        row = [w for w in words if abs(w["top"] - (sw["top"] - 0.75)) <= 1.25 or abs(w["top"] - sw["top"]) <= 1.25]
        # Keep the strike itself and avoid accidentally taking the next row.
        row = [w for w in row if abs(w["top"] - sw["top"]) <= 1.25 or abs(w["top"] - (sw["top"] - 0.75)) <= 1.25]
        data_rows.append((sw["top"], sorted(row, key=lambda w: w["x0"])))
        used.update(id(w) for w in row)

    # Also return non-data visual lines (product/expiry headers) for state tracking.
    remaining = [w for w in words if id(w) not in used]
    remaining = sorted(remaining, key=lambda w: (w["top"], w["x0"]))
    header_rows = []
    for w in remaining:
        if not header_rows or abs(w["top"] - header_rows[-1]["top"]) > 1.5:
            header_rows.append({"top": w["top"], "words": [w]})
        else:
            header_rows[-1]["words"].append(w)
    out = [(g["top"], sorted(g["words"], key=lambda w: w["x0"])) for g in header_rows]
    out.extend(data_rows)
    out.sort(key=lambda x: x[0])
    return [r for _, r in out]


def extract_bulletin_date(pdf) -> str:
    for page in pdf.pages[:3]:
        text = page.extract_text() or ""
        m = DATE_RE.search(text)
        if m:
            mon, day, year = m.groups()
            from datetime import datetime
            return datetime.strptime(f"{mon} {day} {year}", "%b %d %Y").date().isoformat()
    raise ValueError("Could not find PG64 bulletin date in PDF")


def parse(pdf_path: Path) -> dict[str, Any]:
    options = []
    current_product = None
    current_product_name = None
    current_option_type = None
    current_expiry = None

    with pdfplumber.open(pdf_path) as pdf:
        # First pass with pypdf is much faster for page filtering; pdfplumber
        # is used only on pages that actually contain Gold option tables.
        import pypdf
        fast_pdf = pypdf.PdfReader(str(pdf_path))
        bulletin_date = extract_bulletin_date(fast_pdf)
        gold_pages = []
        for idx, fp in enumerate(fast_pdf.pages):
            txt = fp.extract_text() or ""
            if ("GOLD OPTIONS" in txt.upper() or "MICRO GOLD" in txt.upper() or "GOLD WEEKLY" in txt.upper()) and idx + 1 != 70:
                gold_pages.append(idx)
        for idx in gold_pages:
            page_no = idx + 1
            page = pdf.pages[idx]
            for words in row_groups(page):
                if not words:
                    continue
                text = clean_text(" ".join(w["text"] for w in words))
                upper = text.upper()

                # Product header. Only accept Gold-labelled sections.
                if "GOLD OPTIONS" in upper or "MICRO GOLD" in upper or "GOLD WEEKLY" in upper:
                    if "OPTIONS ON FUTURES" not in upper and "PRODUCT INDEX" not in upper:
                        code = words[0]["text"].upper()
                        if code in KNOWN_GOLD_CODES or "GOLD" in upper:
                            current_product = code
                            current_product_name = text
                            current_option_type = "CALL" if re.search(r"\bCALL\b", upper) else ("PUT" if re.search(r"\bPUT\b", upper) else None)
                            current_expiry = None
                    continue

                if current_product:
                    # Expiry is a standalone month/year row, e.g. NOV26.
                    if len(words) == 1 and EXPIRY_RE.fullmatch(words[0]["text"].upper()):
                        current_expiry = words[0]["text"].upper()
                        continue

                    if current_expiry:
                        rec = parse_row(words, current_product, current_option_type, current_expiry)
                        if rec:
                            rec["date"] = bulletin_date
                            rec["page"] = page_no
                            rec["product_name"] = current_product_name
                            options.append(rec)

    return {
        "date": bulletin_date,
        "source": "CME Daily Bulletin PG64",
        "status": "PRELIMINARY",
        "pdf": pdf_path.name,
        "options": options,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "pdf",
        nargs="?",
        default=None,
        help="Optional single PDF. If omitted, parse all PDFs under data/cme-pg64/"
    )
    ap.add_argument(
        "-o",
        "--output",
        default="data/cme-gold-options-history.json",
    )
    ap.add_argument(
        "--input-dir",
        default="data/cme-pg64",
    )
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    output_path = Path(args.output)

    # ------------------------------------------------------------
    # Input PDFs
    # ------------------------------------------------------------
    if args.pdf:
        pdf_paths = [Path(args.pdf)]
    else:
        pdf_paths = sorted(input_dir.glob("*.pdf"))

    if not pdf_paths:
        raise SystemExit(
            f"No PG64 PDF files found in {input_dir}"
        )

    print(f"Found {len(pdf_paths)} PG64 PDF(s)")

    # ------------------------------------------------------------
    # Parse all PDFs first
    # ------------------------------------------------------------
    parsed_by_date = {}

    for pdf_path in pdf_paths:
        print(f"\nParsing: {pdf_path}")

        data = parse(pdf_path)
        bulletin_date = data["date"]

        print(
            f"  Date: {bulletin_date}"
        )
        print(
            f"  Rows: {len(data['options'])}"
        )

        # If multiple PDFs somehow contain the same bulletin date,
        # the later parsed file replaces the earlier one.
        parsed_by_date[bulletin_date] = data

    # ------------------------------------------------------------
    # Load existing history
    # ------------------------------------------------------------
    history_options = []

    if output_path.exists():
        try:
            existing = json.loads(
                output_path.read_text(encoding="utf-8")
            )

            # Current history format
            if isinstance(existing, dict) and isinstance(
                existing.get("options"), list
            ):
                history_options = existing["options"]

            print(
                f"\nExisting history rows: {len(history_options)}"
            )

        except Exception as exc:
            print(
                f"Warning: could not read existing history: {exc}"
            )
            print("Starting with empty history.")

    # ------------------------------------------------------------
    # Remove old records for dates being re-parsed
    # ------------------------------------------------------------
    dates_to_replace = set(parsed_by_date.keys())

    history_options = [
        row
        for row in history_options
        if row.get("date") not in dates_to_replace
    ]

    # ------------------------------------------------------------
    # Add newly parsed records
    # ------------------------------------------------------------
    for bulletin_date in sorted(parsed_by_date):
        history_options.extend(
            parsed_by_date[bulletin_date]["options"]
        )

    # ------------------------------------------------------------
    # Sort history
    # ------------------------------------------------------------
    def sort_key(row):
        return (
            row.get("date") or "",
            row.get("product_code") or "",
            row.get("option_type") or "",
            row.get("expiry") or "",
            float(row.get("strike") or 0),
        )

    history_options.sort(key=sort_key)

    # ------------------------------------------------------------
    # Build output
    # ------------------------------------------------------------
    dates = sorted(
        {
            row["date"]
            for row in history_options
            if row.get("date")
        }
    )

    output = {
        "source": "CME Daily Bulletin PG64",
        "dates": dates,
        "options": history_options,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------
    from collections import Counter

    product_counts = Counter(
        row["product_code"]
        for row in history_options
    )

    print("\n========================================")
    print("PG64 history updated")
    print("========================================")
    print(f"Dates: {len(dates)}")
    print(f"Rows:  {len(history_options)}")
    print(f"Output: {output_path}")

    print("\nDates:")
    for d in dates:
        count = sum(
            1
            for row in history_options
            if row.get("date") == d
        )
        print(f"  {d}: {count} rows")

    print("\nProducts:")
    print(dict(product_counts))


if __name__ == "__main__":
    main()
