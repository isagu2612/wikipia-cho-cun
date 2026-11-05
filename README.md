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
2. Script khởi động `server.py` + `cloudflared`, rồi in ra link dạng
   `https://sgk.ncd-congdinh2612.workers.dev/?api=https://xxx.trycloudflare.com`
   và copy sẵn vào clipboard.
3. Mở link đó (hoặc gửi cho người khác). Trình duyệt tự lưu địa chỉ API vào
   `localStorage`; lần sau chỉ cần mở link gốc.
4. Giữ cửa sổ `share.bat` mở. Tunnel đổi URL mỗi lần chạy → chạy lại script và
   dùng link mới.

Đổi địa chỉ API thủ công: bấm nút **⚙** ở góc phải tiêu đề.

Lưu ý: máy phải bật và 9Router/OpenCode phải chạy; request quá ~95 giây sẽ bị
Cloudflare cắt (script không tự đổi `REQUEST_TIMEOUT`, đặt biến môi trường này
nếu cần, ví dụ `set REQUEST_TIMEOUT=90`).

## Yêu cầu

- **OpenCode CLI** đã cài và đã đăng nhập provider (app gọi `opencode run`).
- **cloudflared** (chỉ cần khi dùng `share.bat`): `winget install Cloudflare.cloudflared`.
- **Python 3.10+** (chỉ dùng thư viện chuẩn để chạy app).

## Cấu trúc

| File | Vai trò |
| --- | --- |
| `server.py` | Web server local + gọi OpenCode CLI sinh lời giải |
| `index.html` | Giao diện chat, hiển thị công thức bằng KaTeX |
| `pages.json` | Nội dung từng trang sách, đã trích sẵn từ `sgkII.pdf` |
| `sgkII.pdf` | Sách gốc, dùng để cắt hình trong sách và trích lại `pages.json` |
| `extract_pages.py` | Tạo lại `pages.json` từ PDF (cần `pymupdf`) |
| `figures.py` | Cắt hình có sẵn trong SGK (cần `pymupdf`) |
| `figures_cache/` | Ảnh hình đã cắt (tự sinh khi chạy) |
| `opencode.json` | Định nghĩa 2 agent: `toan` (giải bài) và `hinhve` (vẽ hình) |
| `prompt.md` | System prompt của agent `toan` |
| `figure.md` | System prompt của agent `hinhve` |
| `start.bat` | Chạy nhanh trên Windows |
| `share.bat` / `share.ps1` | Chạy server + tunnel, in link web có `?api=` |

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

Có 3 chế độ, chuyển bằng nút ở góc trên bên phải:

| Chế độ | Nội dung |
| --- | --- |
| **Normal** (mặc định) | Ngắn gọn: công thức → thay số → kết quả, bỏ định nghĩa dài dòng. |
| **Fast** | Chỉ gồm **đề bài** + **trình bày (để chép)**, không giải thích. |
| **Lí thuyết** | Chi tiết: kiến thức dùng, giải thích từng bước, lỗi thường gặp. |

- Chế độ được lưu trong trình duyệt (localStorage).
- Mọi câu trả lời đều kết thúc bằng mục **Trình bày (để chép)**:
  bản viết gọn: "Ta có:" rồi mỗi bước xuống dòng bắt đầu bằng "=>", đóng khung đáp án.
- Hình chỉ xuất hiện khi người dùng yêu cầu (xem lệnh `/vehinh`).

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
- **Cập nhật lại dữ liệu sách** (khi có bản PDF mới): `python extract_pages.py đường\đẫn\sgkII.pdf`.

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

Hiện chỉ hỗ trợ **SGK Toán 12 – Tập 2** (`sgkII.pdf`, Chương IV–VI).
Muốn thêm Tập 1 (`sgk.pdf`), chạy `extract_pages.py` cho file đó và bổ sung
bộ chọn tập trong `index.html` + `server.py`.
