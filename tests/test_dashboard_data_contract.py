import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_dashboard_data as validator  # noqa: E402


class DashboardDataContractTests(unittest.TestCase):
    def test_valid_cot_and_fred_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cot = root / "cot.json"
            fred = root / "fred.json"
            cot.write_text(json.dumps({
                "schema_version": 1,
                "records": [{
                    "report_date_as_yyyy_mm_dd": "2026-10-06",
                    "cftc_contract_market_code": "088691",
                    "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
                    "m_money_positions_long_all": "12345",
                    "m_money_positions_short_all": "6789"
                }]
            }), encoding="utf-8")
            fred.write_text(json.dumps({
                "schema_version": 1,
                "records": [{
                    "observation_date": "2026-10-15",
                    "values": {"DFII10": None, "DGS10": 4.08, "DTWEXBGS": 120.8},
                    "raw_values": {"DFII10": ".", "DGS10": "4.08", "DTWEXBGS": "120.8"}
                }]
            }), encoding="utf-8")
            self.assertEqual(validator.validate_cot(cot), 1)
            self.assertEqual(validator.validate_fred(fred), 1)

    def test_rejects_wrong_cot_market_and_unsorted_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cot.json"
            path.write_text(json.dumps({"schema_version": 1, "records": [{
                "report_date_as_yyyy_mm_dd": "2026-10-06",
                "cftc_contract_market_code": "999999",
                "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC."
            }]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "contract market code"):
                validator.validate_cot(path)

    def test_rejects_missing_fred_series_and_duplicate_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fred.json"
            row = {
                "observation_date": "2026-10-15",
                "values": {"DFII10": 1.7, "DGS10": 4.0},
                "raw_values": {"DFII10": "1.7", "DGS10": "4.0"}
            }
            path.write_text(json.dumps({"schema_version": 1, "records": [row]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "DTWEXBGS"):
                validator.validate_fred(path)
            row["values"]["DTWEXBGS"] = 120.0
            row["raw_values"]["DTWEXBGS"] = "120.0"
            path.write_text(json.dumps({"schema_version": 1, "records": [row, row]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unique observation date"):
                validator.validate_fred(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
