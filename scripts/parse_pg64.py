#!/usr/bin/env python3
"""Parse CME PG62 Gold futures bulletins into production MASTER JSON.

PG62 follows the same parser architecture as the production PG64 parser:
- semantic page discovery, never page-number semantics
- pdfplumber word coordinates + visual row grouping
- column geometry is discovered/validated from CME table headers
- GC futures rows are parsed only inside the GC FUT COMEX GOLD FUTURES section
- PRELIMINARY and FINAL source observations are retained independently
- MASTER contains observed source facts only
- invalid/incomplete extraction fails before MASTER is written
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

PARSER_VERSION = "pg62-gold-v2.4.0"
SCHEMA_VERSION = "pg62-gc-master-v2.4"

CONTRACT_RE = re.compile(r"^(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2}$", re.I)
GC_HEADER_RE = re.compile(r"\bGC\s+FUT\s+COMEX\s+GOLD\s+FUTURES\b", re.I)
TOTAL_GC_RE = re.compile(r"^TOTAL\s+GC\s+FUT\b", re.I)
NEXT_PRODUCT_RE = re.compile(r"^(?:[A-Z0-9]+\s+){1,5}FUT(?:URES)?\b", re.I)
NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)$")

MAX_VOLUME = 2_000_000
MAX_OI = 10_000_000
MAX_PRICE = 20_000.0

# These are geometry validation anchors, not a second parser.  PG64 uses the
# same design: semantic header recognition + local row geometry.
EXPECTED_X = {
    "open": 120.0,
    "high_low": 204.0,
    "settlement": 294.0,
    "change": 321.0,
    "globex_volume": 414.0,
    "pnt_volume": 468.0,
    "open_interest": 552.0,
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def is_missing(value: Any) -> bool:
    return clean(value).upper() in {"", "-", "--", "---", "----", "—"}


def number(value: Any):
    s = clean(value).replace(",", "")
    if is_missing(s):
        return None
    if s.upper() in {"UNCH", "NEW"}:
        return 0.0 if s.upper() == "UNCH" else None
    if not NUMBER_RE.fullmatch(s):
        return None
    n = float(s)
    return int(n) if n.is_integer() else n


def integer(value: Any):
    n = number(value)
    return None if n is None else int(round(n))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_signed_words(words: list[dict[str, Any]]):
    tokens = [clean(w.get("text")) for w in sorted(words, key=lambda w: w["x0"])]
    joined = "".join(tokens).replace(" ", "")
    if not joined or is_missing(joined):
        return None
    if joined.upper() == "UNCH":
        return 0.0
    if joined.upper() == "NEW":
        return None
    try:
        return float(joined.replace("B", "").replace("A", ""))
    except ValueError:
        return None


def parse_signed_change(words: list[dict[str, Any]]):
    # PG62 price change and OI change can be split into sign + number words.
    return parse_signed_words(words)


def parse_prices(words: list[dict[str, Any]]):
    """Extract one or two prices from the PG62 high/low cell."""
    vals = []
    for w in sorted(words, key=lambda w: w["x0"]):
        s = clean(w.get("text")).replace(",", "").replace("B", "").replace("A", "")
        # The PDF can split 4374.00 /4277.60 into separate words or combine it.
        for part in s.replace("/", " ").split():
            if NUMBER_RE.fullmatch(part):
                vals.append(float(part))
    return vals


def extract_bulletin_meta(pdf) -> dict[str, Any]:
    text = "\n".join((p.extract_text() or "") for p in pdf.pages[:4])
    head = text[:6000]
    status = "FINAL" if re.search(r"\bFINAL\b", head, re.I) else (
        "PRELIMINARY" if re.search(r"\bPRELIMINARY\b", head, re.I) else None
    )
    m = re.search(
        r"PG62\s+BULLETIN\s*#\s*(\d+).*?"
        r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+"
        r"([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})",
        text,
        re.I | re.S,
    )
    if not m:
        return {"bulletin_number": None, "trade_date": None, "bulletin_status": status}
    month, day, year = m.group(2), int(m.group(3)), int(m.group(4))
    date = datetime.strptime(f"{month} {day} {year}", "%b %d %Y").date().isoformat()
    return {
        "bulletin_number": int(m.group(1)),
        "trade_date": date,
        "bulletin_status": status,
    }


def visual_groups(words: list[dict[str, Any]], tolerance: float = 1.5):
    groups: list[dict[str, Any]] = []
    for w in sorted(words, key=lambda x: (x["top"], x["x0"])):
        if not groups or abs(w["top"] - groups[-1]["top"]) > tolerance:
            groups.append({"top": w["top"], "words": [w]})
        else:
            groups[-1]["words"].append(w)
            groups[-1]["top"] = sum(x["top"] for x in groups[-1]["words"]) / len(groups[-1]["words"])
    for g in groups:
        g["words"].sort(key=lambda x: x["x0"])
    return groups


def line_text(words: list[dict[str, Any]]) -> str:
    return " ".join(clean(w.get("text")) for w in words).strip()


def find_header_anchors(words: list[dict[str, Any]]):
    """Find the CME PG62 column-header anchors by semantic labels.

    Header words are intentionally matched by label and x-position.  We do
    not manufacture a band if a required label is absent.
    """
    anchors: dict[str, float] = {}
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    for w in ws:
        t = clean(w.get("text")).upper().replace("®", "")
        x = float(w["x0"])
        if t == "GLOBEX" and 100 <= x <= 140:
            # PG62 labels the first price column as the two-word header
            # GLOBEX / OPEN.  The left-hand GLOBEX word is the column anchor;
            # the row values themselves begin around x=126.
            anchors["open"] = x
        elif t in {"HIGH/LOW", "HIGH/LOW."} or t.startswith("HIGH/LOW"):
            anchors["high_low"] = x
        elif t in {"SETT.", "SETT"}:
            anchors["settlement"] = x
        elif t == "CHGE" or t == "PT.CHGE":
            anchors["change"] = x
        elif t == "VOLUME" and 390 <= x <= 450:
            anchors["globex_volume"] = x
        elif t == "VOLUME" and 450 <= x <= 510:
            anchors["pnt_volume"] = x
        elif t == "INTEREST" and 530 <= x <= 590:
            anchors["open_interest"] = x

    # Header text can be split across two rows; the semantic labels above are
    # sufficient for the observed CME PG62 geometry.
    return anchors


def validate_header_anchors(anchors: dict[str, float], tolerance: float = 14.0):
    required = set(EXPECTED_X)
    missing = sorted(required - set(anchors))
    if missing:
        return False, {"missing": missing, "anchors": anchors}
    bad = {
        k: {"observed": anchors[k], "expected": EXPECTED_X[k]}
        for k in required
        if abs(anchors[k] - EXPECTED_X[k]) > tolerance
    }
    if bad:
        return False, {"bad": bad, "anchors": anchors}
    return True, {"anchors": anchors}


def build_bands(anchors: dict[str, float], page_width: float):
    # Column boundaries are derived from validated header centers.  This is
    # deterministic and mirrors PG64's local-coordinate row parser.
    centers = sorted((x, k) for k, x in anchors.items())
    boundaries = {}
    for i, (x, key) in enumerate(centers):
        left = 70.0 if i == 0 else (centers[i - 1][0] + x) / 2
        right = page_width - 2.0 if i == len(centers) - 1 else (x + centers[i + 1][0]) / 2
        boundaries[key] = (left, right)
    # Contract is before the first numeric column.
    boundaries["contract"] = (0.0, 70.0)
    # PG62 prints OI and its signed change under the same OPEN INTEREST
    # header. The source geometry consistently separates the OI value around
    # x=542-552 from the sign/value pair around x=564-590. Preserve that
    # source geometry explicitly rather than guessing from a missing header.
    boundaries["open_interest"] = (510.0, 562.0)
    boundaries["oi_change"] = (562.0, 610.0)
    return boundaries


def in_band(words, band):
    lo, hi = band
    return [w for w in words if lo <= w["x0"] < hi]


def first_text(words):
    return clean(words[0].get("text")) if words else ""


def parse_contract(words, bands):
    for w in in_band(words, bands["contract"]):
        token = clean(w.get("text")).upper()
        if CONTRACT_RE.fullmatch(token):
            return token
    return None


def validate_row(row: dict[str, Any]):
    errors = []
    for key in ("volume", "volume_globex", "volume_pnt_pit", "open_interest"):
        value = row.get(key)
        if value is not None and value < 0:
            errors.append(f"negative {key}={value}")
    for key in ("open", "high", "low", "settlement"):
        value = row.get(key)
        if value is not None and abs(value) > MAX_PRICE:
            errors.append(f"implausible {key}={value}")
    if row.get("high") is not None and row.get("low") is not None and row["high"] < row["low"]:
        errors.append("high<low")
    for key in ("volume_globex", "volume_pnt_pit"):
        value = row.get(key)
        if value is not None and value > MAX_VOLUME:
            errors.append(f"implausible {key}={value}")
    if row.get("open_interest") is not None and row["open_interest"] > MAX_OI:
        errors.append("implausible open_interest")
    parts = (row.get("volume_globex"), row.get("volume_pnt_pit"))
    if all(v is not None for v in parts):
        expected = parts[0] + parts[1]
        if row.get("volume") != expected:
            errors.append(f"volume mismatch: {row.get('volume')} != {expected}")
    if errors:
        raise ValueError(
            f"PG62 row validation failed for {row.get('date')} {row.get('contract')}: "
            + "; ".join(errors)
        )


def parse_futures_row(words, date, source_file, source_status, bulletin_number, bands, page_no):
    contract = parse_contract(words, bands)
    if not contract:
        return None

    def cell(key):
        return in_band(words, bands[key])

    open_value = number(first_text(cell("open")))
    hl = parse_prices(cell("high_low"))
    high = hl[0] if hl else None
    low = hl[1] if len(hl) > 1 else None
    settlement = number(first_text(cell("settlement")))
    price_change = parse_signed_change(cell("change"))
    globex_volume = integer(first_text(cell("globex_volume")))
    pnt_volume = integer(first_text(cell("pnt_volume")))
    open_interest_words = cell("open_interest")
    open_interest = integer(first_text(open_interest_words))

    # OI change is printed immediately after OI in the same header group.
    oi_change = parse_signed_change(in_band(words, bands["oi_change"]))

    if globex_volume is None and pnt_volume is None:
        volume = None
    else:
        volume = (globex_volume or 0) + (pnt_volume or 0)

    row = {
        "date": date,
        "contract": contract,
        "open": open_value,
        "high": high,
        "low": low,
        "close": settlement,
        "settlement": settlement,
        "price_change": price_change,
        "volume": volume,
        "volume_globex": globex_volume,
        "volume_pnt_pit": pnt_volume,
        "open_interest": open_interest,
        "oi_change": None if oi_change is None else int(round(oi_change)),
        "is_active": False,
        "source_file": source_file,
        "source_status": source_status,
        "bulletin_number": bulletin_number,
        "source_page": page_no,
    }
    validate_row(row)
    return row


def is_header_line(words):
    u = line_text(words).upper()
    return "GLOBEX" in u and "PNT/PIT" in u and "OPEN" in u and "INTEREST" in u


def discover_layout(pdf):
    layouts = []
    for page_no, page in enumerate(pdf.pages, 1):
        words = page.extract_words(x_tolerance=1, y_tolerance=2, keep_blank_chars=False)
        text = line_text(words).upper()
        if "GLOBEX" not in text or "PNT/PIT" not in text or "INTEREST" not in text:
            continue
        anchors = find_header_anchors(words)
        ok, detail = validate_header_anchors(anchors)
        if ok:
            bands = build_bands(anchors, float(page.width))
            if any(a >= b for a, b in bands.values()):
                raise RuntimeError(f"Invalid PG62 column geometry on page {page_no}: {bands}")
            layouts.append({
                "page": page_no,
                "header_anchors": anchors,
                "bands": bands,
                "anchor_mode": "validated_semantic_header",
            })
    if not layouts:
        raise RuntimeError("Could not discover a validated PG62 futures table header")
    # Prefer the first validated geometry; verify all discovered layouts agree.
    base = layouts[0]
    for other in layouts[1:]:
        for key in base["bands"]:
            if key not in other["bands"]:
                raise RuntimeError(f"Inconsistent PG62 layout on page {other['page']}: missing {key}")
            a0, a1 = base["bands"][key]
            b0, b1 = other["bands"][key]
            if abs(a0 - b0) > 8 or abs(a1 - b1) > 8:
                raise RuntimeError(f"Inconsistent PG62 column geometry between pages {base['page']} and {other['page']}")
    return base["bands"], layouts


def gc_pages(pdf):
    pages = []
    for page_no, page in enumerate(pdf.pages, 1):
        t = page.extract_text() or ""
        if GC_HEADER_RE.search(re.sub(r"\s+", " ", t)):
            pages.append(page_no)
    return pages


def extract_pdf(path: Path):
    raw_sha = sha256(path)
    with pdfplumber.open(path) as pdf:
        meta = extract_bulletin_meta(pdf)
        if not meta["trade_date"]:
            raise RuntimeError(f"Missing PG62 trade date: {path.name}")
        if not meta["bulletin_number"]:
            raise RuntimeError(f"Missing PG62 bulletin number: {path.name}")
        if meta["bulletin_status"] not in {"PRELIMINARY", "FINAL"}:
            raise RuntimeError(f"Missing/invalid bulletin status: {path.name}")

        bands, layouts = discover_layout(pdf)
        candidates = gc_pages(pdf)
        if not candidates:
            raise RuntimeError(f"No GC futures section found: {path.name}")

        rows = []
        section_active = False
        for page_no, page in enumerate(pdf.pages, 1):
            # GC can be a section at the bottom of a page. We only enter it on
            # an explicit semantic GC header; subsequent pages are allowed to
            # continue while they contain contract rows and no new product.
            text = page.extract_text() or ""
            compact = re.sub(r"\s+", " ", text)
            explicit_gc = bool(GC_HEADER_RE.search(compact))
            if explicit_gc:
                section_active = True
            if not section_active:
                continue

            words = page.extract_words(x_tolerance=1, y_tolerance=2, keep_blank_chars=False)
            groups = visual_groups(words)
            page_started_gc = False
            for g in groups:
                ws = g["words"]
                line = line_text(ws)
                upper = line.upper()
                if GC_HEADER_RE.search(upper):
                    page_started_gc = True
                    continue
                if TOTAL_GC_RE.search(upper):
                    section_active = False
                    break
                if explicit_gc and not page_started_gc:
                    # The GC section can be near the bottom of a page; ignore
                    # the page header and all preceding products until the
                    # explicit GC section header is reached.
                    continue
                if not page_started_gc and not explicit_gc:
                    # Continuation page: only contract-looking rows are allowed.
                    if not any(CONTRACT_RE.fullmatch(clean(w.get("text")).upper()) for w in ws):
                        continue
                # Stop at a new futures product heading. A contract row has a
                # contract token in column 0, so it is handled first.
                if NEXT_PRODUCT_RE.match(upper) and not CONTRACT_RE.fullmatch(clean(ws[0].get("text")).upper()):
                    section_active = False
                    break
                rec = parse_futures_row(
                    ws,
                    meta["trade_date"],
                    path.name,
                    meta["bulletin_status"],
                    meta["bulletin_number"],
                    bands,
                    page_no,
                )
                if rec:
                    rows.append(rec)

        # Exact source row identity. A contract should occur once per bulletin
        # in the GC section.
        unique = {}
        for r in rows:
            key = (r["date"], r["contract"], r["source_file"], r["source_page"])
            unique[key] = r
        rows = list(unique.values())

        if not rows:
            raise RuntimeError(f"No GC futures rows extracted: {path.name}")
        if len(rows) < 3:
            raise RuntimeError(f"Suspiciously few GC futures rows ({len(rows)}): {path.name}")

        volume_rows = [r for r in rows if r["volume"] is not None]
        if not volume_rows:
            raise RuntimeError(f"No usable GC volume rows extracted: {path.name}")
        if any(r["volume"] != (r["volume_globex"] or 0) + (r["volume_pnt_pit"] or 0) for r in volume_rows):
            raise RuntimeError(f"GC volume consistency failure: {path.name}")

        # Active contract is an EOD representative, not intraday knowledge.
        active = max(
            rows,
            key=lambda r: (
                r["volume"] if r["volume"] is not None else -1,
                r["open_interest"] if r["open_interest"] is not None else -1,
            ),
        )["contract"]
        for r in rows:
            r["is_active"] = r["contract"] == active

        provenance = {
            "source": "CME Daily Bulletin PG62",
            "source_file": path.name,
            "source_sha256": raw_sha,
            "trade_date": meta["trade_date"],
            "bulletin_number": meta["bulletin_number"],
            "source_status": meta["bulletin_status"],
            "parser_version": PARSER_VERSION,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "active_selection_method": "highest_volume_eod_then_open_interest",
            "layout_discovery": layouts,
        }
        return meta, rows, provenance


def load_existing(path: Path):
    if not path.exists():
        return {"observations": [], "provenance": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Cannot read existing MASTER {path}: {exc}")


def observation_key(row):
    return (
        row.get("date"),
        row.get("contract"),
        row.get("source_file"),
        row.get("source_status"),
        row.get("source_sha256"),
    )


def rebuild(observations):
    rank = {"FINAL": 2, "PRELIMINARY": 1}
    latest = {}
    for row in observations:
        key = (row.get("date"), row.get("contract"))
        old = latest.get(key)
        if old is None or rank.get(row.get("source_status"), -1) > rank.get(old.get("source_status"), -1):
            latest[key] = row

    candles = sorted(latest.values(), key=lambda r: (r.get("date") or "", r.get("contract") or ""))
    by_date = {}
    for row in candles:
        row["is_active"] = False
        by_date.setdefault(row["date"], []).append(row)
    for date_rows in by_date.values():
        active = max(
            date_rows,
            key=lambda r: (
                r["volume"] if r.get("volume") is not None else -1,
                r["open_interest"] if r.get("open_interest") is not None else -1,
            ),
        )["contract"]
        for row in date_rows:
            row["is_active"] = row["contract"] == active

    contracts = {}
    for row in candles:
        contracts.setdefault(row["contract"], []).append(row)
    dates = sorted(by_date)
    active = next((r for r in candles if dates and r["date"] == dates[-1] and r["is_active"]), None)
    return candles, contracts, dates, active


def validate_master(data):
    errors = []
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version")
    if data.get("parser_version") != PARSER_VERSION:
        errors.append("parser_version")
    if not isinstance(data.get("observations"), list) or not data["observations"]:
        errors.append("observations")
    if not isinstance(data.get("candles"), list):
        errors.append("candles")
    required = {
        "date", "contract", "open", "high", "low", "close", "settlement",
        "price_change", "volume", "volume_globex", "volume_pnt_pit",
        "open_interest", "oi_change", "source_file", "source_status",
        "bulletin_number", "source_page", "source_sha256", "parser_version",
    }
    for i, row in enumerate(data.get("observations", [])):
        missing = sorted(required - set(row))
        if missing:
            errors.append(f"observation[{i}] missing: {','.join(missing)}")
            break
        if not CONTRACT_RE.fullmatch(str(row["contract"])):
            errors.append(f"observation[{i}] invalid contract")
            break
        if row["source_status"] not in {"PRELIMINARY", "FINAL"}:
            errors.append(f"observation[{i}] invalid source_status")
            break
        if row["volume"] is not None:
            expected = (row["volume_globex"] or 0) + (row["volume_pnt_pit"] or 0)
            if row["volume"] != expected:
                errors.append(f"observation[{i}] volume mismatch")
                break
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="?", type=Path)
    ap.add_argument("--input-dir", type=Path, default=Path("data/cme-pg62"))
    ap.add_argument("--output", type=Path, default=Path("data/cme-gc-history.json"))
    args = ap.parse_args()

    pdfs = [args.pdf] if args.pdf else sorted(args.input_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PG62 PDF files found in {args.input_dir}")

    existing = load_existing(args.output)
    obs_map = {observation_key(r): r for r in existing.get("observations", [])}
    provenance_map = {
        (p.get("source_file"), p.get("source_sha256")): p
        for p in existing.get("provenance", [])
    }

    parsed = []
    for path in pdfs:
        print(f"Parsing: {path}")
        meta, rows, provenance = extract_pdf(path)
        digest = provenance["source_sha256"]
        # Replace only the exact same source artifact; keep PRELIM/FINAL and
        # different bulletin files as independent observed records.
        for key in list(obs_map):
            if obs_map[key].get("source_file") == path.name and obs_map[key].get("source_sha256") == digest:
                del obs_map[key]
        for row in rows:
            row["source_sha256"] = digest
            row["parser_version"] = PARSER_VERSION
            obs_map[observation_key(row)] = row
        provenance_map[(path.name, digest)] = provenance
        parsed.append((path.name, meta, len(rows)))
        print(f"  {meta['trade_date']} {meta['bulletin_status']} bulletin={meta['bulletin_number']} rows={len(rows)}")

    observations = sorted(
        obs_map.values(),
        key=lambda r: (
            r.get("date") or "",
            r.get("contract") or "",
            r.get("source_status") or "",
            r.get("source_file") or "",
        ),
    )
    candles, contracts, dates, latest_active = rebuild(observations)

    data = {
        "schema_version": SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "latest_date": dates[-1] if dates else None,
        "latest_active": latest_active,
        "dates": dates,
        "contracts": contracts,
        "candles": candles,
        "observations": observations,
        "provenance": sorted(
            provenance_map.values(),
            key=lambda p: (p.get("trade_date") or "", p.get("source_file") or ""),
        ),
        "notes": {
            "master_semantics": "Observed source facts only",
            "candles_semantics": "Latest/default observation view; FINAL preferred over PRELIMINARY",
            "active_semantics": "EOD representative only; highest volume then open interest",
            "missing_value": "---- is stored as null, never as zero",
            "analysis_boundary": "IV/Gamma/GEX/regime/dealer positioning are not calculated here",
        },
    }

    errors = validate_master(data)
    if errors:
        raise RuntimeError("MASTER validation failed: " + "; ".join(errors))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(args.output.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(args.output)

    print("\n========================================")
    print("PG62 MASTER generation complete")
    print("========================================")
    print(f"Generated source files: {len(parsed)}")
    print(f"Observations:           {len(observations)}")
    print(f"Default rows:           {len(candles)}")
    print(f"Dates:                  {len(dates)}")
    if latest_active:
        print(f"Latest active:          {latest_active['contract']} {latest_active['settlement']}")
    print(f"Output:                 {args.output}")


if __name__ == "__main__":
    main()
