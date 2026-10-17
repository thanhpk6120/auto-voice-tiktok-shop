# TEST-BUILD — Bằng chứng build .exe (onedir) và cấu hình kết nối

Môi trường: Windows 10 (10.0.26200), Python 3.11.15, PyInstaller 6.22.3, tkinter 8.6.

## 1. Build

```powershell
python scripts/build_exe.py
```

Output thật:

```text
$ ... -m PyInstaller --noconfirm --log-level WARN I:\AI\auto-voice-tiktok-shop\build.spec
241 INFO: PyInstaller: 6.22.3, contrib hooks: 2026.8
241 INFO: Python: 3.11.15
261 INFO: Platform: Windows-10-10.0.26200-SP0

=== BUILD XONG ===
exe          : I:\AI\auto-voice-tiktok-shop\dist\AutoVoiceTikTokShop\AutoVoiceTikTokShop.exe
exe size     : 5.3 MB
dist size    : 61.2 MB
copy them    : context-data, ui, requirements.txt, .env.example, docs/
config mau   : config.json (DEFAULTS)
thoi gian    : 21s
```

Cấu trúc `dist/AutoVoiceTikTokShop/`:

```text
AutoVoiceTikTokShop.exe     5.3 MB   <- GUI khi chay khong tham so; CLI khi co tham so
_internal/                           <- Python runtime + sounddevice/numpy/websockets/tkinter
context-data/                        <- copy tu repo, nguoi dung sua duoc
ui/
config.json                          <- config mau (DEFAULTS)
.env.example
requirements.txt
docs/
```

Tổng 61.2 MB. Copy nguyên thư mục `dist/AutoVoiceTikTokShop/` sang máy khác là chạy được
(máy đích cần Windows 10/11 x64; WebView2 runtime co san tren Win11).

## 2. Config tách khỏi app (để chạy trên máy khác)

Thứ tự ưu tiên khi đọc cấu hình (`src/settings.py`):

1. File JSON: `AUTO_VOICE_CONFIG` env → hoặc `%APPDATA%\AutoVoiceTikTokShop\config.json`
2. Biến môi trường (`.env` / `os.environ`)
3. `DEFAULTS` trong `settings.py`

Config **không** ghi vào thư mục app (vì `Program Files` chỉ đọc). Nhờ đó bản `.exe`
chạy được trên máy khác mà không cần quyền admin.

## 3. Bằng chứng exe chạy thật (frozen)

### 3a. CLI help

```text
$ dist\AutoVoiceTikTokShop\AutoVoiceTikTokShop.exe --help
[launcher] console=stdout-ready exe=I:\AI\auto-voice-tiktok-shop\dist\AutoVoiceTikTokShop\AutoVoiceTikTokShop.exe
usage: AutoVoiceTikTokShop.exe [-h] {simulate,run,doctor,live,stop} ...
EXIT=0
```

`ensure_console()` tự gắn vào console cha → chạy từ terminal vẫn thấy output dù build `console=False`.

### 3b. `--internal simulate` (vòng pipeline thật)

```text
$ dist\...\AutoVoiceTikTokShop.exe --internal simulate --no-play
Starting simulation... (no_play=True)
Simulation done. queue-size=7
Drain order (priority): p1:gift, p1:gift, p1:order, p2:sales, p2:sales, p2:sales, p3:greeting
```

Thứ tự drain đúng thiết kế ưu tiên: p1 (order/gift) → p2 (sales) → p3 (greeting).

### 3c. `--internal doctor` có bridge

```text
$ dist\...\AutoVoiceTikTokShop.exe --internal doctor
[doctor] Auto Voice TikTok Shop - chan doan
  OK   VoiceStudio    : OK http://127.0.0.1:3900 v0.5.6 (15 voices)
  OK   LLM            : OK http://192.168.1.68:20130/v1 model=claude-sonnet-5 latency=3153ms reply='OK.'
  OK   Audio output   : G27Q (NVIDIA High Definition Au (index=4)
  OK   Bridge         : OK ws://127.0.0.1:8765/ws?role=app events=0 trong 2.1s
  OK   Audio queue    : OK uu tien dung p1 truoc p3 (order=[1, 3]), size 0->2->0
  OK   Event simulator: OK 10 event(s) sinh duoc
[doctor] ket qua: TAT CA OK
EXIT 0
```

### 3d. Config override có tác dụng (bằng chứng cấu hình được)

Trỏ LLM sang URL không tồn tại qua config file:

```powershell
$cfg = Get-Content dist/AutoVoiceTikTokShop/config.json -Raw | ConvertFrom-Json
$cfg.llm_base_url = "http://10.255.255.1:1/v1"; $cfg.llm_timeout_s = 3
$cfg | ConvertTo-Json | Set-Content local_cache/cfg_probe.json
$env:AUTO_VOICE_CONFIG = "$PWD\local_cache\cfg_probe.json"
dist\AutoVoiceTikTokShop\AutoVoiceTikTokShop.exe --internal doctor
```

Kết quả:

```text
  OK   VoiceStudio    : OK http://127.0.0.1:3900 v0.5.6 (15 voices)
  FAIL LLM            : FAIL RuntimeError: LLM chat failed: <urlopen error timed out>
  OK   Audio output   : G27Q (NVIDIA High Definition Au (index=4)
  FAIL Bridge         : FAIL ws://127.0.0.1:8765/ws?role=app -> ConnectionRefusedError: [WinError 10061]
  OK   Audio queue    : OK uu tien dung p1 truoc p3 (order=[1, 3]), size 0->2->0
  OK   Event simulator: OK 10 event(s) sinh duoc
[doctor] ket qua: CO VAN DE (LLM, Bridge)
EXIT 1
```

LLM chuyển từ `OK` sang `FAIL` đúng theo config file → chứng minh app đọc cấu hình ngoài.

## 4. Bug đã gặp khi build và cách sửa

### 4a. `python -c BOOTSTRAP` vỡ khi frozen

GUI spawn tiến trình con bằng `[sys.executable, "-c", BOOTSTRAP, "run"]`. Khi đóng gói,
`sys.executable` là `.exe`; PyInstaller **bỏ qua** `-c` nên con mở lại GUI thay vì chạy pipeline.

Sửa: thêm subcommand nội bộ `--internal` vào `src/launcher.py`; `gui.child_cmd()` chọn:

- frozen → `[sys.executable, "--internal", ...]`
- source → `[sys.executable, "src/launcher.py", "--internal", ...]`

### 4b. `app.main()` không nhận tham số

`app.main()` đọc `sys.argv` qua argparse nên `app.main(argv)` ném
`TypeError: main() takes 0 positional arguments but 1 was given`.
Sửa: `run_internal()` ghi lại `sys.argv` rồi khôi phục trong `finally`.

### 4c. `settings.apply()` không tác động tới LLM

`llm_client` đọc `src.config`, nhưng `settings.apply()` set module `config` — hai module
object khác nhau. Sửa: set **cả hai** tên qua `importlib.import_module`.

## 5. Test suite

```text
$ python -m pytest tests/ -q
36 passed
```

## Chưa làm / khi nào cần

- **Chưa code-sign** `.exe`: Windows SmartScreen sẽ cảnh báo khi chạy trên máy khác. Cần chứng chỉ code-signing khi phát hành cho người dùng cuối.
- **Chưa làm installer** (Inno Setup/MSIX): hiện phân phối dạng ZIP thư mục onedir.
- **Chưa test GUI bằng tay trên bản frozen** (chỉ test import + build). Cần mở `.exe` không tham số trên máy đích để xác nhận cửa sổ tkinter hiển thị.
- **Chưa nhúng VoiceStudio backend**: app chỉ là client, trỏ `voicestudio_url` tới VoiceStudio ở máy local hoặc LAN. Model OmniVoice ~2.5GB + CUDA nên không nhúng được vào `.exe`.
