import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "cme-pg62"
OUT_FILE = ROOT / "data" / "cme-gc-history.json"

PARSER_VERSION = "pg62-gold-v2.0.0"

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
    "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
CONTRACT_RE = re.compile(r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})$", re.I)

# PG62 is a fixed-width report, but the parser uses x-ranges only after
# semantic discovery of the GC section. These are local column bands, not
# meanings inferred from the extracted text order.
X = {
    "contract": (0, 70),
    "open": (90, 180),
    "high_low": (180, 280),
    "settlement": (270, 310),
    "change": (310, 360),
    "globex_volume": (390, 465),
    "pnt_volume": (465, 520),
    "open_interest": (520, 560),
    "oi_change": (560, 610),
}


def clean(s):
    return str(s or "").strip().replace(",", "")


def parse_number(s):
    s = clean(s)
    if not s or s.upper() in {"-", "--", "---", "----"}:
        return None
    if s.upper() == "UNCH":
        return 0.0
    s = s.replace("B", "").replace("A", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_int(s):
    value = parse_number(s)
    return None if value is None else int(round(value))


def parse_signed(words):
    text = "".join(clean(w.get("text")) for w in words)
    text = text.replace(" ", "")
    if text.upper() == "UNCH":
        return 0.0
    if text in {"-", "--", "---", "----", ""}:
        return None
    text = text.replace("B", "").replace("A", "")
    try:
        return float(text)
    except ValueError:
        return None


def numeric_prices(text):
    """Extract price values from a single price/high-low cell."""
    text = clean(text).replace("B", "").replace("A", "")
    if not text or set(text) <= {"-", "/", " "}:
        return []
    # Handles both 4422.20/4362.70 and concatenated 4510.804447.20.
    parts = [p for p in text.replace("/", " ").split() if p]
    out = []
    for part in parts:
        if re.fullmatch(r"\d+(?:\.\d+)?", part):
            out.append(float(part))
            continue
        m = re.fullmatch(r"(\d{3,4}\.\d{2})(\d{3,4}\.\d{2})", part)
        if m:
            out.extend([float(m.group(1)), float(m.group(2))])
    return out


def find_bulletin_date(pdf):
    full = "January|February|March|April|May|June|July|August|September|October|November|December"
    short = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
    weekday = "Mon|Tue|Wed|Thu|Fri|Sat|Sun"
    month_map = MONTHS

    for page in pdf.pages:
        text = page.extract_text() or ""
        patterns = [
            rf"\b(?:{weekday})\.?[,]?\s+({short}|{full})\s+(\d{{1,2}}),\s*(\d{{2,4}})\b",
            rf"\b({short}|{full})\s+(\d{{1,2}}),\s*(\d{{2,4}})\b",
            r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.I)
            if not m:
                continue
            g = m.groups()
            if g[0][:3].upper() in month_map:
                month, day, year = month_map[g[0][:3].upper()], int(g[1]), int(g[2])
            else:
                month, day, year = int(g[0]), int(g[1]), int(g[2])
            if year < 100:
                year += 2000
            return f"{year:04d}-{month:02d}-{day:02d}"

    return None


def words_in_band(words, x0, x1):
    return [w for w in words if w["x0"] >= x0 and w["x0"] < x1]


def row_words(words, top, tolerance=1.0):
    return sorted(
        [w for w in words if abs(w["top"] - top) <= tolerance],
        key=lambda w: w["x0"],
    )


def parse_gc_coordinate_row(words, trade_date):
    contract_words = words_in_band(words, *X["contract"])
    if not contract_words:
        return None
    contract = clean(contract_words[0]["text"]).upper()
    m = CONTRACT_RE.fullmatch(contract)
    if not m:
        return None
    contract = f"{m.group(1).upper()}{int(m.group(2)):02d}"

    open_words = words_in_band(words, *X["open"])
    hl_words = words_in_band(words, *X["high_low"])
    settlement_words = words_in_band(words, *X["settlement"])
    change_words = words_in_band(words, *X["change"])
    globex_words = words_in_band(words, *X["globex_volume"])
    pnt_words = words_in_band(words, *X["pnt_volume"])
    oi_words = words_in_band(words, *X["open_interest"])
    oi_change_words = words_in_band(words, *X["oi_change"])

    open_price = parse_number(open_words[0]["text"]) if open_words else None
    hl_text = " ".join(w["text"] for w in hl_words)
    hl_prices = numeric_prices(hl_text)
    high_price = hl_prices[0] if len(hl_prices) >= 1 else None
    low_price = hl_prices[1] if len(hl_prices) >= 2 else None

    settlement = parse_number(settlement_words[0]["text"]) if settlement_words else None
    price_change = parse_signed(change_words)

    globex_volume = parse_int(globex_words[0]["text"]) if globex_words else None
    pnt_volume = parse_int(pnt_words[0]["text"]) if pnt_words else None
    open_interest = parse_int(oi_words[0]["text"]) if oi_words else None
    oi_change = parse_signed(oi_change_words)
    if oi_change is not None:
        oi_change = int(round(oi_change))

    # IMPORTANT: ---- means unavailable, not zero.
    volume = None
    if globex_volume is not None or pnt_volume is not None:
        volume = (globex_volume or 0) + (pnt_volume or 0)

    row = {
        "date": trade_date,
        "contract": contract,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": settlement,
        "settlement": settlement,
        "price_change": price_change,
        "volume": volume,
        "volume_globex": globex_volume,
        "volume_pnt_pit": pnt_volume,
        "open_interest": open_interest,
        "oi_change": oi_change,
        "is_active": False,
    }
    validate_row(row)
    return row


def validate_row(row):
    problems = []
    for k in ("volume", "volume_globex", "volume_pnt_pit", "open_interest"):
        v = row.get(k)
        if v is not None and v < 0:
            problems.append(f"negative {k}={v}")
    if row.get("high") is not None and row.get("low") is not None and row["high"] < row["low"]:
        problems.append(f"high<{row['low']=}")
    if row.get("volume_globex") is not None and row["volume_globex"] > 2_000_000:
        problems.append(f"implausible globex volume={row['volume_globex']}")
    if row.get("open_interest") is not None and row["open_interest"] > 10_000_000:
        problems.append(f"implausible open interest={row['open_interest']}")
    if problems:
        raise ValueError(f"PG62 validation failed for {row['date']} {row['contract']}: " + "; ".join(problems))


def is_gc_header(words):
    text = " ".join(w["text"] for w in words)
    return "GC FUT COMEX GOLD FUTURES" in text


def is_total_gc(words):
    text = " ".join(w["text"] for w in words).strip()
    return text.startswith("TOTAL GC FUT")


def extract_gc(pdf_path):
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        trade_date = find_bulletin_date(pdf)
        if not trade_date:
            raise RuntimeError(f"Could not find bulletin date inside PDF: {pdf_path.name}")

        in_gc = False
        ended = False
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=2, y_tolerance=3, keep_blank_chars=False)
            # Group words by visual line. This preserves the report's columns.
            groups = {}
            for w in words:
                key = round(w["top"], 1)
                groups.setdefault(key, []).append(w)

            for top in sorted(groups):
                line_words = sorted(groups[top], key=lambda w: w["x0"])
                line_text = " ".join(w["text"] for w in line_words)

                if is_gc_header(line_words):
                    in_gc = True
                    continue
                if not in_gc:
                    continue
                if is_total_gc(line_words):
                    ended = True
                    break

                contract = clean(line_words[0]["text"]).upper() if line_words else ""
                if not CONTRACT_RE.fullmatch(contract):
                    continue
                if line_words[0]["x0"] > 50:
                    continue

                row = parse_gc_coordinate_row(line_words, trade_date)
                if row:
                    rows.append(row)

            if ended:
                break

        return trade_date, finalize_rows(rows)


def finalize_rows(rows):
    if not rows:
        raise RuntimeError("No GC futures rows found in PDF.")

    # This is an EOD representative/active-contract rule, not an intraday fact.
    active = max(rows, key=lambda r: (r.get("volume") or 0, r.get("open_interest") or 0))
    active_contract = active["contract"]
    for row in rows:
        row["is_active"] = row["contract"] == active_contract
    return rows


def file_sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_history():
    if not OUT_FILE.exists():
        return {"updated_at": None, "dates": [], "contracts": {}, "candles": []}
    try:
        with OUT_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"updated_at": None, "dates": [], "contracts": {}, "candles": []}


def save_history(history):
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def main():
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        raise RuntimeError(f"No PDF files found in {PDF_DIR}")

    history = load_history()
    existing = {}
    for row in history.get("candles", []):
        key = (row.get("date"), row.get("contract"))
        existing[key] = row

    provenance = []
    for pdf_path in pdfs:
        print(f"\nParsing {pdf_path.name}")
        trade_date, rows = extract_gc(pdf_path)
        print(f"  Date: {trade_date}; rows: {len(rows)}")
        for row in rows:
            existing[(row["date"], row["contract"])] = row
        provenance.append({
            "source_file": pdf_path.name,
            "source_sha256": file_sha256(pdf_path),
            "trade_date": trade_date,
            "parser_version": PARSER_VERSION,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        })

    candles = sorted(existing.values(), key=lambda r: (r.get("date") or "", r.get("contract") or ""))
    contracts = {}
    for row in candles:
        contracts.setdefault(row["contract"], []).append(row)
    dates = sorted({r["date"] for r in candles if r.get("date")})
    latest_active = None
    if dates:
        latest = [r for r in candles if r["date"] == dates[-1] and r.get("is_active")]
        if latest:
            latest_active = latest[0]

    history = {
        "schema_version": "pg62-gc-master-v2",
        "parser_version": PARSER_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "latest_date": dates[-1] if dates else None,
        "latest_active": latest_active,
        "dates": dates,
        "contracts": contracts,
        "candles": candles,
        "provenance": provenance,
    }
    save_history(history)
    print(f"Saved {len(candles)} contract-day rows")
    print(f"Saved {len(dates)} dates")
    if latest_active:
        print(f"Latest active: {latest_active['contract']} {latest_active['settlement']}")
    print(f"Output: {OUT_FILE}")


if __name__ == "__main__":
    main()
