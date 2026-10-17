# TEST TTS REAL — VoiceStudio /v1/audio/speech

- Thời điểm chạy: 2026-10-17T14:23:33
- Endpoint: `http://127.0.0.1:3900/v1/audio/speech`
- Voice: `alloy` | model: OpenAI-compatible `tts-1` | response_format: `wav`
- Lệnh: `python scripts/check_tts.py`

## 1. health()
```json
{'ok': True, 'latency_ms': 17, 'endpoint': 'http://127.0.0.1:3900/v1/audio/speech'}
```

## 2. warmup() — preload model
```json
{'ok': True, 'latency_ms': 1361, 'endpoint': 'http://127.0.0.1:3900/v1/audio/speech', 'path': 'I:\\AI\\auto-voice-tiktok-shop\\out\\warmup\\tts_1792221813785_4e463061.wav'}
```

## 3. synthesize 3 câu tiếng Việt thật

| # | Câu | latency (ms) | bytes | RIFF | >20KB | giây audio | file |
|---|---|---|---|---|---|---|---|
| 1 | Xin chào, cảm ơn bạn đã ghé thăm gian hàng của chúng tôi. | 1592 | 164204 | True | True | 3.42 | `tts_1792221815148_c018357c.wav` |
| 2 | Chiếc áo thun này làm từ cotton 100 phần trăm, form rộng, giá chỉ một trăm năm mươi nghìn đồng. | 1790 | 298604 | True | True | 6.22 | `tts_1792221816740_1c17fb78.wav` |
| 3 | Cảm ơn bạn đã đặt hàng, đơn hàng sẽ được giao trong hai đến ba ngày tới. | 1688 | 205004 | True | True | 4.27 | `tts_1792221818530_697e4b03.wav` |

- VOICESTUDIO_OK sau khi synthesize: **True**

## 4. play_wav() — phát câu cuối ra loa
- Backend ưu tiên: `sounddevice`
- Thiết bị phát khả dụng (16):
  - [3] Microsoft Sound Mapper - Output (2ch, 44100Hz, MME)
  - [4] G27Q (NVIDIA High Definition Au (2ch, 44100Hz, MME)
  - [5] Headset Earphone (2- G435 Wirel (2ch, 44100Hz, MME)
  - [6] Q2775 (NVIDIA High Definition A (2ch, 44100Hz, MME)
  - [10] Primary Sound Driver (2ch, 44100Hz, Windows DirectSound)
  - [11] G27Q (NVIDIA High Definition Audio) (2ch, 44100Hz, Windows DirectSound)
  - [12] Headset Earphone (2- G435 Wireless Gaming Headset) (2ch, 44100Hz, Windows DirectSound)
  - [13] Q2775 (NVIDIA High Definition Audio) (2ch, 44100Hz, Windows DirectSound)
  - [14] G27Q (NVIDIA High Definition Audio) (2ch, 48000Hz, Windows WASAPI)
  - [15] Headset Earphone (2- G435 Wireless Gaming Headset) (2ch, 48000Hz, Windows WASAPI)
  - [16] Q2775 (NVIDIA High Definition Audio) (2ch, 48000Hz, Windows WASAPI)
  - [20] Headset Earphone (G435 Wireless Gaming Headset) (2ch, 48000Hz, Windows WDM-KS)
  - [22] Speakers (Realtek HD Audio output) (8ch, 44100Hz, Windows WDM-KS)
  - [23] Headphones (Realtek HD Audio 2nd output) (2ch, 44100Hz, Windows WDM-KS)
  - [26] Output (NVIDIA High Definition Audio) (2ch, 48000Hz, Windows WDM-KS)
  - [27] Output () (2ch, 44100Hz, Windows WDM-KS)
- Kết quả `play_wav(tts_1792221818530_697e4b03.wav)` = **True** (mất 4.54s)

## 5. Log thô stdout
```text
[tts_client] health={'ok': True, 'latency_ms': 17, 'endpoint': 'http://127.0.0.1:3900/v1/audio/speech'}
[tts_client] warmup={'ok': True, 'latency_ms': 1361, 'endpoint': 'http://127.0.0.1:3900/v1/audio/speech', 'path': 'I:\\AI\\auto-voice-tiktok-shop\\out\\warmup\\tts_1792221813785_4e463061.wav'}
[tts_client] synth ok=True latency_ms=1592 bytes=164204 riff=True >20KB=True file=I:\AI\auto-voice-tiktok-shop\out\tts_check\tts_1792221815148_c018357c.wav
[tts_client] synth ok=True latency_ms=1790 bytes=298604 riff=True >20KB=True file=I:\AI\auto-voice-tiktok-shop\out\tts_check\tts_1792221816740_1c17fb78.wav
[tts_client] synth ok=True latency_ms=1688 bytes=205004 riff=True >20KB=True file=I:\AI\auto-voice-tiktok-shop\out\tts_check\tts_1792221818530_697e4b03.wav
[audio_player] backend=sounddevice devices=16 play_wav=True
```

## 6. Kết luận
- 3/3 câu: `VOICESTUDIO_OK=true` + magic RIFF + > 20KB: **True**
- Latency đo được (ms): [1592, 1790, 1688]
- play_wav trả về: **True**

_(Tổng thời gian script: 11.0s)_
