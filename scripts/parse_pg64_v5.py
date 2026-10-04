#!/usr/bin/env python3
"""PG64 v5 diagnostic-stage parser.

This command reads the PDF and reconstructs candidate main-chain structure, but
intentionally does NOT emit a production MASTER yet. PG64 requires character/run
level cell reconstruction and mandatory TOTAL reconciliation before promotion.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
import pdfplumber

VERSION = "pg64-gold-v5.0.0-diagnostic"
MONTH = r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2}"
PRODUCT = re.compile(r"^(OG[1-4]?|OMG|FMG|GMW|GWT|GWW|GWR)\b", re.I)
STRIKE = re.compile(r"^\d{2,5}(?:\.\d+)?$")

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def norm(s): return re.sub(r"\s+", " ", s or "").strip()
def lines(page):
    words=page.extract_words(x_tolerance=1,y_tolerance=2,keep_blank_chars=False)
    out=[]
    for w in sorted(words,key=lambda q:(q["top"],q["x0"])):
        g=next((z for z in reversed(out) if abs(w["top"]-z["top"])<2.5),None)
        if g is None: out.append({"top":w["top"],"words":[w]})
        else: g["words"].append(w); g["top"]=sum(x["top"] for x in g["words"])/len(g["words"])
    for g in out: g["words"].sort(key=lambda q:q["x0"])
    return out

def audit(path):
    digest=sha(path); pages=[]; main_pages=[]; candidate_rows=[]; totals=[]; unresolved=[]
    with pdfplumber.open(path) as pdf:
        alltext="\n".join(p.extract_text() or "" for p in pdf.pages)
        m=re.search(r"PG64\s+BULLETIN\s*#\s*(\d+)\s*@?\s+METALS? OPTION PRODUCTS\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})",alltext,re.I)
        statuses={x.upper() for x in re.findall(r"\b(FINAL|PRELIMINARY)\b", "\n".join((p.extract_text() or "") for p in pdf.pages[:3]), re.I)}
        if not m: raise ValueError("PG64 bulletin/date metadata not found")
        trade_date=datetime.strptime(f"{m.group(2)} {m.group(3)} {m.group(4)}","%b %d %Y").date().isoformat()
        for pno,page in enumerate(pdf.pages,1):
            page_text=page.extract_text() or ""; u=page_text.upper()
            has_table_header=("VOLUME" in u and "INTEREST" in u and "DELTA" in u and "HIGH/LOW" in u and "SETT.PRICE" in u)
            page_info={"page":pno,"main_chain_header":has_table_header,"gold_mentions":len(re.findall(r"\bGOLD\b",u)),"eoo_blocks_section":"OPTIONS EOO" in u and "BLOCKS" in u}
            if has_table_header:
                main_pages.append(pno)
                cur_product=None; cur_type=None; cur_expiry=None
                for g in lines(page):
                    ws=g["words"]; text=norm(" ".join(w["text"] for w in ws)); up=text.upper()
                    if "OPEN OUTCRY VOLUME" in up or "OPEN INTEREST" == up: continue
                    # Main-chain product headers only; exact supported product labels.
                    pm=PRODUCT.match(up)
                    if pm and "GOLD" in up and "OPTION" in up:
                        cur_product=pm.group(1).upper()
                        cur_type="CALL" if re.search(r"\bCALL\b",up) else ("PUT" if re.search(r"\bPUT\b",up) else "UNSPECIFIED")
                        cur_expiry=None
                        continue
                    em=re.fullmatch(MONTH,up)
                    if em:
                        cur_expiry=up
                        continue
                    if up.startswith("TOTAL"):
                        totals.append({"page":pno,"product":cur_product,"option_type":cur_type,"contract_month":cur_expiry,"raw_line":text})
                        continue
                    if ws and STRIKE.fullmatch(ws[0]["text"]) and float(ws[0]["text"].replace(",",""))>=1000:
                        row={"page":pno,"top":round(g["top"],3),"product":cur_product,"option_type":cur_type,"contract_month":cur_expiry,"strike_raw":ws[0]["text"],"raw_line":text,"token_count":len(ws)}
                        candidate_rows.append(row)
                        if not cur_product or not cur_expiry or not cur_type:
                            unresolved.append({"page":pno,"top":round(g["top"],3),"reason":"unresolved product/type/expiry state","raw_line":text})
            pages.append(page_info)
    return {
        "diagnostic_schema":"pg64.audit.v5",
        "parser_version":VERSION,
        "dataset":"PG64_GOLD_OPTIONS",
        "trade_date":trade_date,
        "bulletin":{"number":int(m.group(1)),"status_candidates":sorted(statuses)},
        "source":{"file":path.name,"sha256":digest,"ingested_at":datetime.now(timezone.utc).isoformat()},
        "page_count":len(pages),"pages_with_main_chain_header":main_pages,
        "candidate_strike_rows":len(candidate_rows),"candidate_total_rows":len(totals),
        "unresolved_state_rows":len(unresolved),
        "known_unhandled_risks":[
            "Character/content-stream reconstruction for overlapping H/L cells is not implemented.",
            "No production cell extraction or mandatory expiry TOTAL reconciliation is performed.",
            "Rows without explicit CALL/PUT are retained as UNSPECIFIED; delta is never used to infer type.",
            "Candidate counts are diagnostic only and must not be treated as complete parsed data."
        ],
        "production_master_status":"BLOCKED_DIAGNOSTIC_ONLY",
        "pages":pages,
        "totals_candidates":totals,
        "unresolved_examples":unresolved[:100],
        "candidate_examples":candidate_rows[:30]
    }

def main():
    ap=argparse.ArgumentParser();ap.add_argument("pdf",type=Path);ap.add_argument("--audit-dir",type=Path,default=Path("data/audit/pg64"));a=ap.parse_args()
    try: d=audit(a.pdf)
    except Exception as e: print(f"AUDIT FAILED: {e}",file=sys.stderr);raise SystemExit(2)
    out=a.audit_dir/d["trade_date"]/f"{d['trade_date']}_{d['bulletin']['status_candidates'][0] if len(d['bulletin']['status_candidates'])==1 else 'AMBIGUOUS'}_AUDIT.json"
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"PG64 AUDIT ONLY: {out} pages={len(d['pages_with_main_chain_header'])} strike_candidates={d['candidate_strike_rows']} totals={d['candidate_total_rows']} unresolved={d['unresolved_state_rows']}")
    print("No production MASTER written (intentional fail-closed gate).")
if __name__=="__main__": main()
