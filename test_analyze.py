import csv
import json
import sqlite3
import unittest
from analyze import ROOT, validate, calculate

class FinancialTests(unittest.TestCase):
    def setUp(self):
        with (ROOT/'data/financials.csv').open() as f:
            self.raw = list(csv.DictReader(f))
        self.sources = json.loads((ROOT/'data/sources.json').read_text())
    def metrics(self, raw=None):
        with sqlite3.connect(':memory:') as conn:
            return calculate(validate(self.raw if raw is None else raw, self.sources), conn)
    def test_reported_fcf_reconciliation(self):
        wmt = {r['fiscal_year']: r for r in self.metrics() if r['ticker']=='WMT'}
        self.assertEqual([wmt[y]['fcf_usd_m'] for y in [2023,2024,2025]], [11984,15120,12660])
        self.assertAlmostEqual(wmt[2025]['operating_margin_pct'], 4.30964, places=5)
    def test_no_cross_company_growth(self):
        rows = self.metrics()
        self.assertTrue(all(r['revenue_growth_pct'] is None for r in [rows[0],rows[3],rows[6]]))
    def test_gap_is_not_yoy(self):
        rows = self.metrics([r for r in self.raw if not (r['ticker']=='WMT' and r['fiscal_year']=='2024')])
        latest = next(r for r in rows if r['ticker']=='WMT' and r['fiscal_year']==2025)
        self.assertIsNone(latest['revenue_growth_pct'])
        self.assertIsNone(latest['fcf_change_usd_m'])
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            validate(self.raw + self.raw[:1], self.sources)
    def test_zero_revenue_and_negative_capex_rejected(self):
        for field, value in [('revenue_usd_m','0'),('capex_usd_m','-1')]:
            raw = [dict(r) for r in self.raw]
            raw[0][field] = value
            with self.assertRaises(ValueError):
                validate(raw, self.sources)
    def test_cash_flow_bridge(self):
        for r in self.metrics():
            if r['fcf_change_usd_m'] is not None:
                self.assertEqual(r['fcf_change_usd_m'],r['cfo_change_usd_m']-r['capex_change_usd_m'])
    def test_missing_source_rejected(self):
        with self.assertRaises(ValueError):
            validate(self.raw, {})

if __name__ == '__main__':
    unittest.main()
