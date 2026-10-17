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

### 3e. GUI bản frozen mở cửa sổ thật (không chỉ import)

Kiểm chứng bằng Win32 `EnumWindows`, không đoán theo thời gian sống của process:

```python
p = subprocess.Popen([r"dist\AutoVoiceTikTokShop\AutoVoiceTikTokShop.exe"])
time.sleep(7)
# EnumWindows -> loc title chua "Auto Voice"
```

Kết quả:

```text
Windows match 'Auto Voice':
   ('Auto Voice TikTok Shop - Cấu hình', 15588, 886, 599)
PID cua process: 15588
```

- Title đúng: `Auto Voice TikTok Shop - Cấu hình`
- Kích thước cửa sổ: **886 × 599**
- PID cửa sổ **khớp** PID process (15588) → cửa sổ thuộc đúng app, không phải window khác.

### 3f. Child spawn bản frozen (bug 4a đã sửa)

`gui.child_cmd()` bản frozen sinh ra `[<exe>, "--internal", ...]`. Chạy đúng lệnh đó:

```text
$ dist\AutoVoiceTikTokShop\AutoVoiceTikTokShop.exe --internal doctor
[doctor] ket qua: TAT CA OK
EXIT 0
```

→ Cùng code path mà nút **Khởi động** / **Doctor** dùng. Trước khi sửa, lệnh này mở lại GUI
thay vì chạy pipeline.

### 3g. Chạy từ vị trí khác, CWD khác, APPDATA sạch (mô phỏng máy mới)

Copy `dist/AutoVoiceTikTokShop/` sang `local_cache/relocate_test/`, xoá `APPDATA` sạch,
chạy với `cwd=C:\`:

```text
[doctor] Auto Voice TikTok Shop - chan doan
  OK   VoiceStudio    : OK http://127.0.0.1:3900 v0.5.6 (15 voices)
  OK   LLM            : OK http://192.168.1.68:20130/v1 model=claude-sonnet-5 latency=4438ms reply='OK. Chưa có task. Đưa yêu cầu cụ thể.'
  OK   Audio output   : G27Q (NVIDIA High Definition Au (index=4)
  FAIL Bridge         : FAIL ws://127.0.0.1:8765/ws?role=app -> ConnectionRefusedError: [WinError 10061]
  OK   Audio queue    : OK uu tien dung p1 truoc p3 (order=[1, 3]), size 0->2->0
  OK   Event simulator: OK 10 event(s) sinh duoc
[doctor] ket qua: CO VAN DE (Bridge)
```

- `context-data` được resolve **cạnh `.exe`**, không phụ thuộc `cwd` → RAG vẫn chạy đúng từ `C:\`.
- `out/` sinh ra cạnh `.exe` (`dist/AutoVoiceTikTokShop/out/`).
- Trên máy mới không có config: app dùng `DEFAULTS` và chạy ngay, không crash.

### 4d. Tiếng Việt bị mất khi stdout là pipe (bug nặng, đã sửa)

**Triệu chứng:** chạy `.exe --internal doctor` qua `subprocess`/redirect, dòng chứa tiếng Việt
(kể cả `LLM : OK ... reply='Được.'`) **mất hoàn toàn** khỏi stdout. Log file `logs/cli.log`
thì vẫn có đủ.

**Root cause:** trên Windows, khi `stdout` là pipe/file, Python dùng `cp1252`. Ghi ký tự
tiếng Việt ném `UnicodeEncodeError`. `_Tee.write()` bắt mọi exception rồi bỏ qua:

```python
def write(self, data: str) -> int:
    for st in self._streams:
        try:
            st.write(data); st.flush()
        except Exception:
            pass      # <-- nuot UnicodeEncodeError => CA DONG bi mat
```

Log file (mở với `encoding="utf-8"`) ghi được, stdout pipe (cp1252) thì không → dòng bị mất
chỉ ở stdout. Bug này ảnh hưởng trực tiếp GUI vì GUI spawn tiến trình con qua pipe.

**Fix:** `_force_utf8(sys.stdout/stderr)` gọi `stream.reconfigure(encoding="utf-8", errors="replace")`
trước khi tee.

**Bằng chứng trước/sau** (`subprocess.run(..., capture_output=True)`, raw bytes):

```text
TRUOC: len stdout = 534 | co chu 'LLM' trong stdout: False
SAU  : co dong LLM: True
       OK   LLM : OK http://192.168.1.68:20130/v1 model=claude-sonnet-5 latency=4438ms reply='OK. Chưa có task. Đưa yêu cầu cụ thể.'
```

Và với `simulate`:

```text
TRUOC: so event line qua PIPE: 0
SAU  : so event line qua PIPE: 7
   event=gift -> speak_text='Cảm ơn Hoàng Nam đã tặng Hoa hồng!' -> priority=1 -> queue-size=1 [no-play]
   event=chat -> speak_text='Shop chưa có dữ liệu size cho áo này, mình không chốt bừa. ...' -> priority=2
   event=join(flushed) -> speak_text="What'up Minh Tuấn, Lan Anh, Phương Thảo, Thu Trang!" -> queue-size=7
EXIT 0
```

**Regression test:** `tests/test_launcher_encoding.py` — 4 test, trong đó
`test_tee_swallows_vietnamese_loss_but_other_stream_keeps_it` tái hiện đúng cơ chế mất dòng
(stream cp1252 không ghi được, stream utf-8 nhận nguyên văn).

## 5. Test suite

```text
$ python -m pytest tests/ -q
41 passed
```

## Chưa làm / khi nào cần

- **Chưa code-sign** `.exe`: Windows SmartScreen sẽ cảnh báo khi chạy trên máy khác. Cần chứng chỉ code-signing khi phát hành cho người dùng cuối.
- **Chưa làm installer** (Inno Setup/MSIX): hiện phân phối dạng ZIP thư mục onedir.
- **Chưa click tay từng nút trên GUI frozen**: đã xác nhận cửa sổ mở đúng (mục 3e) và child spawn đúng (mục 3f), nhưng chưa bấm thử từng nút bằng chuột trên bản `.exe`.
- **Chưa nhúng VoiceStudio backend**: app chỉ là client, trỏ `voicestudio_url` tới VoiceStudio ở máy local hoặc LAN. Model OmniVoice ~2.5GB + CUDA nên không nhúng được vào `.exe`.
