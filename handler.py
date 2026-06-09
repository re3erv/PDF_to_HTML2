"""Оркестратор преобразования input1.pdf в данные HTML-просмотрщика."""

from pathlib import Path

from src.converter import convert_pdf

PDF_PATH = Path("input1.pdf")
DATA_DIR = Path("data")


def main() -> None:
    page_count = convert_pdf(PDF_PATH, DATA_DIR)
    print(f"Готово: {page_count} страниц, данные сохранены в {DATA_DIR}/")


if __name__ == "__main__":
    main()
