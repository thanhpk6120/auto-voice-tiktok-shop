# Kết Quả Kiểm Thử (Test Results)

Ngày chạy: 2026-10-12
Môi trường: Windows / Python 3.11

## 1. Kết quả Smoke Test (`scripts/run_all_tests.py`)

Lệnh: `python scripts/run_all_tests.py`
Output:
```text
Running tests...
Using pytest...
...                                                                      [100%]
3 passed in 7.31s
```
Tình trạng: **PASSED (XANH)**

Các test case bao gồm:
- `test_greeting_batch`: Kiểm tra gộp chào nhiều user bằng `GreetingBatcher` (batching ≥2 user).
- `test_price_reply`: Kiểm tra trích xuất context dữ liệu sản phẩm qua `ChatIntent` (`context-data/*.md`) và sinh phản hồi bán hàng (chứa giá thực tế 150000).
- `test_queue_priority`: Kiểm tra hàng đợi ưu tiên `PriorityAudioQueue` (Order priority 1 > Greeting priority 3).

## 2. Kết quả Chạy Thử Ứng Dụng CLI (`src/app.py simulate`)

Lệnh: `python src/app.py simulate`
Output:
```text
Starting simulation...
VOICESTUDIO_OK=false fallback
event=gift → speak_text='Cảm ơn Hoàng Nam đã tặng Hoa hồng!' → wav=I:\AI\auto-voice-tiktok-shop\out\tts_1791750130983_5066aa2a.wav → queue-size=1
VOICESTUDIO_OK=false fallback
event=chat → speak_text='Dạ anh/chị ơi, Áo thun nam Cotton Compact hiện shop vẫn còn hàng, giá 150000 đồng, mình chốt đơn giúp shop nhé!' → wav=I:\AI\auto-voice-tiktok-shop\out\tts_1791750133036_cff99787.wav → queue-size=2
VOICESTUDIO_OK=false fallback
event=gift → speak_text='Cảm ơn Thu Trang đã tặng Hoa hồng!' → wav=I:\AI\auto-voice-tiktok-shop\out\tts_1791750135084_dd2832e5.wav → queue-size=3
VOICESTUDIO_OK=false fallback
event=chat → speak_text='Dạ anh/chị ơi, Tai nghe True Wireless Bass Boost hiện shop vẫn còn hàng, giá 450000 đồng, mình chốt đơn giúp shop nhé!' → wav=I:\AI\auto-voice-tiktok-shop\out\tts_1791750137130_a9ef1c9b.wav → queue-size=4
VOICESTUDIO_OK=false fallback
event=chat → speak_text='Dạ anh/chị ơi, Kem dưỡng da cấp ẩm Water Gel hiện shop vẫn còn hàng, giá 350000 đồng, mình chốt đơn giúp shop nhé!' → wav=I:\AI\auto-voice-tiktok-shop\out\tts_1791750139174_ff2ee61c.wav → queue-size=5
VOICESTUDIO_OK=false fallback
event=order → speak_text='Cảm ơn Lan Anh đã chốt đơn!' → wav=I:\AI\auto-voice-tiktok-shop\out\tts_1791750141221_e3032f21.wav → queue-size=6
VOICESTUDIO_OK=false fallback
event=join(flushed) → speak_text='Xin chào Minh Tuấn, Lan Anh, Phương Thảo, Thu Trang!' → wav=I:\AI\auto-voice-tiktok-shop\out\tts_1791750143275_2c601dfa.wav → queue-size=7
Simulation done.
```
Tình trạng: **THÀNH CÔNG** (Fallback sinh file WAV hợp lệ khi VoiceStudio offline).
