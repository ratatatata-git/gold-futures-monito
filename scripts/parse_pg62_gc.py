import json
import re
from pathlib import Path
from datetime import datetime

import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "cme-pg62"
OUT_FILE = ROOT / "data" / "cme-gc-history.json"


MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def clean_token(s):
    if s is None:
        return ""
    return s.strip().replace(",", "")


def number(s):
    """
    Convert a normal numeric token to float.
    B/A suffixes used by CME are removed.
    """
    s = clean_token(s)

    if not s:
        return None

    s = s.replace("B", "").replace("A", "")

    if s in {"-", "--", "---", "----"}:
        return None

    try:
        return float(s)
    except ValueError:
        return None


def find_bulletin_date(text):
    """
    Find a date such as:
      09/18/2026
      9/18/2026
    """
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text)

    if not m:
        return None

    month, day, year = map(int, m.groups())

    return f"{year:04d}-{month:02d}-{day:02d}"


def split_price_token(token):
    """
    Handle CME PDF extraction where two prices may become one token.

    Examples:
      4510.80B/4447.20A
      4510.804447.20
      4378.00B
      4447.20A

    Returns a list of numeric-looking price values.
    """
    token = clean_token(token)

    if not token:
        return []

    # Remove bid/ask markers but keep slash.
    token = token.replace("B", "").replace("A", "")

    # Normal slash-separated high/low.
    if "/" in token:
        parts = token.split("/")
        result = []

        for p in parts:
            if re.fullmatch(r"\d+(?:\.\d+)?", p):
                result.append(float(p))

        return result

    # Normal number.
    if re.fullmatch(r"\d+(?:\.\d+)?", token):
        return [float(token)]

    # PDF extraction sometimes glues two prices together:
    # 4510.804447.20
    #
    # Gold futures prices have two decimal places, so this pattern
    # safely separates them.
    m = re.fullmatch(
        r"(\d{3,4}\.\d{2})(\d{3,4}\.\d{2})",
        token
    )

    if m:
        return [float(m.group(1)), float(m.group(2))]

    return []


def parse_gc_line(line, trade_date):
    """
    Parse a GC futures contract row.

    Expected examples:

    DEC26 4381.60 4439.80 /4372.20 4424.90 +25.20
           141307 1612 315327 +1194

    APR27 4466.00 4510.80B/4447.20A 4498.50 +25.80
           2129 11 10307 +775

    SEP26 ---- 4378.00B 4385.90 +25.70 539 ---- 503 +117
    """

    line = " ".join(line.split())

    if not line:
        return None

    # Contract must start the row.
    m = re.match(
        r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})\b(.*)$",
        line,
        re.I,
    )

    if not m:
        return None

    month = m.group(1).upper()
    year2 = int(m.group(2))
    rest = m.group(3).strip()

    contract = f"{month}{year2:02d}"

    tokens = rest.split()

    # Need enough fields to contain settlement, change, volume,
    # volume/PIT, OI and OI change.
    if len(tokens) < 5:
        return None

    # ------------------------------------------------------------
    # IMPORTANT:
    # Work backwards from the right side.
    #
    # The last four fields in a normal GC row are:
    #
    # volume
    # PNT/PIT volume
    # open interest
    # OI change
    #
    # Some rows contain "----" for PNT/PIT.
    # ------------------------------------------------------------

    oi_change = number(tokens[-1])
    open_interest = number(tokens[-2])
    volume_pnt_pit = number(tokens[-3])
    volume = number(tokens[-4])

    if volume is None:
        return None

    # The field before volume is price change.
    price_change = number(tokens[-5])

    if price_change is None:
        return None

    price_tokens = tokens[:-5]

    # ------------------------------------------------------------
    # Extract all price values from the remaining tokens.
    # ------------------------------------------------------------

    prices = []

    for token in price_tokens:
        vals = split_price_token(token)
        prices.extend(vals)

    if not prices:
        return None

    # ------------------------------------------------------------
    # CME rows normally contain:
    #
    # open
    # high
    # low
    # settlement
    #
    # But some rows have missing open/high/low fields.
    #
    # Settlement is the final price before price change.
    # ------------------------------------------------------------

    settlement = prices[-1]

    open_price = None
    high_price = None
    low_price = None

    if len(prices) >= 4:
        open_price = prices[0]
        high_price = prices[1]
        low_price = prices[2]
        settlement = prices[3]

    elif len(prices) == 3:
        # Example of a shortened row.
        open_price = prices[0]
        high_price = prices[1]
        settlement = prices[2]

    elif len(prices) == 2:
        open_price = prices[0]
        settlement = prices[1]

    elif len(prices) == 1:
        settlement = prices[0]

    return {
        "date": trade_date,
        "contract": contract,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "settlement": settlement,
        "price_change": price_change,
        "volume": int(volume) if volume is not None else None,
        "volume_globex": None,
        "volume_pnt_pit": (
            int(volume_pnt_pit)
            if volume_pnt_pit is not None
            else None
        ),
        "open_interest": (
            int(open_interest)
            if open_interest is not None
            else None
        ),
        "oi_change": (
            int(oi_change)
            if oi_change is not None
            else None
        ),
    }


def extract_gc(pdf_path):
    """
    Extract GC futures rows from a CME PG62 PDF.
    """

    all_text = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_text.append(text)

    full_text = "\n".join(all_text)

    trade_date = find_bulletin_date(full_text)

    if not trade_date:
        raise RuntimeError(
            f"Could not find bulletin date in {pdf_path.name}"
        )

    lines = full_text.splitlines()

    in_gc = False
    rows = []

    for raw_line in lines:
        line = " ".join(raw_line.split())

        # Start of GC section.
        if "GC FUT COMEX GOLD FUTURES" in line:
            in_gc = True
            continue

        if not in_gc:
            continue

        # Stop at the next futures product section.
        if re.search(
            r"\b[A-Z]{2,4}\s+FUT\s+",
            line
        ) and "GC FUT COMEX GOLD FUTURES" not in line:
            break

        # Ignore headers.
        if line.startswith("CONTRACT"):
            continue

        if line.startswith("OPEN"):
            continue

        # Ignore total rows.
        if line.startswith("TOTAL"):
            continue

        result = parse_gc_line(line, trade_date)

        if result:
            rows.append(result)

    if not rows:
        raise RuntimeError(
            f"No GC futures rows found in {pdf_path.name}"
        )

    # ------------------------------------------------------------
    # Determine active contract.
    #
    # For now we use the highest-volume GC contract in the
    # bulletin. This can later be replaced with a more explicit
    # CME active-contract rule if desired.
    # ------------------------------------------------------------

    valid_volume_rows = [
        r for r in rows
        if r.get("volume") is not None
    ]

    if valid_volume_rows:
        active = max(
            valid_volume_rows,
            key=lambda r: r["volume"]
        )

        active_contract = active["contract"]

        for row in rows:
            row["is_active"] = (
                row["contract"] == active_contract
            )
    else:
        active_contract = None

        for row in rows:
            row["is_active"] = False

    return trade_date, rows


def load_history():
    if not OUT_FILE.exists():
        return {
            "updated_at": None,
            "dates": [],
            "contracts": {},
            "candles": [],
        }

    try:
        with OUT_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "updated_at": None,
            "dates": [],
            "contracts": {},
            "candles": [],
        }


def save_history(history):
    OUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with OUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            history,
            f,
            ensure_ascii=False,
            indent=2
        )


def main():
    PDFs = sorted(PDF_DIR.glob("*.pdf"))

    if not PDFs:
        raise RuntimeError(
            f"No PDF files found in {PDF_DIR}"
        )

    history = load_history()

    all_rows = []

    for pdf in PDFs:
        print(f"Parsing {pdf.name}")

        trade_date, rows = extract_gc(pdf)

        print(
            f"  Date: {trade_date}"
        )

        print(
            f"  GC rows: {len(rows)}"
        )

        all_rows.extend(rows)

    # ------------------------------------------------------------
    # Merge rows by date + contract.
    # ------------------------------------------------------------

    existing = {}

    for row in history.get("candles", []):
        key = (
            row.get("date"),
            row.get("contract")
        )
        existing[key] = row

    for row in all_rows:
        key = (
            row.get("date"),
            row.get("contract")
        )

        candle = {
            "date": row["date"],
            "contract": row["contract"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["settlement"],
            "settlement": row["settlement"],
            "volume": row["volume"],
            "open_interest": row["open_interest"],
            "oi_change": row["oi_change"],
            "is_active": row["is_active"],
        }

        existing[key] = candle

    candles = list(existing.values())

    candles.sort(
        key=lambda x: (
            x.get("date") or "",
            x.get("contract") or ""
        )
    )

    # ------------------------------------------------------------
    # Build contract history.
    # ------------------------------------------------------------

    contracts = {}

    for row in candles:
        contract = row["contract"]

        contracts.setdefault(
            contract,
            []
        )

        contracts[contract].append(row)

    # ------------------------------------------------------------
    # Dates.
    # ------------------------------------------------------------

    dates = sorted(
        {
            row["date"]
            for row in candles
            if row.get("date")
        }
    )

    history = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "dates": dates,
        "contracts": contracts,
        "candles": candles,
    }

    save_history(history)

    print(
        f"Saved {len(candles)} candles"
    )

    print(
        f"Saved {len(contracts)} contracts"
    )

    print(
        f"Output: {OUT_FILE}"
    )


if __name__ == "__main__":
    main()
