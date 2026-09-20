#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pdfplumber

MONTHS = r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
CONTRACT_RE = re.compile(rf"^{MONTHS}\d{{2}}$")
DATE_RE = re.compile(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})\b")

def norm_lines(pdf_path: Path) -> list[str]:
    out=[]
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text=page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            for raw in text.splitlines():
                line=re.sub(r"\s+", " ", raw.strip())
                if line: out.append(line)
    return out

def parse_bulletin_date(lines):
    for line in lines[:100]:
        m=DATE_RE.search(line)
        if m:
            mon, day, year=m.groups()
            return datetime.strptime(f"{day} {mon} {year}", "%d %b %Y").date().isoformat()
    raise ValueError("Bulletin date not found.")

def num(s):
    s=s.replace(",","").strip()
    if s in {"----","UNCH","NEW"}: return None
    s=re.sub(r"[^0-9.\-+]","",s)
    return float(s) if s and s not in {"+","-"} else None

def integer(s):
    s=s.replace(",","").strip()
    if s in {"----","UNCH","NEW"}: return None
    s=re.sub(r"[^0-9\-+]","",s)
    return int(s) if s and s not in {"+","-"} else None

def signed(sign, value):
    n=integer(str(value))
    if n is None: return None
    return -abs(n) if sign=="-" else abs(n)

def parse_gc_line(line, trade_date):
    t=line.split()
    if not t or not CONTRACT_RE.match(t[0]) or len(t)<6: return None
    contract=t[0]

    # Find the price-change sign after the price columns.
    si=None
    for i in range(2, min(len(t),10)):
        if t[i] in {"+","-","UNCH"} or re.match(r"^[+-]\d",t[i]):
            si=i; break
    if si is None: return None

    prices=[num(x) for x in t[1:si]]
    if len(prices)>=4:
        op,hi,lo,sett=prices[-4:]
    elif len(prices)==3:
        op,hi,lo,sett=None,prices[0],prices[1],prices[2]
    elif len(prices)==2:
        op,hi,lo,sett=None,None,prices[0],prices[1]
    else:
        op,hi,lo,sett=None,None,None,prices[0]

    if t[si] in {"+","-"}:
        ps=t[si]; pc=num(t[si+1]) if si+1<len(t) else None; cur=si+2
    elif t[si].startswith(("+","-")):
        ps=t[si][0]; pc=num(t[si][1:]); cur=si+1
    else:
        ps="UNCH"; pc=0; cur=si+1

    rem=t[cur:]
    if len(rem)<3: return None

    oi_si=None
    for i in range(len(rem)-1,-1,-1):
        if rem[i] in {"+","-","UNCH"} or re.match(r"^[+-]\d",rem[i]):
            oi_si=i; break
    if oi_si is None or oi_si<1: return None

    ost=rem[oi_si]
    if ost in {"+","-"}:
        osign=ost; ochange=rem[oi_si+1] if oi_si+1<len(rem) else None
    else:
        osign=ost[0]; ochange=ost[1:]
    if ochange is None: return None

    before=rem[:oi_si]
    if len(before)<2: return None

    # Standard PG62: Globex volume, PNT/PIT volume, OI.
    if len(before)>=3:
        globex=integer(before[-3]) or 0
        pnt=integer(before[-2]) or 0
        oi=integer(before[-1])
    else:
        globex=integer(before[0]) or 0
        pnt=0
        oi=integer(before[1])

    if sett is None or oi is None: return None

    return {
        "date": trade_date, "contract": contract,
        "open": op, "high": hi, "low": lo, "settlement": sett,
        "price_change": signed(ps, pc) if pc is not None else None,
        "volume": globex+pnt, "volume_globex": globex,
        "volume_pnt_pit": pnt, "open_interest": oi,
        "oi_change": signed(osign, ochange), "is_active": False
    }

def extract_gc(pdf):
    lines=norm_lines(pdf)
    trade_date=parse_bulletin_date(lines)
    start=None
    for i,line in enumerate(lines):
        if "GC FUT COMEX GOLD FUTURES" in line:
            start=i+1; break
    if start is None:
        raise ValueError("GC FUT COMEX GOLD FUTURES section not found.")

    rows=[]
    for line in lines[start:]:
        if line.startswith("TOTAL GC FUT"): break
        r=parse_gc_line(line, trade_date)
        if r: rows.append(r)
    if not rows: raise ValueError("GC section found, but no rows parsed.")
    max(rows, key=lambda r:r["volume"])["is_active"]=True
    return trade_date, rows

def load_history(path):
    if not path.exists(): return []
    obj=json.loads(path.read_text(encoding="utf-8"))
    return obj.get("contracts",[]) if isinstance(obj,dict) else obj

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path)
    ap.add_argument("--input-dir", type=Path, default=Path("data/cme-pg62"))
    ap.add_argument("--output", type=Path, default=Path("data/cme-gc-history.json"))
    a=ap.parse_args()

    pdfs=[a.pdf] if a.pdf else sorted(a.input_dir.glob("*.pdf"))
    if not pdfs: raise SystemExit(f"No PG62 PDF found in {a.input_dir}")

    existing={(r["date"],r["contract"]):r for r in load_history(a.output)}
    for pdf in pdfs:
        d, rows=extract_gc(pdf)
        for r in rows: existing[(r["date"],r["contract"])]=r
        print(f"Parsed {pdf.name}: {d}, {len(rows)} contracts")

    grouped={}
    for r in existing.values(): grouped.setdefault(r["date"],[]).append(r)
    for rows in grouped.values():
        for r in rows: r["is_active"]=False
        max(rows,key=lambda r:r["volume"])["is_active"]=True

    contracts=sorted(existing.values(), key=lambda r:(r["date"],r["contract"]))
    latest=max(r["date"] for r in contracts)
    active=next((r for r in contracts if r["date"]==latest and r["is_active"]),None)
    candles=[
        {"date":r["date"],"contract":r["contract"],"open":r["open"],
         "high":r["high"],"low":r["low"],"close":r["settlement"],
         "settlement":r["settlement"],"volume":r["volume"],
         "open_interest":r["open_interest"],"oi_change":r["oi_change"],
         "is_active":r["is_active"]}
        for r in contracts if r["open"] is not None and r["high"] is not None and r["low"] is not None
    ]
    out={
        "product":"GC","exchange":"COMEX",
        "source":"CME Daily Bulletin PG62 (manual PDF import)",
        "source_pdf":"data/cme-pg62/*.pdf",
        "retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
        "latest_trade_date":latest,
        "active_contract_method":"highest_volume_on_latest_bulletin",
        "active_contract":active["contract"] if active else None,
        "contracts":contracts,"candles":candles
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Wrote {a.output}: {len(contracts)} contract-day records; active={out['active_contract']}")

if __name__=="__main__":
    main()
