# TEST GUI (tkinter) - `src/gui.py`

Ngày chạy: 2026-10-17 · Python 3.11.15 · Tk 8.6 · Windows

## Phạm vi

Cửa sổ `Auto Voice TikTok Shop - Cấu hình`: render form theo `settings.SECTIONS`,
Lưu / Kiểm tra kết nối / Khởi động / Dừng / Mở file config / Đọc lại / Doctor,
log realtime vào `ScrolledText`.

## Cách chạy

```powershell
python -m pytest tests/ -q                      # 31 passed
python -c "import sys; sys.path.insert(0,'src'); import gui; print('import OK')"
python src/gui.py                               # mo cua so
python src/launcher.py                          # .exe: khong tham so -> GUI
```

Headless / thieu tkinter -> in loi ro va `exit 1`:

```
[gui] tkinter không khả dụng: no display
[gui] dùng CLI thay thế: python src/app.py doctor
```

## Kết quả test tự động

```
python -m pytest tests/test_gui_import.py -q
5 passed in 0.27s
```

Vì `src/` không có `__init__.py` (đồng nhất các test cũ), `gui.py` tự thêm
`src/` + gốc repo vào `sys.path`.

| Test | Nội dung |
|---|---|
| `test_import_ok` | import `gui` không cần display; có `main`, `TITLE` đúng |
| `test_build_form_covers_sections` | `build_form` phủ đủ `settings.SECTIONS`, `llm_api_key` che, kind bool/number/text đúng theo `DEFAULTS` |
| `test_coerce_value` | chuỗi Entry -> kiểu gốc; số sai định dạng raise `ValueError` |
| `test_device_spec_roundtrip` | label combobox `12: Headset …` -> spec `12`; giữ nguyên khi là tên |
| `test_safe_devices_never_raises` | `safe_devices()` trả list, không ném khi thiếu sounddevice |

Máy test: `sounddevice` có, 16 thiết bị ra (Sound Mapper, NVIDIA G27Q, G435, Realtek…).

## Kết quả test bằng mắt (Tk thật, `root.update()` thay `mainloop`)

```
fields: 18 | combo: 16
keys: ['llm_base_url', 'llm_api_key', 'llm_model', 'llm_timeout_s',
       'voicestudio_url', 'voicestudio_voice', 'voicestudio_model', 'tts_timeout_s',
       'bridge_url', 'bridge_port', 'audio_device', 'no_play', 'context_dir',
       'out_dir', 'greeting_cooldown_s', 'greeting_max_batch', 'sales_max_words',
       'log_level']
validate try: True False True      # num_ok("8765") / num_ok("abc") / num_ok("3.5")
show truoc: *   show sau: ''       # nut "Hiện" bo che api key
run exit: None
LOG 27
  | config: C:\Users\Thanh\AppData\Roaming\AutoVoiceTikTokShop\config.json
  | data  : I:\AI\auto-voice-tiktok-shop | meipass=-
  | audio : 16 thiết bị ra
  | [save] đã lưu + áp dụng: C:\Users\Thanh\AppData\Roaming\AutoVoiceTikTokShop\config.json
  | [app] [run] bat dau (no_play=False, seconds=vo han). Ctrl+C de dung.
  | [app] [run] nguon event: simulator noi bo (--sim)
  | [app] event=gift -> speak_text='Cảm ơn Hoàng Nam đã tặng Hoa hồng!' -> wav=tts_1792227331563_5066aa2a.wav -> priority=1 -> queue-size=1
  | [app] event=gift -> speak_text='Cảm ơn Thu Trang đã tặng Hoa hồng!' -> wav=tts_1792227333644_dd2832e5.wav -> priority=1 -> queue-size=1
  | [run] đang dừng…
  | [app] tiến trình kết thúc (exit=1)
  | [check] TTS OK   http://127.0.0.1:3900 version=0.5.6 voices=15 err=None
  | [check] LLM OK: 'OK'
  | [check] Audio: 16 thiết bị ra; đang dùng G27Q (NVIDIA High Definition Au (index=4)
  | [check] xong
  | [doctor]   OK   VoiceStudio    : OK http://127.0.0.1:3900 v0.5.6 (15 voices)
  | [doctor]   OK   LLM            : OK http://192.168.1.68:20130/v1 model=claude-sonnet-5 latency=4744ms
  | [doctor]   OK   Audio output   : G27Q (NVIDIA High Definition Au (index=4)
  | [doctor]   FAIL Bridge         : FAIL ws://127.0.0.1:8765/ws?role=app -> ConnectionRefusedError: [WinError 10061]
  | [doctor]   OK   Audio queue    : OK uu tien dung p1 truoc p3 (order=[1, 3]), size 0->2->0
  | [doctor]   OK   Event simulator: OK 10 event(s) sinh duoc
  | [doctor] ket qua: CO VAN DE (Bridge)
  | [config] C:\Users\Thanh\AppData\Roaming\AutoVoiceTikTokShop\config.json
```

Ghi chú: Bridge FAIL là đúng thực tế lúc test (chưa bật `scripts/run_bridge.py`);
`exit=1` của tiến trình con là mã thoát của `app doctor` khi có check FAIL.

## Bug đã gặp và sửa

| Bug | Nguyên nhân | Sửa |
|---|---|---|
| `NameError: _num_ok` khi mở cửa sổ | `validatecommand` trỏ tới hàm static chưa tồn tại ở phạm vi module | đổi thành `app.num_ok` |
| `RuntimeError: main thread is not in main loop` | worker thread của "Kiểm tra kết nối" gọi `root.after(...)` | đặt cờ `devices_dirty`, `_poll_log()` cập nhật combobox trong main thread |

## Thiết kế

- Form sinh từ `settings.SECTIONS` + `DEFAULTS` (không hard-code schema). Thêm key mới: chỉ sửa `settings.py`.
- `SECRET_KEYS` -> `show='*'` + nút "Hiện"/"Ẩn".
- Mọi việc nặng (health/LLM/list device, chạy pipeline, doctor) chạy thread riêng;
  log đẩy vào `queue.Queue`, `after(100, _poll_log)` hút ra Text -> mainloop không block.
- "Khởi động"/"Dừng" chạy `python -c "<bootstrap>" run [--sim]` trong tiến trình con
  (terminate được thật, không phải sửa `app.py` để có stop hook). Nhãn "Mô phỏng (--sim)"
  dùng nguồn event giả để thử không cần bridge.
- Thay đổi kèm theo, tối thiểu:
  - `audio_player.list_output_devices()` (mới) - nguồn dữ liệu cho combobox.
  - `settings.apply()` set `os.environ["AUDIO_OUTPUT_DEVICE"] = cfg["audio_device"]`,
    vì `audio_player` đọc env mỗi lần phát nên không cần API set thêm.
    Cần `AUDIO_OUTPUT_DEVICE` cho đúng thiết bị chứ không có binding cứng nào trong `settings.py`.

## Giới hạn

- GUI dành cho Windows (`os.startfile`, `winsound` fallback). Linux/macOS: "Mở file config"
  báo lỗi vào log, phần còn lại vẫn chạy.
- Tên key hiển thị bằng chính tên config (`llm_base_url`…) - không có bảng nhãn tiếng Việt.
