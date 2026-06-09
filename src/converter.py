"""Преобразование PDF-страниц в компактные данные HTML-просмотрщика."""

import json
import shutil
from io import BytesIO
from pathlib import Path

import brotli
import pymupdf
from PIL import Image


def write_brotli_json(data, destination: Path) -> None:
    """Записать компактный JSON с максимальным сжатием Brotli."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    destination.write_bytes(brotli.compress(payload, quality=11))


def rounded(value: float) -> float:
    """Ограничить точность координат без заметной потери в браузере."""
    return round(value, 3)


def convert_pdf(source: Path, data_dir: Path) -> int:
    """Пересоздать производные данные просмотрщика из PDF."""
    if not source.is_file():
        raise FileNotFoundError(f"Исходный PDF не найден: {source}")

    if data_dir.exists():
        shutil.rmtree(data_dir)
    pages_dir = data_dir / "pages"
    locales_dir = data_dir / "locales"
    diagrams_dir = data_dir / "diagram"
    images_dir = data_dir / "images"
    for directory in (pages_dir, locales_dir, diagrams_dir, images_dir):
        directory.mkdir(parents=True)

    pages = []
    texts = []
    with pymupdf.open(source) as document:
        for page_number, page in enumerate(document, start=1):
            print(f"Преобразование страницы {page_number} из {document.page_count}...")
            page_data = page.get_text("dict")
            text_styles = []
            page_texts = []
            illustrations = []

            for block_number, block in enumerate(page_data["blocks"], start=1):
                if block["type"] == 0:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            x0, y0, x1, y1 = span["bbox"]
                            page_texts.append(span["text"])
                            text_styles.append([
                                rounded(x0), rounded(y0), rounded(x1 - x0), rounded(y1 - y0),
                                span["font"], rounded(span["size"]), span["color"], span["flags"],
                            ])
                elif block["type"] == 1:
                    image_path = images_dir / f"page-{page_number}-image-{block_number}.avif"
                    with Image.open(BytesIO(block["image"])) as image:
                        image.convert("RGB").save(image_path, "AVIF", quality=65)
                    x0, y0, x1, y1 = block["bbox"]
                    illustrations.append([
                        image_path.relative_to(data_dir).as_posix(),
                        rounded(x0), rounded(y0), rounded(x1 - x0), rounded(y1 - y0),
                    ])

            pages.append([rounded(page.rect.width), rounded(page.rect.height), text_styles, illustrations])
            texts.append(page_texts)

    # JSON хранит позиционные массивы: [version, pages] и [version, locale, texts].
    write_brotli_json([2, pages], pages_dir / "index.json.br")
    write_brotli_json([2, "source", texts], locales_dir / "source.json.br")
    return len(pages)
