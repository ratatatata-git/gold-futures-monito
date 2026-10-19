#!/usr/bin/env python3
"""Create a character-first PDF text inventory and deterministic token candidates.

PyMuPDF is used only to expose individual character records and their geometry.
Canonical word boundaries are derived here, not inherited from engine word output.
This is a diagnostic inventory, not a semantic cell parser or accuracy certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from statistics import median
from typing import Any


def group_characters(characters: list[dict[str, Any]], gap_factor: float = 0.35,
                     baseline_factor: float = 0.35) -> list[dict[str, Any]]:
    """Group synthetic or extracted glyph records into line-ordered tokens.

    Input character fields: char_id, page_number, text, bbox=[x0,y0,x1,y1],
    origin_y, font_size. Space glyphs are retained as standalone tokens so that
    coverage accounting can explicitly disposition them instead of silently drop.
    """
    if gap_factor < 0 or baseline_factor < 0:
        raise ValueError("grouping factors must be non-negative")
    by_page: dict[int, list[dict[str, Any]]] = {}
    for char in characters:
        required = {"char_id", "page_number", "text", "bbox", "origin_y", "font_size"}
        if not isinstance(char, dict) or not required.issubset(char):
            raise ValueError("each character requires char_id, page_number, text, bbox, origin_y, font_size")
        if not isinstance(char["text"], str) or len(char["text"]) != 1:
            raise ValueError(f"character {char.get('char_id')} must contain exactly one Unicode code point")
        if not isinstance(char["bbox"], list) or len(char["bbox"]) != 4:
            raise ValueError(f"character {char['char_id']} bbox must contain four numbers")
        by_page.setdefault(int(char["page_number"]), []).append(char)

    lines: list[list[dict[str, Any]]] = []
    for page_number in sorted(by_page):
        page_chars = sorted(by_page[page_number], key=lambda c: (float(c["origin_y"]), float(c["bbox"][0])))
        page_lines: list[list[dict[str, Any]]] = []
        line_baselines: list[float] = []
        for char in page_chars:
            size = max(float(char["font_size"]), 1.0)
            compatible = [
                idx for idx, baseline in enumerate(line_baselines)
                if abs(float(char["origin_y"]) - baseline) <= baseline_factor * max(size, 1.0)
            ]
            if not compatible:
                page_lines.append([char])
                line_baselines.append(float(char["origin_y"]))
            else:
                idx = min(compatible, key=lambda j: abs(float(char["origin_y"]) - line_baselines[j]))
                page_lines[idx].append(char)
                # Keep a robust running median-like baseline by averaging; lines
                # with materially different baselines are kept separate.
                line_baselines[idx] = (line_baselines[idx] * (len(page_lines[idx]) - 1) + float(char["origin_y"])) / len(page_lines[idx])
        for line in page_lines:
            line.sort(key=lambda c: (float(c["bbox"][0]), float(c["bbox"][2])))
            lines.append(line)

    tokens: list[dict[str, Any]] = []
    for line in lines:
        current: list[dict[str, Any]] = []

        def emit(chars: list[dict[str, Any]], whitespace: bool = False) -> None:
            if not chars:
                return
            boxes = [c["bbox"] for c in chars]
            token = {
                "token_id": f"p{int(chars[0]['page_number'])}-t{len(tokens) + 1:06d}",
                "page_number": int(chars[0]["page_number"]),
                "text": "".join(c["text"] for c in chars),
                "char_ids": [c["char_id"] for c in chars],
                "bbox": [
                    min(float(b[0]) for b in boxes), min(float(b[1]) for b in boxes),
                    max(float(b[2]) for b in boxes), max(float(b[3]) for b in boxes),
                ],
                "font_size_median": median(float(c["font_size"]) for c in chars),
                "token_kind": "WHITESPACE" if whitespace else "TEXT",
            }
            tokens.append(token)

        for char in line:
            text = char["text"]
            if text.isspace():
                emit(current)
                current = []
                emit([char], whitespace=True)
                continue
            if current:
                previous = current[-1]
                gap = float(char["bbox"][0]) - float(previous["bbox"][2])
                size = median(float(c["font_size"]) for c in current + [char])
                if gap > gap_factor * max(size, 1.0):
                    emit(current)
                    current = []
            current.append(char)
        emit(current)
    return tokens


def extract_inventory(pdf_path: Path, gap_factor: float = 0.35,
                      baseline_factor: float = 0.35) -> dict[str, Any]:
    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required: install pymupdf") from exc

    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    document = fitz.open(pdf_path)
    characters: list[dict[str, Any]] = []
    page_geometry: list[dict[str, Any]] = []
    try:
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            page_geometry.append({
                "page_number": page_number,
                "width": float(page.rect.width),
                "height": float(page.rect.height),
            })
            raw = page.get_text("rawdict", sort=False)
            char_index = 0
            for block in raw.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        size = float(span.get("size") or 0)
                        for glyph in span.get("chars", []):
                            char_index += 1
                            origin = glyph.get("origin", [0, glyph["bbox"][3]])
                            characters.append({
                                "char_id": f"p{page_number}-c{char_index:06d}",
                                "page_number": page_number,
                                "text": glyph.get("c", ""),
                                "bbox": [float(v) for v in glyph["bbox"]],
                                "origin_y": float(origin[1]),
                                "font_size": size,
                                "font": span.get("font", ""),
                                "flags": span.get("flags"),
                                "block_no": block.get("number"),
                            })
    finally:
        document.close()

    tokens = group_characters(characters, gap_factor=gap_factor, baseline_factor=baseline_factor)
    return {
        "schema_version": 1,
        "extraction_mode": "CHARACTER_FIRST_DIAGNOSTIC",
        "source": {
            "filename": pdf_path.name,
            "sha256": digest,
            "page_count": len(page_geometry),
        },
        "page_geometry": page_geometry,
        "grouping": {
            "algorithm": "baseline-cluster + font-size-relative horizontal gap",
            "gap_factor": gap_factor,
            "baseline_factor": baseline_factor,
        },
        "characters": characters,
        "tokens": tokens,
        "limitations": [
            "No semantic cell assignment is performed.",
            "Token grouping thresholds require validation against multiple layouts and dates.",
            "This inventory is not an accuracy or publication approval.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gap-factor", type=float, default=0.35)
    parser.add_argument("--baseline-factor", type=float, default=0.35)
    args = parser.parse_args()
    try:
        result = extract_inventory(args.pdf, args.gap_factor, args.baseline_factor)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        f"CHARACTER_FIRST_DIAGNOSTIC: pages={result['source']['page_count']} "
        f"characters={len(result['characters'])} tokens={len(result['tokens'])} "
        f"sha256={result['source']['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
