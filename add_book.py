"""Thêm một tài liệu nguồn vào thư viện kiến thức.

Một tài liệu nguồn gồm 2 file trong thư mục sources/:
    sources/<id>.pdf          bản gốc, dùng để cắt hình trong tài liệu
    sources/<id>.pages.json   nội dung từng trang, đã trích sẵn

Sau khi thêm, tài liệu tự xuất hiện ở cột "Thư viện kiến thức" và dùng được
mọi tính năng như sgkII (hỏi bài, /chitiet, /vehinh, cắt hình).

Chạy:
    python add_book.py duong/dan/sach.pdf
    python add_book.py sach.pdf --id toan-11-t1 --name "Toán 11 - Tập 1"

Tùy chọn:
    --id    mã không dấu (mặc định lấy từ tên file)
    --name  tên hiển thị (mặc định lấy từ tên file)
    --force ghi đè nếu id đã tồn tại
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import pymupdf

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
BOOKS_FILE = BASE / "books.json"
SOURCES_DIR = BASE / "sources"


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "tai-lieu"


def read_books() -> list[dict]:
    if not BOOKS_FILE.exists():
        return []
    try:
        data = json.loads(BOOKS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [b for b in data.get("books", []) if isinstance(b, dict)]


def write_books(books: list[dict]) -> None:
    BOOKS_FILE.write_text(
        json.dumps({"books": books}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def extract_pages(pdf_path: Path, out_path: Path) -> int:
    doc = pymupdf.open(pdf_path)
    try:
        pages = [doc[i].get_text("text", sort=True).strip() for i in range(doc.page_count)]
    finally:
        doc.close()
    out_path.write_text(
        json.dumps(
            {"source": pdf_path.name, "count": len(pages), "pages": pages},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return len(pages)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Thêm một tài liệu nguồn vào thư viện kiến thức"
    )
    parser.add_argument("pdf", help="Đường dẫn tới file PDF")
    parser.add_argument("--id", dest="book_id", default="")
    parser.add_argument("--name", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.is_file():
        sys.exit(f"Không tìm thấy file: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        sys.exit("Chỉ hỗ trợ file PDF.")

    book_id = args.book_id.strip() or slugify(pdf_path.stem)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", book_id):
        sys.exit("--id chỉ dùng chữ thường, số và dấu gạch ngang (ví dụ: toan-11-t1).")

    name = args.name.strip() or pdf_path.stem

    books = read_books()
    existing = next((i for i, b in enumerate(books) if b.get("id") == book_id), None)
    if existing is not None and not args.force:
        sys.exit(
            f"Đã có tài liệu id '{book_id}'. Dùng --id khác hoặc --force để ghi đè."
        )

    SOURCES_DIR.mkdir(exist_ok=True)
    pdf_out = SOURCES_DIR / f"{book_id}.pdf"
    pages_out = SOURCES_DIR / f"{book_id}.pages.json"

    if pdf_path != pdf_out:
        shutil.copy2(pdf_path, pdf_out)

    print(f"Đang trích nội dung: {pdf_out.name}")
    count = extract_pages(pdf_out, pages_out)

    entry = {
        "id": book_id,
        "name": name,
        "short": name,
        "pages": f"sources/{pages_out.name}",
        "pdf": f"sources/{pdf_out.name}",
    }
    if existing is not None:
        books[existing] = entry
    else:
        books.append(entry)
    write_books(books)

    print(f"Đã thêm tài liệu nguồn: {name}")
    print(f"  id     : {book_id}")
    print(f"  số trang: {count}")
    print(f"  pdf    : {entry['pdf']}")
    print(f"  pages  : {entry['pages']}")
    print("Mở lại trang web và chọn tài liệu ở cột Thư viện kiến thức.")


if __name__ == "__main__":
    main()
