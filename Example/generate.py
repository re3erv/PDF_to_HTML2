# generate.py (исправленная версия)
import json
import os
import random
import sys
import subprocess
import shutil
import gzip
from pathlib import Path

# ------------------- АВТОУСТАНОВКА ЗАВИСИМОСТЕЙ -------------------
def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def ensure_pillow_avif():
    try:
        from PIL import Image
        try:
            import pillow_avif
        except ImportError:
            print("Устанавливаю pillow-avif-plugin...")
            install("pillow-avif-plugin")
        return True
    except Exception:
        print("⚠️  Pillow не установлен. Изображения будут пустыми заглушками.")
        return False

def ensure_msgpack():
    try:
        import msgpack
        return msgpack
    except ImportError:
        print("Устанавливаю msgpack...")
        install("msgpack")
        import msgpack
        return msgpack

HAS_AVIF = ensure_pillow_avif()
msgpack = ensure_msgpack()   # теперь это модуль

# ------------------- НАСТРОЙКИ -------------------
NUM_PAGES = 800
WORDS_PER_PAGE = 200
FONTS = ["Times New Roman", "Arial", "Courier New", "Verdana"]
SIZES = [10, 11, 12, 14]
COLORS = ["#000000", "#333333", "#555555"]
QUALITY_AVIF = 85

DATA_DIR = Path("Example/data")
IMAGES_DIR = DATA_DIR / "images"
LOCALES_DIR = Path("Example/data/locales")

random.seed(42)

print(f"Генерация {NUM_PAGES} страниц, {WORDS_PER_PAGE} слов на страницу...")

RU_WORDS = ["привет", "мир", "дом", "книга", "река", "ночь", "день",
            "звезда", "мечта", "огонь", "вода", "земля", "небо", "птица"]
EN_WORDS = ["hello", "world", "house", "book", "river", "night", "day",
            "star", "dream", "fire", "water", "earth", "sky", "bird"]

FONT_LIST = list(set(FONTS))
COLOR_LIST = list(set(COLORS))
IMG_SOURCES = [f"images/page{i+1}_img1.avif" for i in range(NUM_PAGES)]

pages_out = []
for page_idx in range(NUM_PAGES):
    elements = []
    for word_idx in range(WORDS_PER_PAGE):
        font = random.choice(FONTS)
        size = random.choice(SIZES)
        bold = 1 if random.choice([True, False]) else 0
        italic = 1 if (random.random() < 0.2) else 0
        color = random.choice(COLORS)
        col = word_idx % 15
        row = word_idx // 15
        x = 100 + col * 80
        y = 100 + row * 25
        w = random.randint(30, 70)
        h = size + 2
        elements.append([
            0,                          # type = text
            word_idx,
            FONT_LIST.index(font),
            size,
            bold,
            italic,
            COLOR_LIST.index(color),
            x, y, w, h
        ])
    elements.append([1, page_idx, 300, 600, 200, 150])  # image
    svg_string = (
        f'<svg width="100" height="100"><circle cx="50" cy="50" r="40" fill="#ccf"/>'
        f'<text x="50" y="55" text-anchor="middle" font-size="12">P{page_idx+1}</text></svg>'
    )
    elements.append([2, svg_string, 550, 600, 100, 100])  # svg
    # страница как массив: [width, height, elements]
    pages_out.append([1240, 1754, elements])

pages_data = {
    "fonts": FONT_LIST,
    "colors": COLOR_LIST,
    "images": IMG_SOURCES,
    "pages": pages_out
}

# Генерация локалей в том же стиле (массивы)
def generate_locale(word_pool):
    words = list(set(word_pool))
    word_to_idx = {w: i for i, w in enumerate(words)}
    pages_trans = []
    for _ in range(NUM_PAGES):
        page_words = [random.choice(word_pool) for _ in range(WORDS_PER_PAGE)]
        page_idxs = [word_to_idx[w] for w in page_words]
        pages_trans.append(page_idxs)
    return [words, pages_trans]  # массив [words, pages]

ru_locale = generate_locale(RU_WORDS)
en_locale = generate_locale(EN_WORDS)

# ------------------- СОХРАНЕНИЕ -------------------
if DATA_DIR.exists():
    shutil.rmtree(DATA_DIR)
if LOCALES_DIR.exists():
    shutil.rmtree(LOCALES_DIR)
DATA_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)
LOCALES_DIR.mkdir(exist_ok=True)

def save_msgpack_gz(obj, path):
    """Сериализует объект в msgpack и сжимает gzip."""
    with gzip.open(path, 'wb', compresslevel=9) as f:
        f.write(msgpack.packb(obj))

pages_msgpack_path = DATA_DIR / "pages.msgpack.gz"
ru_msgpack_path = LOCALES_DIR / "ru.msgpack.gz"
en_msgpack_path = LOCALES_DIR / "en.msgpack.gz"

print("Сохранение в MessagePack + gzip...")
save_msgpack_gz(pages_data, pages_msgpack_path)
save_msgpack_gz(ru_locale, ru_msgpack_path)
save_msgpack_gz(en_locale, en_msgpack_path)

# Для отчёта сохраним также JSON (необязательно)
pages_json_path = DATA_DIR / "pages.json"
ru_json_path = LOCALES_DIR / "ru.json"
en_json_path = LOCALES_DIR / "en.json"
with open(pages_json_path, "w", encoding="utf-8") as f:
    json.dump(pages_data, f, ensure_ascii=False)
with open(ru_json_path, "w", encoding="utf-8") as f:
    json.dump(ru_locale, f, ensure_ascii=False)
with open(en_json_path, "w", encoding="utf-8") as f:
    json.dump(en_locale, f, ensure_ascii=False)

# ------------------- AVIF -------------------
if HAS_AVIF:
    from PIL import Image, ImageDraw
    print("Создание AVIF-изображений...")
    for page_idx in range(NUM_PAGES):
        img = Image.new('RGB', (200, 150), color=(220, 220, 240))
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), f"Img {page_idx+1}", fill=(0, 0, 100))
        img.save(IMAGES_DIR / f"page{page_idx+1}_img1.avif", "AVIF", quality=QUALITY_AVIF)
else:
    print("Создание пустых заглушек вместо AVIF...")
    for page_idx in range(NUM_PAGES):
        (IMAGES_DIR / f"page{page_idx+1}_img1.avif").touch()

# ------------------- ОТЧЁТ -------------------
def file_size(path):
    return os.path.getsize(path) if path.exists() else 0

print("\n" + "=" * 60)
print("Генерация завершена!")
print("-" * 60)
print(f"Страниц:            {NUM_PAGES}")
print(f"Слов на странице:   {WORDS_PER_PAGE}")
print()
print("Размеры файлов (MessagePack + gzip):")
print(f"  pages.msgpack.gz : {file_size(pages_msgpack_path):>10,} байт")
print(f"  ru.msgpack.gz    : {file_size(ru_msgpack_path):>10,} байт")
print(f"  en.msgpack.gz    : {file_size(en_msgpack_path):>10,} байт")
total_img = sum(file_size(IMAGES_DIR / f"page{i+1}_img1.avif") for i in range(NUM_PAGES))
print(f"  images (все AVIF): {total_img:>10,} байт")
print()
total = file_size(pages_msgpack_path) + file_size(ru_msgpack_path) + total_img
print(f"  Итого (pages.msgpack.gz + ru.msgpack.gz + img): {total:>10,} байт (~{total/1024:.1f} КБ)")
print("=" * 60)
print("\nЗапустите сервер: python -m http.server 8000")