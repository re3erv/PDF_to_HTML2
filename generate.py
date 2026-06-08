import json
import os
import random
import shutil
from pathlib import Path

import brotli
import pillow_avif  # noqa: F401 — регистрирует поддержку AVIF в Pillow
from PIL import Image, ImageDraw

# ------------------- НАСТРОЙКИ -------------------
NUM_PAGES = 50
WORDS_PER_PAGE = 200         # количество текстовых элементов на страницу
FONTS = ["Times New Roman", "Arial", "Courier New", "Verdana"]
SIZES = [10, 11, 12, 14]
COLORS = ["#000000", "#333333", "#555555"]
QUALITY_AVIF = 85            # качество картинок (0–100)

# Папки (относительно места запуска)
DATA_DIR = Path("data")
IMAGES_DIR = DATA_DIR / "images"
LOCALES_DIR = Path("locales")

# ------------------- ГЕНЕРАЦИЯ ДАННЫХ -------------------
random.seed(42)

print(f"Генерация {NUM_PAGES} страниц, {WORDS_PER_PAGE} слов на страницу...")

# 1. Переводы (ru, en) — массив массивов строк
ru_translations = []
en_translations = []

RU_WORDS = ["привет", "мир", "дом", "книга", "река", "ночь", "день",
            "звезда", "мечта", "огонь", "вода", "земля", "небо", "птица"]
EN_WORDS = ["hello", "world", "house", "book", "river", "night", "day",
            "star", "dream", "fire", "water", "earth", "sky", "bird"]

for _ in range(NUM_PAGES):
    ru_page = [random.choice(RU_WORDS) for _ in range(WORDS_PER_PAGE)]
    en_page = [random.choice(EN_WORDS) for _ in range(WORDS_PER_PAGE)]
    ru_translations.append(ru_page)
    en_translations.append(en_page)

# 2. Структура страниц (pages.json)
pages = []
for page_idx in range(NUM_PAGES):
    elements = []
    # Текстовые элементы
    for word_idx in range(WORDS_PER_PAGE):
        font = random.choice(FONTS)
        size = random.choice(SIZES)
        bold = random.choice([True, False])
        italic = random.choice([True, False]) if random.random() < 0.2 else False
        color = random.choice(COLORS)
        col = word_idx % 15
        row = word_idx // 15
        x = 100 + col * 80
        y = 100 + row * 25
        w = random.randint(30, 70)
        h = size + 2
        elements.append({
            "type": "text",
            "textIdx": word_idx,
            "font": font,
            "size": size,
            "bold": bold,
            "italic": italic,
            "color": color,
            "x": x,
            "y": y,
            "w": w,
            "h": h
        })
    # Изображение (одно на страницу)
    img_name = f"page{page_idx+1}_img1.avif"
    elements.append({
        "type": "image",
        "src": f"images/{img_name}",
        "x": 300,
        "y": 600,
        "w": 200,
        "h": 150
    })
    # SVG-схема
    svg_string = (
        f'<svg width="100" height="100"><circle cx="50" cy="50" r="40" fill="#ccf"/>'
        f'<text x="50" y="55" text-anchor="middle" font-size="12">P{page_idx+1}</text></svg>'
    )
    elements.append({
        "type": "svg",
        "svg": svg_string,
        "x": 550,
        "y": 600,
        "w": 100,
        "h": 100
    })
    pages.append({
        "width": 1240,
        "height": 1754,
        "elements": elements
    })

# ------------------- КОМПАКТНЫЙ LOSSLESS-ФОРМАТ -------------------
# Корень: [version, fonts, colors, sources, svgs, styles, pageSizes, pages]
# Стиль: [fontIdx, size, flags, colorIdx], flags: bit 0 = bold, bit 1 = italic
# Размер страницы: [width, height]; страница: [pageSizeIdx, elements]
# Элементы сохраняют исходный порядок:
#   text  = [0, textIdx, styleIdx, x, y, w, h]
#   image = [1, srcIdx, x, y, w, h]
#   svg   = [2, svgIdx, x, y, w, h]

def intern(value, values, indexes):
    if value not in indexes:
        indexes[value] = len(values)
        values.append(value)
    return indexes[value]


def compact_pages(source_pages):
    fonts, font_indexes = [], {}
    colors, color_indexes = [], {}
    sources, source_indexes = [], {}
    svgs, svg_indexes = [], {}
    styles, style_indexes = [], {}
    page_sizes, page_size_indexes = [], {}
    compact = []

    for page in source_pages:
        elements = []
        for element in page["elements"]:
            element_type = element["type"]
            if element_type == "text":
                style = (
                    intern(element["font"], fonts, font_indexes),
                    element["size"],
                    int(element["bold"]) | (int(element["italic"]) << 1),
                    intern(element["color"], colors, color_indexes),
                )
                style_idx = intern(style, styles, style_indexes)
                elements.append([
                    0, element["textIdx"], style_idx,
                    element["x"], element["y"], element["w"], element["h"],
                ])
            elif element_type == "image":
                elements.append([
                    1, intern(element["src"], sources, source_indexes),
                    element["x"], element["y"], element["w"], element["h"],
                ])
            elif element_type == "svg":
                elements.append([
                    2, intern(element["svg"], svgs, svg_indexes),
                    element["x"], element["y"], element["w"], element["h"],
                ])
            else:
                raise ValueError(f"Неизвестный тип элемента: {element_type}")
        page_size = (page["width"], page["height"])
        compact.append([intern(page_size, page_sizes, page_size_indexes), elements])

    return [
        1, fonts, colors, sources, svgs, [list(style) for style in styles],
        [list(page_size) for page_size in page_sizes], compact,
    ]


def expand_pages(document):
    """Восстанавливает исходную схему; используется для проверки отсутствия потерь."""
    version, fonts, colors, sources, svgs, styles, page_sizes, compact = document
    if version != 1:
        raise ValueError(f"Неподдерживаемая версия формата: {version}")

    expanded = []
    for page_size_idx, compact_elements in compact:
        width, height = page_sizes[page_size_idx]
        elements = []
        for element in compact_elements:
            element_type = element[0]
            if element_type == 0:
                _, text_idx, style_idx, x, y, w, h = element
                font_idx, size, flags, color_idx = styles[style_idx]
                elements.append({
                    "type": "text", "textIdx": text_idx, "font": fonts[font_idx],
                    "size": size, "bold": bool(flags & 1), "italic": bool(flags & 2),
                    "color": colors[color_idx], "x": x, "y": y, "w": w, "h": h,
                })
            elif element_type == 1:
                _, src_idx, x, y, w, h = element
                elements.append({
                    "type": "image", "src": sources[src_idx],
                    "x": x, "y": y, "w": w, "h": h,
                })
            elif element_type == 2:
                _, svg_idx, x, y, w, h = element
                elements.append({
                    "type": "svg", "svg": svgs[svg_idx],
                    "x": x, "y": y, "w": w, "h": h,
                })
            else:
                raise ValueError(f"Неизвестный код типа элемента: {element_type}")
        expanded.append({"width": width, "height": height, "elements": elements})
    return expanded


compact_document = compact_pages(pages)
if expand_pages(compact_document) != pages:
    raise AssertionError("Компактный формат изменил исходные данные")

# ------------------- СОХРАНЕНИЕ BROTLI-ФАЙЛОВ -------------------
# Очищаем старые данные, чтобы несжатые JSON и gzip не оставались на диске.
if DATA_DIR.exists():
    shutil.rmtree(DATA_DIR)
if LOCALES_DIR.exists():
    shutil.rmtree(LOCALES_DIR)

DATA_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)
LOCALES_DIR.mkdir(exist_ok=True)

def write_brotli_json(data, destination):
    payload = json.dumps(
        data, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    destination.write_bytes(brotli.compress(payload, quality=11))

pages_br_path = DATA_DIR / "pages.json.br"
ru_br_path = LOCALES_DIR / "ru.json.br"
en_br_path = LOCALES_DIR / "en.json.br"

print("Сжатие Brotli (quality 11)...")
write_brotli_json(compact_document, pages_br_path)
write_brotli_json(ru_translations, ru_br_path)
write_brotli_json(en_translations, en_br_path)

# ------------------- ГЕНЕРАЦИЯ AVIF-ИЗОБРАЖЕНИЙ -------------------
print("Создание AVIF-изображений...")
for page_idx in range(NUM_PAGES):
    img = Image.new("RGB", (200, 150), color=(220, 220, 240))
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), f"Img {page_idx+1}", fill=(0, 0, 100))
    img.save(IMAGES_DIR / f"page{page_idx+1}_img1.avif", "AVIF", quality=QUALITY_AVIF)

# ------------------- ОТЧЁТ -------------------
def file_size(path):
    return os.path.getsize(path) if path.exists() else 0

print("\n" + "=" * 60)
print("Генерация завершена!")
print("-" * 60)
print(f"Страниц:            {NUM_PAGES}")
print(f"Слов на странице:   {WORDS_PER_PAGE}")
print()
print("Размеры Brotli-файлов:")
print(f"  pages.json.br     : {file_size(pages_br_path):>10,} байт")
print(f"  ru.json.br        : {file_size(ru_br_path):>10,} байт")
print(f"  en.json.br        : {file_size(en_br_path):>10,} байт")
total_img = sum(file_size(IMAGES_DIR / f"page{i+1}_img1.avif") for i in range(NUM_PAGES))
print(f"  images (все AVIF) : {total_img:>10,} байт")
print()
total = file_size(pages_br_path) + file_size(ru_br_path) + total_img
print(f"  Итого (pages.br + ru.br + img): {total:>10,} байт (~{total/1024:.1f} КБ)")
print("=" * 60)
print("\nЗапустите сервер: python server.py")
