"""Trích nội dung trang từ PDF và làm sạch chữ bị lặp.

Một số PDF (ví dụ `sgk.pdf`) vẽ chữ hai lần lệch nhau rất ít, nên pymupdf trả
về chữ bị nhân đôi dính liền: "BÀIBÀI TẬPTẬP", "BàiBài 3".

`clean_text` chỉ gộp các từ bị lặp **dính liền** (không có dấu cách), nên không
đụng tới cụm từ hợp lệ như "song song", "luôn luôn".
"""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf

# "BÀIBÀI", "BàiBài", "TẬPTẬP" -> một lần (không áp dụng khi có dấu cách)
_REPEAT_WORD = re.compile(r"(?<![^\W\d_])([^\W\d_]{2,})\1", re.IGNORECASE)


def clean_text(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    text = _REPEAT_WORD.sub(r"\1", text)
    text = re.sub(r"[ \t]{4,}", "   ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def page_text(page) -> str:
    return clean_text(page.get_text("text", sort=True))


def pdf_page_texts(pdf_path: Path | str) -> list[str]:
    doc = pymupdf.open(pdf_path)
    try:
        return [page_text(doc[i]) for i in range(doc.page_count)]
    finally:
        doc.close()
