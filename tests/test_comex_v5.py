#!/usr/bin/env python3
"""Integration checks for the current COMEX parser prototype."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent

def load(name, file):
    spec=importlib.util.spec_from_file_location(name, ROOT/file)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

pg62=load('pg62v5','parse_pg62_v5.py')
pg64=load('pg64v5','parse_pg64_v5.py')

class PG62Integration(unittest.TestCase):
    def test_2026_09_23(self):
        p=ROOT/'PG62_2026-09-23.pdf'
        if not p.exists(): self.skipTest('fixture PDF not present')
        d=pg62.parse_pdf(p)
        self.assertEqual(d['trade_date'],'2026-09-23')
        self.assertEqual(len(d['contracts']),28)
        self.assertEqual(d['bulletin']['status'],'FINAL')
        self.assertTrue(all(x['pass'] for x in d['validation']['total_reconciliation']))
        self.assertEqual({x['field'] for x in d['validation']['total_reconciliation']},{'volume_globex','volume_pnt_pit','open_interest','oi_change'})
    def test_2026_09_25(self):
        p=ROOT/'PG62_2026-09-25.pdf'
        if not p.exists(): self.skipTest('fixture PDF not present')
        d=pg62.parse_pdf(p)
        self.assertEqual(d['trade_date'],'2026-09-25')
        self.assertEqual(len(d['contracts']),28)
        self.assertEqual(d['bulletin']['status'],'PRELIMINARY')
        self.assertTrue(all(x['pass'] for x in d['validation']['total_reconciliation']))

class PG64Audit(unittest.TestCase):
    def test_audit_only_not_master(self):
        p=ROOT/'PG64_2026-09-25.pdf'
        if not p.exists(): self.skipTest('fixture PDF not present')
        d=pg64.audit(p)
        self.assertEqual(d['production_master_status'],'BLOCKED_DIAGNOSTIC_ONLY')
        self.assertGreater(len(d['pages_with_main_chain_header']),0)
        self.assertGreater(d['candidate_strike_rows'],0)
        self.assertTrue(any('character/content-stream' in x.lower() for x in d['known_unhandled_risks']))

if __name__=='__main__': unittest.main(verbosity=2)
