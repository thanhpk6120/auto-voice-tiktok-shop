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
- `remind_text`: câu nhắc gốc, mặc định *"Mọi người xem lai nhớ cho sốp xin một tim và com men sản phẩm cần tư vấn nhé, sốp cảm ơn"*.
- Chỉ đọc khi hàng đợi rảnh — **không chen ngang** khách hỏi hàng/chốt đơn.

**Bộ 10 câu nhắc khác nhau (`src/remind_text.py`)**

Từ câu gốc, app sinh thêm **9 câu khác** (tổng 10) rồi phát ngẫu nhiên, không lặp:

| Bước | Xử lý |
|---|---|
| 1 | Gọi LLM (`llm_base_url`/`llm_model`) viết lại câu gốc thành 9 cách nói khác nhau |
| 2 | LLM lỗi/offline → dựng 9 biến thể cục bộ từ chính câu gốc (openers × hành động × kết câu) |
| 3 | Cache bộ 10 câu vào `local_cache/pool_remind.json` theo **signature = nội dung câu gốc**; đổi `remind_text` mới sinh lại |
| 4 | Mỗi lần phát, `phrase_cache.pick_unused` chọn câu **chưa nằm trong 10 lần phát gần nhất** |

### 12.5 Tư vấn sản phẩm dài & nhiều thông tin hơn

- `sales_max_words` nâng từ 35 lên **75 từ** (cấu hình được).
- Prompt `system_sales.md` ép LLM trả lời theo **4 bước chuẩn streamer**: chào + xác nhận SP → chất liệu/ưu điểm/giải đáp → giá ưu đãi + freeship → CTA chốt đơn giỏ hàng.
- `system_batch.md` bổ sung priority 1 cho `viewing_product` và yêu cầu 50–80 từ cho câu hỏi `sales`.

### 12.6 Giao diện: tooltip + dropdown

- **Tooltip (?):** mọi biến cấu hình đều có chú thích giải thích (`settings.FIELD_DOCS`), rê chuột vào nhãn hoặc ô nhập để xem.
- **Dropdown bắt buộc chọn:** `interrupt_mode`, `browser_mode`, `log_level`, `voicestudio_model`, `voicestudio_voice` (`FIELD_OPTIONS`).
- Tab **Hướng dẫn Clone Giọng** hiển thị trực tiếp nội dung [`docs/HUONG-DAN-CLONE-GIONG.md`](docs/HUONG-DAN-CLONE-GIONG.md).

### 12.7 Clone giọng nói

Xem hướng dẫn đầy đủ tại [`docs/HUONG-DAN-CLONE-GIONG.md`](docs/HUONG-DAN-CLONE-GIONG.md): chuẩn bị file mẫu 5–15s → tạo voice trong VoiceStudio (CosyVoice / GPT-SoVITS) → chọn giọng trong dropdown → kiểm tra bằng Simulator.

**Tên giọng vs mã giọng (lỗi hay gặp nhất)**

VoiceStudio 0.5.6 chỉ nhận **voice_id** của giọng clone (mã ngắn như `ef920857`) trong `/v1/audio/speech`;
truyền **tên** (`SonTungMTP`) **không gây lỗi** nhưng VoiceStudio lặng lẽ đọc bằng giọng mặc định —
nghe như "clone rồi mà không giống".

App xử lý việc này ở `tts_client`:

| Hàm | Việc |
|---|---|
| `list_voices()` | Đọc `/v1/audio/voices`, tách `aliases` (OpenAI) và `profiles` (giọng đã clone), cache theo URL |
| `resolve_voice(name)` | Tên duy nhất → đổi sang `voice_id`; đã là `voice_id`/alias → giữ nguyên; không tồn tại → trả cảnh báo |
| `synthesize()` | Gọi `resolve_voice` trước khi POST, in cảnh báo ra log nếu tên sai |

GUI: dropdown `voicestudio_voice` lấy **danh sách động** từ VoiceStudio, giọng clone hiển thị dạng
`Tên  <voice_id>`; khi lưu chỉ ghi **voice_id trần**; nút **🔄 Làm mới** đọc lại sau khi tạo giọng mới.
`doctor` in thêm `voice='...' -> <voice_id>`, và trả **FAIL kèm cảnh báo** nếu tên không tồn tại.

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
- **Simulator sinh đủ 6 loại sự kiện:** thêm `viewing_product` vào `event_simulator.py` để test được luồng ưu tiên P1 tại chỗ (`--sim`).

---

## 13. Tính năng nâng cấp: Crawl sản phẩm, Phân loại ý định & Prompt JSON

> **Nguyên tắc dữ liệu:** mọi câu thoại sinh ra đều phải bám **context-live hiện tại**.
> `context-data/` chỉ là dự phòng khi `context-live/` rỗng. Không có prompt mẫu, câu chào
> fallback hay dữ liệu simulator nào chứa sẵn tên sản phẩm/giá — nếu không LLM sẽ đọc
> quảng cáo món khách không hề nhắc.


### 13.1 Danh sách sản phẩm Live đọc từ browser (không dùng AI)

Nút **🔄 Tải lại giỏ hàng live** (tab *Sản phẩm Live*) đọc dashboard
`https://shop.tiktok.com/streamer/live/product/dashboard` bằng 2 lớp:

1. **Nguồn chính — gọi lại `/live_product/list` ngay trong tab dashboard.**
   Lấy URL đã ký (`msToken`/`X-Bogus`) từ `performance.getEntriesByType('resource')` rồi
   `fetch` lại với cookie của trang. **Không reload** nên không gián đoạn phiên live.
   Khoá dữ liệu là `data.products` (không phải `list`/`items`).
   Kết quả: **35 sản phẩm** có `product_id`, giá, tồn kho, shop trong ~1 giây.
   *(Nếu chữ ký đã hết hạn: bắt response qua CDP `Network.getResponseBody` khi trang tự tải lại.)*
2. **Dự phòng — quét DOM virtual list.** Dashboard mới không dùng `<tr>`/`arco-table-tr` nữa
   mà là `div.rounded-4.mb-8` (~90–200px) bên trong `[class*="virtualized-container"]`.
   DOM có tên + giá + "Còn: ..." + "Lựa chọn yêu thích" nhưng **không có product_id**,
   nên lớp này chỉ dùng khi chưa bắt được API.

Trả về dict:

| Trường | Nguồn lấy |
|---|---|
| `index` | thứ tự trong danh sách API (hoặc DOM) |
| `id` | `product_id` từ API; rỗng ở chế độ DOM dự phòng |
| `name` | `title` từ API; hoặc dòng text dài đầu tiên trong row DOM |
| `price` | `format_available_price` (giá niêm yết giỏ hàng ban đầu) |
| `is_pinned` | chuẩn xác từ `introduce_id` của API (chỉ tối đa 1 sản phẩm ghim trên live, không nhầm với nhãn "Lựa chọn yêu thích") |
| `url` | `https://shop.tiktok.com/view/product/<id>` |
| `has_context` | `true` nếu sản phẩm đã có file context-live (do lần *Load context-live* trước sinh ra) |
| `real_price` | giá khuyến mại đã lưu trong context-live (nếu có) — **được ưu tiên đè lên `price`** |

**Ưu tiên giá:** giá niêm yết lấy từ giỏ hàng chỉ là giá tạm. Khi cache giỏ hàng được nạp
(mở app) hoặc sau mỗi lần **🔄 Tải lại giỏ hàng live**, app gọi `merge_context_prices()` để
**nạp lại giá khuyến mại đã lưu** trong `context-live/*.md` cho các sản phẩm đã có context.
Nhờ vậy bảng luôn hiển thị đúng giá sale của lần *Load context-live* trước, không bị giá
niêm yết của giỏ hàng đè mất. Cột **Context-live** trong bảng hiển thị `✅ Đã có` / `— Chưa có`.

Nếu **🔄 Tải lại giỏ hàng live** không đọc được sản phẩm (trình duyệt chưa mở dashboard, CDP
chưa bật), bảng **giữ nguyên** danh sách đã nạp thay vì bị xoá trắng.

**Không gọi AI** ở bước này, và **không reload** tab dashboard — bấm nút giữa live vẫn an toàn.
Danh sách sản phẩm được tự động lưu vào cache (`_products_cache.json` trong thư mục `context-live`). Lần sau mở app, toàn bộ sản phẩm và giá bán sẽ được nạp sẵn ngay lập tức mà không cần quét lại.

### 13.2 Nút **📥 Load context-live** — Lấy giá khuyến mại thực tế & mô tả

Thay cho nút *Lưu vào context-live* cũ. Với từng sản phẩm trong bảng:

1. Nhúng PDP vào **iframe ẩn cùng-origin trong tab dashboard** (không mở tab mới —
   tab mới dính trang "Security Check" slide của TikTok), chờ load rồi đọc DOM.
2. **Lấy giá khuyến mại thực tế trên live:** Giá hiển thị trên giỏ hàng ban đầu chỉ là giá niêm yết;
   khi mở PDP, hệ thống trích xuất **giá khuyến mại thực tế** (`real_price`), **giá gốc** (`origin_price`),
   và **tỷ lệ giảm giá** (`discount`, ví dụ: giảm -87%). Giá này được cập nhật ngay lên bảng giao diện app.
3. Lấy **tên**, **mô tả sản phẩm**, và **tối đa 10 comment/đánh giá đầu tiên**
   (nếu trang ít hơn thì lấy hết những gì có, kể cả 0).
4. Ghi ra `context-live/` với tên file suy ra **từ tên sản phẩm** (slug bỏ dấu), ghi rõ giá khuyến mại
   và hướng dẫn AI tư vấn chuẩn giá sale cho khách.

**Xử lý trùng khi nạp context-live:** Nếu sản phẩm đã có sẵn file context trong thư mục, hệ thống sẽ hiện hộp thoại hỏi lựa chọn:
- **Ghi đè:** Tải lại thông tin chi tiết và ghi đè sản phẩm hiện tại.
- **Bỏ qua:** Giữ nguyên file cũ, đọc lại giá đã lưu để hiển thị lên bảng, không tốn thời gian tải lại.
- **Ghi đè tất cả:** Áp dụng ghi đè cho toàn bộ các sản phẩm đã có mà không hỏi lại.
- **Bỏ qua tất cả:** Áp dụng bỏ qua cho toàn bộ các sản phẩm đã có mà không hỏi lại (chỉ tải các sản phẩm mới).

**Chống trùng file:** file chỉ mục `context-live/_index.json` giữ khoá `<id>||<slug>`, giá trị là tên file.

| Trường hợp | Kết quả |
|---|---|
| Trùng **cả tên và id** | **Ghi đè** đúng file cũ, không tạo file mới |
| Cùng **tên** nhưng **khác id** | 2 sản phẩm khác nhau → file thứ hai thêm hậu tố `-<id>` |
| Khác tên | Tạo file mới |

Tên file suy ra **từ tên sản phẩm** (`kem-duong-da-cap-am-water-gel.md`), không dùng tiền tố thứ tự giỏ hàng.
`context-live/README.md` và `_products_cache.json` được bỏ qua khi nạp ngữ cảnh, không bị coi là sản phẩm.

### 13.3 Phân loại ý định bằng model AI cấu hình được (`analyst_llm_model`)

Luồng: **bình luận → phân loại ý định → chọn đúng prompt → gọi LLM → đọc JSON**.

Áp dụng cho **cả hai đường xử lý**:

| Đường | Hàm | Cách dùng prompt |
|---|---|---|
| Xử lý từng sự kiện | `event_analyzer.analyze()` → `answer_by_intent()` | 1 sự kiện → 1 prompt theo ý định |
| Xử lý theo lô (đường `app.py` chạy) | `batch_processor.process_event_batch()` | **nhóm sự kiện theo ý định**, mỗi nhóm gọi LLM 1 lần với prompt của nhóm đó |

**Nhóm theo ý định không làm tăng số lời gọi LLM:** số lời gọi = số ý định *có mặt trong lô*
(tối đa 6), không phải số sự kiện. Ví dụ lô 12 sự kiện gồm 3 order + 2 gift + 5 chat hỏi hàng
+ 2 join → chỉ **4 lời gọi** (`system_order`, `system_gift`, `system_sales`, `system_greeting`)
thay vì 12.

`group_events_by_intent()` ánh xạ: `order`→order, `gift`→gift, `join`→greeting,
`viewing_product`→product_question (khách đang xem = quan tâm sản phẩm), `chat`→phân loại theo
nội dung. Sau khi LLM trả về, `type` và `priority` được **ép lại theo nhóm** để LLM không hạ ưu tiên
của đơn hàng/quà tặng.

| Ý định | Prompt dùng | Ưu tiên |
|---|---|---|
| `greeting` | `system_greeting` | chat: 2, join: 3 |
| `product_question` | `system_sales` | 2 |
| `order` | `system_order` | 1 |
| `gift` | `system_gift` | 1 |
| `chat` / `other` | `system_chat` | 2 |

- Model phân tích đặt ở cấu hình `analyst_llm_model` (ví dụ `openrouter/typesafe/jev-router`),
  timeout ở `analyst_llm_timeout_s`. Để trống → tắt AI, dùng **luật từ khoá dự phòng**
  (`classify_intent_rules`).
- Khi model phân tích lỗi (ví dụ gateway trả `429 Too Many Requests`), log ghi rõ lý do qua
  `intent_router.last_analyze_error()` và tự động chuyển sang luật dự phòng — không làm dừng phiên live.
- Gặp `429` thì **tạm hoãn gọi model phân tích 30 giây** (`rate_limit_remaining_s()` cho biết còn bao lâu)
  để không dội thêm request vào server đang giới hạn tần suất. Hết thời gian hoãn sẽ tự thử lại.
  Đây là backoff nhẹ, không có tầng cache/retry phức tạp.
- Câu hỏi sản phẩm: dò sản phẩm trong **context-live** — nguồn **duy nhất** khi thư mục này
  đã có sản phẩm. `context-data` chỉ được nạp khi `context-live` rỗng (chưa đồng bộ giỏ hàng
  live), nên sản phẩm demo (`sp-01-ao-thun`, `sp-02-kem-duong`, `sp-03-tai-nghe`) không bao giờ
  lẫn vào câu trả lời trên live thật.

### 13.4 Tab **Quản lý Prompt** (sửa prompt ngay trong app)

- Combobox chọn prompt → `ScrolledText` hiển thị nội dung → **💾 Lưu prompt** ghi thẳng ra `prompts/*.md`
  (có hiệu lực ở lần gọi LLM kế tiếp).
- Nút **⬇ Tải danh sách model** gọi `/v1/models` của server LLM, đổ vào dropdown (gồm cả model `jev`;
  đã kiểm chứng tải được 1184 model từ gateway nội bộ).
- Nút **💾 Lưu model** ghi `analyst_llm_model` vào file cấu hình, áp dụng ngay, **và đồng bộ sang ô
  cấu hình tương ứng ở tab LLM** để lần "Lưu cấu hình"/"Bắt đầu" sau không ghi đè mất giá trị vừa chọn.

### 13.5 Mọi prompt đều "only JSON" + có JSON mẫu

7 prompt: `system_analyzer`, `system_greeting`, `system_sales`, `system_order`, `system_gift`,
`system_chat`, `system_batch`. Mỗi prompt đều yêu cầu **chỉ trả về JSON** và **kèm JSON mẫu**
để model bám theo. `intent_router.build_speak_prompt()` tự ghép phần ràng buộc JSON vào prompt nền.

**Dự phòng khi thiếu file prompt:** nếu `prompts_dir` sai/không đọc được, `get_prompt()` trả về
prompt dựng sẵn trong code cho **cả 7 prompt** — cũng only-JSON, có JSON mẫu, tiếng Việt có dấu,
và ép LLM tự xưng `"sóp"` để giọng đọc luôn đúng vai streamer.

**Ép tự xưng:** mọi prompt sinh câu thoại đều bắt buộc có chữ `"sóp"` và cấm LLM tự gọi mình là
"trợ lý"/"AI". Ngoài ra `phoneticize_vietnamese()` phiên âm `shop`/`sop` → `sóp` trước khi đưa vào TTS,
nên dù LLM có trả về "shop" thì giọng đọc vẫn đúng.

Đọc kết quả bằng `src/json_utils.py` — chịu được mọi kiểu JSON lỗi thường gặp của LLM:

| Lỗi LLM hay mắc | Cách xử lý |
|---|---|
| Bọc trong ```` ```json ... ``` ```` | `strip_code_fence()` |
| Có lời dẫn/lời kết quanh JSON | `extract_json_block()` cắt khối cân bằng ngoặc |
| Nháy đơn `'value'` | `_single_to_double()` |
| Key/giá trị không nháy `{ type: greeting }` | regex thêm nháy, loại trừ literal JSON |
| Dấu phẩy thừa `[...,]` | regex bỏ phẩy trước `}` `]` |
| `True`/`False`/`None`/`NaN` | đổi về `true`/`false`/`null` |
| Nháy cong `“ ”` | map về nháy thẳng |
| Xuống dòng thật trong chuỗi | escape thành `\n` |
| Comment JS, BOM, ký tự điều khiển | loại bỏ |
| JSON kiểu Python | fallback `ast.literal_eval` |

Trợ giúp đọc khoá: `get_str`, `get_int`, `get_bool` chấp nhận nhiều tên khoá (kể cả tiếng Việt
có dấu) và tự ép kiểu.

### 13.6 Sản phẩm khách đang xem & **yêu cầu minh họa** (`viewing_product`)

**Yêu cầu minh họa:** khách bấm nút *Yêu cầu minh họa* ở giỏ hàng → dashboard hiện dòng
`Thanh muốn xem minh họa sản phẩm Sói 🐺`. Dòng này được nhận diện **trước** các nhánh
`order`/`gift` (vì chứa cả chữ "sản phẩm" lẫn "xem sản phẩm"), rồi xử lý:

| Bước | Xử lý |
|---|---|
| 1 | `CDP_SETUP_JS` / `extension/content.js`: regex `minh họa sản phẩm` → `type=viewing_product`, tách tên món |
| 2 | `analyze()` (nhánh `chat`): bắt lại cùng regex phòng khi extension/CDP cũ chỉ gửi `chat` |
| 3 | Bóc emoji khỏi tên món (`_strip_emoji`) — `"Sói 🐺"` → `"Sói"` |
| 4 | `ChatIntent.match()` đối chiếu **context-live** |
| 5 | Khớp → `generate_by_intent(..., "product_question", product=matched)` tư vấn đúng món |
| 6 | **Không khớp → không gọi LLM**, trả lời "sóp chưa thấy món X trong giỏ hàng lai hiện tại" |

Ưu tiên `1` (ngang order/gift) nên chen ngang được câu chào đang chờ.

**Bộ lọc nhiễu (`isJunk`)**: danh sách nhãn UI đổi từ khớp **tiền tố** sang khớp **chính xác**
+ tiền tố chỉ khi dòng ngắn (`JUNK_PREFIX_MAX = 22`). Trước đây `startsWith('sản phẩm')`
nuốt mất comment thật như *"Sản phẩm này còn hàng không shop?"*.

### 13.7 Chống lặp câu chào (`src/phrase_cache.py`)

Mọi câu chào đã phát được ghi vào `local_cache/recent_greeting.json` (giữ đúng **10 câu gần nhất**).

| Điểm chặn | Cách xử lý |
|---|---|
| LLM sinh câu chào (`generate_by_intent` intent `greeting`) | Chèn khối *"10 CÂU GẦN NHẤT ĐÃ DÙNG … TUYỆT ĐỐI KHÔNG lặp lại"* vào **user prompt** trước khi gọi LLM |
| Batch (`process_event_batch`, nhóm `greeting`) | Cùng khối `avoid_block` chèn vào `ctx_str` gửi LLM |
| `GreetingBatcher.flush` (gộp nhiều người vào cùng lúc) | Chọn mẫu **chưa dùng** trong 10 câu gần nhất (`pick_unused`) |
| Câu đáp nhanh "shop ơi / alo" | `pick_unused` trên 4 mẫu, hết mẫu mới lặp |
| LLM lỗi hoàn toàn | `_greeting_fallback` có **10 mẫu**, cũng chọn theo `pick_unused` |
| Remind | `local_cache/recent_remind.json` giữ 10 câu nhắc gần nhất |

Sau khi phát, `phrase_cache.remember(kind, text)` ghi lại (chống ghi trùng liền kề nhau).
Chuẩn hoá so trùng: bỏ dấu câu, gộp khoảng trắng, lowercase — nên "Chào A!" và "chào a" tính là trùng.

> So sánh câu chào mới với 10 câu cũ được làm **hai lớp**: (1) LLM được yêu cầu tránh, (2) cache
> vẫn ghi nhận để lần sau danh sách "cấm" được cập nhật.

### 13.8 Ngôn ngữ trong app

Toàn bộ chuỗi hiển thị (log, tooltip, label, hộp thoại, `--help`) dùng **tiếng Việt có dấu**:

- **34/34 tooltip** cấu hình trong `settings.FIELD_DOCS` đều có dấu.
- Log CLI (`[run]`, `[doctor]`, `[browser]`, `[BRIDGE]`, `[settings]`) đã Việt hoá có dấu.
- Thuật ngữ kỹ thuật giữ nguyên: `TTS`, `bridge`, `CDP`, `join`, `no-play`, `LLM`.

