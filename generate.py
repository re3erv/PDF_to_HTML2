"""Преобразует векторные страницы input1.pdf в автономные SVG-страницы HTML-просмотрщика."""

import html
import json
import re
import shutil
import zlib
from pathlib import Path

import brotli

PDF_PATH = Path("input1.pdf")
DATA_DIR = Path("data")
LOCALES_DIR = Path("locales")
OUTPUT_PATH = DATA_DIR / "pages.json.br"

OBJECT_RE = re.compile(rb"(?:^|\n)(\d+)\s+\d+\s+obj\s*(.*?)\s*endobj", re.DOTALL)
PAGE_RE = re.compile(rb"/Type\s*/Page(?!s)")
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
MEDIA_BOX_RE = re.compile(
    rb"/MediaBox\s*\[\s*(" + NUMBER.encode() + rb")\s+(" + NUMBER.encode()
    + rb")\s+(" + NUMBER.encode() + rb")\s+(" + NUMBER.encode() + rb")\s*\]"
)
OPERATORS = {"m", "l", "c", "h", "f", "f*", "S", "n", "q", "Q", "cm", "rg", "RG", "w", "J", "j", "M", "W", "W*"}


def fmt(value):
    """Компактно записывает число, не внося заметной погрешности в геометрию."""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def multiply(left, right):
    """Перемножает две affine-матрицы в SVG/PDF-представлении."""
    a, b, c, d, e, f = left
    g, h, i, j, k, l = right
    return (
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * l + e,
        b * k + d * l + f,
    )


def rgb(values):
    channels = [max(0, min(255, round(float(value) * 255))) for value in values]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def get_stream(body):
    start = body.find(b"stream")
    if start < 0:
        raise ValueError("Объект содержимого PDF не содержит stream")
    start += len(b"stream")
    if body[start:start + 2] == b"\r\n":
        start += 2
    elif body[start:start + 1] in {b"\r", b"\n"}:
        start += 1
    compressed = body[start:body.rfind(b"endstream")].rstrip(b"\r\n")
    if b"/FlateDecode" not in body[:start]:
        raise ValueError("Поддерживаются только FlateDecode-потоки PDF")
    return zlib.decompress(compressed).decode("latin-1")


def parse_pdf(path):
    payload = path.read_bytes()
    objects = {int(match.group(1)): match.group(2) for match in OBJECT_RE.finditer(payload)}
    pages = []
    for object_number, body in objects.items():
        if not PAGE_RE.search(body):
            continue
        media_box = MEDIA_BOX_RE.search(body)
        contents = re.search(rb"/Contents\s*\[(.*?)\]", body, re.DOTALL)
        if not media_box or not contents:
            raise ValueError(f"Не удалось прочитать страницу из PDF-объекта {object_number}")
        x0, y0, x1, y1 = (float(value) for value in media_box.groups())
        references = [int(value) for value in re.findall(rb"(\d+)\s+0\s+R", contents.group(1))]
        pages.append((object_number, x1 - x0, y1 - y0, "\n".join(get_stream(objects[reference]) for reference in references)))
    if not pages:
        raise ValueError("В PDF не найдены страницы")
    return pages


def page_to_svg(width, height, content):
    state = {
        "ctm": (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        "fill": "#000000",
        "stroke": "#000000",
        "width": 1.0,
        "linecap": 0,
        "linejoin": 0,
        "miter": 10.0,
    }
    stack = []
    operands = []
    path = []
    output = []
    view_transform = (1.0, 0.0, 0.0, -1.0, 0.0, height)

    def transformed_matrix():
        return " ".join(fmt(value) for value in multiply(view_transform, state["ctm"]))

    def paint(kind, evenodd=False):
        if not path:
            return
        attributes = [f'd="{html.escape(" ".join(path), quote=True)}"', f'transform="matrix({transformed_matrix()})"']
        if kind == "fill":
            attributes.extend((f'fill="{state["fill"]}"', 'stroke="none"'))
            if evenodd:
                attributes.append('fill-rule="evenodd"')
        else:
            linecaps = ("butt", "round", "square")
            linejoins = ("miter", "round", "bevel")
            attributes.extend((
                'fill="none"', f'stroke="{state["stroke"]}"', f'stroke-width="{fmt(state["width"])}"',
                f'stroke-linecap="{linecaps[min(state["linecap"], 2)]}"',
                f'stroke-linejoin="{linejoins[min(state["linejoin"], 2)]}"', f'stroke-miterlimit="{fmt(state["miter"])}"',
            ))
        output.append("<path " + " ".join(attributes) + "/>")
        path.clear()

    tokens = re.findall(r"\S+", content)
    for token in tokens:
        if token not in OPERATORS:
            operands.append(token)
            continue
        if token == "m":
            path.append(f"M {operands[-2]} {operands[-1]}")
        elif token == "l":
            path.append(f"L {operands[-2]} {operands[-1]}")
        elif token == "c":
            path.append("C " + " ".join(operands[-6:]))
        elif token == "h":
            path.append("Z")
        elif token in {"f", "f*"}:
            paint("fill", token == "f*")
        elif token == "S":
            paint("stroke")
        elif token == "n":
            path.clear()
        elif token == "q":
            stack.append(state.copy())
        elif token == "Q":
            if not stack:
                raise ValueError("Некорректный баланс q/Q в PDF")
            state = stack.pop()
        elif token == "cm":
            state["ctm"] = multiply(state["ctm"], tuple(float(value) for value in operands[-6:]))
        elif token == "rg":
            state["fill"] = rgb(operands[-3:])
        elif token == "RG":
            state["stroke"] = rgb(operands[-3:])
        elif token == "w":
            state["width"] = float(operands[-1])
        elif token == "J":
            state["linecap"] = int(float(operands[-1]))
        elif token == "j":
            state["linejoin"] = int(float(operands[-1]))
        elif token == "M":
            state["miter"] = float(operands[-1])
        # W/W* задают clip-path страницы; MediaBox и overflow уже ограничивают результат.
        operands.clear()

    if path:
        raise ValueError("После разбора страницы остался незакрашенный путь")
    if stack:
        raise ValueError("Некорректный баланс q/Q в PDF")
    return (
        f'<svg viewBox="0 0 {fmt(width)} {fmt(height)}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="Страница PDF">{"".join(output)}</svg>'
    )


def write_brotli_json(data, destination):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    destination.write_bytes(brotli.compress(payload, quality=11))


def main():
    parsed_pages = parse_pdf(PDF_PATH)
    svgs = []
    page_sizes = []
    page_size_indexes = {}
    pages = []
    for page_number, (_, width, height, content) in enumerate(parsed_pages, start=1):
        print(f"Преобразование страницы {page_number} из {len(parsed_pages)}...")
        size = (width, height)
        if size not in page_size_indexes:
            page_size_indexes[size] = len(page_sizes)
            page_sizes.append(list(size))
        pages.append([page_size_indexes[size], len(svgs)])
        svgs.append(page_to_svg(width, height, content))

    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    if LOCALES_DIR.exists():
        shutil.rmtree(LOCALES_DIR)
    DATA_DIR.mkdir()
    document = [2, svgs, page_sizes, pages]
    write_brotli_json(document, OUTPUT_PATH)
    print(f"Готово: {len(pages)} страниц, {OUTPUT_PATH.stat().st_size:,} байт")


if __name__ == "__main__":
    main()
