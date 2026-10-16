import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_fred_context import ingest, parse_csv  # noqa: E402


CSV = b"observation_date,DFII10,DGS10,DTWEXBGS\n2026-10-14,1.72,4.10,120.4\n2026-10-15,.,4.08,120.8\n"


class FredContextTests(unittest.TestCase):
    def test_parse_values_and_preserve_missing(self):
        rows = parse_csv(CSV)
        self.assertEqual(rows[0]["values"]["DFII10"], 1.72)
        self.assertIsNone(rows[1]["values"]["DFII10"])
        self.assertEqual(rows[1]["raw_values"]["DFII10"], ".")

    def test_reject_missing_column_and_duplicate_dates(self):
        with self.assertRaisesRegex(ValueError, "missing expected"):
            parse_csv(b"observation_date,DFII10\n2026-10-14,1.7\n")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            parse_csv(CSV + b"2026-10-15,1.7,4.0,120.0\n")

    def test_idempotent_ingestion_and_revision_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history.json"
            raw = root / "raw"
            first = ingest(CSV, history, raw, "2026-10-16T00:00:00+00:00")
            second = ingest(CSV, history, raw, "2026-10-16T01:00:00+00:00")
            self.assertEqual(first["rows_added"], 2)
            self.assertEqual(second["rows_added"], 0)
            self.assertEqual(second["rows_revised"], 0)
            self.assertEqual(len(list(raw.glob("*.csv"))), 1)

            revised_csv = CSV.replace(b"1.72", b"1.73")
            third = ingest(revised_csv, history, raw, "2026-10-16T02:00:00+00:00")
            self.assertEqual(third["rows_added"], 0)
            self.assertEqual(third["rows_revised"], 1)
            self.assertEqual(len(list(raw.glob("*.csv"))), 2)


if __name__ == "__main__":
    unittest.main()
