#!/usr/bin/env python3
"""
PDF -> accessible HTML bundle.

Implements the main README.MD contract:
- page raster layer as AVIF images;
- word boxes as compact delta JSON;
- Brotli-compressed JSON plus uncompressed JSON fallback;
- OCR fallback with Tesseract psm=11;
- OpenCV-assisted line/region/marker metadata;
- generated index.html/css/js viewer assets.

Usage:
    python pdf_to_html.py input.pdf --out project
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

import brotli
import cv2
import fitz  # PyMuPDF
import numpy as np
import pytesseract
from PIL import Image

try:
    import pillow_avif  # noqa: F401  # registers AVIF support in Pillow
except Exception:
    pillow_avif = None


ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "fig", "eq", "no", "vol", "pp", "cf",
}


@dataclass
class WordBox:
    text: str
    x: int
    y: int
    w: int
    h: int
    conf: int = 100
    source: str = "pdf_text"
    rule: str = "native_pdf_text"

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h


def clamp_int(value: float, min_value: int = 0) -> int:
    return max(min_value, int(round(value)))


def fit_size(width: int, height: int, portrait_max: tuple[int, int], landscape_max: tuple[int, int]) -> tuple[int, int]:
    max_w, max_h = portrait_max if height >= width else landscape_max
    scale = min(max_w / width, max_h / height, 1.0)
    return max(1, round(width * scale)), max(1, round(height * scale))


def render_page(page: fitz.Page, dpi: int, portrait_max: tuple[int, int], landscape_max: tuple[int, int]) -> tuple[Image.Image, float, float]:
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    target_w, target_h = fit_size(image.width, image.height, portrait_max, landscape_max)
    if (target_w, target_h) != (image.width, image.height):
        image = image.resize((target_w, target_h), Image.Resampling.LANCZOS)

    scale_x = image.width / float(page.rect.width)
    scale_y = image.height / float(page.rect.height)
    return image, scale_x, scale_y


def extract_native_words(page: fitz.Page, scale_x: float, scale_y: float) -> list[WordBox]:
    words: list[WordBox] = []
    for item in page.get_text("words"):
        x0, y0, x1, y1, text = item[:5]
        text = str(text).strip()
        if not text:
            continue
        x = clamp_int(x0 * scale_x)
        y = clamp_int(y0 * scale_y)
        w = max(1, clamp_int((x1 - x0) * scale_x))
        h = max(1, clamp_int((y1 - y0) * scale_y))
        words.append(WordBox(text=text, x=x, y=y, w=w, h=h, conf=100, source="pdf_text", rule="native_pdf_text"))
    return words


def extract_ocr_words(image: Image.Image, psm: int = 11) -> list[WordBox]:
    data = pytesseract.image_to_data(image, config=f"--psm {psm}", output_type=pytesseract.Output.DICT)
    words: list[WordBox] = []
    for i, raw_text in enumerate(data.get("text", [])):
        text = str(raw_text).strip()
        if not text:
            continue

        try:
            conf_float = float(data["conf"][i])
        except Exception:
            conf_float = -1

        if conf_float < 0:
            continue

        x = clamp_int(data["left"][i])
        y = clamp_int(data["top"][i])
        w = max(1, clamp_int(data["width"][i]))
        h = max(1, clamp_int(data["height"][i]))

        words.append(
            WordBox(
                text=text,
                x=x,
                y=y,
                w=w,
                h=h,
                conf=max(0, min(100, int(round(conf_float)))),
                source="ocr",
                rule=f"tesseract_psm_{psm}",
            )
        )
    return words


def choose_words(page: fitz.Page, image: Image.Image, scale_x: float, scale_y: float, force_ocr: bool, psm: int) -> list[WordBox]:
    native = [] if force_ocr else extract_native_words(page, scale_x, scale_y)
    if native:
        return native
    return extract_ocr_words(image, psm=psm)


def save_avif(image: Image.Image, path: Path, quality: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="AVIF", quality=quality)


def detect_linear_objects(image: Image.Image) -> list[dict[str, Any]]:
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 50, 150, apertureSize=3)

    min_len = max(30, min(image.width, image.height) // 15)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=min_len, maxLineGap=8)

    result: list[dict[str, Any]] = []
    if lines is None:
        return result

    for raw in lines[:300]:
        x1, y1, x2, y2 = [int(v) for v in raw[0]]
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length < min_len:
            continue
        if abs(dx) >= abs(dy) * 3:
            orientation = "horizontal"
        elif abs(dy) >= abs(dx) * 3:
            orientation = "vertical"
        else:
            orientation = "diagonal"

        result.append(
            {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "orientation": orientation,
                "length": round(length, 2),
                "rule": "opencv_hough_lines_p",
            }
        )
    return result


def line_groups(words: list[WordBox]) -> list[dict[str, Any]]:
    if not words:
        return []

    median_h = np.median([w.h for w in words]) if words else 12
    threshold = max(6, int(round(median_h * 0.75)))

    lines: list[list[WordBox]] = []
    for word in sorted(words, key=lambda w: (w.y + w.h / 2, w.x)):
        cy = word.y + word.h / 2
        best_line: list[WordBox] | None = None
        best_dist = 999999.0
        for line in lines:
            line_cy = np.mean([w.y + w.h / 2 for w in line])
            dist = abs(cy - line_cy)
            if dist < threshold and dist < best_dist:
                best_line = line
                best_dist = dist
        if best_line is None:
            lines.append([word])
        else:
            best_line.append(word)

    result = []
    for idx, line_words in enumerate(lines):
        line_words.sort(key=lambda w: w.x)
        result.append(
            {
                "id": idx,
                "text": " ".join(w.text for w in line_words),
                "x": min(w.x for w in line_words),
                "y": min(w.y for w in line_words),
                "w": max(w.right for w in line_words) - min(w.x for w in line_words),
                "h": max(w.bottom for w in line_words) - min(w.y for w in line_words),
                "wordIndexes": [],  # filled later after page-local indexes are known
            }
        )
    return result


def average_line_interval(lines: list[dict[str, Any]]) -> float:
    if len(lines) < 2:
        return 12.0
    centers = sorted(line["y"] + line["h"] / 2 for line in lines)
    gaps = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
    return float(np.mean(gaps)) if gaps else 12.0


def detect_empty_regions(width: int, height: int, words: list[WordBox], lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Practical approximation of README empty-space orders:
    finds large horizontal/vertical gaps between text lines/columns.
    """
    regions: list[dict[str, Any]] = []
    avg_interval = average_line_interval(lines)
    min_power = max(6, int(round(avg_interval * 1.1)))

    # horizontal bands between lines
    sorted_lines = sorted(lines, key=lambda item: item["y"])
    prev_bottom = 0
    for line in sorted_lines:
        gap = line["y"] - prev_bottom
        if gap >= min_power:
            regions.append(
                {
                    "x": 0,
                    "y": prev_bottom,
                    "w": width,
                    "h": gap,
                    "orientation": "horizontal",
                    "power": min(width, gap),
                    "rule": "empty_horizontal_gap_between_text_lines",
                }
            )
        prev_bottom = max(prev_bottom, line["y"] + line["h"])
    bottom_gap = height - prev_bottom
    if bottom_gap >= min_power:
        regions.append(
            {
                "x": 0,
                "y": prev_bottom,
                "w": width,
                "h": bottom_gap,
                "orientation": "horizontal",
                "power": min(width, bottom_gap),
                "rule": "empty_horizontal_gap_after_last_text_line",
            }
        )

    # vertical bands from projection of occupied word boxes
    if words:
        intervals = sorted((w.x, w.right) for w in words)
        merged: list[list[int]] = []
        for left, right in intervals:
            if not merged or left > merged[-1][1] + 4:
                merged.append([left, right])
            else:
                merged[-1][1] = max(merged[-1][1], right)

        prev_right = 0
        for left, right in merged:
            gap = left - prev_right
            if gap >= min_power:
                regions.append(
                    {
                        "x": prev_right,
                        "y": 0,
                        "w": gap,
                        "h": height,
                        "orientation": "vertical",
                        "power": min(gap, height),
                        "rule": "empty_vertical_gap_between_text_columns",
                    }
                )
            prev_right = max(prev_right, right)
        right_gap = width - prev_right
        if right_gap >= min_power:
            regions.append(
                {
                    "x": prev_right,
                    "y": 0,
                    "w": right_gap,
                    "h": height,
                    "orientation": "vertical",
                    "power": min(right_gap, height),
                    "rule": "empty_vertical_gap_after_last_text_column",
                }
            )

    regions = sorted(regions, key=lambda item: item["power"], reverse=True)[:10]
    for order, region in enumerate(regions, start=1):
        region["order"] = order
    return regions


def select_painted_regions(width: int, height: int, regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select and annotate the structural regions that README.MD says to paint."""
    vertical = [region for region in regions if region["orientation"] == "vertical"]
    left_thirds = [region for region in vertical if region["x"] <= width * 0.35 and region["x"] + region["w"] >= width * 0.30]
    right_thirds = [region for region in vertical if region["x"] <= width * 0.70 and region["x"] + region["w"] >= width * 0.60]
    selected_vertical: list[dict[str, Any]] = []
    rules: dict[int, str] = {}

    for region in vertical:
        if region["x"] <= width * 0.525 and region["x"] + region["w"] >= width * 0.475:
            selected_vertical.append(region)
            rules[id(region)] = "middle_vertical_split"
    if left_thirds and right_thirds:
        for region in [*left_thirds, *right_thirds]:
            selected_vertical.append(region)
            rules[id(region)] = "thirds_vertical_split_pair"

    painted = []
    for region in regions:
        horizontal_full = region["orientation"] == "horizontal" and region["x"] <= 3 and region["x"] + region["w"] >= width - 3
        horizontal_to_vertical = region["orientation"] == "horizontal" and any(
            (region["x"] <= 3 or region["x"] + region["w"] >= width - 3)
            and region["x"] <= cut["x"] + cut["w"] / 2 <= region["x"] + region["w"]
            for cut in selected_vertical
        )
        if region in selected_vertical or horizontal_full or horizontal_to_vertical:
            copy = dict(region)
            copy["painted"] = True
            copy["paintRule"] = rules.get(id(region), "full_width_horizontal" if horizontal_full else "horizontal_to_vertical_split")
            painted.append(copy)
    return painted


def detect_blocks(lines: list[dict[str, Any]], width: int, painted_regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group lines into text blocks bounded by painted structural regions."""
    if not lines:
        return []

    vertical_cuts = sorted(
        region["x"] + region["w"] / 2
        for region in painted_regions
        if region["orientation"] == "vertical"
    )
    horizontal_cuts = [
        region for region in painted_regions if region["orientation"] == "horizontal"
    ]
    avg_h = float(np.median([line["h"] for line in lines]))
    gap_limit = max(16, avg_h * 2.2)

    def column(line: dict[str, Any]) -> int:
        center = line["x"] + line["w"] / 2
        return sum(center > cut for cut in vertical_cuts)

    def separated(previous: dict[str, Any], current: dict[str, Any]) -> bool:
        gap_top = previous["y"] + previous["h"]
        for region in horizontal_cuts:
            overlaps_x = region["x"] < current["x"] + current["w"] and region["x"] + region["w"] > current["x"]
            if overlaps_x and gap_top <= region["y"] + region["h"] and current["y"] >= region["y"]:
                return True
        return False

    grouped: dict[int, list[dict[str, Any]]] = {}
    for line in lines:
        grouped.setdefault(column(line), []).append(line)

    raw_blocks: list[list[dict[str, Any]]] = []
    for column_id in sorted(grouped):
        for line in sorted(grouped[column_id], key=lambda item: (item["y"], item["x"])):
            if not raw_blocks or column(raw_blocks[-1][-1]) != column_id:
                raw_blocks.append([line])
                continue
            previous = raw_blocks[-1][-1]
            vertical_gap = line["y"] - (previous["y"] + previous["h"])
            if vertical_gap > gap_limit or separated(previous, line):
                raw_blocks.append([line])
            else:
                raw_blocks[-1].append(line)

    result = []
    for idx, block_lines in enumerate(raw_blocks, start=1):
        x1 = min(line["x"] for line in block_lines)
        y1 = min(line["y"] for line in block_lines)
        x2 = max(line["x"] + line["w"] for line in block_lines)
        y2 = max(line["y"] + line["h"] for line in block_lines)
        result.append({
            "id": idx, "x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1,
            "lineIds": [line["id"] for line in block_lines],
            "rule": "bounded_by_painted_regions_or_page_edge",
        })
    return result


def detect_markers(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    pattern = re.compile(r"^\s*(([-+*•✓✔■□◆◇○●])|(\(?[0-9]+[\).])|([a-zA-Zа-яА-Я][\).]))\s+")
    for line in lines:
        match = pattern.match(line["text"])
        if not match:
            continue
        markers.append({
            "lineId": line["id"], "x": line["x"], "y": line["y"],
            "w": min(line["w"], max(12, int(line["h"] * 1.6))), "h": line["h"],
            "marker": match.group(1).strip(), "rule": "repeated_list_marker_regex_or_symbol",
        })
    return markers


def sentence_break(prev_word: str, next_word: str) -> bool:
    stripped = prev_word.strip()
    if not stripped or stripped[-1] not in ".!?":
        return False
    normalized = stripped.rstrip(".!?").lower()
    if normalized in ABBREVIATIONS or re.match(r"^(?:[A-ZА-Я]\.)+$", stripped):
        return False
    if re.match(r"^\(?([0-9]+|[A-Za-zА-Яа-я])\)?[.)]$", stripped):
        return False
    if not next_word:
        return True
    next_letter = re.search(r"[A-Za-zА-Яа-яЁё]", next_word)
    return bool(next_letter and next_letter.group(0).isupper())


def block_position(block: dict[str, Any], page_width: int) -> str:
    center = (block["x"] + block["w"] / 2) / max(1, page_width)
    if center < 0.4:
        return "left"
    if center > 0.6:
        return "right"
    return "center"


def build_sentences(words: list[WordBox], lines: list[dict[str, Any]], blocks: list[dict[str, Any]], markers: list[dict[str, Any]], page_width: int) -> list[dict[str, Any]]:
    """Split text inside ordered blocks, allowing only README.MD block transitions."""
    marker_lines = {marker["lineId"] for marker in markers}
    line_by_id = {line["id"]: line for line in lines}
    ordered_lines = [
        (line_by_id[line_id], block)
        for block in blocks
        for line_id in block["lineIds"]
        if line_id in line_by_id
    ]
    sentences: list[dict[str, Any]] = []
    current: list[int] = []
    rules: list[str] = []
    previous_line: dict[str, Any] | None = None
    previous_block: dict[str, Any] | None = None

    def flush(rule: str) -> None:
        nonlocal current, rules
        if current:
            sentences.append({
                "id": len(sentences), "wordIndexes": current,
                "text": " ".join(words[index].text for index in current),
                "rule": rule, "rules": sorted(set(rules + [rule])),
                "isListPart": any(item.startswith("list_") for item in rules + [rule]),
            })
        current, rules = [], []

    for line_position, (line, block) in enumerate(ordered_lines):
        indexes = line.get("wordIndexes", [])
        if not indexes:
            continue
        block_changed = previous_block is not None and block["id"] != previous_block["id"]
        allowed_block_transition = block_changed and (
            (block_position(previous_block, page_width), block_position(block, page_width))
            in {("left", "right"), ("center", "center")}
        )
        if current and block_changed and not allowed_block_transition:
            flush("text_block_boundary")
        indent_changed = (
            previous_line is not None and not block_changed
            and abs(line["x"] - previous_line["x"]) > max(8, line["h"])
        )
        if current and (line["id"] in marker_lines or indent_changed):
            flush("list_marker" if line["id"] in marker_lines else "left_indent_change")
        if line["id"] in marker_lines:
            rules.append("list_marker")

        for position, index in enumerate(indexes):
            current.append(index)
            next_index = indexes[position + 1] if position + 1 < len(indexes) else None
            if next_index is None:
                for following_line, _ in ordered_lines[line_position + 1:]:
                    if following_line.get("wordIndexes"):
                        next_index = following_line["wordIndexes"][0]
                        break
            next_word = words[next_index].text if next_index is not None else ""
            if sentence_break(words[index].text, next_word):
                flush("terminal_punctuation")

        if current and line["text"].rstrip().endswith((":", ";")):
            rules.append("list_colon_or_semicolon")
            flush("list_colon_or_semicolon")
        previous_line = line
        previous_block = block

    flush("end_of_document")
    return sentences


def encode_delta_words(words: list[WordBox], dictionary: dict[str, int]) -> tuple[list[list[int]], list[dict[str, Any]]]:
    encoded: list[list[int]] = []
    meta: list[dict[str, Any]] = []
    prev_x = 0
    prev_y = 0

    for word in words:
        if word.text not in dictionary:
            dictionary[word.text] = len(dictionary)

        dx = word.x - prev_x
        dy = word.y - prev_y
        encoded.append([dictionary[word.text], dx, dy, word.w, word.h, word.conf])
        meta.append({"source": word.source, "rule": word.rule})

        prev_x = word.x
        prev_y = word.y

    return encoded, meta


def write_json_and_br(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)
    path.with_suffix(path.suffix + ".br").write_bytes(brotli.compress(raw, quality=11))


def copy_viewer_assets(out_dir: Path) -> None:
    base_dir = Path(__file__).resolve().parent

    for rel in ("index.html", "css/style.css", "js/renderer.js"):
        src = base_dir / rel
        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, dst)


def total_output_size(out_dir: Path) -> int:
    return sum(path.stat().st_size for path in out_dir.rglob("*") if path.is_file())


def process_pdf(args: argparse.Namespace) -> None:
    input_pdf = Path(args.input_pdf)
    out_dir = Path(args.out)
    data_dir = out_dir / "data"
    images_dir = data_dir / "images"
    locales_dir = out_dir / "locales"

    out_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    locales_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(input_pdf)
    dictionary: dict[str, int] = {}
    pages_payload: list[dict[str, Any]] = []

    for page_index, page in enumerate(doc, start=1):
        image, scale_x, scale_y = render_page(
            page,
            dpi=args.dpi,
            portrait_max=(args.portrait_width, args.portrait_height),
            landscape_max=(args.landscape_width, args.landscape_height),
        )

        image_name = f"page{page_index}.avif"
        save_avif(image, images_dir / image_name, quality=args.avif_quality)

        words = choose_words(page, image, scale_x, scale_y, force_ocr=args.force_ocr, psm=args.psm)
        words.sort(key=lambda word: (word.y, word.x))

        lines = line_groups(words)
        line_objects = detect_linear_objects(image)
        regions = detect_empty_regions(image.width, image.height, words, lines)
        painted_regions = select_painted_regions(image.width, image.height, regions)
        blocks = detect_blocks(lines, image.width, painted_regions)
        markers = detect_markers(lines)

        encoded_words, word_meta = encode_delta_words(words, dictionary)

        # Fill line word indexes after dictionary/page-local order is stable.
        line_payload = []
        for line in lines:
            local_indexes = [
                idx for idx, word in enumerate(words)
                if word.x >= line["x"] and word.right <= line["x"] + line["w"] and
                word.y >= line["y"] - 2 and word.bottom <= line["y"] + line["h"] + 2
            ]
            item = dict(line)
            item["wordIndexes"] = local_indexes
            line_payload.append(item)

        sentences = build_sentences(words, line_payload, blocks, markers, image.width)

        pages_payload.append(
            {
                "w": image.width,
                "h": image.height,
                "img": f"images/{image_name}",
                "words": encoded_words,
                "wordMeta": word_meta,
                "lines": line_payload,
                "lineObjects": line_objects,
                "regions": regions,
                "paintedRegions": painted_regions,
                "blocks": blocks,
                "markers": markers,
                "sentences": sentences,
                "meta": {
                    "sourcePdfPage": page_index,
                    "ocrPsm": args.psm,
                    "dpi": args.dpi,
                    "avifQuality": args.avif_quality,
                    "scaleX": scale_x,
                    "scaleY": scale_y,
                },
            }
        )

        print(f"page {page_index}/{len(doc)}: {len(words)} words, {len(lines)} lines, {len(regions)} regions")

    payload = {
        "v": 1,
        "format": "word-delta",
        "dict": {"words": [word for word, _ in sorted(dictionary.items(), key=lambda item: item[1])]},
        "pages": pages_payload,
    }

    write_json_and_br(data_dir / "pages.delta.json", payload)
    write_json_and_br(data_dir / "pages.word_select.delta.json", payload)

    # Empty locale placeholders keep README paths valid and are safe to replace by real translations.
    empty_locale = [[] for _ in pages_payload]
    write_json_and_br(locales_dir / "ru.json", empty_locale)
    write_json_and_br(locales_dir / "en.json", empty_locale)

    copy_viewer_assets(out_dir)

    total = total_output_size(out_dir)
    print(f"Total output size: {total} bytes ({total / 1024 / 1024:.2f} MiB)")
    print(f"Open: {out_dir / 'index.html'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert PDF to accessible HTML bundle.")
    parser.add_argument("input_pdf", help="Path to input PDF")
    parser.add_argument("--out", default="project", help="Output directory")
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--avif-quality", type=int, default=85)
    parser.add_argument("--psm", type=int, default=11, help="Tesseract page segmentation mode for OCR fallback")
    parser.add_argument("--force-ocr", action="store_true", help="Use OCR even when PDF has a native text layer")
    parser.add_argument("--portrait-width", type=int, default=1080)
    parser.add_argument("--portrait-height", type=int, default=1920)
    parser.add_argument("--landscape-width", type=int, default=1920)
    parser.add_argument("--landscape-height", type=int, default=1080)
    return parser.parse_args()


if __name__ == "__main__":
    process_pdf(parse_args())
