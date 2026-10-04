#!/usr/bin/env python3
"""PG62 Gold Futures -> fail-closed daily MASTER prototype (v5.0.0).

This first implementation deliberately scopes itself to the GC futures table.
It preserves source cell state/raw text, validates against TOTAL GC FUT, and
writes no MASTER when structural or reconciliation checks fail.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import pdfplumber

PARSER_VERSION = "pg62-gold-v5.0.0"
SCHEMA_VERSION = "pg62.master.daily.v5"
CONTRACT_RE = re.compile(r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})$", re.I)
GC_HEADER_RE = re.compile(r"\bGC\s+FUT\s+COMEX\s+GOLD\s+FUTURES\b", re.I)
NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)$")
NULL_TOKENS = {"----", "---", "--", "-", "—", "–"}
# Local PG62 table geometry. Geometry is checked against numeric/contract rows;
# these bands are not silently shifted or repaired if validation fails.
BANDS = {
    "contract": (0, 70), "open": (70, 180), "high_low": (180, 280),
    "settlement": (280, 310), "price_change": (310, 365),
    "volume_globex": (365, 455), "volume_pnt_pit": (455, 520),
    "open_interest": (520, 565), "oi_change": (565, 620),
}

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def words_by_line(page):
    words = page.extract_words(x_tolerance=1, y_tolerance=2, keep_blank_chars=False)
    lines = []
    for w in sorted(words, key=lambda z: (z["top"], z["x0"])):
        # Avoid round(top): cluster by baseline/vertical proximity.
        target = next((g for g in reversed(lines) if abs(w["top"] - g["top"]) < 2.5), None)
        if target is None:
            lines.append({"top": w["top"], "words": [w]})
        else:
            target["words"].append(w)
            target["top"] = sum(x["top"] for x in target["words"]) / len(target["words"])
    for g in lines:
        g["words"].sort(key=lambda z: z["x0"])
    return lines

def text_of(ws):
    return " ".join(str(w.get("text", "")).strip() for w in sorted(ws, key=lambda z: z["x0"])).strip()

def cell_words(ws, key):
    lo, hi = BANDS[key]
    return [w for w in ws if lo <= (w["x0"] + w["x1"]) / 2 < hi]

def raw_cell(ws, key):
    selected = cell_words(ws, key)
    return "".join(str(w["text"]).strip() for w in selected).strip(), selected

def parse_decimal(raw: str):
    s = raw.replace(",", "").strip()
    if not s or s.upper() in NULL_TOKENS:
        return None
    if not NUMBER_RE.fullmatch(s):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None

def parse_signed(raw: str):
    s = re.sub(r"\s+", "", raw).upper()
    if s in {"", *NULL_TOKENS, "NEW"}:
        return None
    if s == "UNCH":
        return Decimal("0")
    # Sign may be a separate text token. Preserve it as part of the cell grammar.
    s = s.replace("+", "") if s.startswith("+") else s
    return parse_decimal(s)

def state(raw: str, parsed):
    s = raw.strip().upper()
    if not s:
        return {"state": "EMPTY", "raw": raw, "value": None}
    if s in NULL_TOKENS:
        return {"state": "SOURCE_NULL", "raw": raw, "value": None}
    if parsed is None:
        return {"state": "PARSER_ERROR", "raw": raw, "value": None}
    return {"state": "VALUE", "raw": raw, "value": format(parsed, "f")}

def parse_hilo(raw: str):
    # H/L can be plain slash-delimited, B/A decorated, one-sided, or null.
    s = re.sub(r"\s+", "", raw).upper()
    if not s:
        return None, None
    if s in NULL_TOKENS:
        return None, None
    parts = s.split("/")
    if len(parts) == 1:
        # Single source quote such as 4378.00B: do not invent the other side.
        v = parse_decimal(re.sub(r"[ABPRN]$", "", parts[0]))
        return v, None
    if len(parts) != 2:
        return None, None
    vals=[]
    for p in parts:
        if p in NULL_TOKENS:
            vals.append(None)
        else:
            vals.append(parse_decimal(re.sub(r"[ABPRN]$", "", p)))
    return vals[0], vals[1]

def contract_from(ws):
    for w in cell_words(ws, "contract"):
        s=str(w["text"]).upper()
        if CONTRACT_RE.fullmatch(s): return s
    return None

def meta_from(pdf_text: str):
    # Status is dataset-specific and must be unambiguous.
    statuses = set(re.findall(r"\b(FINAL|PRELIMINARY)\b", pdf_text[:12000], re.I))
    statuses = {s.upper() for s in statuses}
    if len(statuses) != 1:
        raise ValueError(f"PG62 status missing or ambiguous: {sorted(statuses)}")
    m = re.search(r"PG62\s+BULLETIN\s*#\s*(\d+)\s*@?\s+METAL FUTURES PRODUCTS\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})", pdf_text, re.I)
    if not m:
        raise ValueError("Could not identify PG62 bulletin number/date")
    d = datetime.strptime(f"{m.group(2)} {m.group(3)} {m.group(4)}", "%b %d %Y").date().isoformat()
    return {"number": int(m.group(1)), "trade_date": d, "status": next(iter(statuses))}

def parse_pdf(path: Path):
    digest = sha256(path)
    with pdfplumber.open(path) as pdf:
        all_text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        meta = meta_from(all_text)
        rows, totals, target_seen, target_done = [], [], False, False
        pages_with_rows = set()
        geometry = []
        for pno, page in enumerate(pdf.pages, 1):
            for group in words_by_line(page):
                ws = group["words"]
                line = text_of(ws)
                upper = line.upper()
                if GC_HEADER_RE.search(upper):
                    target_seen = True
                    continue
                if not target_seen or target_done:
                    continue
                if re.match(r"^TOTAL\s+GC\s+FUT\b", upper):
                    # Total columns: Globex volume, PNT/Pit volume, OI, OI change.
                    vals = []
                    for k in ("volume_globex", "volume_pnt_pit", "open_interest", "oi_change"):
                        raw, _ = raw_cell(ws, k)
                        parsed = parse_signed(raw) if k == "oi_change" else parse_decimal(raw)
                        vals.append({"field": k, **state(raw, parsed)})
                    totals.append({"page": pno, "raw_line": line, "cells": vals})
                    target_done = True
                    continue
                contract = contract_from(ws)
                if not contract:
                    # Page headers/footers and other products are not rows.
                    continue
                def get(k, parser=parse_decimal):
                    raw, selected = raw_cell(ws, k)
                    return state(raw, parser(raw)), selected
                o, ow = get("open")
                hraw, _ = raw_cell(ws, "high_low")
                high, low = parse_hilo(hraw)
                st, _ = get("settlement")
                ch, _ = get("price_change", parse_signed)
                vg, _ = get("volume_globex")
                vp, _ = get("volume_pnt_pit")
                oi, _ = get("open_interest")
                oc, _ = get("oi_change", parse_signed)
                # Require a row to contain source evidence in multiple independent columns.
                if sum(x["state"] in {"VALUE", "SOURCE_NULL"} for x in (o, st, ch, vg, vp, oi, oc)) < 5:
                    raise ValueError(f"Unrecognized GC contract row {contract} on page {pno}: {line}")
                rec = {
                    "contract": contract,
                    "open": o,
                    "high": state(hraw, high),
                    "low": state(hraw, low),
                    "settlement": st,
                    "price_change": ch,
                    "volume_globex": vg,
                    "volume_pnt_pit": vp,
                    "open_interest": oi,
                    "oi_change": oc,
                    "source": {"page": pno, "raw_line": line, "top": round(group["top"], 3)},
                }
                # A malformed numeric token is never silently converted to null.
                for field in ("open", "settlement", "price_change", "volume_globex", "volume_pnt_pit", "open_interest", "oi_change"):
                    if rec[field]["state"] == "PARSER_ERROR":
                        raise ValueError(f"PARSER_ERROR {contract}.{field} page {pno}: {rec[field]['raw']!r}; line={line}")
                for field in ("volume_globex", "volume_pnt_pit", "open_interest"):
                    if rec[field]["state"] == "VALUE" and Decimal(rec[field]["value"]) < 0:
                        raise ValueError(f"Negative {field} for {contract}: {rec[field]['value']}")
                if high is not None and low is not None and high < low:
                    raise ValueError(f"high<low for {contract}: {hraw!r}")
                rows.append(rec); pages_with_rows.add(pno)
                geometry.append({"page": pno, "contract_x": round(min(w["x0"] for w in cell_words(ws,"contract")),2), "row_top": round(group["top"],3)})
        if not target_seen: raise ValueError("GC FUT COMEX GOLD FUTURES section not found")
        if not target_done or len(totals) != 1: raise ValueError("Missing/ambiguous TOTAL GC FUT; refusing MASTER")
        if len(rows) < 20: raise ValueError(f"Implausibly incomplete GC table: {len(rows)} rows; refusing MASTER")
        contracts = [r["contract"] for r in rows]
        if len(contracts) != len(set(contracts)): raise ValueError("Duplicate contract month in GC table")
        # Independently reconcile parsed values against source TOTAL row.
        total_map = {x["field"]: x for x in totals[0]["cells"]}
        checks = []
        for field in ("volume_globex", "volume_pnt_pit", "open_interest", "oi_change"):
            parsed_values = [r[field] for r in rows]
            known = [x for x in parsed_values if x["state"] == "VALUE"]
            # Keep SOURCE_NULL distinct in MASTER. For the reconciliation only,
            # sum explicitly printed numeric cells and report how many source-null
            # cells were excluded; never rewrite those cells as zero.
            if not known:
                continue
            agg = sum((Decimal(x["value"]) for x in known), Decimal(0))
            src = total_map[field]
            if src["state"] != "VALUE": raise ValueError(f"TOTAL {field} is not numeric; cannot reconcile")
            expected = Decimal(src["value"])
            checks.append({"field": field, "parsed_sum_of_numeric_cells": format(agg,"f"), "source_total": format(expected,"f"), "numeric_cells": len(known), "source_null_cells_excluded": sum(x["state"] == "SOURCE_NULL" for x in parsed_values), "empty_cells_excluded": sum(x["state"] == "EMPTY" for x in parsed_values), "pass": agg == expected})
            if agg != expected: raise ValueError(f"TOTAL reconciliation failed for {field}: parsed={agg}, source={expected}")
        if len(checks) < 3: raise ValueError("Insufficient independent TOTAL reconciliation checks")
        return {
            "schema_version": SCHEMA_VERSION,
            "parser_version": PARSER_VERSION,
            "dataset": "PG62_GC_FUTURES",
            "trade_date": meta["trade_date"],
            "bulletin": {"number": meta["number"], "status": meta["status"]},
            "semantics": "Source-observed facts only. Derived total volume, active contract, indicators and analysis are excluded.",
            "source": {"file": path.name, "sha256": digest, "ingested_at": datetime.now(timezone.utc).isoformat()},
            "validation": {"contract_rows": len(rows), "pages_with_rows": sorted(pages_with_rows), "total_reconciliation": checks, "status": "PASS"},
            "contracts": rows,
            "source_total": totals[0],
        }

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("pdf",type=Path); ap.add_argument("--output-dir",type=Path,default=Path("data/master/pg62")); args=ap.parse_args()
    try:
        data=parse_pdf(args.pdf)
    except Exception as e:
        print(f"FAIL-CLOSED: {e}",file=sys.stderr); raise SystemExit(2)
    out=args.output_dir/data["trade_date"]/f"{data['trade_date']}_{data['bulletin']['status']}.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    # Immutable output: do not overwrite a different source/version artifact.
    if out.exists():
        old=json.loads(out.read_text(encoding="utf-8"))
        if old.get("source",{}).get("sha256")==data["source"]["sha256"] and old.get("parser_version")==PARSER_VERSION:
            print(f"SKIP unchanged: {out}"); return
        raise SystemExit(f"Refusing to overwrite existing MASTER: {out}; use versioned path/archive")
    tmp=out.with_suffix(out.suffix+".tmp"); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(out)
    print(f"PG62 MASTER PASS: {out} rows={len(data['contracts'])} totals={len(data['validation']['total_reconciliation'])}")
if __name__=="__main__": main()
