"""Chatbox giải bài tập SGK Toán 12 - Tập 2.

Server web chạy local, chỉ dùng thư viện chuẩn Python. Giao diện chat nhận câu
kiểu "bài 1a trang 5", trích đúng trang sách rồi gọi OpenCode CLI
(`opencode run`) để sinh lời giải chi tiết. Với bài hình học, một agent riêng
chạy song song để vẽ hình minh họa bằng SVG.

Chạy:
    python server.py                 # mở http://127.0.0.1:8765
    python server.py --port 9000 --no-browser

Biến môi trường:
    OPENCODE_TOAN_MODEL  model dùng để giải
                         (mặc định: 9router/cmc/deepseek/deepseek-v4.1-flash)
    OPENCODE_BIN         đường dẫn tới opencode (mặc định tự tìm trong PATH)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
BOOKS_FILE = BASE / "books.json"
INDEX_FILE = BASE / "index.html"

MODEL = os.environ.get("OPENCODE_TOAN_MODEL", "9router/cmc/deepseek/deepseek-v4.1-flash")
AGENT = "toan"          # agent giải bài (system prompt + khoá công cụ)
FIGURE_AGENT = "hinhve"  # agent chỉ vẽ hình SVG
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "300"))
CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# Chế độ trình bày: mặc định ngắn gọn (cho học sinh), chi tiết khi dạy.
DEFAULT_MODE = "concise"
MODES = {
    "concise": (
        "[CHẾ ĐỘ: NGẮN GỌN - CHO HỌC SINH] Trình bày theo mạch: công thức → "
        "thay số → kết quả. Không nhắc định nghĩa dài dòng, không thêm mục "
        "lỗi thường gặp / ghi nhớ / mở rộng. Vẫn thể hiện rõ từng bước làm. "
        "KHÔNG tự vẽ hình."
    ),
    "detailed": (
        "[CHẾ ĐỘ: CHI TIẾT - LÍ THUYẾT] Trình bày đầy đủ: kiến thức dùng "
        "(định nghĩa/định lí ngắn), giải thích từng bước vì sao làm vậy, "
        "nêu 1-3 lỗi thường gặp khi dạy, kết luận rõ ràng. "
        "KHÔNG tự vẽ hình."
    ),
    "fast": (
        "[CHẾ ĐỘ: FAST - CHỈ ĐỀ BÀI + TRÌNH BÀY] Chỉ trả về đúng hai phần: "
        "**Đề.** (trích gọn đề bài) và **Trình bày (để chép).** "
        "(Ta có → => → => → Vậy, đáp án đóng khung). "
        "KHÔNG thêm phần giải thích, định nghĩa, lưu ý hay nhận xét nào khác. "
        "KHÔNG tự vẽ hình."
    ),
}

# Nhận "trang 5", "tr/5", hoặc viết tắt "1a/5".
PAGE_RE = re.compile(
    r"(?:\b(?:trang|page|tr)\s*[.:]?\s*|/)\s*(\d{1,3})\b",
    re.IGNORECASE,
)

# Viết tắt người dùng hay gõ -> mở rộng cho model dễ hiểu.
ABBREVIATIONS = [
    (re.compile(r"\bvd\.?\s*", re.IGNORECASE), "ví dụ "),
]

# Nhãn bài/ví dụ để chọn đúng hình trong trang.
LABEL_RE = re.compile(
    r"\b(?:bài|bai)\s*(\d{1,3})|\b(?:ví\s*dụ|vi\s*du)\s*(\d{1,3})",
    re.IGNORECASE,
)

# Người dùng chủ động yêu cầu vẽ hình.
DRAW_REQUEST_RE = re.compile(
    r"\bvẽ\b|\bminh\s*h[oọ]a\b|\bkèm\s+hình\b|\bcho\s+hình\b|\bcó\s+hình\b|\bxem\s+hình\b",
    re.IGNORECASE,
)

FIGURES_DIR = BASE / "figures_cache"

# --- Cache câu trả lời: hỏi lại cùng bài/mode trả về tức thì ---
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL = 3600   # giây
CACHE_MAX = 300    # số mục tối đa


def cache_get(key: str) -> dict | None:
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        ts, payload = item
        if time.time() - ts > CACHE_TTL:
            _CACHE.pop(key, None)
            return None
        return payload


def cache_set(key: str, payload: dict) -> None:
    with _CACHE_LOCK:
        if len(_CACHE) >= CACHE_MAX:
            oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
            _CACHE.pop(oldest, None)
        _CACHE[key] = (time.time(), payload)


def normalize_message(text: str) -> str:
    for pattern, repl in ABBREVIATIONS:
        text = pattern.sub(repl, text)
    return text.strip()

# Dấu hiệu nhận biết bài hình học -> mới gọi thêm agent vẽ hình.
GEO_RE = re.compile(
    r"hình học|hình phẳng|hình hộp|hình chóp|hình nón|hình trụ|hình cầu|"
    r"tam giác|tứ giác|đa giác|đường tròn|mặt phẳng|mặt cầu|đường thẳng|"
    r"vectơ|vector|tọa độ|toạ độ|oxyz|góc|khoảng cách|parabol|elip|"
    r"thể tích|diện tích|thiết diện|trục|mặt đáy|đường sinh",
    re.IGNORECASE,
)

# Bài hình dùng PHƯƠNG PHÁP TỌA ĐỘ -> không vẽ hình (nhận diện theo nội dung câu hỏi).
COORD_RE = re.compile(
    r"oxyz"
    r"|phương\s+pháp\s+t[oọ][aạ]\s*độ"
    r"|hệ\s+trục\s+t[oọ][aạ]\s*độ"
    r"|t[oọ][aạ]\s*độ\s+(?:của\s+)?(?:điểm|vectơ|véc\s*tơ|trung\s+điểm)"
    r"|\btrục\s+(?:ox|oy|oz)\b"
    r"|\(\s*-?\d+(?:[.,]\d+)?\s*;\s*-?\d+(?:[.,]\d+)?\s*;\s*-?\d+(?:[.,]\d+)?\s*\)"
    r"|phương\s+trình[^.\n]{0,40}(?:mặt\s+phẳng|mặt\s+cầu|đường\s+thẳng)"
    r"|(?:mặt\s+phẳng|mặt\s+cầu|đường\s+thẳng)[^.\n]{0,40}phương\s+trình"
    r"|\b[xyz]\s*=\s*[-−+]?\s*\d"
    r"|đường\s+thẳng\s+[^\n:]{0,15}:"
    r"|mặt\s+phẳng\s*\([^)]{0,12}\)\s*[:=]",
    re.IGNORECASE,
)


DEFAULT_BOOK = {
    "id": "toan-12-t2",
    "name": "Toán 12 – Tập 2",
    "short": "Tập 2",
    "pages": "pages.json",
    "pdf": "sgkII.pdf",
}

_BOOK_PAGES: dict[str, list[str]] = {}
_BOOK_LOCK = threading.Lock()
_BOOKS_CACHE: dict = {"mtime": None, "books": []}


def _parse_books() -> list[dict]:
    """Đọc books.json. Thiếu hoặc hỏng thì dùng đúng một sách mặc định."""
    if not BOOKS_FILE.exists():
        return [dict(DEFAULT_BOOK)]
    try:
        data = json.loads(BOOKS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [dict(DEFAULT_BOOK)]

    books: list[dict] = []
    for item in data.get("books", []):
        if not isinstance(item, dict):
            continue
        book = {
            "id": str(item.get("id") or "").strip(),
            "name": str(item.get("name") or "").strip(),
            "short": str(item.get("short") or "").strip(),
            "pages": str(item.get("pages") or "").strip(),
            "pdf": str(item.get("pdf") or "").strip(),
        }
        if book["id"] and book["name"] and book["pages"]:
            books.append(book)
    return books or [dict(DEFAULT_BOOK)]


def load_books() -> list[dict]:
    """Đọc books.json, tự nạp lại khi file thay đổi (không cần restart)."""
    try:
        mtime = BOOKS_FILE.stat().st_mtime
    except OSError:
        mtime = None

    with _BOOK_LOCK:
        if mtime is not None and _BOOKS_CACHE["mtime"] == mtime:
            return _BOOKS_CACHE["books"]

    books = _parse_books()
    with _BOOK_LOCK:
        _BOOKS_CACHE["mtime"] = mtime
        _BOOKS_CACHE["books"] = books
    return books


def book_pages(book: dict) -> list[str]:
    """Nội dung từng trang của một sách (đọc một lần, giữ trong bộ nhớ)."""
    with _BOOK_LOCK:
        cached = _BOOK_PAGES.get(book["id"])
    if cached is not None:
        return cached
    path = (BASE / book["pages"]).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    pages = data["pages"]
    with _BOOK_LOCK:
        _BOOK_PAGES[book["id"]] = pages
    return pages


def book_pdf(book: dict) -> Path | None:
    """Đường dẫn PDF gốc để cắt hình (nếu có)."""
    name = book.get("pdf") or ""
    if not name:
        return None
    path = (BASE / name).resolve()
    return path if path.is_file() else None


def find_opencode() -> str:
    """Tìm opencode, ƯU TIÊN file .exe thật.

    Shim `opencode.cmd` do npm tạo sẽ bị cmd.exe cắt tham số tại ký tự xuống
    dòng, làm mất phần lớn nội dung trang sách. Vì vậy ta tìm thẳng
    `node_modules/@opencode/cli/bin/opencode.exe`.
    """
    env = os.environ.get("OPENCODE_BIN")
    if env:
        return env

    candidates: list[str] = []

    exe_on_path = shutil.which("opencode.exe")
    if exe_on_path:
        candidates.append(exe_on_path)

    for shim in ("opencode.cmd", "opencode"):
        hit = shutil.which(shim)
        if hit:
            npm_dir = Path(hit).parent
            candidates.append(str(npm_dir / "node_modules" / "@opencode" / "cli" / "bin" / "opencode.exe"))

    for cand in candidates:
        if Path(cand).is_file():
            return cand

    for shim in ("opencode.cmd", "opencode"):
        hit = shutil.which(shim)
        if hit:
            return hit

    return "opencode"


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def is_losing_shim(binary: str) -> bool:
    return binary.lower().endswith((".cmd", ".bat", ".ps1"))


def build_prompt(
    user_msg: str, page_no: int | None, page_text: str | None, mode: str = DEFAULT_MODE
) -> str:
    blocks = []
    if page_text:
        blocks.append(f"[TRANG {page_no}]\n{page_text}")
    else:
        blocks.append("[TRANG ?] (Học sinh không nêu số trang sách.)")
    blocks.append(f"[CÂU HỎI] {user_msg}")
    blocks.append(MODES.get(mode, MODES[DEFAULT_MODE]))
    return "\n\n".join(blocks)


def build_figure_prompt(user_msg: str, page_no: int | None, page_text: str | None) -> str:
    blocks = []
    if page_text:
        blocks.append(f"[TRANG {page_no}]\n{page_text}")
    blocks.append(f"[CÂU HỎI] {user_msg}")
    blocks.append(
        "Nhiệm vụ: chỉ vẽ MỘT hình minh họa cho bài tập trên. "
        "Trả về duy nhất một khối mã ```svg ... ```, không giải thích gì thêm."
    )
    return "\n\n".join(blocks)


def looks_like_geometry(user_msg: str, page_text: str | None) -> bool:
    if GEO_RE.search(user_msg):
        return True
    return bool(page_text and GEO_RE.search(page_text))


SVG_RE = re.compile(r"<svg[\s\S]*?</svg>", re.IGNORECASE)


def extract_svg(text: str) -> str:
    match = SVG_RE.search(text or "")
    return match.group(0) if match else ""


def is_coordinate_context(user_msg: str, exercise_text: str = "") -> bool:
    return bool(COORD_RE.search(user_msg) or (exercise_text and COORD_RE.search(exercise_text)))


SVG_FENCE_RE = re.compile(r"```svg\b[\s\S]*?```", re.IGNORECASE)
FIGURE_HEAD_RE = re.compile(
    r"^[ \t]*\*\*\s*(?:Hình vẽ|Hình minh họa)\s*\.?\s*\*\*[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


def strip_figures(text: str) -> str:
    """Bỏ mọi hình SVG (dùng cho bài hình có tọa độ)."""
    text = SVG_FENCE_RE.sub("", text)
    text = SVG_RE.sub("", text)
    text = FIGURE_HEAD_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def analyze_page(
    page_no: int | None, message: str, pdf_path: Path | None = None
) -> dict:
    """Cắt hình trong sách + lấy đoạn đề bài của đúng bài."""
    if page_no is None:
        return {"text": "", "figure": None}
    try:
        import figures  # import muộn: thiếu pymupdf thì app vẫn chạy
    except Exception:
        return {"text": "", "figure": None}

    label = None
    match = LABEL_RE.search(message)
    if match:
        if match.group(1):
            label = ("Bài", int(match.group(1)))
        else:
            label = ("Ví dụ", int(match.group(2)))

    try:
        return figures.analyze(page_no, label, pdf_path) if pdf_path \
            else figures.analyze(page_no, label)
    except Exception:
        return {"text": "", "figure": None}


def run_opencode(prompt: str, agent: str = AGENT) -> tuple[str, str | None]:
    """Trả về (nội_dung, thông_báo_lỗi)."""
    cmd = [
        find_opencode(), "run",
        "--agent", agent,
        "--format", "json",
        "--model", MODEL,
        prompt,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(BASE),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=REQUEST_TIMEOUT,
            creationflags=CREATIONFLAGS,
        )
    except subprocess.TimeoutExpired:
        return "", f"Hết thời gian chờ ({REQUEST_TIMEOUT}s). Vui lòng thử lại."
    except FileNotFoundError:
        return "", f"Không chạy được lệnh `{cmd[0]}`. Kiểm tra OpenCode CLI đã cài chưa."

    order: list[str] = []
    by_id: dict[str, str] = {}
    err: str | None = None

    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = event.get("type")
        if etype == "text":
            part = event.get("part") or {}
            text = part.get("text")
            if isinstance(text, str) and text:
                pid = part.get("id") or f"_anon{len(order)}"
                if pid not in by_id:
                    order.append(pid)
                by_id[pid] = text
        elif etype == "error":
            raw = event.get("error")
            err = raw.get("message") if isinstance(raw, dict) else str(raw)

    answer = "\n\n".join(by_id[pid] for pid in order).strip()

    if not answer:
        if err:
            return "", f"Lỗi từ OpenCode/provider: {err}"
        detail = (proc.stderr or "").strip()
        detail = detail[-500:] if detail else f"mã thoát {proc.returncode}"
        return "", f"Mô hình không trả về nội dung. Chi tiết: {detail}"

    return answer, err


class Handler(BaseHTTPRequestHandler):
    server_version = "ToanChatbox/1.0"
    pages: list[str] = []
    books: list[dict] = []

    def _book(self, book_id: str) -> dict | None:
        # Đọc lại mỗi request: thêm tài liệu mới không cần khởi động lại server.
        books = load_books()
        if not book_id:
            return books[0] if books else None
        for book in books:
            if book["id"] == book_id:
                return book
        return None

    def log_message(self, fmt: str, *args) -> None:  # giữ log gọn
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        # Cho phép trang chạy trên Cloudflare Worker gọi API qua tunnel.
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, ngrok-skip-browser-warning")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            if not INDEX_FILE.exists():
                self._send(500, b"Thieu index.html", "text/plain; charset=utf-8")
                return
            self._send(200, INDEX_FILE.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/health":
            self._json(200, {"ok": True, "pages": len(self.pages)})
        elif path == "/api/books":
            books = load_books()
            items = []
            for book in books:
                try:
                    count = len(book_pages(book))
                except (OSError, KeyError, json.JSONDecodeError):
                    count = 0
                items.append({
                    "id": book["id"],
                    "name": book["name"],
                    "short": book.get("short") or book["name"],
                    "pages": count,
                })
            default = books[0]["id"] if books else ""
            self._json(200, {"books": items, "default": default})
        elif path.startswith("/figures/"):
            name = path[len("/figures/"):]
            if not re.fullmatch(r"fig_[0-9a-f]{12}\.png", name):
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            file = FIGURES_DIR / name
            if not file.is_file():
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            self._send(200, file.read_bytes(), "image/png")
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")

    def _figure_response(
        self,
        message: str,
        page_no: int | None,
        page_text: str | None,
        pdf_path: Path | None,
    ) -> None:
        """Vẽ/chọn hình cho một bài (dùng cho lệnh /vehinh)."""
        info = analyze_page(page_no, message, pdf_path)
        if info.get("figure"):
            self._json(200, {
                "type": "book",
                "page": page_no,
                "url": "/figures/" + info["figure"],
            })
            return

        if not looks_like_geometry(message, page_text):
            self._json(200, {
                "type": "none",
                "page": page_no,
                "reason": "Bài này không phải dạng hình học nên không có hình để vẽ.",
            })
            return

        figure_raw, err = run_opencode(
            build_figure_prompt(message, page_no, page_text), FIGURE_AGENT
        )
        svg = extract_svg(figure_raw)
        if not svg:
            self._json(200, {
                "type": "none",
                "page": page_no,
                "reason": err or "Không vẽ được hình cho bài này.",
            })
            return
        self._json(200, {"type": "svg", "page": page_no, "svg": svg})

    def do_POST(self) -> None:
        # Luôn trả JSON: nếu handler ném lỗi thì trình duyệt không nhận body rỗng
        # (body rỗng gây "Unexpected end of JSON input" ở client).
        try:
            self._route_post()
        except Exception as exc:
            try:
                self._json(500, {"error": f"Lỗi máy chủ: {exc}"})
            except Exception:
                pass

    def _route_post(self) -> None:
        path = self.path.split("?", 1)[0]
        if path not in ("/api/ask", "/api/figure"):
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json(400, {"error": "Dữ liệu gửi lên không hợp lệ."})
            return

        raw_message = (payload.get("message") or "").strip()
        if not raw_message:
            self._json(400, {"error": "Bạn chưa nhập câu hỏi."})
            return
        message = normalize_message(raw_message)

        mode = (payload.get("mode") or DEFAULT_MODE).strip().lower()
        if mode not in MODES:
            mode = DEFAULT_MODE

        book = self._book((payload.get("book") or "").strip())
        if book is None:
            self._json(400, {"error": "Không tìm thấy tài liệu này trong thư viện."})
            return
        try:
            pages = book_pages(book)
        except (OSError, KeyError, json.JSONDecodeError):
            self._json(500, {
                "error": f"Không đọc được dữ liệu trang của “{book['name']}”."
            })
            return
        pdf_path = book_pdf(book)

        match = PAGE_RE.search(message)
        page_no = int(match.group(1)) if match else None
        page_text: str | None = None

        if page_no is not None:
            if not (1 <= page_no < len(pages)):
                self._json(400, {
                    "page": page_no,
                    "error": f"“{book['name']}” chỉ có các trang 1-{len(pages) - 1}. "
                             f"Bạn kiểm tra lại số trang nhé.",
                })
                return
            page_text = pages[page_no]

        if path == "/api/figure":
            self._figure_response(message, page_no, page_text, pdf_path)
            return

        cache_key = f"{book['id']}|{page_no}|{mode}|{message}"
        cached = cache_get(cache_key)
        if cached is not None:
            hit = dict(cached)
            hit["cached"] = True
            hit["elapsedMs"] = 0
            self._json(200, hit)
            return

        started = time.time()
        wants_figure = bool(DRAW_REQUEST_RE.search(message))
        allow_figure = wants_figure  # chỉ vẽ khi người dùng yêu cầu

        info = analyze_page(page_no, message, pdf_path)
        book_fig = info.get("figure") if allow_figure else None
        coordinate = is_coordinate_context(message, info.get("text", ""))
        geometry = looks_like_geometry(message, page_text)

        draw_ai = (
            allow_figure
            and geometry
            and not book_fig
            and (not coordinate or wants_figure)
        )

        if draw_ai:
            # Chạy song song: agent giải bài + agent vẽ hình (không phụ thuộc nhau).
            with ThreadPoolExecutor(max_workers=2) as pool:
                main_future = pool.submit(
                    run_opencode, build_prompt(message, page_no, page_text, mode), AGENT
                )
                figure_future = pool.submit(
                    run_opencode, build_figure_prompt(message, page_no, page_text), FIGURE_AGENT
                )
                answer, err = main_future.result()
                figure_raw, _figure_err = figure_future.result()
        else:
            answer, err = run_opencode(build_prompt(message, page_no, page_text, mode), AGENT)
            figure_raw = ""

        if (not allow_figure) or (coordinate and not wants_figure):
            answer = strip_figures(answer)

        svg = extract_svg(figure_raw)
        if svg and answer and "<svg" not in answer.lower():
            answer = "**Hình minh họa.**\n\n```svg\n" + svg + "\n```\n\n---\n\n" + answer

        if book_fig:
            answer = (
                "**Hình trong sách.**\n\n![Hình trong sách](/figures/%s)\n\n---\n\n" % book_fig
            ) + answer

        elapsed_ms = int((time.time() - started) * 1000)

        result = {
            "book": book["id"],
            "page": page_no,
            "pageText": page_text,
            "answer": answer,
            "mode": mode,
            "geometry": geometry,
            "coordinate": coordinate,
            "hasFigure": bool(svg) or bool(book_fig),
            "bookFigure": book_fig,
            "error": err,
            "elapsedMs": elapsed_ms,
        }
        cache_set(cache_key, dict(result))
        result["cached"] = False
        self._json(200, result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chatbox giải bài tập SGK Toán 12 - Tập 2")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    Handler.books = load_books()
    try:
        Handler.pages = book_pages(Handler.books[0])
    except (OSError, KeyError, json.JSONDecodeError):
        sys.exit(
            f"Không đọc được {Handler.books[0]['pages']}. Hãy chạy trước:\n"
            f"    python extract_pages.py\n"
            f"để tạo dữ liệu trang sách từ PDF."
        )
    url = f"http://{args.host}:{args.port}/"
    if port_in_use(args.host, args.port):
        print(f"App có vẻ đã chạy sẵn tại {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    binary = find_opencode()
    print(f"Chatbox Toán 12 - Tập 2 đang chạy tại {url}")
    print(f"Model: {MODEL}")
    for book in Handler.books:
        try:
            count = len(book_pages(book))
        except (OSError, KeyError, json.JSONDecodeError):
            count = 0
        print(f"Tài liệu: {book['name']} ({count} trang)")
    print(f"OpenCode: {binary}")
    if is_losing_shim(binary):
        print("CẢNH BÁO: đang dùng shim .cmd/.ps1; nội dung nhiều dòng có thể bị cắt.")
        print("Hãy đặt biến môi trường OPENCODE_BIN trỏ tới opencode.exe nếu lời giải thiếu dữ kiện.")
    print("Nhấn Ctrl+C để dừng.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
