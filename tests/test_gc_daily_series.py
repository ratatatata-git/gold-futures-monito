import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "gc_daily_gate", ROOT / "scripts" / "validate_gc_daily_series.py"
)
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def make_row(date, status="FINAL", contract="DEC26", settlement="4400.00",
             price_change="10.00", oi=1000, oi_change=20):
    return {
        "date": date, "source_status": status, "contract": contract,
        "settlement": settlement, "price_change": price_change,
        "open_interest": oi, "oi_change": oi_change,
    }


class GcDailyGateTests(unittest.TestCase):
    def test_valid_adjacent_values_are_checked(self):
        data = {"observations": [
            make_row("2026-10-13", settlement="4390.00", price_change="0",
                     oi=980, oi_change=0),
            make_row("2026-10-14"),
        ]}
        result = GATE.inspect_series(data)
        self.assertEqual(result["gate"], "INCOMPLETE")
        current = [x for x in result["checks"] if x["date"] == "2026-10-14"]
        self.assertEqual([x["status"] for x in current], ["CHECKED", "CHECKED"])

    def test_settlement_mismatch_blocks(self):
        data = {"observations": [
            make_row("2026-10-13", settlement="4390.00", oi=980),
            make_row("2026-10-14", price_change="9.00"),
        ]}
        result = GATE.inspect_series(data)
        self.assertEqual(result["gate"], "BLOCKED")
        self.assertEqual(result["counts"]["mismatches"], 1)

    def test_preliminary_is_excluded(self):
        data = {"observations": [
            make_row("2026-10-13", status="PRELIMINARY", settlement="4390.00", oi=980),
            make_row("2026-10-14"),
        ]}
        result = GATE.inspect_series(data)
        self.assertEqual(result["gate"], "INCOMPLETE")
        self.assertTrue(all(x["status"] == "NOT_CHECKED" for x in result["checks"]))

    def test_duplicate_final_key_raises(self):
        data = {"observations": [
            make_row("2026-10-14"), make_row("2026-10-14", settlement="4401.00")
        ]}
        with self.assertRaisesRegex(ValueError, "duplicate FINAL"):
            GATE.inspect_series(data)

    def test_new_contract_is_not_assumed_pass(self):
        data = {"observations": [
            make_row("2026-10-13", contract="DEC26"),
            make_row("2026-10-14", contract="FEB27"),
        ]}
        result = GATE.inspect_series(data)
        self.assertEqual(result["gate"], "INCOMPLETE")
        self.assertTrue(all(x["status"] == "NOT_CHECKED" for x in result["checks"]))


if __name__ == "__main__":
    unittest.main()
