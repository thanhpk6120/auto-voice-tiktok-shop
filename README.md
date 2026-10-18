# Auto Voice TikTok Shop LIVE (Desktop Application)

Ứng dụng Desktop tự động bắt sự kiện (comment, quà tặng, đơn hàng, follow...) từ phiên livestream TikTok Shop tại Dashboard Streamer (`https://shop.tiktok.com/streamer/live/product/dashboard`), chuyển đổi thành giọng nói (Text-To-Speech) và phát ra loa / truyền vào OBS theo hàng đợi ưu tiên realtime.

---

## 1. Đánh giá `debpalash/VoiceStudio`

- **Kho lưu trữ:** [debpalash/VoiceStudio](https://github.com/debpalash/VoiceStudio)
- **Mục đích & Kiến trúc:** 
  - Khung làm việc AI Audio local-first thay thế ElevenLabs mã nguồn mở (hơn 30k stars).
  - Backend Python (FastAPI, k2-fsa/OmniVoice) + Frontend Electron (React 19, Tailwind v4, Vite).
  - Tích hợp **17 TTS engines** (OmniVoice, CosyVoice, GPT-SoVITS, Sherpa-ONNX, KittenTTS, audio.cpp...) và **11 ASR engines** (WhisperX, Faster-Whisper, FunASR...).
  - Cung cấp sẵn Local API (OpenAI-compatible HTTP/WebSocket tại port `3900`) và MCP server.
- **Khả năng ứng dụng cho Auto Voice TikTok Shop:**
  - **Điểm mạnh:** Có thể chạy làm TTS local server (gọi qua HTTP port 3900 không cần internet), hỗ trợ voice cloning chất lượng cao.
  - **Hạn chế:**
    - Cồng kềnh: Cần GPU rời mạnh (VRAM ≥ 6-8GB) để chạy mượt các model cloning giọng (CosyVoice/GPT-SoVITS).
    - Độ trễ (latency): Các model cloning nặng có độ trễ 1-3s, khó đáp ứng đọc dồn dập khi phiên live có hàng trăm comment/phút.
    - Hỗ trợ tiếng Việt: Model mặc định chưa tối ưu riêng cho ngữ điệu bán hàng tiếng Việt bằng các mô hình chuyên biệt.

---

## 2. Các giải pháp TTS tương tự & So sánh

| Giải pháp | Cơ chế | Tiếng Việt | Voice Clone | Latency | Chi phí / Yêu cầu phần cứng | Đánh giá cho Live Shop |
|---|---|---|---|---|---|---|
| **Piper TTS** | Local (ONNX) | Rất tốt (`vi_VN-vais1000`) | Cần train trước | **< 150ms** | 0đ, chạy mượt trên CPU, RAM < 100MB | ⭐ **Tốt nhất cho Offline/Free** |
| **Edge-TTS** | Cloud (Microsoft) | Xuất sắc (`HoaiMy`, `NamMinh`) | Không | **200-400ms** | 0đ (không cần key API, cần internet) | ⭐ **Tốt nhất cho chất lượng tự nhiên + Free** |
| **Azure Speech** | Cloud (Chính thức) | Chuẩn đài truyền hình | Custom Neural | **150-300ms** | Free 0.5M ký tự/tháng (~15$/1M ký tự) | ⭐ **Ổn định nhất cho sản xuất** |
| **ElevenLabs Flash v2.5** | Cloud | Rất tự nhiên, có cảm xúc | Clone cực nhanh (10s mẫu) | **250-400ms** | Trả phí (~40-50$/1M ký tự) | Dành cho shop cần giọng clone độc quyền |
| **StyleTTS2-lite-vi** | Local | Tự nhiên, cảm xúc | Zero-shot (~3s mẫu) | **< 200ms** | GPU rời (VRAM ≥ 4GB) | Lựa chọn local nếu có card RTX |

---

## 3. Phương án đọc sự kiện từ TikTok Shop LIVE Dashboard

Khung chat tại `https://shop.tiktok.com/streamer/live/product/dashboard` là khu vực quản trị seller (có đăng nhập, bảo mật cao). Có 3 phương án lấy dữ liệu:

### Phương án A: Chrome Extension / UserScript (Khuyến nghị cho Seller Dashboard)
- **Cách hoạt động:** Cài 1 Extension nhẹ trên trình duyệt Chrome/Edge đang mở Dashboard Live của TikTok Shop. Extension đọc trực tiếp DOM hoặc bắt gói tin WebSocket của Dashboard rồi gửi qua `WebSocket local (ws://localhost:PORT)` về App Desktop.
- **Ưu điểm:** An toàn tuyệt đối 100% cho tài khoản shop (dùng chính phiên đăng nhập người dùng, không bị coi là bot/scraper, không rủi ro khóa shop/mất quyền live).
- **Nhược điểm:** Cần người dùng mở trình duyệt quản trị cùng lúc với App Desktop.

### Phương án B: Desktop App nhúng WebView2 / Chromium (All-in-one)
- **Cách hoạt động:** App Desktop tích hợp sẵn trình duyệt (WebView2 / Electron). Người dùng đăng nhập TikTok Seller ngay trong App; App tự động inject script bắt comment, ghim sản phẩm và quà tặng.
- **Ưu điểm:** Tiện lợi, chỉ cần 1 cửa sổ ứng dụng duy nhất.
- **Nhược điểm:** Tiêu tốn thêm tài nguyên RAM/CPU (khoảng 200-400MB cho WebView).

### Phương án C: TikTok-Live-Connector / TikTokLive (Public WebSocket)
- **Cách hoạt động:** Kết nối qua `unique_id` (kênh live công khai) bằng thư viện Reverse Engineering Webcast protocol (Node.js/Python).
- **Ưu điểm:** Không cần đăng nhập tài khoản Shop.
- **Nhược điểm:** Thường xuyên bị TikTok chặn/đổi proto `_signature`/Euler token; không đọc được các sự kiện nội bộ riêng của Seller Dashboard (như đơn hàng vừa thanh toán, số lượng giỏ hàng nhảy realtime).

---

## 4. Kiến trúc hệ thống đề xuất

```text
[TikTok Shop Live Dashboard] (https://shop.tiktok.com/streamer/live/product/dashboard)
           │
           ▼ (WebView2 DOM Observer & WebSocket Hook)
┌─────────────────────────────────────────────────────────────────────────────┐
│                       TAURI V2 (RUST CORE)                                  │
│                                                                             │
│  1. EVENT ANALYZER LAYER (Phân loại & Xử lý sự kiện)                        │
│     ├── Sự kiện USER JOIN:                                                  │
│     │   - Cooldown: 3s (cho phép cấu hình số giây)                          │
│     │   - Gộp chào batch nếu nhiều user vào cùng lúc                         │
│     │   - Random template: "Chào {user}", "Xin chào {user}", "Hello {user}",│
│     │     "What'up {user}", "Chào mừng {user} ghé live shop nhé!"           │
│     │                                                                       │
│     └── Sự kiện USER CHAT / COMMENT:                                        │
│         - Lọc spam, icon, icon rác                                          │
│         - Nhận diện câu hỏi sản phẩm (Intent check)                         │
│         - Lấy thông tin từ KHO CONTEXT SẢN PHẨM:                            │
│           + Đọc các file `.md` trong thư mục `context-data/`                │
│           + Tự động crawl thông tin SP đang ghim/bán trên Live Dashboard    │
│         - Gọi AI LLM (OpenAI-compatible: custom baseURL, apiKey, modelId)   │
│           sinh câu trả lời ngắn, chốt sale gán thẳng tên user               │
│                                                                             │
│  2. PRIORITY FIFO AUDIO QUEUE                                               │
│     - Ưu tiên 1: Đơn hàng mới / Quà tặng (Ngắt hoặc chèn lên đầu)           │
│     - Ưu tiên 2: Trả lời tư vấn bán hàng cho khách hỏi SP                  │
│     - Ưu tiên 3: Chào mừng user join (drop nếu dồn quá nhiều)               │
│                                                                             │
│  3. TTS CLIENT (VoiceStudio Local API @ http://127.0.0.1:3900)             │
│     - Gửi text sang VoiceStudio sinh audio buffer                           │
│                                                                             │
│  4. AUDIO ROUTER (Rodio / CPAL)                                             │
│     -> Loa ngoài / Tai nghe streamer                                        │
│     -> Virtual Audio Cable (VB-CABLE) đưa vào OBS Stream                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Kiến trúc đã chốt & Kế hoạch triển khai

### 5.1 Các quyết định đã thống nhất
1. **Khung Chat & Sự kiện:** **WebView2 nhúng trong ứng dụng Tauri**.
   - Tauri mở cửa sổ / tab nhúng WebView2 truy cập `https://shop.tiktok.com/streamer/live/product/dashboard`.
   - Cấu hình persistent user data dir trong `tauri.conf.json` để giữ phiên đăng nhập tài khoản Shop vĩnh viễn qua các lần mở app.
   - Tauri inject script (`MutationObserver` theo dõi khung chat & intercept WebSocket stream) để trích xuất comment, quà, đơn hàng và gửi về Rust core qua Tauri IPC.
2. **Lớp Phân tích Sự kiện & AI Tư vấn Bán hàng (Event Analyzer):**
   - **User Join:** 
     - Cooldown 3s (cho phép tùy chỉnh số giây trên UI).
     - Thuật toán gộp chào: gom các user join trong cửa sổ 3s thành một câu chào tự nhiên (ví dụ: *"Chào bạn A, bạn B và bạn C đã ghé live shop nha!"*).
     - Random template: *"Chào {user}"*, *"Hello {user}"*, *"Xin chào {user}"*, *"What'up {user}"*...
   - **User Chat:**
     - **Kho context sản phẩm:** Quản lý trong folder `context-data/` chứa các file markdown (`sp-01-ao-thun.md`, `sp-02-kem-duong.md`...) kèm thông tin tự động crawl từ Dashboard (tên SP, số thứ tự ghim, giá flash sale, tồn kho).
     - **LLM Engine:** Kết nối chuẩn OpenAI-compatible. Người dùng tự do cấu hình `base_url`, `api_key`, `model_id` trên giao diện Settings.
     - **Prompting:** Ép LLM trả về câu trả lời dưới 25-35 từ, tập trung vào trọng tâm câu hỏi khách, xưng hô thân thiện, chốt sale nhanh.
3. **TTS Engine:** **VoiceStudio local (GPU)**.
   - Kết nối tới VoiceStudio local API chạy ở cổng `3900` (`http://127.0.0.1:3900`).
   - Hàng đợi bất đồng bộ (Async Queue) tránh gián đoạn WebView2 khi VoiceStudio sinh voice.
4. **Desktop Tech Stack:** **Tauri v2 (Rust + React / Tailwind UI)**.
   - Native Windows WebView2 runtime, RAM app shell < 60MB.
   - Quản lý audio routing sang Virtual Audio Cable để OBS bắt được tiếng trực tiếp.

### 5.2 Lộ trình triển khai (Roadmap)
- [ ] **Giai đoạn 1:** Khởi tạo dự án Tauri v2 với Rust backend + React frontend.
- [ ] **Giai đoạn 2:** Tích hợp WebView2 persistent profile nhúng Dashboard TikTok Shop và script inject trích xuất sự kiện chat.
- [ ] **Giai đoạn 3:** Xây dựng Module `EventAnalyzer`:
  - Quản lý folder `context-data/` nạp file `.md` và crawl data SP từ DOM dashboard.
  - Cooldown + batching cho sự kiện user join (3s).
  - Client gọi LLM OpenAI-compatible sinh kịch bản tư vấn.
- [ ] **Giai đoạn 4:** Xây dựng Client kết nối VoiceStudio Local API (`localhost:3900`) và Priority Audio Queue xuất ra Virtual Audio Cable.
- [ ] **Giai đoạn 5:** Hoàn thiện giao diện Settings (Cấu hình LLM, VoiceStudio endpoint, template chào, thời gian cooldown).

## Chạy thật (Windows)

Pipeline thật: TikTok Shop Dashboard (extension) -> **event bridge** (WebSocket `ws://127.0.0.1:8765`) -> `event_analyzer` -> VoiceStudio TTS (`:3900`) -> **priority audio queue** -> loa.

### Bước 0. Cài phụ thuộc
```powershell
pip install websockets sounddevice numpy
```
- `websockets`: bridge + app client. `sounddevice`/`numpy`: phát WAV có thể **ngắt giữa chừng** (priority 1 chen ngang). Thiếu `sounddevice` thì tự lùi về `winsound` (không ngắt được).

### Bước 1. Bật VoiceStudio (TTS engine, cổng 3900)
```powershell
# Ví dụ (xem chi tiết trong docs/VOICESTUDIO-INSTALL.md)
cd vendor\VoiceStudio
start VoiceStudio.exe          # hoặc: bun run dev
```
Kiểm tra: `curl http://127.0.0.1:3900/system/info` phải trả JSON (`app_version`).

### Bước 2. Bật event bridge
```powershell
# Không cần extension (tự sinh event gia lập để test):
python src/event_bridge.py serve --port 8765 --sim --speed 1.0

# Hoặc chỉ chờ event thật từ extension:
python src/event_bridge.py serve --port 8765
```
- Bridge lắng nghe `ws://127.0.0.1:8765/ws`, hai vai trò qua query param: `?role=source` (extension gửi lên) và `?role=app` (app nhận về).

### Bước 3. Load extension vào Chrome/Edge
1. Mở `chrome://extensions` -> bật **Developer mode**.
2. **Load unpacked** -> chọn thư mục `extension/` của repo.
3. Mở dashboard `https://shop.tiktok.com/streamer/live/product/dashboard` -> extension tự bắt DOM (chat/gift/order/join) và gửi về bridge; xem log ở DevTools console (`[bridge/content]`).

Kiểm tra event có chảy qua bridge không (không cần extension):
```powershell
python scripts/run_bridge.py --duration 20          # in event nhan duoc tu bridge
python scripts/send_test_events.py --events 6       # gia lap client role=source gui event that
```
Hoặc mở `ui/index.html` bằng trình duyệt rồi bấm nút Join / Chat / Gift / Order (trang gửi thẳng vào `ws://127.0.0.1:8765/ws?role=source`).

### Bước 4. Chạy app (vòng lặp thật)
```powershell
python src/app.py run                          # nhận event tu bridge, phat ra loa
python src/app.py run --no-play                # test khong phat tieng
python src/app.py run --max-events 5           # tu dung sau 5 event
python src/app.py run --seconds 60             # tu dung sau 60 giay
python src/app.py run --sim                    # khong can bridge, dung simulator noi bo
```
Dừng bằng `Ctrl+C`; app in `=== RUN SUMMARY ===` (event nhận, câu đã đọc, TTS latency min/avg/max, thống kê queue).

### Bước 5. Chẩn đoán (doctor)
```powershell
python src/app.py doctor
```
In trạng thái: VoiceStudio health, LLM health, thiết bị loa ra, bridge (số event nhận trong cửa sổ nghe), hàng đợi ưu tiên, simulator. Exit code `0` = tất cả OK, `1` = có thành phần FAIL.

### Cấu hình (.env, tùy chọn)
| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `VOICE_URL` | `http://127.0.0.1:3900` | Endpoint VoiceStudio |
| `VOICE_MODEL` | `omnivoice` | TTS engine của VoiceStudio |
| `VOICE_NAME` | `default` | Voice profile / preset |
| `TTS_TIMEOUT` | `60` | Timeout giây cho 1 lần synthesize |
| `BRIDGE_URL` | `ws://127.0.0.1:8765/ws?role=app` | Bridge cho `run`/`doctor` |
| `AUDIO_OUTPUT_DEVICE` | (mặc định) | Index (số) hoặc một phần tên thiết bị loa |
| `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` | xem `src/config.py` | LLM OpenAI-compatible cho analyzer |

### Chạy lại đúng kết quả đã kiểm chứng
- Bằng chứng phiên chạy thật (doctor + simulate + run + phát tiếng + latency): [`docs/TEST-E2E-REAL.md`](docs/TEST-E2E-REAL.md).

## Chạy thử nhanh (không cần server)

Để chạy thử ứng dụng và kiểm tra pipeline từ sự kiện tới hàng đợi âm thanh:

1. **Chạy mô phỏng sự kiện (CLI, không cần VoiceStudio):**
   ```bash
   python src/app.py simulate --no-play
   ```
   Lệnh này mô phỏng các sự kiện (join/chat/gift/order) và in log `event -> speak_text -> wav -> priority -> queue-size` rồi in thứ tự xả hàng đợi theo ưu tiên (p1 -> p2 -> p3).

2. **Chạy toàn bộ bài test:**
   ```bash
   python scripts/run_all_tests.py
   # hoặc
   python -m pytest tests/ -q
   ```

3. **Mở giao diện Web giả lập:**
   - Mở file `ui/index.html` trực tiếp trên trình duyệt để bấm thử các nút bắn sự kiện (Join, Chat, Gift, Order).

## Build .exe (chạy trên máy khác)

Đóng gói onedir bằng PyInstaller (đã kiểm chứng: exe 5.3 MB, dist 61.2 MB):

```powershell
python scripts/build_exe.py
```

Kết quả: `dist/AutoVoiceTikTokShop/AutoVoiceTikTokShop.exe`. Copy **nguyên thư mục**
`dist/AutoVoiceTikTokShop/` sang máy khác là chạy được (máy đích: Windows 10/11 x64).

```powershell
# Mở GUI cấu hình (không tham số)
dist\AutoVoiceTikTokShop\AutoVoiceTikTokShop.exe

# Hoặc dùng CLI
dist\AutoVoiceTikTokShop\AutoVoiceTikTokShop.exe doctor
dist\AutoVoiceTikTokShop\AutoVoiceTikTokShop.exe run
dist\AutoVoiceTikTokShop\AutoVoiceTikTokShop.exe simulate --no-play
```

### Cấu hình kết nối (GUI hoặc file JSON)

GUI tkinter có form đầy đủ, chia nhóm, nút **Lưu / Kiểm tra kết nối / Khởi động / Dừng / Doctor**,
log realtime, dropdown chọn thiết bị loa:

```powershell
python src/gui.py          # chạy từ source
# hoặc: .exe không tham số
```

| Nhóm | Thông số |
|---|---|
| LLM | `llm_base_url`, `llm_api_key`, `llm_model`, `llm_timeout_s` |
| VoiceStudio TTS | `voicestudio_url`, `voicestudio_voice`, `voicestudio_model`, `tts_timeout_s` |
| Event Bridge | `bridge_url`, `bridge_port` |
| Audio & Analyzer | `audio_device`, `no_play`, `interrupt_mode` (`finish`/`interrupt`), `context_dir`, `out_dir`, `greeting_cooldown_s`, `greeting_max_batch`, `sales_max_words` |
| Trình duyệt / GoLogin | `gologin_dir`, `gologin_profiles_dir`, `gologin_active_version`, `gologin_profile_id`, `browser_mode` (`extension`/`gologin_cdp`) |
Config lưu ở `%APPDATA%\AutoVoiceTikTokShop\config.json` (không ghi vào thư mục app →
chạy được cả khi đặt trong `Program Files`). Ghi đè bằng biến môi trường
`AUTO_VOICE_CONFIG=<duong dan json>` khi cần nhiều profile.

Thứ tự ưu tiên: **file JSON → biến môi trường (.env) → DEFAULTS**.

Ví dụ `config.json`:

```json
{
  "llm_base_url": "http://192.168.1.68:20130/v1",
  "llm_api_key": "sk-...",
  "llm_model": "claude-sonnet-5",
  "voicestudio_url": "http://127.0.0.1:3900",
  "voicestudio_voice": "alloy",
  "bridge_url": "ws://127.0.0.1:8765/ws?role=app",
  "audio_device": "",
  "greeting_cooldown_s": 3.0,
  "interrupt_mode": "finish"
}
```

> **VoiceStudio không được nhúng vào `.exe`.** App là client: trỏ `voicestudio_url` tới
> VoiceStudio ở máy local hoặc máy khác trong LAN. Model OmniVoice ~2.5 GB + CUDA nên
> không đóng gói kèm được.


### Quản lý Trình duyệt GoLogin & Phiên bản Chrome

Ứng dụng tích hợp sẵn bộ quản lý trình duyệt GoLogin Offline và nhân trình duyệt Orbita Browser:

1. **Cấu hình đường dẫn & Profile:**
   - `gologin_dir`: Thư mục GoLogin (mặc định `./gologin-basic-offline`), có nút chọn thư mục trên GUI.
   - `gologin_profiles_dir`: Thư mục lưu dữ liệu profile/cookies TikTok Shop.
   - `gologin_profile_id`: Tự động quét và hiển thị danh sách profile. Nút **Mở Profile** khởi chạy Orbita với cổng CDP debug.
   - `browser_mode`:
     - `extension`: Nhận sự kiện qua Chrome Extension & WebSocket bridge.
     - `gologin_cdp`: Kết nối trực tiếp qua **Chrome DevTools Protocol (CDP)** tại cổng debug, inject observer đọc chat tự động mà **không cần cài Extension**.

2. **Quản lý Phiên bản Chrome (Tải / Xoá / Kích hoạt):**
   - Nút **Quản lý Chrome...** mở hộp thoại chuyên biệt:
     - Xem các phiên bản đã cài đặt trong máy (141, 120...).
     - **Kích hoạt** phiên bản mong muốn.
     - **Xoá** phiên bản không dùng (có cơ chế bảo vệ: không cho xoá phiên bản đang kích hoạt).
     - **Tải phiên bản mới từ GitHub Release**: Chọn phiên bản từ danh sách (141, 120, 119, 118...), tự động tải và giải nén Orbita Browser + ChromeDriver trong luồng nền.
Bằng chứng build + config override: [`docs/TEST-BUILD.md`](docs/TEST-BUILD.md).

---

## 12. Tính năng nâng cấp: Batch mới nhất, Ưu tiên cao tốc, Giỏ hàng Live & Clone giọng

### 12.1 Cơ chế gom sự kiện "chỉ lấy cái mới nhất" (Overwriting Buffer)

`BatchEventCollector` được thiết kế lại để **không tích lũy vô hạn** trong bộ nhớ:

| Loại hoạt động | Cách xử lý | Ghi chú |
|---|---|---|
| `join` / `follow` | Chỉ giữ **N người mới nhất** (mặc định 5), đè lên người cũ | Tránh lưu hàng nghìn người vào phòng |
| `viewing_product` | Giữ **1 sản phẩm mới nhất theo từng user** (dict theo user, ghi đè) | Khách đổi sản phẩm liên tục không tràn RAM |
| `order` / `gift` / `chat` | Đẩy vào hàng đợi ưu tiên + **kích hoạt fast-track** | Tạo voice ngay, không đợi hết cửa sổ |
| `grep` khác | Chỉ giữ sự kiện cuối cùng | — |

- `wait_for_batch(timeout)` thức dậy **ngay lập tức** khi có sự kiện ưu tiên cao thay vì sleep cứng 5 giây.
- `drain()` lấy toàn bộ sự kiện mới nhất và **giải phóng bộ nhớ ngay** sau mỗi chu kỳ.
- Sau khi âm thanh phát xong, callback `on_finish` báo hiệu để lấy ngay sự kiện mới nhất phát tiếp — **không chờ nhau**.

### 12.2 Thứ tự ưu tiên (không ngắt voice đang phát)

| Priority | Loại sự kiện | Hành vi |
|---|---|---|
| **1** | `order`, `gift`, `viewing_product` (đang xem sản phẩm) | Tạo voice nhanh nhất, phát **ngay sau khi câu hiện tại đọc xong** |
| **2** | `sales` (hỏi sản phẩm), `chat` | Ưu tiên vừa |
| **3** | `greeting` (chào), `remind` (nhắc tương tác) | Ưu tiên thấp, bị bỏ nếu hàng đợi > 50 |

> Chế độ mặc định `interrupt_mode = "finish"` **không bao giờ ngắt** câu đang phát. Đặt `"interrupt"` nếu muốn cắt ngang khi có đơn hàng/quà tặng.

### 12.3 Tab "Sản phẩm Live" — đồng bộ giỏ hàng

- **Tải lại giỏ hàng live:** kết nối CDP đến dashboard, quét bảng sản phẩm, hiển thị **tên + số thứ tự + giá + trạng thái ghim**.
- **Lưu vào context-live:** ghi mỗi sản phẩm thành 1 file `.md` (`sp-01-ten.md`, `sp-02-ten.md`...) vào thư mục `context_live_dir`.
- AI tự nhận diện **"mã 1", "số 2", "sp 3"** hoặc tên sản phẩm → tư vấn đúng sản phẩm, đúng giá, đúng thứ tự hiện tại.
- Đường dẫn cấu hình qua `context_live_dir` (mặc định `context-live`, có nút chọn thư mục + nút mở thư mục).

### 12.4 Nhắc tương tác định kỳ (random X–Y giây)

- `remind_enabled`: bật/tắt (mặc định **bật**).
- `remind_min_s` / `remind_max_s`: khoảng random giây giữa 2 lần nhắc (mặc định 60–120s).
- `remind_text`: nội dung câu nhắc, mặc định *"Mọi người xem lai nhớ cho sốp xin một tim và com men sản phẩm cần tư vấn nhé, sốp cảm ơn"*.
- Chỉ đọc khi hàng đợi rảnh — **không chen ngang** khách hỏi hàng/chốt đơn.

### 12.5 Tư vấn sản phẩm dài & nhiều thông tin hơn

- `sales_max_words` nâng từ 35 lên **75 từ** (cấu hình được).
- Prompt `system_sales.md` ép LLM trả lời theo **4 bước chuẩn streamer**: chào + xác nhận SP → chất liệu/ưu điểm/giải đáp → giá ưu đãi + freeship → CTA chốt đơn giỏ hàng.
- `system_batch.md` bổ sung priority 1 cho `viewing_product` và yêu cầu 50–80 từ cho câu hỏi `sales`.

### 12.6 Giao diện: tooltip + dropdown

- **Tooltip (?):** mọi biến cấu hình đều có chú thích giải thích (`settings.FIELD_DOCS`), rê chuột vào nhãn hoặc ô nhập để xem.
- **Dropdown bắt buộc chọn:** `interrupt_mode`, `browser_mode`, `log_level`, `voicestudio_model`, `voicestudio_voice` (`FIELD_OPTIONS`).
- Tab **Hướng dẫn Clone Giọng** hiển thị trực tiếp nội dung [`docs/HUONG-DAN-CLONE-GIONG.md`](docs/HUONG-DAN-CLONE-GIONG.md).

### 12.7 Clone giọng nói

Xem hướng dẫn đầy đủ tại [`docs/HUONG-DAN-CLONE-GIONG.md`](docs/HUONG-DAN-CLONE-GIONG.md): chuẩn bị file mẫu 5–15s → tạo voice trong VoiceStudio (CosyVoice / GPT-SoVITS) → đặt tên vào `voicestudio_voice` → kiểm tra bằng Simulator.
### 12.8 Bổ sung sau khi kiểm chứng end-to-end

- **Không chờ nhau:** `PriorityAudioQueue` phát xong 1 câu → callback `on_finish` gọi `collector.wake()`
  đánh thức worker batch ngay, lấy sự kiện mới nhất vừa được gom để tạo text/voice tiếp
  (không đợi hết `batch_window_s`). `drain()` clear trigger **bên trong lock** nên không mất tín hiệu.
- **Đè lên bản cũ cùng người dùng:** đơn hàng/quà tặng/chat của cùng 1 user được ghi đè — chỉ giữ bản mới nhất.
- **Chặn trần bộ nhớ:** tối đa 20 sự kiện ưu tiên cao; vượt ngưỡng thì **giữ 100% order/gift** và cắt bớt phần còn lại.
- **Phân biệt nguồn ngữ cảnh:** sản phẩm đọc từ `context_live_dir` (giỏ hàng hiện tại) được ưu tiên hơn
  `context_dir` khi hoà điểm — tư vấn luôn khớp giỏ hàng đang chạy.
- **Regex mã số linh hoạt:** nhận cả `mã 1`, `ma 1`, `số 2`, `so 2`, `sp 3`, `item 4` (kể cả không dấu).
- **Lọc "meta" của LLM:** câu trả lời đôi khi kèm `[Pre-flight] ... Action: Direct` — `strip_agent_meta()`
  tự cắt bỏ trước khi đưa cho TTS.
- **Giữ CTA khi cắt bớt câu dài:** nếu vượt `sales_max_words`, câu chốt đơn ("bấm giỏ hàng...") được giữ lại ở cuối.
