#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARSER = ROOT / 'parse_pg64_v1.py'
FIX = ROOT / 'pg64_fixtures'
OUT = ROOT / 'pg64_tests' / 'out'
OUT.mkdir(parents=True, exist_ok=True)

EXPECTED = {
    '21': {
        'bulletin_number': 181,
        'status': 'PRELIMINARY',
        'codes': {'OG','OG1','OG2','OG3','OG4','OMG','G1R','G1W','G2M','G2T','G3M','G3R','G4M','G4T','G4W','G5W','4WG'},
        'unresolved_family': set(),
    },
    '23': {
        'bulletin_number': 183,
        'status': 'FINAL',
        'codes': {'OG','OG1','OG2','OG3','OG4','OMG','G1M','G2R','G3R','G4M','G4W','G5T','G5W','4FG','4WG'},
        'unresolved_family': {('MMG', None)},
    },
    '25': {
        'bulletin_number': 185,
        'status': 'PRELIMINARY',
        'codes': {'OG','OG1','OG2','OG3','OG4','OMG','G1R','G1W','G2R','G3R','G4M','G5T','G5W','4FG'},
        'unresolved_family': {('MMG', None)},
    },
}

FILES = {
    '21': FIX/'PG64_2026-09-21(1).pdf',
    '23': FIX/'PG64_2026-09-23.pdf',
    '25': FIX/'PG64_2026-09-25.pdf',
}


def run(key):
    out = OUT / f'pg64_{key}.json'
    subprocess.run([sys.executable, str(PARSER), str(FILES[key]), '-o', str(out)], check=True)
    return json.loads(out.read_text())[0]


def main():
    for key, exp in EXPECTED.items():
        data = run(key)
        assert data['bulletin']['bulletin_number'] == exp['bulletin_number']
        assert data['bulletin']['bulletin_status'] == exp['status']
        codes = {r['product_code'] for r in data['rows'] if r['product_code']}
        assert codes == exp['codes'], (key, codes ^ exp['codes'])
        unresolved = {(r['product_family_label'], r['week_number']) for r in data['rows'] if r['product_code'] is None}
        assert unresolved == exp['unresolved_family'], (key, unresolved)
        # MASTER invariants
        for r in data['rows']:
            assert r['option_type'] in {'CALL','PUT','UNKNOWN',None}
            assert r['strike'] is not None
            assert r['product_family_label']
        assert all(r['product_code'] in exp['codes'] or r['product_code'] is None for r in data['rows'])
        print(f'PASS {key}: codes={len(codes)} rows={len(data["rows"])} totals={len(data["totals"])}')
    print('ALL PG64 v1 REGRESSION TESTS PASSED')

if __name__ == '__main__':
    main()
