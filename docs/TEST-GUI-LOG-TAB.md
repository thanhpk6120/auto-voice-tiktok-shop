# Báo cáo Kiểm thử: Tab Log Realtime & Tab Trạng thái trong GUI (`src/gui.py`)

Ngày chạy: 2026-10-17 · Python 3.11.15 · Tk 8.6 · Windows 10/11 x64

---

## 1. Mục tiêu & Phạm vi Thay đổi

1. **Chuyển Log thành TAB trong `ttk.Notebook`**:
   - Tab **"Log đang chạy"**: Chứa `ScrolledText` log realtime thread-safe (`log_q` + `_write` + `_poll_log`). Có toolbar chức năng:
     - Dropdown **Lọc** mức log / tag (`Tất cả`, `[app]`, `[doctor]`, `[check]`, `[save]`, `[run]`, `[gui]`).
     - Checkbox **Tự cuộn** (auto-scroll, mặc định bật).
     - Nút **Xoá log**: xóa trắng màn hình log hiện hành.
     - Nút **Sao chép log**: chép toàn bộ log hiển thị vào clipboard hệ thống (`root.clipboard_clear` / `append`).
     - Nút **Mở thư mục log**: mở thư mục `logs/` bằng `os.startfile` (Windows).
   - Tab **"Trạng thái"**: Hiển thị realtime, tự cập nhật mỗi 100ms trong `_poll_log`:
     - **Tiến trình & Pipeline**: Trạng thái pipeline (*Đang dừng* / *Đang chạy* / *Đang chạy mô phỏng*), PID tiến trình con, thời gian chạy (`HH:MM:SS`).
     - **Sự kiện nhận diện (từ log)**: Đếm tự động số lượng sự kiện theo từng loại: `chat`, `gift`, `order`, `join` (bao gồm `join(flushed)`), và tổng số sự kiện.
     - **Hàng đợi âm thanh & Phát**: Kích thước hàng đợi hiện tại (`queue_size`), số audio đã phát (`played`), bị ngắt (`interrupted`), bị bỏ qua do tràn hàng đợi (`dropped`).
     - Nút **Đặt lại số đếm**: reset các bộ đếm về 0 khi bắt đầu phiên livestream mới.
   - **Bố cục cửa sổ**:
     - Thanh nút hành động chính (Lưu, Kiểm tra kết nối, Khởi động, Dừng, Mở config, Đọc lại, Doctor, Mở thư mục log, Checkbox Mô phỏng) được đặt cố định ở **dưới cùng** (`side="bottom"`), không che khuất màn hình log.
     - `ttk.Notebook` đặt ở trên và chiếm toàn bộ diện tích chính của cửa sổ (`expand=True`, `fill="both"`).
     - Các tab cấu hình (`settings.SECTIONS`: LLM, VoiceStudio TTS, Event Bridge, Audio & Analyzer, Khác) được giữ nguyên vẹn.

2. **Log realtime tiến trình con**:
   - Tiến trình con được spawn qua `subprocess.Popen` với `text=True`, `encoding="utf-8"`, `errors="replace"`, `bufsize=1`.
   - Thread `_pump` đọc từng dòng stdout (kể cả tiếng Việt có dấu) và đẩy qua `_write` vào `log_q`.

3. **Logic thuần độc lập với UI**:
   - `parse_event_line(line: str) -> dict | None`: Nhận diện `event=<type>`, `speak_text='...'`, `priority=<n>`, `queue-size=<n>`. Trả về `dict` tương ứng hoặc `None` nếu dòng không khớp.
   - `StatusCounters`: Đếm số lượng event theo loại, theo dõi `queue_size` cuối cùng, bắt các số liệu `played`, `interrupted`, `dropped` từ dòng queue stats. Phương thức `feed(line)` và `snapshot() -> dict`, hoàn toàn không phụ thuộc Tkinter.

---

## 2. Kết quả Kiểm thử Tự động (pytest)

### 2.1 Test logic trạng thái & GUI (`tests/test_gui_status.py`)
```powershell
python -m pytest tests/test_gui_status.py -v
```
Kết quả:
```
tests/test_gui_status.py::test_parse_event_line_real_sample PASSED        [ 16%]
tests/test_gui_status.py::test_parse_event_line_non_matching PASSED       [ 33%]
tests/test_gui_status.py::test_parse_event_line_variations PASSED         [ 50%]
tests/test_gui_status.py::test_status_counters_counts_by_type_and_final_queue_size PASSED [ 66%]
tests/test_gui_status.py::test_status_counters_stats_and_reset PASSED    [ 83%]
tests/test_gui_status.py::test_gui_notebook_tabs_and_actions PASSED       [100%]

============================== 6 passed in 0.50s ==============================
```

Chi tiết test cases:
1. `test_parse_event_line_real_sample`: Kiểm tra dòng thật từ app `[app] event=chat -> speak_text='Shop chưa có dữ liệu size cho áo này' -> wav=... -> priority=2 -> queue-size=7`. Parse chính xác `event="chat"`, `priority=2`, `queue_size=7`, và đúng chuỗi tiếng Việt.
2. `test_parse_event_line_non_matching`: Kiểm tra các dòng không phải event log (`Starting simulation...`, `tiến trình kết thúc`, `config: ...`, `--- doctor ---`) đều trả về `None`.
3. `test_parse_event_line_variations`: Parse chuẩn xác nháy kép (`"What'up Minh Tuấn!"`), trường hợp không có priority (`join(flushed)`), trường hợp có `[no-play]`.
4. `test_status_counters_counts_by_type_and_final_queue_size`: Đếm đúng theo từng loại (`chat=2`, `gift=1`, `order=1`, `join=2`), tổng sự kiện = 6, và `queue_size` lấy giá trị cuối cùng (= 9).
5. `test_status_counters_stats_and_reset`: Cập nhật đúng stats `played=5`, `interrupted=2`, `dropped=1`, hàm `reset()` xóa sạch về 0.
6. `test_gui_notebook_tabs_and_actions`: Kiểm tra tích hợp Tkinter thật (headless withdraw), xác nhận sự hiện diện của tab "Trạng thái", tab "Log đang chạy", các nút trên toolbar, tính năng lọc log động và cập nhật trạng thái UI.

### 2.2 Toàn bộ Test Suite của dự án
```powershell
python -m pytest tests/ -q
```
Kết quả:
```
...................................................                      [100%]
51 passed in 115.08s
```
Tất cả 51 tests cũ và mới đều **xanh 100%**.

---

## 3. Bằng chứng Build lại Exe (`scripts/build_exe.py`)

Thực hiện lệnh:
```powershell
python scripts/build_exe.py
```
Output:
```
$ python.exe -m PyInstaller --noconfirm --log-level WARN I:\AI\auto-voice-tiktok-shop\build.spec
INFO: PyInstaller: 6.22.3, contrib hooks: 2026.8
INFO: Python: 3.11.15
INFO: Platform: Windows-10-10.0.26200-SP0

=== BUILD XONG ===
exe          : I:\AI\auto-voice-tiktok-shop\dist\AutoVoiceTikTokShop\AutoVoiceTikTokShop.exe
exe size     : 5.3 MB
dist size    : 61.3 MB
copy them    : context-data, ui, requirements.txt, .env.example, docs/
config mau   : config.json (DEFAULTS)
thoi gian    : 21s
```

---

## 4. Xác nhận Thực tế trên Executable (`AutoVoiceTikTokShop.exe`)

Đã chạy `dist\AutoVoiceTikTokShop\AutoVoiceTikTokShop.exe` thực tế và xác nhận:
1. **Tìm kiếm cửa sổ qua Windows API**:
   - Sử dụng `ctypes.windll.user32.EnumWindows` duyệt danh sách top-level windows.
   - Tìm thấy cửa sổ tương ứng với PID của tiến trình .exe:
     - `HWND: 396140` (hoặc `461654`)
     - `Window Title: Auto Voice TikTok Shop - Cấu hình`
2. **Kiểm tra trực quan và chụp ảnh giao diện**:
   - Ảnh chụp toàn cảnh cửa sổ GUI từ bản build: `docs/gui_tabs_screenshot.png`
   - Ảnh chụp tab **"Trạng thái"**: `docs/gui_tab_status.png` (hiển thị đầy đủ 3 nhóm: Tiến trình & Pipeline, Sự kiện nhận diện, Hàng đợi & Phát âm)
   - Ảnh chụp tab **"Log đang chạy"**: `docs/gui_tab_log.png` (hiển thị toolbar với Combobox Lọc, Checkbox Tự cuộn, Xoá log, Sao chép log, Mở thư mục log và màn hình log)

---

## 5. Kết luận

- Toàn bộ yêu cầu của bài toán đã hoàn thành đầy đủ, đạt độ ổn định cao.
- Không phát sinh hồi quy, giữ nguyên toàn bộ kiến trúc và tính tương thích với các module khác.
- File exe đóng gói hoạt động chính xác và hiển thị các tab realtime như thiết kế.
