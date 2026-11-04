"""Cắt hình minh họa có sẵn trong SGK (vector hoặc ảnh) để dán vào lời giải.

Ý tưởng:
- Gom các nét vẽ (drawings) rời rạc thành cụm theo khoảng cách.
- Bỏ các đường kẻ/dải nền chạy hết bề ngang trang và icon góc trang.
- Không gom chữ vào hình; chỉ lấy vùng nét vẽ và thêm lề khi cắt.
- Nếu có nhãn bài (Bài n / Ví dụ n), chỉ lấy cụm nằm trong khoảng dọc của bài đó.
- Ưu tiên hình vector; nếu không có mới dùng ảnh raster.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf

BASE = Path(__file__).resolve().parent
CACHE_DIR = BASE / "figures_cache"
DEFAULT_PDF = BASE.parent / "sgkII.pdf"


def _cluster(rects: list[pymupdf.Rect], gap: float = 12.0) -> list[pymupdf.Rect]:
    """Gộp các rect gần nhau thành cụm."""
    clusters = [pymupdf.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False
        out: list[pymupdf.Rect] = []
        while clusters:
            base = clusters.pop()
            i = 0
            while i < len(clusters):
                pad = pymupdf.Rect(base.x0 - gap, base.y0 - gap, base.x1 + gap, base.y1 + gap)
                if pad.intersects(clusters[i]):
                    base = base | clusters[i]
                    clusters.pop(i)
                    changed = True
                else:
                    i += 1
            out.append(base)
        clusters = out
    return clusters


def _anchors(page) -> list[float]:
    """Mọi mốc ngắt đoạn: nhãn Bài/Ví dụ + tiêu đề BÀI TẬP RÈN LUYỆN."""
    ys = _label_ys(page, "Bài") + _label_ys(page, "Ví dụ")
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        bb = pymupdf.Rect(block["bbox"])
        if bb.height > 50:
            continue
        txt = "".join(
            (span.get("text") or "")
            for line in block.get("lines", [])
            for span in line.get("spans", [])
        ).lower()
        if "luyện" in txt:
            ys.append(bb.y0)
    ys.sort()
    out: list[float] = []
    for y in ys:
        if not out or abs(y - out[-1]) > 6:
            out.append(y)
    return out


def _label_band(page, label) -> tuple[float, float] | None:
    kind, num = label
    y0 = _find_label_y(page, kind, num)
    if y0 is None:
        return None
    ends = [y for y in _anchors(page) if y > y0 + 2]
    y1 = (min(ends) - 6) if ends else (page.rect.height - 40)
    top = y0 - 6
    if y1 <= top:
        return None
    return (top, y1)


def _label_ys(page, kind: str) -> list[float]:
    key = "dụ" if kind.lower().startswith("ví") else "bài"
    raw = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        bb = pymupdf.Rect(block["bbox"])
        if bb.width > 220 or bb.height > 40:
            continue
        txt = "".join(
            (span.get("text") or "")
            for line in block.get("lines", [])
            for span in line.get("spans", [])
        )
        if key in txt.replace(" ", "").lower():
            raw.append(bb.y0)
    raw.sort()
    out: list[float] = []
    for y in raw:
        if not out or abs(y - out[-1]) > 6:
            out.append(y)
    return out


def _find_label_y(page, kind: str, num: int) -> float | None:
    # 1) tìm trực tiếp bằng search_for
    for q in (f"{kind} {num}", f"{kind}{num}"):
        rects = page.search_for(q)
        if rects:
            return min(r.y0 for r in rects)
    # 2) dò nhãn theo thứ tự (PDF hay vẽ trùng glyph: "BàiBài 11")
    ys = _label_ys(page, kind)
    return ys[num - 1] if 1 <= num <= len(ys) else None


def _label_spans(page):
    """Chỉ lấy chữ từ các BLOCK NHỎ (nhãn điểm/độ dài), bỏ đoạn văn."""
    out = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        bb = pymupdf.Rect(block["bbox"])
        if bb.width > 200 or bb.height > 60:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                t = (span.get("text") or "").strip()
                if t and not t.startswith("."):
                    out.append((pymupdf.Rect(span["bbox"]), t))
    return out


def find_figure(page, label=None) -> pymupdf.Rect | None:
    """Trả về bbox (đã gồm nhãn chữ) của hình phù hợp, hoặc None."""
    W, H = page.rect.width, page.rect.height

    strokes: list[pymupdf.Rect] = []
    for d in page.get_drawings():
        r = pymupdf.Rect(d["rect"])
        w, h = r.width, r.height
        # nét mảnh/điểm có kích thước 0 -> nới nhẹ để gom cụm
        if w < 0.5 or h < 0.5:
            r = pymupdf.Rect(r.x0 - 0.5, r.y0 - 0.5, r.x1 + 0.5, r.y1 + 0.5)
            w, h = r.width, r.height
        # bỏ nét/khung chạy gần hết bề ngang trang (khung "Ví dụ", đường kẻ)
        if w > 0.55 * W:
            continue
        # bỏ hộp tô đặc lớn (nhãn "Ví dụ", nền) — giữ chấm nhỏ/arrowhead
        if d.get("type") == "f" and w > 18 and h > 12:
            continue
        # icon trang trí ở góc dưới (trái hoặc phải)
        if r.y0 > H - 115 and (r.x0 > W - 95 or r.x1 < 95):
            continue
        strokes.append(r)

    figs: list[tuple[pymupdf.Rect, int, str]] = []

    spans = _label_spans(page)

    for c in _cluster(strokes, gap=12):
        # đếm phần tử theo TÂM (điểm đỉnh kích thước 0 vẫn được tính)
        count = 0
        for r in strokes:
            cx = (r.x0 + r.x1) / 2
            cy = (r.y0 + r.y1) / 2
            if c.x0 - 1 <= cx <= c.x1 + 1 and c.y0 - 1 <= cy <= c.y1 + 1:
                count += 1
        if count < 2:
            continue
        if c.width < 45 or c.height < 30:
            continue
        if c.width * c.height < 1800:
            continue
        if c.width > 0.85 * W and c.height < 55:
            continue
        box = pymupdf.Rect(c)
        # gom nhãn điểm/độ dài quanh hình (đã lọc chỉ block nhỏ)
        ex = pymupdf.Rect(box.x0 - 40, box.y0 - 20, box.x1 + 40, box.y1 + 20)
        for r, _t in spans:
            if ex.intersects(r):
                box = box | r
        figs.append((box, count, "vector"))

    for info in page.get_image_info(xrefs=True):
        r = pymupdf.Rect(info["bbox"])
        w, h = r.width, r.height
        if w < 45 or h < 35:
            continue
        if w > 0.7 * W and h < 45:
            continue
        # icon trang trí ở góc dưới (trái hoặc phải)
        if r.y0 > H - 115 and (r.x0 > W - 95 or r.x1 < 95):
            continue
        if w * h > 0.6 * W * H:
            continue
        figs.append((r, 1, "raster"))

    if not figs:
        return None

    if label:
        band = _label_band(page, label)
        if band:
            inside = [f for f in figs if band[0] <= (f[0].y0 + f[0].y1) / 2 <= band[1]]
            if inside:
                figs = inside

    figs.sort(key=lambda f: (f[2] == "vector", f[0].width * f[0].height), reverse=True)
    return figs[0][0]


def crop_figure(page, box: pymupdf.Rect, dpi: int = 200, pad: float = 4.0) -> tuple[Path, str]:
    clip = pymupdf.Rect(box.x0 - pad, box.y0 - pad, box.x1 + pad, box.y1 + pad) & page.rect
    pix = page.get_pixmap(clip=clip, dpi=dpi)
    CACHE_DIR.mkdir(exist_ok=True)
    key = "%d_%d_%d_%d_%d_%d_%d" % (
        page.number, round(box.x0), round(box.y0), round(box.x1), round(box.y1),
        dpi, round(pad)
    )
    name = "fig_" + hashlib.md5(key.encode()).hexdigest()[:12] + ".png"
    path = CACHE_DIR / name
    if not path.exists():
        pix.save(path)
    return path, name


def extract_figure(page_no: int, label=None, pdf_path: Path | str = DEFAULT_PDF):
    """Trả về (đường_dẫn_png, tên_file) hoặc None."""
    doc = pymupdf.open(pdf_path)
    try:
        if page_no < 0 or page_no >= doc.page_count:
            return None
        page = doc[page_no]
        box = find_figure(page, label)
        if box is None:
            return None
        return crop_figure(page, box)
    finally:
        doc.close()


def exercise_text(page, label) -> str:
    """Lấy chữ trong khoảng dọc của bài (để nhận diện bài có tọa độ)."""
    band = _label_band(page, label)
    if not band:
        return ""
    parts = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        bb = pymupdf.Rect(block["bbox"])
        cy = (bb.y0 + bb.y1) / 2
        if not (band[0] <= cy <= band[1]):
            continue
        txt = " ".join(
            (span.get("text") or "").strip()
            for line in block.get("lines", [])
            for span in line.get("spans", [])
        )
        txt = " ".join(txt.split())
        if txt:
            parts.append(txt)
    return "\n".join(parts)


def analyze(page_no: int, label=None, pdf_path: Path | str = DEFAULT_PDF) -> dict:
    """Trả về {"text": đoạn đề bài, "figure": tên file PNG | None}."""
    result = {"text": "", "figure": None}
    doc = pymupdf.open(pdf_path)
    try:
        if page_no < 0 or page_no >= doc.page_count:
            return result
        page = doc[page_no]
        if label:
            result["text"] = exercise_text(page, label)
        box = find_figure(page, label)
        if box is not None:
            _path, name = crop_figure(page, box)
            result["figure"] = name
    finally:
        doc.close()
    return result
