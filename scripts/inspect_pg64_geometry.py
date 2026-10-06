#!/usr/bin/env python3
"""PG64 multi-day geometry/document-structure survey (diagnostic only)."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pdfplumber

VERSION="pg64-geometry-survey-v1.0.0"
MONTH_RE=re.compile(r"^(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2}$",re.I)
GOLD_RE=re.compile(r"\bGOLD\b.*\bOPTIONS?\b|\bOPTIONS?\b.*\bGOLD\b",re.I)
CALL_RE=re.compile(r"\bCALL\b",re.I); PUT_RE=re.compile(r"\bPUT\b",re.I)
TOTAL_RE=re.compile(r"^\s*TOTAL\b",re.I)
STRIKE_RE=re.compile(r"^\d{2,5}(?:\.\d+)?$")
SPECIAL=("NEW","UNCH","----","---")

def sha256(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(s): return re.sub(r"\s+"," ",s or "").strip()

def groups(page):
    ws=page.extract_words(x_tolerance=1,y_tolerance=2,keep_blank_chars=False)
    out=[]
    for w in sorted(ws,key=lambda x:(x["top"],x["x0"])):
        g=next((g for g in reversed(out) if abs(w["top"]-g["top"])<2.5),None)
        if g is None: out.append({"top":float(w["top"]),"words":[w]})
        else: g["words"].append(w); g["top"]=sum(x["top"] for x in g["words"])/len(g["words"])
    for g in out:
        g["words"].sort(key=lambda x:x["x0"])
        g["text"]=norm(" ".join(x["text"] for x in g["words"]))
    return out

def word(w):
    return {k:round(float(w[k]),3) for k in ("x0","x1","top","bottom")} | {"text":w["text"]}

def char(c):
    return {k:round(float(c[k]),3) for k in ("x0","x1","top","bottom")} | {"text":c["text"]}

def metadata(text):
    m=re.search(r"PG64\s+BULLETIN\s*#\s*(\d+)\s*@?\s+METALS?\s+OPTION\s+PRODUCTS\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})",text,re.I)
    if not m: raise ValueError("PG64 bulletin/date metadata not found")
    d=datetime.strptime(f"{m[2]} {m[3]} {m[4]}","%b %d %Y").date().isoformat()
    return int(m[1]),d

def product_header(text):
    u=norm(text).upper()
    if not GOLD_RE.search(u): return None
    return {"source_label":text,"normalized_label":u,
            "option_type":"CALL" if CALL_RE.search(u) else ("PUT" if PUT_RE.search(u) else None)}

def header_like(text):
    u=text.upper()
    return ("VOLUME" in u and "INTEREST" in u and
            ("SETT.PRICE" in u or "SETT PRICE" in u or "HIGH/LOW" in u))

def special(text):
    u=text.upper(); r=[x for x in SPECIAL if x in u]
    if re.search(r"\d+(?:\.\d+)?[ABPRN](?:/|$)",u): r.append("INDICATOR_SUFFIX")
    if "/" in u and re.search(r"[ABPRN]",u): r.append("HL_INDICATOR")
    return sorted(set(r))

def analyze(path, detail_pages, max_detail):
    digest=sha256(path)
    with pdfplumber.open(path) as pdf:
        alltext="\n".join(p.extract_text() or "" for p in pdf.pages)
        bulletin,date=metadata(alltext)
        statuses=sorted(set(x.upper() for x in re.findall(r"\b(FINAL|PRELIMINARY)\b",
                       "\n".join((p.extract_text() or "") for p in pdf.pages[:3]),re.I)))
        pages=[]
        auto_details=0
        for n,page in enumerate(pdf.pages,1):
            gs=groups(page); text=page.extract_text() or ""
            gold_headers=[product_header(g["text"]) for g in gs if product_header(g["text"])]
            headers=[{"top":round(g["top"],3),"text":g["text"],
                      "words":[word(w) for w in g["words"]]} for g in gs if header_like(g["text"])]
            totals=[{"top":round(g["top"],3),"text":g["text"],
                     "words":[word(w) for w in g["words"]]} for g in gs if TOTAL_RE.match(g["text"])]
            rows=[]
            for g in gs:
                if g["words"] and STRIKE_RE.fullmatch(g["words"][0]["text"].replace(",","")):
                    rows.append({"top":round(g["top"],3),"text":g["text"],
                                 "words":[word(w) for w in g["words"]],
                                 "special":special(g["text"])})
            gold=bool(gold_headers) or (bool(re.search(r"\bGOLD\b",text,re.I)) and header_like(text))
            rec={"page":n,"width":round(float(page.width),3),"height":round(float(page.height),3),
                 "gold_candidate":gold,"gold_headers":gold_headers,"header_lines":headers,
                 "total_lines":totals,"candidate_rows":rows,
                 "gold_mentions":len(re.findall(r"\bGOLD\b",text,re.I))}
            if gold and (n in detail_pages or auto_details<max_detail):
                rec["chars"]=[char(c) for c in page.chars]
                auto_details+=1
            pages.append(rec)
        return {"survey_schema":"pg64.geometry.survey.v1","parser_version":VERSION,
                "dataset":"PG64_GOLD_OPTIONS",
                "source":{"file":path.name,"sha256":digest,"page_count":len(pdf.pages),
                          "ingested_at":datetime.now(timezone.utc).isoformat()},
                "bulletin":{"number":bulletin,"trade_date":date,"status_candidates":statuses},
                "survey":{"gold_candidate_pages":[x["page"] for x in pages if x["gold_candidate"]],
                          "gold_header_pages":[x["page"] for x in pages if x["gold_headers"]],
                          "total_pages":[x["page"] for x in pages if x["total_lines"]],
                          "special_pages":[x["page"] for x in pages if any(y["special"] for y in x["candidate_rows"])]},
                "pages":pages}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("pdf_dir",type=Path)
    ap.add_argument("--output-dir",type=Path,default=Path("data/audit/pg64_geometry"))
    ap.add_argument("--detail-pages",default="")
    ap.add_argument("--max-detail-pages",type=int,default=20)
    a=ap.parse_args()
    pdfs=sorted(a.pdf_dir.glob("*.pdf"))
    if not pdfs: print("ERROR: no PG64 PDFs found",file=sys.stderr); return 2
    detail={int(x) for x in a.detail_pages.split(",") if x.strip()}
    a.output_dir.mkdir(parents=True,exist_ok=True)
    reports=[]; failures=[]
    for pdf in pdfs:
        try:
            r=analyze(pdf,detail,a.max_detail_pages); reports.append(r)
            out=a.output_dir/f"{r['bulletin']['trade_date']}_SURVEY.json"
            out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding="utf-8")
            print(f"{pdf.name}: date={r['bulletin']['trade_date']} pages={r['source']['page_count']} "
                  f"gold={len(r['survey']['gold_candidate_pages'])} headers={len(r['survey']['gold_header_pages'])} "
                  f"totals={len(r['survey']['total_pages'])}")
        except Exception as e:
            failures.append({"file":pdf.name,"error":f"{type(e).__name__}: {e}"}); print(f"FAILED {pdf.name}: {e}",file=sys.stderr)
    combined={"comparison_schema":"pg64.geometry.comparison.v1","parser_version":VERSION,
              "documents":[{"file":r["source"]["file"],"trade_date":r["bulletin"]["trade_date"],
                           "sha256":r["source"]["sha256"],"page_count":r["source"]["page_count"],
                           "gold_pages":r["survey"]["gold_candidate_pages"],
                           "gold_header_pages":r["survey"]["gold_header_pages"],
                           "total_pages":r["survey"]["total_pages"],
                           "special_pages":r["survey"]["special_pages"]} for r in reports],
              "failures":failures}
    out=a.output_dir/"COMBINED_SURVEY.json"
    out.write_text(json.dumps(combined,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"COMBINED: {out}; PDFs={len(reports)} failures={len(failures)}")
    return 1 if failures else 0

if __name__=="__main__": raise SystemExit(main())
