"""
V24: original AVIF page images + selectable word boxes + structural overlays.

Based on v16, but:
  - removed char boxes and image_to_boxes
  - image_to_data word boxes retain OCR structural identifiers
  - OpenCV detects lines, whitespace regions, text blocks, and list markers
  - word boxes contain actual text for browser selection/copy
  - OCR still runs on preprocessed image
  - saved AVIF is original unfiltered PDF render
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import os
from pathlib import Path
import shutil
from typing import Any

import brotli
import cv2
import fitz
import numpy as np
from PIL import Image, ImageEnhance
import pillow_avif  # noqa: F401 - registers AVIF support in Pillow
import pytesseract
import zstandard

HAS_AVIF = True
HAS_ZSTD = True


# ------------------- defaults -------------------
INPUT_PDF = Path(os.getenv("INPUT_PDF", "input1.pdf"))
if not INPUT_PDF.exists() and not os.getenv("INPUT_PDF"):
    INPUT_PDF = Path("input.pdf")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

OCR_LANG = os.getenv("OCR_LANG", "rus+eng")
OCR_DPI = int(os.getenv("OCR_DPI", "300"))
OCR_PSM = int(os.getenv("OCR_PSM", "11"))
OCR_MIN_CONF = float(os.getenv("OCR_MIN_CONF", "0"))
QUALITY_AVIF = int(os.getenv("QUALITY_AVIF", "65"))

# preprocessing for OCR only
PREPROCESS_CONTRAST = float(os.getenv("PREPROCESS_CONTRAST", "1.8"))
PREPROCESS_SHARPEN = float(os.getenv("PREPROCESS_SHARPEN", "1.2"))
PREPROCESS_MEDIAN = int(os.getenv("PREPROCESS_MEDIAN", "3"))
THRESHOLD_MODE = os.getenv("THRESHOLD_MODE", "otsu").strip().lower()  # otsu | adaptive
MORPH_OPEN = int(os.getenv("MORPH_OPEN", "1"))
MORPH_CLOSE = int(os.getenv("MORPH_CLOSE", "1"))

# box refinement
REFINE_PAD = int(os.getenv("REFINE_PAD", "2"))
ROW_INK_FRAC = float(os.getenv("ROW_INK_FRAC", "0.08"))
COL_INK_FRAC = float(os.getenv("COL_INK_FRAC", "0.04"))
MIN_ROW_PIXELS = int(os.getenv("MIN_ROW_PIXELS", "2"))
MIN_COL_PIXELS = int(os.getenv("MIN_COL_PIXELS", "2"))
REFINE_WORDS = os.getenv("REFINE_WORDS", "1") != "0"

MAX_PAGES = int(os.getenv("MAX_PAGES", "0"))
MAX_STRUCTURAL_REGIONS = int(os.getenv("MAX_STRUCTURAL_REGIONS", "10"))
ZSTD_LEVEL = int(os.getenv("ZSTD_LEVEL", "19"))

DATA_DIR = Path("data")
IMG_DIR = DATA_DIR / "images"
LOCALES_DIR = DATA_DIR / "locales"
PAGES_DIR = DATA_DIR / "pages"
DIAGRAM_DIR = DATA_DIR / "diagram"
DEBUG_DIR = DATA_DIR / "debug"


# ------------------- IO helpers -------------------
def clean_output_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    LOCALES_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    DIAGRAM_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    cleanup = [
        DATA_DIR / "pages.word_select_v24.readable.json",
        DATA_DIR / "pages.word_select_v24.abs.json",
        DATA_DIR / "pages.word_select_v24.abs.json.gz",
        DATA_DIR / "pages.word_select_v24.abs.json.zst",
        DATA_DIR / "pages.word_select_v24.delta.json",
        DATA_DIR / "pages.word_select_v24.delta.json.gz",
        DATA_DIR / "pages.word_select_v24.delta.json.zst",
        DATA_DIR / "manifest.word_select_v24.json",
        LOCALES_DIR / "words_v24.json",
        LOCALES_DIR / "en.json",
        LOCALES_DIR / "en.json.br",
        LOCALES_DIR / "ru.json",
        LOCALES_DIR / "ru.json.br",
        PAGES_DIR / "pages.json",
        PAGES_DIR / "pages.json.br",
    ]
    for path in cleanup:
        path.unlink(missing_ok=True)

    # Refresh page images aggressively; stale AVIFs make quality tests misleading.
    for path in IMG_DIR.glob("page*.avif"):
        path.unlink(missing_ok=True)
    for path in IMG_DIR.glob("page*.png"):
        path.unlink(missing_ok=True)
    for path in IMG_DIR.glob("page*.webp"):
        path.unlink(missing_ok=True)
    for path in IMG_DIR.glob("page*.jpg"):
        path.unlink(missing_ok=True)
    for path in DEBUG_DIR.glob("page*_ocr_mask.png"):
        path.unlink(missing_ok=True)


def write_json(path: Path, data: Any, *, pretty: bool = False) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        data,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )
    path.write_text(text, encoding="utf-8")
    return path.stat().st_size


def gzip_file(path: Path) -> int:
    out = path.with_suffix(path.suffix + ".gz")
    with path.open("rb") as src, gzip.open(out, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    return out.stat().st_size


def zstd_file(path: Path) -> int:
    if not HAS_ZSTD:
        return 0
    out = path.with_suffix(path.suffix + ".zst")
    cctx = zstandard.ZstdCompressor(level=ZSTD_LEVEL)
    out.write_bytes(cctx.compress(path.read_bytes()))
    return out.stat().st_size


def brotli_file(path: Path) -> int:
    """Write a browser-decodable Brotli copy using the project-required quality."""
    out = path.with_suffix(path.suffix + ".br")
    out.write_bytes(brotli.compress(path.read_bytes(), quality=11))
    return out.stat().st_size


def dir_size(path: Path, patterns: tuple[str, ...]) -> int:
    total = 0
    for pattern in patterns:
        total += sum(file.stat().st_size for file in path.glob(pattern) if file.is_file())
    return total


# ------------------- OCR + render helpers -------------------
def configure_tesseract() -> None:
    if TESSERACT_CMD:
        candidate = Path(TESSERACT_CMD)
        if candidate.exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
        else:
            print(f"Предупреждение: TESSERACT_CMD не найден: {candidate}")


def render_pdf_page(page, dpi: int):
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def save_page_image_avif_exact(image, page_no: int) -> str:
    name = f"page{page_no}.avif" if HAS_AVIF else f"page{page_no}.png"
    path = IMG_DIR / name
    if HAS_AVIF:
        try:
            image.save(path, quality=QUALITY_AVIF, speed=6)
        except TypeError:
            image.save(path, quality=QUALITY_AVIF)
    else:
        image.save(path, optimize=True)
    return f"images/{name}"


def preprocess_for_ocr(image):
    """Return preprocessed PIL image for Tesseract and binary foreground mask."""
    gray = image.convert("L")
    if PREPROCESS_CONTRAST != 1.0:
        gray = ImageEnhance.Contrast(gray).enhance(PREPROCESS_CONTRAST)
    if PREPROCESS_SHARPEN != 1.0:
        gray = ImageEnhance.Sharpness(gray).enhance(PREPROCESS_SHARPEN)

    arr = np.array(gray)

    if PREPROCESS_MEDIAN and PREPROCESS_MEDIAN >= 3 and PREPROCESS_MEDIAN % 2 == 1:
        arr = cv2.medianBlur(arr, PREPROCESS_MEDIAN)

    if THRESHOLD_MODE == "adaptive":
        bw = cv2.adaptiveThreshold(
            arr, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31, 15
        )
    else:
        _thr, bw = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    if MORPH_OPEN > 0:
        kernel = np.ones((MORPH_OPEN, MORPH_OPEN), np.uint8)
        bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel)
    if MORPH_CLOSE > 0:
        kernel = np.ones((MORPH_CLOSE, MORPH_CLOSE), np.uint8)
        bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel)

    ocr_arr = np.where(bw > 0, 0, 255).astype(np.uint8)
    return Image.fromarray(ocr_arr, mode="L"), bw


def refine_box_by_mask(mask_fg: Any, x: int, y: int, w: int, h: int, pad: int = REFINE_PAD):
    H, W = mask_fg.shape[:2]
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(W, x + w + pad)
    y1 = min(H, y + h + pad)
    if x1 <= x0 or y1 <= y0:
        return x, y, w, h

    crop = mask_fg[y0:y1, x0:x1]
    if crop.size == 0:
        return x, y, w, h

    row_sums = (crop > 0).sum(axis=1)
    col_sums = (crop > 0).sum(axis=0)

    row_thr = max(MIN_ROW_PIXELS, int(round(crop.shape[1] * ROW_INK_FRAC)))
    col_thr = max(MIN_COL_PIXELS, int(round(crop.shape[0] * COL_INK_FRAC)))

    valid_rows = np.where(row_sums >= row_thr)[0]
    valid_cols = np.where(col_sums >= col_thr)[0]

    if len(valid_rows) == 0:
        valid_rows = np.where(row_sums > 0)[0]
    if len(valid_cols) == 0:
        valid_cols = np.where(col_sums > 0)[0]

    if len(valid_rows) == 0 or len(valid_cols) == 0:
        return x, y, w, h

    new_y0 = y0 + int(valid_rows[0])
    new_y1 = y0 + int(valid_rows[-1]) + 1
    new_x0 = x0 + int(valid_cols[0])
    new_x1 = x0 + int(valid_cols[-1]) + 1

    new_w = max(1, new_x1 - new_x0)
    new_h = max(1, new_y1 - new_y0)

    if new_w < max(1, int(w * 0.2)) or new_h < max(1, int(h * 0.2)):
        return x, y, w, h

    return int(new_x0), int(new_y0), int(new_w), int(new_h)


def _boxes_from_mask(mask: Any, min_w: int, min_h: int) -> list[list[int]]:
    contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= min_w and h >= min_h:
            boxes.append([int(x), int(y), int(w), int(h)])
    return boxes


def detect_linear_objects(mask_fg: Any) -> list[list[int]]:
    """Detect long horizontal and vertical objects without changing the OCR mask."""
    height, width = mask_fg.shape[:2]
    lines: list[list[int]] = []
    for kernel, min_w, min_h in (
        (cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, width // 30), 1)), max(20, width // 25), 1),
        (cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, height // 30))), 1, max(20, height // 25)),
    ):
        opened = cv2.morphologyEx(mask_fg, cv2.MORPH_OPEN, kernel)
        lines.extend(_boxes_from_mask(opened, min_w, min_h))
    return sorted({tuple(box) for box in lines}, key=lambda box: (box[1], box[0]))


def _empty_runs(values: Any) -> list[tuple[int, int]]:
    runs = []
    start = None
    for index, value in enumerate(values):
        if value == 0 and start is None:
            start = index
        elif value != 0 and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(values)))
    return runs


def find_structural_regions(width: int, height: int, words: list[dict[str, Any]], lines: list[list[int]]) -> tuple[list[dict[str, Any]], float]:
    """Recursively find whitespace cuts, then rank them independently by thickness."""
    occupied = np.zeros((height, width), dtype=np.uint8)
    for item in [*[ [word["x"], word["y"], word["w"], word["h"]] for word in words], *lines]:
        x, y, w, h = item
        occupied[max(0, y):min(height, y + h), max(0, x):min(width, x + w)] = 1

    line_centers: dict[tuple[int, int, int], list[float]] = {}
    for word in words:
        line_centers.setdefault((word["b"], word["p"], word["l"]), []).append(word["y"] + word["h"] / 2)
    centers = sorted(float(np.median(items)) for items in line_centers.values())
    intervals = [b - a for a, b in zip(centers, centers[1:]) if b > a]
    average_interval = float(np.median(intervals)) if intervals else float(np.median([word["h"] for word in words]) if words else 1)
    minimum_power = max(2, int(round(average_interval * 1.1)))
    candidates: list[dict[str, Any]] = []

    def split(x: int, y: int, w: int, h: int, depth: int = 0) -> None:
        if depth >= 20 or w < minimum_power * 2 or h < minimum_power * 2:
            return
        crop = occupied[y:y + h, x:x + w]
        choices = []
        for start, end in _empty_runs(crop.max(axis=1)):
            if end - start >= minimum_power:
                choices.append((end - start, "h", x, y + start, w, end - start))
        for start, end in _empty_runs(crop.max(axis=0)):
            if end - start >= minimum_power:
                choices.append((end - start, "v", x + start, y, end - start, h))
        if not choices:
            return
        power, orientation, rx, ry, rw, rh = max(choices, key=lambda item: item[0])
        candidates.append({"x": rx, "y": ry, "w": rw, "h": rh, "power": power, "orientation": orientation})
        if orientation == "h":
            split(x, y, w, ry - y, depth + 1)
            split(x, ry + rh, w, y + h - ry - rh, depth + 1)
        else:
            split(x, y, rx - x, h, depth + 1)
            split(rx + rw, y, x + w - rx - rw, h, depth + 1)

    split(0, 0, width, height)
    unique = {(item["x"], item["y"], item["w"], item["h"]): item for item in candidates}
    ranked = sorted(unique.values(), key=lambda item: (-item["power"], item["y"], item["x"]))[:MAX_STRUCTURAL_REGIONS]
    centers = [item["x"] + item["w"] / 2 for item in ranked if item["orientation"] == "v"]
    has_left_column_cut = any(width * 0.30 <= center <= width * 0.35 for center in centers)
    has_right_column_cut = any(width * 0.60 <= center <= width * 0.70 for center in centers)
    for rank, item in enumerate(ranked, 1):
        item["rank"] = rank
        center_x = item["x"] + item["w"] / 2
        is_full_width = item["orientation"] == "h" and item["w"] >= width * 0.9
        is_center_cut = item["orientation"] == "v" and width * 0.475 <= center_x <= width * 0.525
        is_column_pair = item["orientation"] == "v" and has_left_column_cut and has_right_column_cut and (
            width * 0.30 <= center_x <= width * 0.35 or width * 0.60 <= center_x <= width * 0.70
        )
        item["highlighted"] = is_full_width or is_center_cut or is_column_pair

    highlighted_vertical = [item for item in ranked if item["highlighted"] and item["orientation"] == "v"]
    for item in ranked:
        if item["orientation"] != "h" or item["highlighted"]:
            continue
        x0, x1 = item["x"], item["x"] + item["w"]
        item["highlighted"] = any(
            (x0 <= 1 and abs(x1 - cut["x"]) <= minimum_power)
            or (x1 >= width - 1 and abs(x0 - (cut["x"] + cut["w"])) <= minimum_power)
            for cut in highlighted_vertical
        )
    return ranked, round(average_interval, 2)


def find_text_blocks(words: list[dict[str, Any]], regions: list[dict[str, Any]], page_width: int) -> list[list[int]]:
    vertical = sorted(item["x"] + item["w"] // 2 for item in regions if item["highlighted"] and item["orientation"] == "v")
    horizontal = sorted(item["y"] + item["h"] // 2 for item in regions if item["highlighted"] and item["orientation"] == "h")
    groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for word in words:
        cx, cy = word["x"] + word["w"] / 2, word["y"] + word["h"] / 2
        key = (sum(cx > cut for cut in vertical), sum(cy > cut for cut in horizontal))
        groups.setdefault(key, []).append(word)
    blocks = []
    for group in groups.values():
        x0, y0 = min(w["x"] for w in group), min(w["y"] for w in group)
        x1, y1 = max(w["x"] + w["w"] for w in group), max(w["y"] + w["h"] for w in group)
        blocks.append([x0, y0, x1 - x0, y1 - y0])
    return sorted(blocks, key=lambda box: (box[0] >= page_width / 2, box[1], box[0]))


def find_list_markers(mask_fg: Any, words: list[dict[str, Any]]) -> list[list[int]]:
    """Find small foreground components immediately left of OCR line starts."""
    leftmost: dict[tuple[int, int, int], dict[str, Any]] = {}
    for word in words:
        key = (word["b"], word["p"], word["l"])
        if key not in leftmost or word["x"] < leftmost[key]["x"]:
            leftmost[key] = word

    contours, _hierarchy = cv2.findContours(mask_fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    components = [cv2.boundingRect(contour) for contour in contours]
    markers = set()
    for word in leftmost.values():
        line_height = max(1, word["h"])
        for x, y, w, h in components:
            gap = word["x"] - x - w
            aligned = abs((y + h / 2) - (word["y"] + line_height / 2)) <= line_height
            if 0 <= gap <= line_height * 2 and aligned and 1 <= w <= line_height * 2 and 1 <= h <= line_height * 2:
                markers.add((int(x), int(y), int(w), int(h)))
    return [list(box) for box in sorted(markers, key=lambda box: (box[1], box[0]))]


def analyze_page_content(mask_fg: Any, words: list[dict[str, Any]]) -> dict[str, Any]:
    height, width = mask_fg.shape[:2]
    lines = detect_linear_objects(mask_fg)
    regions, average_interval = find_structural_regions(width, height, words, lines)
    return {
        "averageLineInterval": average_interval,
        "lines": lines,
        "regions": regions,
        "blocks": find_text_blocks(words, regions, width),
        "markers": find_list_markers(mask_fg, words),
    }


def ocr_words_image_to_data(ocr_image, mask_fg):
    config = f"--psm {OCR_PSM}"
    raw = pytesseract.image_to_data(
        ocr_image,
        lang=OCR_LANG,
        config=config,
        output_type=pytesseract.Output.STRING,
    )

    words: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(raw), delimiter="\t")
    for row in reader:
        if not row:
            continue

        text = (row.get("text") or "").strip()
        if not text:
            continue

        try:
            conf = float(row.get("conf", "-1") or -1)
        except ValueError:
            conf = -1.0

        if conf >= 0 and conf < OCR_MIN_CONF:
            continue

        try:
            left = int(float(row.get("left", "0") or 0))
            top = int(float(row.get("top", "0") or 0))
            width = int(float(row.get("width", "0") or 0))
            height = int(float(row.get("height", "0") or 0))
        except ValueError:
            continue

        if width <= 0 or height <= 0:
            continue

        if REFINE_WORDS:
            left, top, width, height = refine_box_by_mask(mask_fg, left, top, width, height)

        def int_field(name: str) -> int:
            try:
                return int(float(row.get(name, "0") or 0))
            except ValueError:
                return 0

        words.append({
            "t": text,
            "x": left,
            "y": top,
            "w": width,
            "h": height,
            "c": round(conf, 2),
            "b": int_field("block_num"),
            "p": int_field("par_num"),
            "l": int_field("line_num"),
            "n": int_field("word_num"),
        })

    # Preserve OCR reading order first. Sorting by y/x breaks words in one line when
    # their top coordinates differ slightly, e.g. "of" y=1196 before
    # "Depressurisation" y=1199 even if it is visually to the right.
    words.sort(key=lambda item: (item["b"], item["p"], item["l"], item["n"], item["y"], item["x"]))
    return words


# ------------------- compact encodings -------------------
def build_dictionary(values: set[str]) -> tuple[list[str], dict[str, int]]:
    ordered = sorted(values)
    return ordered, {value: index for index, value in enumerate(ordered)}


def readable_pages_json(pages_meta: list[dict[str, Any]], pages_words: list[list[dict[str, Any]]]):
    pages = []
    for meta, words in zip(pages_meta, pages_words, strict=True):
        pages.append({
            "width": meta["w"],
            "height": meta["h"],
            "image": meta["img"],
            "words": words,
        })
    return {"v": 24, "mode": "readable", "pages": pages}


def absolute_encoding(pages_meta: list[dict[str, Any]], pages_words: list[list[dict[str, Any]]], word_to_idx: dict[str, int]):
    pages = []
    for meta, words in zip(pages_meta, pages_words, strict=True):
        pages.append({
            "w": meta["w"],
            "h": meta["h"],
            "img": meta["img"],
            "words": [[word_to_idx[w["t"]], w["x"], w["y"], w["w"], w["h"], w["c"]] for w in words],
        })
    return {"v": 24, "mode": "abs", "d": {"words": list(word_to_idx.keys())}, "p": pages}


def delta_encoding(pages_meta: list[dict[str, Any]], pages_words: list[list[dict[str, Any]]], word_to_idx: dict[str, int]):
    pages = []
    for meta, words in zip(pages_meta, pages_words, strict=True):
        encoded = []
        prev_x = 0
        prev_y = 0
        for w in words:
            dx = w["x"] - prev_x
            dy = w["y"] - prev_y
            encoded.append([word_to_idx[w["t"]], dx, dy, w["w"], w["h"], w["c"]])
            prev_x = w["x"]
            prev_y = w["y"]
        pages.append({"w": meta["w"], "h": meta["h"], "img": meta["img"], "words": encoded})
    return {"v": 24, "mode": "delta", "d": {"words": list(word_to_idx.keys())}, "p": pages}


# ------------------- main -------------------

def positional_encoding(pages_meta: list[dict[str, Any]], pages_words: list[list[dict[str, Any]]], pages_analysis: list[dict[str, Any]], word_to_idx: dict[str, int]):
    """Encode page structure and formatting as positional arrays."""
    pages = []
    for meta, words, analysis in zip(pages_meta, pages_words, pages_analysis, strict=True):
        encoded = []
        prev_x = 0
        prev_y = 0
        for word in words:
            encoded.append([word_to_idx[word["t"]], word["x"] - prev_x, word["y"] - prev_y, word["w"], word["h"], word["c"], word["b"], word["p"], word["l"], word["n"]])
            prev_x = word["x"]
            prev_y = word["y"]
        pages.append([meta["w"], meta["h"], meta["img"], encoded, analysis])
    return [24, pages]

def main() -> None:
    configure_tesseract()
    clean_output_dirs()

    if not INPUT_PDF.exists():
        raise FileNotFoundError(f"Не найден PDF: {INPUT_PDF.resolve()}")

    print(f"Tesseract: {pytesseract.pytesseract.tesseract_cmd}")
    print(f"PDF: {INPUT_PDF}")
    print("V24: selectable word boxes + content analysis, single OCR pass psm=11")
    print("OCR on preprocessed image; saved AVIF uses original page render")
    print(f"OCR_DPI={OCR_DPI}, QUALITY_AVIF={QUALITY_AVIF}, OCR_LANG={OCR_LANG}, psm={OCR_PSM}")
    print(f"Preprocess: contrast={PREPROCESS_CONTRAST}, sharpen={PREPROCESS_SHARPEN}, median={PREPROCESS_MEDIAN}, threshold={THRESHOLD_MODE}, open={MORPH_OPEN}, close={MORPH_CLOSE}")
    print(f"Refine word boxes: {int(REFINE_WORDS)}, pad={REFINE_PAD}, row_frac={ROW_INK_FRAC}, col_frac={COL_INK_FRAC}")

    doc = fitz.open(INPUT_PDF)
    total_pages = len(doc) if MAX_PAGES <= 0 else min(MAX_PAGES, len(doc))
    print(f"Страниц к обработке: {total_pages}")

    pages_meta: list[dict[str, Any]] = []
    pages_words: list[list[dict[str, Any]]] = []
    pages_analysis: list[dict[str, Any]] = []

    total_words = 0

    for page_index in range(total_pages):
        page_no = page_index + 1
        page = doc.load_page(page_index)

        orig_img = render_pdf_page(page, OCR_DPI)
        pre_img, mask_fg = preprocess_for_ocr(orig_img)

        img_src = save_page_image_avif_exact(orig_img, page_no)
        words = ocr_words_image_to_data(pre_img, mask_fg)
        analysis = analyze_page_content(mask_fg, words)

        pages_meta.append({"w": orig_img.width, "h": orig_img.height, "img": img_src})
        pages_words.append(words)
        pages_analysis.append(analysis)

        total_words += len(words)

        Image.fromarray(mask_fg).save(DEBUG_DIR / f"page{page_no}_ocr_mask.png")
        print(f"  page {page_no:>4}: {orig_img.width}x{orig_img.height}, words={len(words)}, lines={len(analysis['lines'])}, regions={len(analysis['regions'])}, blocks={len(analysis['blocks'])}, markers={len(analysis['markers'])}")

    doc.close()

    word_dict, word_to_idx = build_dictionary({w["t"] for words in pages_words for w in words})

    variants = {
        "pages.word_select_v24.readable.json": readable_pages_json(pages_meta, pages_words),
        "pages.word_select_v24.abs.json": absolute_encoding(pages_meta, pages_words, word_to_idx),
        "pages.word_select_v24.delta.json": delta_encoding(pages_meta, pages_words, word_to_idx),
    }

    sizes: dict[str, dict[str, int]] = {}
    for filename, data in variants.items():
        path = DATA_DIR / filename
        raw = write_json(path, data, pretty=filename.endswith("readable.json"))
        gz = gzip_file(path)
        zst = zstd_file(path)
        sizes[filename] = {"raw": raw, "gz": gz, "zst": zst}

    write_json(LOCALES_DIR / "words_v24.json", [" ".join(w["t"] for w in words) for words in pages_words], pretty=True)

    # Canonical viewer data follows README: positional arrays in dedicated folders,
    # compressed with Brotli quality 11. Translation may replace ru.json independently.
    pages_path = PAGES_DIR / "pages.json"
    write_json(pages_path, positional_encoding(pages_meta, pages_words, pages_analysis, word_to_idx))
    brotli_file(pages_path)
    for language in ("en", "ru"):
        locale_path = LOCALES_DIR / f"{language}.json"
        write_json(locale_path, [word_dict])
        brotli_file(locale_path)

    manifest = {
        "v": 24,
        "mode": "original_avif_plus_selectable_words_and_content_analysis",
        "input_pdf": str(INPUT_PDF),
        "pages": total_pages,
        "ocr_dpi": OCR_DPI,
        "saved_image_resolution": "same_as_ocr_render_original",
        "quality_avif": QUALITY_AVIF,
        "asset_format": "avif" if HAS_AVIF else "png",
        "preprocess": {
            "contrast": PREPROCESS_CONTRAST,
            "sharpen": PREPROCESS_SHARPEN,
            "median": PREPROCESS_MEDIAN,
            "threshold_mode": THRESHOLD_MODE,
            "morph_open": MORPH_OPEN,
            "morph_close": MORPH_CLOSE,
        },
        "refine": {
            "words": REFINE_WORDS,
            "pad": REFINE_PAD,
            "row_ink_frac": ROW_INK_FRAC,
            "col_ink_frac": COL_INK_FRAC,
            "min_row_pixels": MIN_ROW_PIXELS,
            "min_col_pixels": MIN_COL_PIXELS,
        },
        "content_analysis": {"max_structural_regions": MAX_STRUCTURAL_REGIONS},
        "total_words": total_words,
        "unique_words": len(word_dict),
        "sizes": sizes,
    }
    write_json(DATA_DIR / "manifest.word_select_v24.json", manifest, pretty=True)

    image_size = dir_size(IMG_DIR, ("page*.avif", "page*.png"))
    debug_size = dir_size(DEBUG_DIR, ("page*_ocr_mask.png",))

    print()
    print("=" * 92)
    print("V24 selectable word boxes, psm=11 завершён")
    print("-" * 92)
    print(f"Страниц:             {total_pages}")
    print(f"Всего слов:          {total_words:,}")
    print(f"Уникальных слов:     {len(word_dict):,}")
    avg_image = image_size / max(1, total_pages)
    print(f"Page images:         {image_size:>10,} байт (~{image_size / 1024:.1f} КБ), avg={avg_image:,.0f} байт/page, AVIF quality={QUALITY_AVIF}")
    print(f"Debug masks:         {debug_size:>10,} байт (~{debug_size / 1024:.1f} КБ)")
    print()
    print("Сравнение хранения word layer:")
    for filename, item in sizes.items():
        total_zst_assets = item["zst"] + image_size
        print(f"  {filename:<33} raw={item['raw']:>10,} gz={item['gz']:>9,} zst={item['zst']:>9,}  +images={total_zst_assets:>10,}")

    abs_zst = sizes["pages.word_select_v24.abs.json"]["zst"]
    delta_zst = sizes["pages.word_select_v24.delta.json"]["zst"]
    print()
    print("Эффект относительного хранения после zstd:")
    if abs_zst:
        print(f"  delta vs abs       : {abs_zst - delta_zst:>9,} байт ({(abs_zst - delta_zst) / abs_zst * 100:.2f}%)")
    print("=" * 92)
    print()
    print("Локальный сервер:")
    print("  py -m http.server 8000")
    print("Открыть:")
    print("  http://localhost:8000/index_word_select_v24.html")


if __name__ == "__main__":
    main()
