#!/usr/bin/env python3

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
DATA_DIR = ROOT / "data" / "cme-pg62"


def load_module(name, filename):
    path = SCRIPTS_DIR / filename

    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )

    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_module(
    "build_pg62_master",
    "build_pg62_master.py",
)


class PG62MasterTest(unittest.TestCase):

    def test_final_master(self):
        pdf = DATA_DIR / "PG62_2026-09-23.pdf"

        if not pdf.exists():
            self.skipTest(
                f"fixture PDF not present: {pdf}"
            )

        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)

            output = builder.build_master(
                pdf,
                output_root,
            )

            self.assertTrue(output.exists())

            data = json.loads(
                output.read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                data["trade_date"],
                "2026-09-23",
            )

            self.assertEqual(
                data["bulletin"]["status"],
                "FINAL",
            )

            self.assertEqual(
                data["validation"]["status"],
                "PASS",
            )

            self.assertEqual(
                len(data["contracts"]),
                28,
            )

            self.assertEqual(
                data["master"]["status"],
                "VALIDATED",
            )

            self.assertTrue(
                data["master"]["source_observation"]
            )

            self.assertFalse(
                data["master"]["derived_analysis"]
            )

    def test_preliminary_master(self):
        pdf = DATA_DIR / "PG62_2026-09-25.pdf"

        if not pdf.exists():
            self.skipTest(
                f"fixture PDF not present: {pdf}"
            )

        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)

            output = builder.build_master(
                pdf,
                output_root,
            )

            self.assertTrue(output.exists())

            data = json.loads(
                output.read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                data["trade_date"],
                "2026-09-25",
            )

            self.assertEqual(
                data["bulletin"]["status"],
                "PRELIMINARY",
            )

            self.assertEqual(
                data["validation"]["status"],
                "PASS",
            )

            self.assertEqual(
                len(data["contracts"]),
                28,
            )

    def test_existing_different_source_is_not_overwritten(self):
        pdf = DATA_DIR / "PG62_2026-09-23.pdf"

        if not pdf.exists():
            self.skipTest(
                f"fixture PDF not present: {pdf}"
            )

        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)

            output = builder.build_master(
                pdf,
                output_root,
            )

            original = output.read_text(
                encoding="utf-8"
            )

            data = json.loads(original)

            # Simulate a conflicting artifact.
            data["source"]["sha256"] = "DIFFERENT_SOURCE"

            output.write_text(
                json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                builder.build_master(
                    pdf,
                    output_root,
                )

            after = output.read_text(
                encoding="utf-8"
            )

            self.assertEqual(
                after,
                json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2,
                ),
            )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
