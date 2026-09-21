import json
import re
from datetime import datetime, timezone
from pathlib import Path

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


def clean(s):
    return str(s or "").strip().replace(",", "")


def to_number(s):
    """
    Convert CME numeric fields to float.

    ---- / --- / -- / - => None
    UNCH => 0
    """

    s = clean(s)

    if not s:
        return None

    if s.upper() == "UNCH":
        return 0.0

    s = s.replace("B", "").replace("A", "")

    if s in {"-", "--", "---", "----"}:
        return None

    try:
        return float(s)
    except ValueError:
        return None


def to_int(s):
    value = to_number(s)

    if value is None:
        return None

    return int(round(value))


def find_bulletin_date(pdf):
    """
    Find the bulletin date INSIDE the PDF.

    The filename is deliberately never used.

    CME PG62 examples include:

        Fri, Sep 18, 2026

    We also support numeric dates and month-name dates.
    """

    month_map = MONTHS

    full_months = (
        "January|February|March|April|May|June|July|August|"
        "September|October|November|December"
    )

    short_months = (
        "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
    )

    weekday = (
        "Mon|Tue|Wed|Thu|Fri|Sat|Sun"
    )

    # ------------------------------------------------------------
    # Search normal extracted text.
    # ------------------------------------------------------------

    for page in pdf.pages:

        text = page.extract_text() or ""

        # Example:
        # Fri, Sep 18, 2026
        patterns = [
            rf"\b(?:{weekday})\.?,?\s+"
            rf"({short_months}|{full_months})\s+"
            rf"(\d{{1,2}}),\s*(\d{{2,4}})\b",

            rf"\b({short_months}|{full_months})\s+"
            rf"(\d{{1,2}}),\s*(\d{{2,4}})\b",

            # 09/18/2026 or 09/18/26
            r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b",
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE,
            )

            if not match:
                continue

            groups = match.groups()

            # Month-name date.
            if groups[0][:3].upper() in month_map:

                month = month_map[
                    groups[0][:3].upper()
                ]

                day = int(groups[1])
                year = int(groups[2])

                if year < 100:
                    year += 2000

                return (
                    f"{year:04d}-"
                    f"{month:02d}-"
                    f"{day:02d}"
                )

            # Numeric date.
            month = int(groups[0])
            day = int(groups[1])
            year = int(groups[2])

            if year < 100:
                year += 2000

            return (
                f"{year:04d}-"
                f"{month:02d}-"
                f"{day:02d}"
            )

    # ------------------------------------------------------------
    # Search individual words.
    # This handles PDFs where the date is split into separate
    # positioned text objects.
    # ------------------------------------------------------------

    for page in pdf.pages:

        words = page.extract_words(
            x_tolerance=2,
            y_tolerance=3,
            keep_blank_chars=False,
        )

        for i, word in enumerate(words):

            current = clean(
                word.get("text", "")
            )

            nearby = " ".join(
                clean(w.get("text", ""))
                for w in words[i:i + 5]
            )

            # Example:
            # Fri, Sep 18, 2026
            match = re.search(
                rf"\b(?:{weekday})\.?,?\s+"
                rf"({short_months}|{full_months})\s+"
                rf"(\d{{1,2}}),?\s*(\d{{2,4}})\b",
                nearby,
                re.IGNORECASE,
            )

            if match:

                month = month_map[
                    match.group(1)[:3].upper()
                ]

                day = int(match.group(2))
                year = int(match.group(3))

                if year < 100:
                    year += 2000

                return (
                    f"{year:04d}-"
                    f"{month:02d}-"
                    f"{day:02d}"
                )

            # Numeric date as one PDF word.
            match = re.fullmatch(
                r"(\d{1,2})/(\d{1,2})/(\d{2,4})",
                current,
            )

            if match:

                month = int(match.group(1))
                day = int(match.group(2))
                year = int(match.group(3))

                if year < 100:
                    year += 2000

                return (
                    f"{year:04d}-"
                    f"{month:02d}-"
                    f"{day:02d}"
                )

    return None


def split_price_token(token):
    """
    Extract one or more Gold prices from a PDF token.

    Handles:

        4510.80B
        4447.20A
        4510.80B/4447.20A
        4510.804447.20
    """

    token = clean(token)

    if not token:
        return []

    token = token.replace("B", "")
    token = token.replace("A", "")

    # Slash-separated bid/ask or high/low.
    if "/" in token:

        result = []

        for part in token.split("/"):

            if re.fullmatch(
                r"\d+(?:\.\d+)?",
                part,
            ):
                result.append(float(part))

        return result

    # Normal price.
    if re.fullmatch(
        r"\d+(?:\.\d+)?",
        token,
    ):
        return [float(token)]

    # PDF may concatenate two prices:
    #
    # 4510.804447.20
    #
    match = re.fullmatch(
        r"(\d{3,4}\.\d{2})(\d{3,4}\.\d{2})",
        token,
    )

    if match:

        return [
            float(match.group(1)),
            float(match.group(2)),
        ]

    return []


def normalize_gc_line(line):
    """
    Normalize PDF extraction artifacts.
    """

    line = " ".join(line.split())

    # Combine separated signs:
    #
    # + 25.20 -> +25.20
    # - 581   -> -581
    #
    line = re.sub(
        r"([+-])\s+(\d+(?:\.\d+)?)",
        r"\1\2",
        line,
    )

    # Separate B/A markers:
    #
    # 4510.80B -> 4510.80 B
    # 4447.20A -> 4447.20 A
    line = re.sub(
        r"(?<=\d)(?=[BA])",
        " ",
        line,
    )

    # Put slash on its own.
    line = line.replace("/", " / ")

    # Split concatenated prices:
    #
    # 4510.804447.20
    # -> 4510.80 4447.20
    line = re.sub(
        r"(\d{3,4}\.\d{2})(?=\d{3,4}\.\d{2})",
        r"\1 ",
        line,
    )

    return " ".join(line.split())


def parse_gc_line(line, trade_date):
    """
    Parse one CME GC futures row.

    Actual CME structure:

      CONTRACT
      OPEN
      HIGH/LOW
      SETTLEMENT
      CHANGE
      GLOBEX VOLUME
      PNT/PIT VOLUME
      OPEN INTEREST
      OI CHANGE

    Example:

      DEC26 4381.60 4439.80 /4372.20 4424.90
      +25.20 141307 1612 315327 +1194
    """

    line = normalize_gc_line(line)

    match = re.match(
        r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
        r"(\d{2})\b(.*)$",
        line,
        re.IGNORECASE,
    )

    if not match:
        return None

    month = match.group(1).upper()
    year = int(match.group(2))

    contract = f"{month}{year:02d}"

    rest = match.group(3).strip()
    tokens = rest.split()

    # Need:
    #
    # price(s)
    # price change
    # globex volume
    # PNT/PIT volume
    # OI
    # OI change
    if len(tokens) < 5:
        return None

    # ------------------------------------------------------------
    # Work backwards from the right.
    #
    # Example:
    #
    # +25.20 141307 1612 315327 +1194
    #
    #                 [-4] [-3] [-2] [-1]
    # ------------------------------------------------------------

    oi_change_raw = tokens[-1]
    oi_raw = tokens[-2]
    pnt_raw = tokens[-3]
    globex_raw = tokens[-4]
    price_change_raw = tokens[-5]

    globex_volume = to_int(globex_raw)
    pnt_volume = to_int(pnt_raw)
    open_interest = to_int(oi_raw)

    oi_change = to_int(oi_change_raw)

    price_change = to_number(
        price_change_raw
    )

    # If CME says UNCH, represent change as 0.
    if str(oi_change_raw).upper() == "UNCH":
        oi_change = 0

    if str(price_change_raw).upper() == "UNCH":
        price_change = 0

    # Total volume = Globex + PNT/PIT.
    #
    # Missing ---- means zero.
    volume = (
        (globex_volume or 0)
        +
        (pnt_volume or 0)
    )

    # ------------------------------------------------------------
    # Prices.
    # ------------------------------------------------------------

    price_tokens = tokens[:-5]

    prices = []

    for token in price_tokens:

        prices.extend(
            split_price_token(token)
        )

    if not prices:
        return None

    settlement = prices[-1]

    open_price = None
    high_price = None
    low_price = None

    # Standard:
    #
    # OPEN HIGH LOW SETTLEMENT
    if len(prices) >= 4:

        open_price = prices[0]
        high_price = prices[1]
        low_price = prices[2]
        settlement = prices[3]

    # Some CME rows have:
    #
    # OPEN HIGH SETTLEMENT
    elif len(prices) == 3:

        open_price = prices[0]
        high_price = prices[1]
        settlement = prices[2]

    # Example:
    #
    # ---- 4378.00B 4385.90
    elif len(prices) == 2:

        open_price = prices[0]
        settlement = prices[1]

    # Example:
    #
    # ---- ---- 4518.00
    elif len(prices) == 1:

        settlement = prices[0]

    return {
        "date": trade_date,
        "contract": contract,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": settlement,
        "settlement": settlement,
        "price_change": price_change,
        "volume": volume,
        "volume_globex": globex_volume or 0,
        "volume_pnt_pit": pnt_volume or 0,
        "open_interest": open_interest,
        "oi_change": oi_change,
        "is_active": False,
    }


def extract_gc(pdf_path):
    """
    Extract the GC section from the actual PDF.

    Important:
    The GC section continues across PDF pages.
    We therefore DO NOT stop just because another page starts.

    We stop only at:
        TOTAL GC FUT
    """

    rows = []

    with pdfplumber.open(pdf_path) as pdf:

        trade_date = find_bulletin_date(pdf)

        if not trade_date:
            raise RuntimeError(
                "Could not find bulletin date inside PDF: "
                f"{pdf_path.name}"
            )

        print(
            f"  Bulletin date from PDF: {trade_date}"
        )

        in_gc = False

        for page_number, page in enumerate(
            pdf.pages,
            start=1,
        ):

            text = page.extract_text() or ""

            for raw_line in text.splitlines():

                line = " ".join(
                    raw_line.split()
                )

                if not line:
                    continue

                # GC section starts here.
                if "GC FUT COMEX GOLD FUTURES" in line:

                    in_gc = True
                    continue

                if not in_gc:
                    continue

                # GC section ends here.
                if line.startswith(
                    "TOTAL GC FUT"
                ):

                    return trade_date, finalize_rows(
                        rows
                    )

                # Ignore page headers.
                if "PG62 BULLETIN" in line:
                    continue

                if "PRELIMINARY" in line:
                    continue

                if "METAL FUTURES PRODUCTS" in line:
                    continue

                result = parse_gc_line(
                    line,
                    trade_date,
                )

                if result:
                    rows.append(result)

    return trade_date, finalize_rows(rows)


def finalize_rows(rows):
    """
    Determine active contract by total GC volume.
    """

    if not rows:
        raise RuntimeError(
            "No GC futures rows found in PDF."
        )

    # Highest total volume = active contract for Stage 2.
    active = max(
        rows,
        key=lambda r: (
            r.get("volume") or 0,
            r.get("open_interest") or 0,
        ),
    )

    active_contract = active["contract"]

    for row in rows:

        row["is_active"] = (
            row["contract"]
            == active_contract
        )

    print(
        f"  GC contracts parsed: {len(rows)}"
    )

    print(
        f"  Active contract: {active_contract}"
    )

    print(
        f"  Active volume: "
        f"{active.get('volume', 0):,}"
    )

    return rows


def load_history():
    if not OUT_FILE.exists():

        return {
            "updated_at": None,
            "dates": [],
            "contracts": {},
            "candles": [],
        }

    try:

        with OUT_FILE.open(
            "r",
            encoding="utf-8",
        ) as f:

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
        exist_ok=True,
    )

    with OUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            history,
            f,
            ensure_ascii=False,
            indent=2,
        )


def main():

    pdfs = sorted(
        PDF_DIR.glob("*.pdf")
    )

    if not pdfs:

        raise RuntimeError(
            f"No PDF files found in {PDF_DIR}"
        )

    history = load_history()

    # ------------------------------------------------------------
    # Existing data.
    # ------------------------------------------------------------

    existing = {}

    for row in history.get(
        "candles",
        [],
    ):

        key = (
            row.get("date"),
            row.get("contract"),
        )

        existing[key] = row

    # ------------------------------------------------------------
    # Parse every PDF currently in the folder.
    # ------------------------------------------------------------

    for pdf_path in pdfs:

        print("")
        print(
            f"Parsing {pdf_path.name}"
        )

        trade_date, rows = extract_gc(
            pdf_path
        )

        print(
            f"  Date: {trade_date}"
        )

        for row in rows:

            key = (
                row["date"],
                row["contract"],
            )

            existing[key] = row

    # ------------------------------------------------------------
    # Rebuild candles.
    # ------------------------------------------------------------

    candles = list(
        existing.values()
    )

    candles.sort(
        key=lambda row: (
            row.get("date") or "",
            row.get("contract") or "",
        )
    )

    # ------------------------------------------------------------
    # Rebuild contract index.
    # ------------------------------------------------------------

    contracts = {}

    for row in candles:

        contract = row["contract"]

        contracts.setdefault(
            contract,
            [],
        )

        contracts[contract].append(
            row
        )

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

    # ------------------------------------------------------------
    # Latest active contract.
    # ------------------------------------------------------------

    latest_active = None

    if dates:

        latest_date = dates[-1]

        latest_rows = [
            row
            for row in candles
            if row["date"] == latest_date
            and row.get("is_active")
        ]

        if latest_rows:

            latest_active = latest_rows[0]

    history = {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "latest_date": (
            dates[-1]
            if dates
            else None
        ),

        "latest_active": latest_active,

        "dates": dates,

        "contracts": contracts,

        "candles": candles,
    }

    save_history(history)

    print("")
    print(
        f"Saved {len(candles)} contract-day rows"
    )

    print(
        f"Saved {len(dates)} dates"
    )

    if latest_active:

        print(
            "Latest active: "
            f"{latest_active['contract']} "
            f"{latest_active['settlement']}"
        )

    print(
        f"Output: {OUT_FILE}"
    )


if __name__ == "__main__":
    main()
