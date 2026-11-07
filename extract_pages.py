"""Trích nội dung từng trang SGK Toán 12 - Tập 2 (sgkII.pdf) -> pages.json.

Quy ước quan trọng: trong file sgkII.pdf này, CHỈ SỐ TRANG 0-based (vị trí trong
file PDF) TRÙNG với SỐ TRANG IN ở chân trang. Kiểm chứng:
    - vị trí 2  -> trang in số 2   (§1. Nguyên hàm)
    - vị trí 5  -> trang in số 5   (Bài 1 Dạng 2)
    - vị trí 60 -> trang in số 60  (§3. Ứng dụng hình học của tích phân)
    - vị trí 344-> trang in số 344 (§3. Ôn tập chương 6)
Nên: nội dung trang sách số N nằm ở pages.pages[N].

Chạy:  python extract_pages.py [đường_dẫn_pdf] [đường_dẫn_pages.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pymupdf

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
DEFAULT_PDF = BASE / "sgkII.pdf"
if not DEFAULT_PDF.exists():
    DEFAULT_PDF = BASE.parent / "sgkII.pdf"


def main() -> None:
    pdf_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_PDF
    if not pdf_path.exists():
        sys.exit(f"Không tìm thấy file PDF: {pdf_path}")

    doc = pymupdf.open(pdf_path)
    pages = [doc[i].get_text("text", sort=True).strip() for i in range(doc.page_count)]
    doc.close()

    out_path = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else BASE / "pages.json"
    data = {
        "source": pdf_path.name,
        "count": len(pages),
        "pages": pages,
    }
    out_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"Đã trích {len(pages)} trang -> {out_path}")


if __name__ == "__main__":
    main()
