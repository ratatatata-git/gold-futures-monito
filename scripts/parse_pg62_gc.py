import hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
import pdfplumber

ROOT=Path(__file__).resolve().parents[1]
PDF_DIR=ROOT/'data'/'cme-pg62'
OUT_FILE=ROOT/'data'/'cme-gc-history.json'
PARSER_VERSION='pg62-gold-v2.1.0'
MONTHS={m:i for i,m in enumerate(('JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'),1)}
CONTRACT_RE=re.compile(r'^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})$',re.I)
MAX_VOLUME=2_000_000; MAX_OI=10_000_000; MAX_PRICE=20_000.0

def clean(x): return str(x or '').strip().replace(',','')
def missing(x): return clean(x).upper() in {'','-','--','---','----'}
def num(x):
    s=clean(x)
    if missing(s): return None
    if s.upper()=='UNCH': return 0.0
    try: return float(s.replace('B','').replace('A',''))
    except ValueError: return None
def integer(x):
    v=num(x); return None if v is None else int(round(v))
def signed(words):
    s=''.join(clean(w.get('text')) for w in words).replace(' ','')
    if not s or s in {'-','--','---','----'}: return None
    if s.upper()=='UNCH': return 0.0
    try: return float(s.replace('B','').replace('A',''))
    except ValueError: return None

def prices(s):
    s=clean(s).replace('B','').replace('A','')
    out=[]
    for p in s.replace('/',' ').split():
        if re.fullmatch(r'\d+(?:\.\d+)?',p): out.append(float(p)); continue
        m=re.fullmatch(r'(\d{3,5}\.\d{1,4})(\d{3,5}\.\d{1,4})',p)
        if m: out += [float(m.group(1)),float(m.group(2))]
    return out

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def bulletin_date(pdf):
    mon='Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec'
    full='January|February|March|April|May|June|July|August|September|October|November|December'
    wd='Mon|Tue|Wed|Thu|Fri|Sat|Sun'
    pats=[rf'\b(?:{wd})\.?[,]?\s+({mon}|{full})\s+(\d{{1,2}}),\s*(\d{{2,4}})\b',rf'\b({mon}|{full})\s+(\d{{1,2}}),\s*(\d{{2,4}})\b',r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b']
    for p in pdf.pages:
        t=p.extract_text() or ''
        for pat in pats:
            m=re.search(pat,t,re.I)
            if not m: continue
            a,b,c=m.groups()
            if a[:3].upper() in MONTHS: mo,day,yr=MONTHS[a[:3].upper()],int(b),int(c)
            else: mo,day,yr=int(a),int(b),int(c)
            if yr<100: yr+=2000
            return f'{yr:04d}-{mo:02d}-{day:02d}'
    return None

def status(pdf):
    for p in pdf.pages[:4]:
        t=(p.extract_text() or '').upper()
        if re.search(r'\bFINAL\b',t): return 'FINAL'
        if re.search(r'\bPRELIMINARY\b',t): return 'PRELIMINARY'
    return 'UNKNOWN'

def bulletin_no(pdf):
    for p in pdf.pages[:4]:
        m=re.search(r'PG62\s+BULLETIN\s*#\s*(\d+)',p.extract_text() or '',re.I)
        if m: return int(m.group(1))
    return None

def groups(words,tol=1.4):
    gs=[]
    for w in sorted(words,key=lambda x:(x['top'],x['x0'])):
        if not gs or abs(w['top']-gs[-1]['top'])>tol: gs.append({'top':w['top'],'words':[w]})
        else:
            gs[-1]['words'].append(w); gs[-1]['top']=sum(x['top'] for x in gs[-1]['words'])/len(gs[-1]['words'])
    for g in gs:g['words'].sort(key=lambda x:x['x0'])
    return gs

def text(words): return ' '.join(clean(w.get('text')) for w in words)
def gc_header(words): return 'GC FUT COMEX GOLD FUTURES' in text(words).upper()
def total(words): return text(words).upper().startswith('TOTAL GC FUT')
def gc_page(page): return 'GC FUT COMEX GOLD FUTURES' in (page.extract_text() or '').upper()

def anchors(lines,i):
    search=lines[max(0,i-3):min(len(lines),i+4)]; out={}
    pats={'open':r'^OPEN$','high_low':r'HIGH/?LOW','settlement':r'SETT\.?PRICE|^SETT$','change':r'PT\.?CHGE|PRICE.*CHANGE','open_interest':r'OPEN.*INTEREST','delta':r'^DELTA$','globex_open':r'GLOBEX.*OPEN','pnt_volume':r'^PNT$|PNT.*VOLUME','globex_volume':r'GLOBEX.*VOLUME'}
    for k,p in pats.items():
        c=[w for ln in search for w in ln['words'] if re.search(p,clean(w.get('text')),re.I)]
        if c: out[k]=min(c,key=lambda w:w['x0'])['x0']
    return out

def bands(a,width):
    order=['open','high_low','settlement','change','open_interest','delta','globex_open','pnt_volume','globex_volume']
    u=sorted([(k,a[k]) for k in order if k in a],key=lambda z:z[1]); b={}
    for i,(k,x) in enumerate(u): b[k]=(0 if i==0 else (u[i-1][1]+x)/2,width if i==len(u)-1 else (x+u[i+1][1])/2)
    first=min([x for _,x in u],default=70); b['contract']=(0,max(70,first-5))
    return b

def fallback(width):
    return {'contract':(0,70),'open':(90,180),'high_low':(180,280),'settlement':(270,310),'change':(310,360),'open_interest':(520,560),'delta':(560,610),'globex_open':(610,650),'pnt_volume':(650,710),'globex_volume':(710,min(width,780))}

def inband(words,band): return [w for w in words if band[0]<=w['x0']<band[1]]
def first(ws): return clean(ws[0]['text']) if ws else ''
def contract(words,b):
    for w in inband(words,b['contract']):
        m=CONTRACT_RE.fullmatch(clean(w['text']).upper())
        if m:return f'{m.group(1)}{int(m.group(2)):02d}'
    return None

def validate(r):
    bad=[]
    for k in ('volume','volume_globex','volume_pnt_pit','open_interest'):
        if r[k] is not None and r[k]<0: bad.append(f'negative {k}={r[k]}')
    for k in ('open','high','low','settlement'):
        if r[k] is not None and abs(r[k])>MAX_PRICE: bad.append(f'implausible {k}={r[k]}')
    if r['high'] is not None and r['low'] is not None and r['high']<r['low']: bad.append('high<low')
    if r['volume_globex'] is not None and r['volume_globex']>MAX_VOLUME: bad.append('implausible globex volume')
    if r['volume_pnt_pit'] is not None and r['volume_pnt_pit']>MAX_VOLUME: bad.append('implausible pnt volume')
    if r['open_interest'] is not None and r['open_interest']>MAX_OI: bad.append('implausible open interest')
    if all(r[k] is not None for k in ('volume','volume_globex','volume_pnt_pit')) and r['volume']!=r['volume_globex']+r['volume_pnt_pit']: bad.append('volume != globex + pnt/pit')
    if bad: raise ValueError(f"PG62 validation failed for {r['date']} {r['contract']}: {'; '.join(bad)}")


def validate_extraction(rows, date, pdf_name):
    """
    Production guardrail:
    - Never treat a PDF as successfully parsed when only a few GC rows were found.
    - Require usable volume extraction because active-contract selection depends on it.
    - Reject impossible/partial volume states instead of silently producing nulls.
    """
    if not rows:
        raise RuntimeError(
            f"{pdf_name}: {date}: GC extraction returned 0 rows. "
            "Header/section discovery failed."
        )

    # A normal GC futures page contains substantially more than three contracts.
    # Keep this deliberately conservative so the parser fails rather than fabricates
    # an apparently valid MASTER from a partial extraction.
    if len(rows) < 5:
        raise RuntimeError(
            f"{pdf_name}: {date}: only {len(rows)} GC rows extracted. "
            "Refusing to write MASTER; likely column/header/row discovery failure."
        )

    volume_rows = [
        r for r in rows
        if r.get("volume") is not None
        or r.get("volume_globex") is not None
        or r.get("volume_pnt_pit") is not None
    ]
    if not volume_rows:
        raise RuntimeError(
            f"{pdf_name}: {date}: no usable volume values extracted. "
            "Refusing active-contract selection."
        )

    for r in rows:
        vg = r.get("volume_globex")
        vp = r.get("volume_pnt_pit")
        vol = r.get("volume")

        for name, value in (
            ("volume_globex", vg),
            ("volume_pnt_pit", vp),
            ("volume", vol),
        ):
            if value is not None and value < 0:
                raise RuntimeError(
                    f"{pdf_name}: {date}: negative {name}={value} "
                    f"for contract={r.get('contract')}"
                )

        if vg is not None and vp is not None and vol is not None:
            if abs(vol - (vg + vp)) > 1:
                raise RuntimeError(
                    f"{pdf_name}: {date}: volume mismatch for "
                    f"{r.get('contract')}: volume={vol}, "
                    f"globex={vg}, pnt={vp}"
                )

    return True


def validate_bands(b):
    """Reject missing/reversed/overlapping critical x-bands."""
    if not b:
        raise RuntimeError("GC header bands are missing; refusing row extraction.")

    required = (
        "contract", "open", "high_low", "settlement", "change",
        "open_interest", "delta", "globex_open", "pnt_volume",
        "globex_volume",
    )
    for key in required:
        band = b.get(key)
        if not band or len(band) != 2:
            raise RuntimeError(f"Invalid GC header band: {key}={band!r}")
        x0, x1 = band
        if x0 >= x1:
            raise RuntimeError(
                f"Invalid GC header band: {key}={band!r}; x0 must be < x1."
            )
    return True

def parse_row(words,date,source,st,bno,b):
    c=contract(words,b)
    if not c:return None
    def t(k):return ' '.join(w['text'] for w in inband(words,b[k]))
    hp=prices(t('high_low')); ow=num(first(inband(words,b['open']))); hi=hp[0] if hp else None; lo=hp[1] if len(hp)>1 else None
    sett=num(first(inband(words,b['settlement']))); ch=signed(inband(words,b['change']))
    oi=integer(first(inband(words,b['open_interest']))); d=signed(inband(words,b['delta'])); d=None if d is None else int(round(d))
    pnt=integer(first(inband(words,b['pnt_volume']))); glob=integer(first(inband(words,b['globex_volume'])))
    vol=None if pnt is None and glob is None else (pnt or 0)+(glob or 0)
    r={'date':date,'contract':c,'open':ow,'high':hi,'low':lo,'close':sett,'settlement':sett,'price_change':ch,'volume':vol,'volume_globex':glob,'volume_pnt_pit':pnt,'open_interest':oi,'oi_change':d,'is_active':False,'source_file':source,'source_status':st,'bulletin_number':bno}
    validate(r);return r

def extract(path):
    with pdfplumber.open(path) as pdf:
        date=bulletin_date(pdf)
        if not date: raise RuntimeError(f'Could not find bulletin date: {path.name}')
        st=status(pdf); bno=bulletin_no(pdf); rows=[]; ingc=False; layout=[]
        for pn,page in enumerate(pdf.pages,1):
            if not ingc and not gc_page(page): continue
            lines=groups(page.extract_words(x_tolerance=2,y_tolerance=3,keep_blank_chars=False))
            b=None
            for i,line in enumerate(lines):
                ws=line['words']
                if gc_header(ws):
                    ingc=True; a=anchors(lines,i); b=bands(a,float(page.width)); fb=fallback(float(page.width)); [b.setdefault(k,v) for k,v in fb.items()]
                    layout.append({'page':pn,'header_anchors':a,'bands':b,'anchor_mode':'dynamic_header'}); continue
                if not ingc: continue
                if total(ws): break
                # A GC page can contain rows before the wrapped header has been
                # recognized by the line parser. Never call parse_row without bands.
                if b is None:
                    continue
                r=parse_row(ws,date,path.name,st,bno,b)
                if r:r['source_page']=pn; rows.append(r)
            if ingc and any(x['source_page']==pn for x in rows) and total(lines[-1]['words']): break
        if not rows: raise RuntimeError(f'No GC futures rows found in {path.name}')
        # Exact duplicate lines only.
        d={(r['date'],r['contract'],r['source_file'],r['source_page']):r for r in rows}; rows=list(d.values())
        active=max(rows,key=lambda r:(r['volume'] if r['volume'] is not None else -1,r['open_interest'] if r['open_interest'] is not None else -1))['contract']
        for r in rows:r['is_active']=r['contract']==active
        return date,st,bno,rows,layout

def load():
    if not OUT_FILE.exists(): return {'observations':[],'provenance':[]}
    try:
        with OUT_FILE.open(encoding='utf-8') as f:return json.load(f)
    except Exception:return {'observations':[],'provenance':[]}

def obskey(r):return (r.get('date'),r.get('contract'),r.get('source_file'),r.get('source_status'))
def rebuild(obs):
    rank={'FINAL':2,'PRELIMINARY':1,'UNKNOWN':0}; latest={}
    for r in obs:
        k=(r.get('date'),r.get('contract')); old=latest.get(k)
        if old is None or rank.get(r.get('source_status'),0)>rank.get(old.get('source_status'),0):latest[k]=r
    candles=sorted(latest.values(),key=lambda r:(r.get('date') or '',r.get('contract') or ''))
    by={}
    for r in candles:r['is_active']=False;by.setdefault(r['date'],[]).append(r)
    for rows in by.values():
        a=max(rows,key=lambda r:(r['volume'] if r['volume'] is not None else -1,r['open_interest'] if r['open_interest'] is not None else -1))['contract']
        for r in rows:r['is_active']=r['contract']==a
    contracts={}
    for r in candles:contracts.setdefault(r['contract'],[]).append(r)
    dates=sorted(by); active=next((r for r in candles if dates and r['date']==dates[-1] and r['is_active']),None)
    return candles,contracts,dates,active

def main():
    pdfs=sorted(PDF_DIR.glob('*.pdf'))
    if not pdfs:raise RuntimeError(f'No PDF files found in {PDF_DIR}')
    h=load(); om={obskey(r):r for r in h.get('observations',[])}; pm={}
    for p in h.get('provenance',[]):pm[(p.get('source_file'),p.get('source_sha256'),p.get('trade_date'))]=p
    for path in pdfs:
        print(f'Parsing {path.name}'); date,st,bno,rows,layout=extract(path); digest=sha(path)
        for k in list(om):
            if om[k].get('source_file')==path.name and om[k].get('source_sha256')==digest:del om[k]
        for r in rows:r['source_sha256']=digest;r['parser_version']=PARSER_VERSION;om[obskey(r)]=r
        pm[(path.name,digest,date)]={'source_file':path.name,'source_sha256':digest,'trade_date':date,'bulletin_number':bno,'source_status':st,'parser_version':PARSER_VERSION,'ingested_at':datetime.now(timezone.utc).isoformat(),'active_selection_method':'highest_volume_eod_then_open_interest','layout_discovery':layout}
        print(f'  {date} {st} bulletin={bno} rows={len(rows)}')
    obs=sorted(om.values(),key=lambda r:(r.get('date') or '',r.get('contract') or '',r.get('source_status') or '',r.get('source_file') or ''))
    candles,contracts,dates,active=rebuild(obs)
    out={'schema_version':'pg62-gc-master-v2.1','parser_version':PARSER_VERSION,'updated_at':datetime.now(timezone.utc).isoformat(),'latest_date':dates[-1] if dates else None,'latest_active':active,'dates':dates,'contracts':contracts,'candles':candles,'observations':obs,'provenance':sorted(pm.values(),key=lambda p:(p.get('trade_date') or '',p.get('source_file') or '')),'notes':{'master_semantics':'Observed source facts only','candles_semantics':'Latest/default observation view; FINAL preferred over PRELIMINARY','active_semantics':'EOD representative only; highest volume then open interest','missing_value':'---- is stored as null, never as zero','analysis_boundary':'IV/Gamma/GEX/regime/dealer positioning are not calculated here'}}
    OUT_FILE.parent.mkdir(parents=True,exist_ok=True)
    with OUT_FILE.open('w',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
    print(f'Saved {len(obs)} observations / {len(candles)} default rows / {len(dates)} dates')
    if active:print(f"Latest active: {active['contract']} {active['settlement']}")
    print(f'Output: {OUT_FILE}')

if __name__=='__main__':main()


# v2.2.0 production contract:
# This parser intentionally fails rather than writing a partially extracted
# PG62 MASTER. A successful run must have:
#   1) recognized GC header bands,
#   2) >=5 GC contract rows per bulletin,
#   3) usable volume extraction,
#   4) non-negative volumes,
#   5) volume == Globex + PNT/Pit when all three are present.
