# Chatbox giải bài tập SGK Toán 12 – Tập 2

Web app chạy local: gõ tên bài kèm số trang (ví dụ `bài 1a trang 5`), app trích
đúng trang sách rồi sinh **đáp án + lời giải chi tiết** bằng OpenCode CLI.

## Cách chạy

```bat
start.bat
```

hoặc

```bat
python server.py
```

Mặc định mở tại <http://127.0.0.1:8765>. Tùy chọn:

```bat
python server.py --port 9000 --no-browser
```

> **Nên chạy `start.bat` bằng cách bấm đúp** (terminal riêng), để app không bị tắt
> khi OpenCode khởi động lại. Nếu cổng đã có app chạy sẵn, `start.bat` chỉ mở
> trình duyệt chứ không báo lỗi.

## Dùng qua web công khai (Cloudflare Worker + tunnel)

Bản trên `https://sgk.ncd-congdinh2612.workers.dev` chỉ là **giao diện tĩnh**;
phần giải bài vẫn chạy trên máy bạn. Cách nối hai bên:

1. Bấm đúp `share.bat`.
2. Script khởi động `server.py` + `ngrok http 8765`. ngrok dùng domain cố định
   gắn với tài khoản (`API_DEFAULT` trong `index.html`), nên **link công khai
   không bao giờ đổi**: chỉ cần chia sẻ `https://sgk.ncd-congdinh2612.workers.dev`.
3. Giữ cửa sổ `share.bat` mở; Ctrl+C để dừng tunnel.

Đổi địa chỉ API thủ công: bấm nút **⚙** ở góc phải tiêu đề (hoặc mở link với
`?api=<url>` để ghi đè một lần).

Lưu ý: máy phải bật và 9Router/OpenCode phải chạy; request quá ~95 giây sẽ bị
Cloudflare cắt (script không tự đổi `REQUEST_TIMEOUT`, đặt biến môi trường này
nếu cần, ví dụ `set REQUEST_TIMEOUT=90`).

## Yêu cầu

- **OpenCode CLI** đã cài và đã đăng nhập provider (app gọi `opencode run`).
- **ngrok** (chỉ cần khi dùng `share.bat`): `winget install Ngrok.Ngrok`, sau đó
  `ngrok config add-authtoken <token>` và dùng domain free cố định của tài khoản.
- **Python 3.10+** (chỉ dùng thư viện chuẩn để chạy app).

## Cấu trúc

| File | Vai trò |
| --- | --- |
| `server.py` | Web server local + gọi OpenCode CLI sinh lời giải |
| `index.html` | Giao diện chat, hiển thị công thức bằng KaTeX |
| `pages.json` | Nội dung từng trang của tài liệu nguồn mặc định (`sgkII.pdf`) |
| `books.json` | Danh sách **tài liệu nguồn** công khai hiện ở cột **Thư viện kiến thức** |
| `books.local.json` | Tài liệu nguồn thêm trên máy này (không đẩy lên GitHub) |
| `add_book.py` | Thêm tài liệu nguồn mới (copy PDF + trích trang + ghi danh sách) |
| `doc_text.py` | Trích chữ từ PDF, khử lớp chữ bị lặp (cần `pymupdf`) |
| `sources/` | PDF và `pages.json` của các tài liệu thêm sau (tự sinh) |
| `sgkII.pdf` | Tài liệu nguồn đầu tiên, dùng để cắt hình và trích lại `pages.json` |
| `extract_pages.py` | Trích lại nội dung trang từ một PDF bất kỳ (cần `pymupdf`) |
| `figures.py` | Cắt hình có sẵn trong tài liệu nguồn (cần `pymupdf`) |
| `figures_cache/` | Ảnh hình đã cắt (tự sinh khi chạy) |
| `opencode.json` | Định nghĩa 2 agent: `toan` (giải bài) và `hinhve` (vẽ hình) |
| `prompt.md` | System prompt của agent `toan` |
| `figure.md` | System prompt của agent `hinhve` |
| `start.bat` | Chạy nhanh trên Windows |
| `share.bat` / `share.ps1` | Chạy server + ngrok để link web cố định hoạt động |

## Thư viện kiến thức (tài liệu nguồn)

Cột **Thư viện kiến thức** bên trái liệt kê các **tài liệu nguồn**, lấy từ hai file:

| File | Nội dung | Đẩy lên GitHub? |
| --- | --- | --- |
| `books.json` | Tài liệu công khai (đi kèm repo, ví dụ `sgkII.pdf`) | Có |
| `books.local.json` | Tài liệu thêm trên máy này (PDF nằm trong `sources/`) | **Không** |

Server gộp hai file lại (trùng `id` thì bản local thắng). Nhờ vậy repo công khai
không bị trỏ tới file PDF không tồn tại.

Ví dụ `books.json`:

```json
{
  "books": [
    {
      "id": "toan-12-t2",
      "name": "Toán 12 – Tập 2",
      "short": "Tập 2",
      "pages": "pages.json",
      "pdf": "sgkII.pdf"
    }
  ]
}
```

- `id`: mã không dấu, dùng trong API (`book`).
- `pages`: file nội dung từng trang (do `extract_pages.py` tạo).
- `pdf`: file gốc, dùng để cắt hình trong tài liệu (bỏ trống nếu không cần).
- Tài liệu đang chọn được lưu trong trình duyệt; đổi tài liệu sẽ đặt lại
  "bài gần nhất" của `/chitiet` và `/vehinh`.
- Nút **☰** trên tiêu đề để **ẩn/hiện** cột này (trượt ra vào, trạng thái được
  ghi nhớ). Trên màn hình hẹp, nút đó mở thư viện dạng ngăn kéo.
- API: `GET /api/books` trả danh sách; `/api/ask` và `/api/figure` nhận thêm
  trường `book`.

### Thêm tài liệu nguồn mới

```bat
python add_book.py "D:\sach\toan-11-tap1.pdf"
python add_book.py sach.pdf --id toan-11-t1 --name "Toán 11 – Tập 1"
```

Script làm đúng quy trình như `sgkII`:

1. Copy PDF vào `sources/<id>.pdf`.
2. Trích nội dung từng trang → `sources/<id>.pages.json` (đã khử chữ bị lặp).
3. Ghi mục vào `books.local.json` (không trùng `id`; `--force` để ghi đè).

Sau đó tải lại trang web — **không cần khởi động lại** `server.py`, vì danh sách
được đọc lại mỗi khi `books.json` / `books.local.json` thay đổi.

Tài liệu mới có ngay đủ tính năng: hỏi bài theo số trang, 4 chế độ,
`/chitiet`, `/vehinh`, cắt hình từ chính PDF của nó.

> Lưu ý: quy ước "số trang in = chỉ mục mảng" chỉ đúng với từng PDF đã kiểm tra.
> Nếu tài liệu mới bị lệch trang, kiểm tra lại bằng vài trang đầu trước khi dùng.

## Cách hoạt động

1. Người dùng gõ `bài 1a trang 5`.
2. `server.py` tách số trang bằng regex, lấy nội dung `pages[5]` từ `pages.json`.
3. Gửi khối `[TRANG 5]` + `[CÂU HỎI]` cho agent `toan` qua `opencode run`.
4. Hình chỉ xuất hiện khi người dùng **yêu cầu rõ** (gõ "vẽ hình", "minh họa"…),
   ở mọi chế độ. Khi đó: nếu trang có hình sẵn cho đúng bài (`Bài n` / `Ví dụ n`)
   thì **cắt hình đó từ PDF**; nếu không, agent `hinhve` vẽ hình SVG. Bài tọa độ
   (Oxyz, tọa độ điểm/vectơ, đường thẳng/mặt phẳng có phương trình, hệ `x=…, y=…,
   z=…`) **không vẽ hình**. Việc nhận diện dựa trên **đúng đoạn đề bài** của bài.
5. Không yêu cầu thì **không có hình** ở bất kỳ chế độ nào.
6. Trả Markdown về trình duyệt: render công thức bằng KaTeX, và biến khối
   ` ```svg ` thành hình vẽ (đã lọc bỏ script/thuộc tính nguy hiểm).
7. Câu trả lời được **cache 1 giờ**: hỏi lại đúng bài + chế độ sẽ trả về tức thì.

> **Quy ước số trang** (đã kiểm chứng với `sgkII.pdf`): số trang in ở chân trang
> **trùng** với chỉ mục 0-based trong file PDF. Nên nội dung trang in số `N` nằm ở
> `pages.pages[N]`. Ví dụ trang in 5 nằm ở phần tử `pages[5]`.
>
> Lưu ý: số trang hiển thị trên phần mềm xem PDF thường **lớn hơn 1** so với số
> trang in (do có bìa). App dùng **số trang in** – đúng như số in ở chân trang.

## Cú pháp câu hỏi

Các cách viết sau được hiểu như nhau:

- `bài 1a trang 5`
- `bài 1a/5` (dấu `/` thay cho chữ "trang")
- `bài 1a tr/5`, `bài 1a page 5`

`vd` được hiểu là `ví dụ`:

- `vd 1/156` = `ví dụ 1 trang 156`

## Chế độ trả lời

Có 4 chế độ, chuyển bằng nút ở góc trên bên phải:

| Chế độ | Nội dung |
| --- | --- |
| **Normal** (mặc định) | Ngắn gọn: công thức → thay số → kết quả, bỏ định nghĩa dài dòng. |
| **Fast** | Chỉ gồm **đề bài** + **trình bày (để chép)**, không giải thích. |
| **Kết quả** | Chỉ **đề bài** + **đáp án cuối cùng**, bỏ toàn bộ bước giải. |
| **Lí thuyết** | Chi tiết: kiến thức dùng, giải thích từng bước, lỗi thường gặp. |

- Chế độ được lưu trong trình duyệt (localStorage).
- Ở các chế độ Normal / Fast / Lí thuyết, câu trả lời kết thúc bằng mục
  **Trình bày (để chép)**: "Ta có:" rồi mỗi bước xuống dòng bắt đầu bằng "=>",
  đóng khung đáp án. Chế độ **Kết quả** không có phần này.
- Đề nhắc tới hình ("hình bên", "đồ thị như hình"…) thì hình trong sách được
  hiện kèm và gửi cho model đọc; ngoài ra hình chỉ xuất hiện khi gõ `/vehinh`.

## Lệnh nhanh

| Lệnh | Tác dụng |
| --- | --- |
| `/chitiet` | Giải lại **bài gần nhất** ở chế độ **Lí thuyết** (không đổi chế độ hiện tại). |
| `/vehinh` | Vẽ thêm hình cho **bài gần nhất** (lấy hình trong sách nếu có, không thì AI vẽ). |

Có thể kèm câu hỏi ngay sau lệnh, ví dụ `/chitiet bài 1a trang 5`, `/vehinh bài 2 trang 224`.

## Tùy chỉnh

- **Đổi model**: đặt biến môi trường `OPENCODE_TOAN_MODEL` (mặc định
  `9router/cmc/deepseek/deepseek-v4.1-flash`), ví dụ
  `set OPENCODE_TOAN_MODEL=9router/groq/openai/gpt-oss-120b` rồi chạy lại.
- **Đổi nội dung/cách giải**: sửa `prompt.md`.
- **Chặn/mở công cụ cho agent**: sửa `permissions` trong `opencode.json`.
- **Cập nhật lại dữ liệu của một tài liệu nguồn**: `python add_book.py <file.pdf> --id <id> --force`
  (hoặc `python extract_pages.py <file.pdf> <pages.json>` nếu chỉ muốn trích trang).

## Xử lý sự cố

- **Lời giải báo “trang trống” / thiếu nội dung**: app đang dùng shim `opencode.cmd`,
  mà `cmd.exe` cắt tham số tại ký tự xuống dòng. `server.py` đã tự ưu tiên
  `opencode.exe`; nếu vẫn gặp, đặt `OPENCODE_BIN` trỏ tới `opencode.exe` thật.
- **Báo “Unexpected end of JSON input” / “Máy chủ trả về dữ liệu không hợp lệ”**:
  app bị tắt hoặc khởi động lại đúng lúc đang chờ trả lời (thường do `start.bat`
  chạy trong terminal của OpenCode, rồi OpenCode restart). Bấm đúp `start.bat`
  để app có cửa sổ riêng, sau đó tải lại trang bằng `Ctrl+F5`.
- **Lỗi “Không thấy pages.json”**: chạy `python extract_pages.py` (cần `pip install pymupdf`).
- **Công thức hiện dạng thô**: máy cần Internet để tải KaTeX/marked từ CDN.

## Phạm vi

`sgkII.pdf` (SGK Toán 12 – Tập 2, Chương IV–VI) là **tài liệu nguồn** đầu tiên.
Thêm tài liệu khác bằng `python add_book.py <file.pdf>` — xem mục
**Thư viện kiến thức** ở trên. Mỗi tài liệu nguồn có nội dung trang và PDF
riêng, dùng chung một giao diện chat.
