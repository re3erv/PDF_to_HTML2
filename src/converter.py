"""Преобразование PDF-страниц в компактные данные HTML-просмотрщика."""

import json
import shutil
from pathlib import Path

import brotli
import pymupdf
from PIL import Image


def write_brotli_json(data, destination: Path) -> None:
    """Записать компактный JSON с максимальным сжатием Brotli."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    destination.write_bytes(brotli.compress(payload, quality=11))


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
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            image_path = images_dir / f"page-{page_number}.avif"
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            image.save(image_path, "AVIF", quality=65)

            pages.append({
                "image": image_path.relative_to(data_dir).as_posix(),
                "width": pixmap.width,
                "height": pixmap.height,
            })
            texts.append(page.get_text("text"))

    write_brotli_json({"version": 1, "pages": pages}, pages_dir / "index.json.br")
    write_brotli_json({"version": 1, "locale": "source", "pages": texts}, locales_dir / "source.json.br")
    return len(pages)
