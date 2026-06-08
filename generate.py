import json
import os
import shutil
from pathlib import Path

import brotli

# ------------------- НАСТРОЙКИ -------------------
PAGE_WIDTH = 850
PAGE_HEIGHT = 1140

DATA_DIR = Path("data")
LOCALES_DIR = Path("locales")

# Фрагмент из произведения Льюиса Кэрролла «Alice's Adventures in Wonderland»
# (1865, общественное достояние). Русский текст — перевод для этого проекта.
CONTENT = [
    [
        (
            "ALICE'S ADVENTURES IN WONDERLAND",
            "ПРИКЛЮЧЕНИЯ АЛИСЫ В СТРАНЕ ЧУДЕС",
            "title",
        ),
        ("Lewis Carroll · 1865", "Льюис Кэрролл · 1865", "subtitle"),
        ("CHAPTER I. Down the Rabbit-Hole", "ГЛАВА I. Вниз по кроличьей норе", "chapter"),
        (
            "Alice was beginning to get very tired of sitting by her sister on the bank, "
            "and of having nothing to do: once or twice she had peeped into the book her "
            "sister was reading, but it had no pictures or conversations in it, ‘and what "
            "is the use of a book,’ thought Alice ‘without pictures or conversations?’",
            "Алисе начинало ужасно надоедать сидеть рядом с сестрой на берегу без всякого "
            "дела. Раз или два она заглянула в книгу, которую читала сестра, но там не было "
            "ни картинок, ни разговоров. «И что пользы от книги, — подумала Алиса, — если "
            "в ней нет ни картинок, ни разговоров?»",
            "body",
        ),
        (
            "So she was considering in her own mind (as well as she could, for the hot day "
            "made her feel very sleepy and stupid), whether the pleasure of making a "
            "daisy-chain would be worth the trouble of getting up and picking the daisies, "
            "when suddenly a White Rabbit with pink eyes ran close by her.",
            "Она размышляла про себя (насколько могла, потому что от жаркого дня её клонило "
            "в сон и мысли путались), стоит ли удовольствие сплести цепочку из маргариток "
            "того, чтобы встать и нарвать цветов, как вдруг совсем рядом пробежал Белый "
            "Кролик с розовыми глазами.",
            "body",
        ),
    ],
    [
        (
            "There was nothing so VERY remarkable in that; nor did Alice think it so VERY "
            "much out of the way to hear the Rabbit say to itself, ‘Oh dear! Oh dear! I shall "
            "be late!’ (when she thought it over afterwards, it occurred to her that she "
            "ought to have wondered at this, but at the time it all seemed quite natural); "
            "but when the Rabbit actually TOOK A WATCH OUT OF ITS WAISTCOAT-POCKET, and "
            "looked at it, and then hurried on, Alice started to her feet, for it flashed "
            "across her mind that she had never before seen a rabbit with either a "
            "waistcoat-pocket, or a watch to take out of it, and burning with curiosity, "
            "she ran across the field after it, and fortunately was just in time to see it "
            "pop down a large rabbit-hole under the hedge.",
            "Само по себе это не было ТАК уж удивительно; и Алиса не сочла ТАК уж необычным, "
            "услышав, как Кролик говорит себе: «Ах, боже мой! Боже мой! Я опоздаю!» "
            "(позже, обдумав случившееся, она поняла, что этому следовало удивиться, но в "
            "тот миг всё казалось совершенно естественным). Но когда Кролик и в самом деле "
            "ДОСТАЛ ЧАСЫ ИЗ КАРМАНА ЖИЛЕТА, взглянул на них и поспешил дальше, Алиса вскочила: "
            "её вдруг осенило, что прежде она никогда не видела кролика ни с карманом на "
            "жилете, ни с часами, которые можно из него достать. Сгорая от любопытства, она "
            "побежала за ним через поле и, к счастью, успела заметить, как он юркнул в "
            "большую кроличью нору под изгородью.",
            "body_tall",
        ),
        (
            "In another moment down went Alice after it, never once considering how in the "
            "world she was to get out again.",
            "В следующий миг Алиса нырнула туда следом, ни разу не задумавшись, как же она "
            "потом выберется обратно.",
            "body_short",
        ),
        (
            "The rabbit-hole went straight on like a tunnel for some way, and then dipped "
            "suddenly down, so suddenly that Alice had not a moment to think about stopping "
            "herself before she found herself falling down a very deep well.",
            "Сначала кроличья нора шла прямо, словно туннель, а потом внезапно круто "
            "обрывалась вниз — так внезапно, что Алиса не успела и подумать о том, чтобы "
            "остановиться, как уже падала в очень глубокий колодец.",
            "body",
        ),
        (
            "Either the well was very deep, or she fell very slowly, for she had plenty of "
            "time as she went down to look about her and to wonder what was going to happen next.",
            "То ли колодец был очень глубок, то ли падала она очень медленно, но по пути у "
            "неё было достаточно времени осмотреться и подумать, что же случится дальше.",
            "body",
        ),
    ],
]

STYLE_PRESETS = {
    "title": {"font": "Georgia", "size": 28, "bold": True, "italic": False, "color": "#23395d", "x": 70, "y": 70, "w": 710, "h": 45},
    "subtitle": {"font": "Georgia", "size": 15, "bold": False, "italic": True, "color": "#6b4f35", "x": 70, "y": 125, "w": 710, "h": 30},
    "chapter": {"font": "Georgia", "size": 21, "bold": True, "italic": False, "color": "#6b4f35", "x": 70, "y": 180, "w": 710, "h": 40},
    "body": {"font": "Georgia", "size": 18, "bold": False, "italic": False, "color": "#252525", "x": 70, "w": 710, "h": 205},
    "body_tall": {"font": "Georgia", "size": 18, "bold": False, "italic": False, "color": "#252525", "x": 70, "w": 710, "h": 385},
    "body_short": {"font": "Georgia", "size": 18, "bold": False, "italic": False, "color": "#252525", "x": 70, "w": 710, "h": 95},
}

print(f"Генерация фрагмента Alice's Adventures in Wonderland: {len(CONTENT)} страницы...")

pages = []
en_translations = []
ru_translations = []
for page_idx, content_page in enumerate(CONTENT):
    elements = []
    en_page = []
    ru_page = []
    body_y = 250 if page_idx == 0 else 100

    for text_idx, (english, russian, preset_name) in enumerate(content_page):
        preset = STYLE_PRESETS[preset_name]
        y = preset.get("y", body_y)
        elements.append({
            "type": "text", "textIdx": text_idx,
            "font": preset["font"], "size": preset["size"],
            "bold": preset["bold"], "italic": preset["italic"], "color": preset["color"],
            "x": preset["x"], "y": y, "w": preset["w"], "h": preset["h"],
        })
        en_page.append(english)
        ru_page.append(russian)
        if preset_name.startswith("body"):
            body_y += preset["h"] + 25

    divider = '<svg viewBox="0 0 710 20" xmlns="http://www.w3.org/2000/svg"><path d="M0 10 H320 M390 10 H710" stroke="#b89b72"/><circle cx="355" cy="10" r="6" fill="#b89b72"/></svg>'
    elements.append({"type": "svg", "svg": divider, "x": 70, "y": 1080, "w": 710, "h": 20})
    pages.append({"width": PAGE_WIDTH, "height": PAGE_HEIGHT, "elements": elements})
    en_translations.append(en_page)
    ru_translations.append(ru_page)


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
                style = (intern(element["font"], fonts, font_indexes), element["size"], int(element["bold"]) | (int(element["italic"]) << 1), intern(element["color"], colors, color_indexes))
                elements.append([0, element["textIdx"], intern(style, styles, style_indexes), element["x"], element["y"], element["w"], element["h"]])
            elif element_type == "image":
                elements.append([1, intern(element["src"], sources, source_indexes), element["x"], element["y"], element["w"], element["h"]])
            elif element_type == "svg":
                elements.append([2, intern(element["svg"], svgs, svg_indexes), element["x"], element["y"], element["w"], element["h"]])
            else:
                raise ValueError(f"Неизвестный тип элемента: {element_type}")
        page_size = (page["width"], page["height"])
        compact.append([intern(page_size, page_sizes, page_size_indexes), elements])

    return [1, fonts, colors, sources, svgs, [list(style) for style in styles], [list(size) for size in page_sizes], compact]


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
            if element[0] == 0:
                _, text_idx, style_idx, x, y, w, h = element
                font_idx, size, flags, color_idx = styles[style_idx]
                elements.append({"type": "text", "textIdx": text_idx, "font": fonts[font_idx], "size": size, "bold": bool(flags & 1), "italic": bool(flags & 2), "color": colors[color_idx], "x": x, "y": y, "w": w, "h": h})
            elif element[0] == 1:
                _, src_idx, x, y, w, h = element
                elements.append({"type": "image", "src": sources[src_idx], "x": x, "y": y, "w": w, "h": h})
            elif element[0] == 2:
                _, svg_idx, x, y, w, h = element
                elements.append({"type": "svg", "svg": svgs[svg_idx], "x": x, "y": y, "w": w, "h": h})
            else:
                raise ValueError(f"Неизвестный код типа элемента: {element[0]}")
        expanded.append({"width": width, "height": height, "elements": elements})
    return expanded


compact_document = compact_pages(pages)
if expand_pages(compact_document) != pages:
    raise AssertionError("Компактный формат изменил исходные данные")

if DATA_DIR.exists():
    shutil.rmtree(DATA_DIR)
if LOCALES_DIR.exists():
    shutil.rmtree(LOCALES_DIR)
DATA_DIR.mkdir()
LOCALES_DIR.mkdir()


def write_brotli_json(data, destination):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    destination.write_bytes(brotli.compress(payload, quality=11))


pages_br_path = DATA_DIR / "pages.json.br"
ru_br_path = LOCALES_DIR / "ru.json.br"
en_br_path = LOCALES_DIR / "en.json.br"
write_brotli_json(compact_document, pages_br_path)
write_brotli_json(ru_translations, ru_br_path)
write_brotli_json(en_translations, en_br_path)

def file_size(path):
    return os.path.getsize(path)


print("Генерация завершена!")
print(f"Страниц: {len(CONTENT)}")
print(f"pages.json.br: {file_size(pages_br_path):,} байт")
print(f"ru.json.br: {file_size(ru_br_path):,} байт")
print(f"en.json.br: {file_size(en_br_path):,} байт")
print("Запустите сервер: python server.py")
