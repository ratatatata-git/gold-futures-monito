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

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_module(
    "build_pg62_master",
    "build_pg62_master.py",
)


def assert_no_parser_error(testcase, value, path="root"):
    if isinstance(value, dict):
        testcase.assertNotEqual(
            value.get("state"),
            "PARSER_ERROR",
            f"PARSER_ERROR found at {path}: {value!r}",
        )

        for key, child in value.items():
            assert_no_parser_error(
                testcase,
                child,
                f"{path}.{key}",
            )

    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_parser_error(
                testcase,
                child,
                f"{path}[{index}]",
            )


class PG62MasterTest(unittest.TestCase):

    def build_and_load(self, pdf_name):
        pdf = DATA_DIR / pdf_name

        self.assertTrue(
            pdf.exists(),
            f"Required fixture PDF is missing: {pdf}",
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)

            output = builder.build_master(
                pdf,
                output_root,
            )

            self.assertTrue(
                output.exists(),
                f"MASTER output was not created: {output}",
            )

            data = json.loads(
                output.read_text(
                    encoding="utf-8"
                )
            )

            return data

    def assert_master_common(self, data):
        self.assertEqual(
            data["schema_version"],
            "pg62.master.daily.v5",
        )

        self.assertEqual(
            data["dataset"],
            "PG62_GC_FUTURES",
        )

        self.assertEqual(
            data["validation"]["status"],
            "PASS",
        )

        self.assertEqual(
            data["validation"]["contract_rows"],
            28,
        )

        self.assertEqual(
            len(data["contracts"]),
            28,
        )

        self.assertTrue(
            data["source"]["sha256"],
            "MASTER must contain source SHA256",
        )

        self.assertEqual(
            len(data["source"]["sha256"]),
            64,
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

        self.assertEqual(
            data["build"]["source_sha256"],
            data["source"]["sha256"],
        )

        reconciliation = data["validation"]["total_reconciliation"]

        expected_fields = {
            "volume_globex",
            "volume_pnt_pit",
            "open_interest",
            "oi_change",
        }

        actual_fields = {
            item["field"]
            for item in reconciliation
        }

        self.assertEqual(
            actual_fields,
            expected_fields,
        )

        self.assertEqual(
            len(reconciliation),
            4,
        )

        for item in reconciliation:
            self.assertTrue(
                item["pass"],
                f"TOTAL reconciliation failed: {item}",
            )

            self.assertEqual(
                item["parsed_sum_of_numeric_cells"],
                item["source_total"],
                f"Parsed/source TOTAL mismatch: {item}",
            )

        assert_no_parser_error(
            self,
            data,
        )

    def test_final_master(self):
        pdf = DATA_DIR / "PG62_2026-09-23.pdf"

        self.assertTrue(
            pdf.exists(),
            f"Required fixture PDF is missing: {pdf}",
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
            data["bulletin"]["number"],
            183,
        )

        self.assertEqual(
            data["bulletin"]["status"],
            "FINAL",
        )

        self.assert_master_common(data)

    def test_preliminary_master(self):
        pdf = DATA_DIR / "PG62_2026-09-25.pdf"

        self.assertTrue(
            pdf.exists(),
            f"Required fixture PDF is missing: {pdf}",
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
            data["bulletin"]["number"],
            185,
        )

        self.assertEqual(
            data["bulletin"]["status"],
            "PRELIMINARY",
        )

        self.assert_master_common(data)

    def test_existing_different_source_is_not_overwritten(self):
        pdf = DATA_DIR / "PG62_2026-09-23.pdf"

        self.assertTrue(
            pdf.exists(),
            f"Required fixture PDF is missing: {pdf}",
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

            data["source"]["sha256"] = "DIFFERENT_SOURCE"

            modified = json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            )

            output.write_text(
                modified,
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
                modified,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
