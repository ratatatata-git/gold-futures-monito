#!/usr/bin/env python3
"""PG64 Gold options parser v1.

RAW -> MASTER only. No IV/Gamma/GEX or other derived analytics are written.
Uses semantic Gold-section discovery and local coordinate bands for the stable
CME PG64 table geometry; page number is never used to identify meaning.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pdfplumber

PARSER_VERSION = "pg64-gold-v1.0.0"

# Possible CME Product Master codes, not simultaneously listed contracts.
PRODUCT_CODES = {"OG", "OMG", "OG1", "OG2", "OG3", "OG4", "OG5"}
PRODUCT_CODES |= {f"G{i}{d}" for d in "MTWR" for i in range(1,6)}
PRODUCT_CODES |= {f"{i}MG" for i in range(1,6)}
PRODUCT_CODES |= {f"{i}WG" for i in range(1,6)}
PRODUCT_CODES |= {f"{i}FG" for i in range(1,6)}

FAMILY_META = {
    "GMW": ("GOLD_WEEKLY", "MONDAY"),
    "GWT": ("GOLD_WEEKLY", "TUESDAY"),
    "GWW": ("GOLD_WEEKLY", "WEDNESDAY"),
    "GWR": ("GOLD_WEEKLY", "THURSDAY"),
    "MMG": ("MICRO_GOLD_WEEKLY", "MONDAY"),
    "WMG": ("MICRO_GOLD_WEEKLY", "WEDNESDAY"),
    "FMG": ("MICRO_GOLD_WEEKLY", "FRIDAY"),
}

# Local x anchors observed from the CME PG64 table. The parser validates them
# against the header on each page before using them.
EXPECTED_X = {
    "open_outcry_volume": 53,
    "open_range": 85,
    "open_outcry_high_low": 160,
    "globex_high_low": 225,
    "open_outcry_close_range": 277,
    "settlement": 349,
    "price_change": 378,
    "delta": 411,
    "exercises": 437,
    "globex_open": 467,
    "pnt_volume": 521,
    "globex_volume": 527,
    "open_interest": 574,
    "status": 587,
}

NUM_RE = re.compile(r"^[+-]?(?:\d+(?:,\d{3})*|\d+\.\d+)$")
STRIKE_RE = re.compile(r"^\d{2,5}(?:\.\d+)?$")
EXPIRY_RE = re.compile(r"^(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2}$", re.I)


def clean(v: str | None):
    if v is None: return None
    v = v.strip()
    return None if v in {"----", "—", "- - - -"} else v


def number(v: str | None):
    v = clean(v)
    if v is None: return None
    v = v.replace(",", "")
    try:
        if re.fullmatch(r"[+-]?\d+", v): return int(v)
        return float(v)
    except ValueError:
        return None


def parse_pair(v: str | None):
    v = clean(v)
    if v is None: return None
    # Preserve CME bid/ask annotations (B/A) as raw strings; MASTER is observed.
    return v


def parse_change(v: str | None):
    v = clean(v)
    if v is None: return None
    try: return float(v.replace(",", ""))
    except ValueError: return v


def parse_bulletin_meta(text: str):
    m = re.search(r"PG64 BULLETIN #\s*(\d+)@.*?(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s*([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4}).*?PG64", text, re.S)
    if not m:
        m = re.search(r"PG64 BULLETIN #\s*(\d+)@.*?([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4}).*?PG64", text, re.S)
    status = "FINAL" if re.search(r"\bFINAL\b", text[:1000]) else ("PRELIMINARY" if re.search(r"\bPRELIMINARY\b", text[:1000]) else None)
    if not m: return {"bulletin_number": None, "trade_date": None, "bulletin_status": status}
    mon, day, year = m.group(3), int(m.group(4)), int(m.group(5))
    date = datetime.strptime(f"{mon} {day} {year}", "%b %d %Y").date().isoformat()
    return {"bulletin_number": int(m.group(1)), "trade_date": date, "bulletin_status": status}


def family_to_code(label: str, week: int | None, direct: str | None):
    if direct:
        return direct if direct in PRODUCT_CODES else None
    if not week: return None
    mapping = {"GMW":"M", "GWT":"T", "GWW":"W", "GWR":"R"}
    if label in mapping: return f"G{week}{mapping[label]}"
    if label == "MMG": return f"{week}MG"
    if label == "WMG": return f"{week}WG"
    if label == "FMG": return f"{week}FG"
    return None


def parse_family_header(line: str):
    u = re.sub(r"\s+", " ", line.upper()).strip()
    m = re.match(r"(OG\d?|OMG|GMW|GWT|GWW|GWR|MMG|WMG|FMG)\b", u)
    if not m or "GOLD" not in u or "OPTION" not in u:
        return None
    label = m.group(1)
    direct = label if label in {"OG","OG1","OG2","OG3","OG4","OG5","OMG"} else None
    week_m = re.search(r"\bWEEK\s*([1-5])\b", u)
    week = int(week_m.group(1)) if week_m else None
    if label in FAMILY_META:
        family, weekday = FAMILY_META[label]
    elif label.startswith("OG"):
        family, weekday = "GOLD_MONTHLY_OR_WEEKLY_FRIDAY", "FRIDAY"
    else:
        family, weekday = "GOLD_MONTHLY", None
    return {"product_family_label": label, "product_family": family,
            "weekday": weekday, "week_number": week,
            "product_code": family_to_code(label, week, direct),
            "header_raw": line}


def parse_option_type(line: str):
    u = line.upper()
    if " GOLD OPTIONS" not in u: return None
    if re.search(r"\bCALL\b", u): return "CALL"
    if re.search(r"\bPUT\b", u): return "PUT"
    if re.search(r"\bOPT\b", u): return "UNKNOWN"
    return None


def nearest_word(words, x, tol=9):
    candidates = [w for w in words if abs((w["x0"]+w["x1"])/2 - x) <= tol]
    if not candidates: return None
    return min(candidates, key=lambda w: abs((w["x0"]+w["x1"])/2-x))


def header_validation(words):
    # Header anchor validation. We require several unambiguous anchors.
    anchors = {}
    for w in words:
        t = w["text"].upper()
        cx = (w["x0"]+w["x1"])/2
        if t == "DELTA": anchors["delta"] = cx
        elif t == "EXER": anchors["exercises"] = cx
        elif t == "PNT": anchors["pnt_volume"] = cx
        elif t == "INTEREST": anchors["open_interest"] = cx
    checks = []
    for k, x in anchors.items():
        checks.append(abs(x-EXPECTED_X[k]) <= 12)
    return sum(checks) >= 3, anchors


def row_from_words(row_words):
    # Coordinate bands intentionally leave gaps between columns.
    fields = {}
    bands = {
      "strike": (10, 40), "open_outcry_volume": (40, 68), "open_range": (68, 108),
      "open_outcry_high_low": (108, 188), "globex_high_low": (188, 260),
      "open_outcry_close_range": (260, 310), "settlement": (310, 363),
      "price_change": (363, 397), "delta": (397, 426), "exercises": (426, 452),
      "globex_open": (452, 482), "pnt_volume": (482, 512), "globex_volume": (512, 546),
      "open_interest": (546, 575), "status": (575, 610),
    }
    for name,(lo,hi) in bands.items():
        vals=[w["text"] for w in row_words if lo <= (w["x0"]+w["x1"])/2 < hi]
        if vals: fields[name]=" ".join(vals)
    if "strike" not in fields or not STRIKE_RE.match(fields["strike"]): return None
    return {
      "strike": number(fields["strike"]),
      "open_outcry_volume": number(fields.get("open_outcry_volume")),
      "open_outcry_open_range": parse_pair(fields.get("open_range")),
      "open_outcry_high_low": parse_pair(fields.get("open_outcry_high_low")),
      "globex_high_low": parse_pair(fields.get("globex_high_low")),
      "open_outcry_close_range": parse_pair(fields.get("open_outcry_close_range")),
      "settlement": number(fields.get("settlement")),
      "price_change": parse_change(fields.get("price_change")),
      "open_interest": number(fields.get("open_interest")),
      "delta": number(fields.get("delta")),
      "exercises": number(fields.get("exercises")),
      "globex_open": number(fields.get("globex_open")),
      "pnt_volume": number(fields.get("pnt_volume")),
      "globex_volume": number(fields.get("globex_volume")),
      "status": clean(fields.get("status")),
      "raw_row": " ".join(w["text"] for w in sorted(row_words,key=lambda w:w["x0"])),
    }


def parse_pdf(path: Path):
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    retrieved = datetime.now(timezone.utc).isoformat()
    rows=[]; totals=[]; eoo=[]; warnings=[]
    bulletin={}
    with pdfplumber.open(path) as pdf:
        # Global metadata from first pages.
        all_first="\n".join((p.extract_text() or "") for p in pdf.pages[:2])
        bulletin=parse_bulletin_meta(all_first)
        state=None
        for page_no,page in enumerate(pdf.pages,1):
            words=page.extract_words(x_tolerance=1, y_tolerance=2, keep_blank_chars=False)
            text=page.extract_text() or ""
            # Semantic discovery: only pages containing a Gold option header are candidates.
            page_has_gold=bool(re.search(r"\b(?:OG\d?|OMG|GMW|GWT|GWW|GWR|MMG|WMG|FMG)\b.*\bGOLD\b.*\bOPTION", text, re.I))
            if not page_has_gold:
                # Do not leak Gold state into unrelated metals pages. Gold sections
                # repeat their semantic family header; a non-Gold page terminates state.
                state = None
                continue
            header_ok, header_anchors=header_validation(words)
            if page_has_gold and not header_ok:
                warnings.append({"page":page_no,"type":"header_validation","anchors":header_anchors})
            # Group words by visual line.
            lines={}
            for w in words:
                key=round(w["top"],1)
                # merge near-identical tops
                target=next((k for k in lines if abs(k-key)<=1.2),key)
                lines.setdefault(target,[]).append(w)
            current_state=state
            for top in sorted(lines):
                ws=sorted(lines[top],key=lambda w:w["x0"])
                line=" ".join(w["text"] for w in ws)
                fh=parse_family_header(line)
                if fh:
                    current_state=fh.copy()
                    current_state["option_type"]=parse_option_type(line)
                    continue
                ot=parse_option_type(line)
                if ot and current_state:
                    current_state["option_type"]=ot
                    continue
                if current_state and any(EXPIRY_RE.match(w["text"]) for w in ws):
                    exp=next(w["text"].upper() for w in ws if EXPIRY_RE.match(w["text"]))
                    # Expiry is a section line, not a strike row.
                    if len(ws)<=3:
                        current_state["expiry"]=exp
                        continue
                if current_state and ws and ws[0]["text"].upper()=="TOTAL":
                    vals=[w["text"] for w in ws[1:]]
                    totals.append({**current_state,"page":page_no,"total_tokens":vals,"raw":" ".join(w["text"] for w in ws)})
                    continue
                if current_state and ws and STRIKE_RE.match(ws[0]["text"]):
                    rr=row_from_words(ws)
                    if rr and "expiry" in current_state:
                        rec={"trade_date":bulletin.get("trade_date"),"bulletin_number":bulletin.get("bulletin_number"),
                             "bulletin_status":bulletin.get("bulletin_status"),"page":page_no,
                             "product_family":current_state.get("product_family"),"product_family_label":current_state.get("product_family_label"),
                             "product_code":current_state.get("product_code"),"weekday":current_state.get("weekday"),
                             "week_number":current_state.get("week_number"),"option_type":current_state.get("option_type"),
                             "expiry":current_state.get("expiry"),**rr}
                        rows.append(rec)
            state=current_state
    provenance={"source_file":path.name,"sha256":sha,"parser_version":PARSER_VERSION,"ingested_at":retrieved}
    return {"schema_version":"pg64.master.v1","provenance":provenance,"bulletin":bulletin,
            "rows":rows,"totals":totals,"eoo_block":eoo,"warnings":warnings}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("pdf",nargs="+",type=Path); ap.add_argument("-o","--output",type=Path,default=Path("pg64_master.json")); args=ap.parse_args()
    out=[]
    for p in args.pdf:
        out.append(parse_pdf(p))
    args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"wrote {args.output} ({len(out)} bulletin(s))")
    for x in out:
        print(x["bulletin"], "rows=",len(x["rows"]),"totals=",len(x["totals"]),"warnings=",len(x["warnings"]))

if __name__=="__main__": main()
