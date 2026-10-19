import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import extract_pdf_character_inventory as extractor  # noqa: E402


def char(char_id, text, x0, x1, baseline=10.0, size=10.0, page=1):
    return {
        "char_id": char_id,
        "page_number": page,
        "text": text,
        "bbox": [x0, 0.0, x1, 10.0],
        "origin_y": baseline,
        "font_size": size,
    }


class CharacterFirstTokenizerTests(unittest.TestCase):
    def test_close_glyphs_form_word_and_large_gap_splits(self):
        chars = [
            char("c1", "A", 0, 5),
            char("c2", "B", 5.5, 10.5),
            char("c3", "C", 20, 25),
        ]
        tokens = extractor.group_characters(chars)
        self.assertEqual([t["text"] for t in tokens], ["AB", "C"])
        self.assertEqual(tokens[0]["char_ids"], ["c1", "c2"])

    def test_whitespace_is_retained_as_explicit_token(self):
        chars = [
            char("c1", "A", 0, 5),
            char("c2", " ", 5, 8),
            char("c3", "B", 8, 13),
        ]
        tokens = extractor.group_characters(chars)
        self.assertEqual([t["text"] for t in tokens], ["A", " ", "B"])
        self.assertEqual(tokens[1]["token_kind"], "WHITESPACE")

    def test_font_size_relative_gap(self):
        chars = [
            char("c1", "1", 0, 4, size=8),
            char("c2", "2", 5, 9, size=8),
            char("c3", "3", 13, 17, size=8),
        ]
        tokens = extractor.group_characters(chars, gap_factor=0.35)
        self.assertEqual([t["text"] for t in tokens], ["12", "3"])

    def test_baseline_difference_separates_lines(self):
        chars = [
            char("c1", "A", 0, 5, baseline=10),
            char("c2", "B", 0, 5, baseline=20),
        ]
        tokens = extractor.group_characters(chars)
        self.assertEqual([t["text"] for t in tokens], ["A", "B"])

    def test_every_character_is_retained_exactly_once(self):
        chars = [
            char("c1", "A", 0, 5),
            char("c2", " ", 5, 8),
            char("c3", "B", 8, 13),
            char("c4", "-", 0, 5, baseline=20),
            char("c5", "1", 5, 10, baseline=20),
        ]
        tokens = extractor.group_characters(chars)
        flattened = [char_id for token in tokens for char_id in token["char_ids"]]
        self.assertCountEqual(flattened, [c["char_id"] for c in chars])
        self.assertEqual(len(flattened), len(set(flattened)))

    def test_invalid_grouping_threshold_is_rejected(self):
        with self.assertRaises(ValueError):
            extractor.group_characters([], gap_factor=-1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
