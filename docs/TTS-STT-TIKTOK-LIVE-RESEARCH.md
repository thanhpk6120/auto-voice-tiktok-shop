# Báo cáo Nghiên cứu TTS, STT và TikTok LIVE cho Auto Voice

## 1. TTS local thay VoiceStudio

| Engine | Tiếng Việt | Voice clone | Latency | VRAM / CPU | License + Link |
|---|---|---|---|---|---|
| Coqui XTTS-v2 | Không gốc. Gốc 17 NN (en/es/fr/de/it/pt/pl/tr/ru/nl/cs/ar/zh/ja/hu/ko/hi), cần finetune cộng đồng | Có, 3-6s mẫu | ~500ms first-token, RTF ~0.1 | 4-6GB VRAM | CPML (phi thương mại). [Repo](https://github.com/coqui-ai/TTS) / [Model](https://huggingface.co/coqui/XTTS-v2) |
| Piper / onnx | Rất tốt. `vi_VN` sẵn: vais1000, vivos | Không, phải train riêng | Rất nhanh, realtime CPU | CPU, RAM <100MB | MIT. [Repo](https://github.com/rhasspy/piper) / [Voice Vi](https://huggingface.co/rhasspy/piper-voices/tree/main/vi/vi_VN) |
| Bark (Suno) | Kém, không chính thức, hallucinate | Style-prompt, không zero-shot chuẩn | Rất chậm | >8GB VRAM | MIT. [Repo](https://github.com/suno-ai/bark) |
| StyleTTS2 | Tốt qua finetune `StyleTTS2-lite-vi` | Có, zero-shot ~3s | Nhanh, RTF <0.1 | 4-6GB VRAM | MIT. [Repo](https://github.com/yl4579/StyleTTS2) / [Vi](https://huggingface.co/dangtr0408/StyleTTS2-lite-vi) |
| Edge-TTS | Rất tốt, `vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural` | Không | Phụ thuộc mạng, cache mp3 dùng offline được | ~0, online | GPL-3.0 (tool). [Repo](https://github.com/rany2/edge-tts) |

**Kết luận local:** Không cần clone dùng **Piper**. Cần clone/biểu cảm dùng **StyleTTS2 bản finetune Việt**. XTTS-v2 gốc và Bark không nên làm default đọc Việt.

Lệnh kiểm chứng nhanh:
```bash
piper -m vi_VN-vais1000-medium.onnx -c config.json -f out.wav
edge-tts --voice vi-VN-HoaiMyNeural --text "Xin chào" --write-media out.mp3
```

## 2. TTS cloud

| Provider | Giá | Latency / stream | Giọng Việt | Link |
|---|---|---|---|---|
| OpenAI `tts-1` | $15/1M chars | <400ms, chunked REST | 6 giọng đa ngữ, Việt hơi lơ lớ | [Docs](https://platform.openai.com/docs/guides/text-to-speech) / [Giá](https://openai.com/pricing) |
| OpenAI `tts-1-hd` | $30/1M chars | 800ms-1.2s, streaming | Hay hơn, vẫn hơi ngoại quốc | [Docs](https://platform.openai.com/docs/models/tts-1-hd) |
| OpenAI `gpt-4o-mini-tts` | ~$0.6 in + $12 audio /1M token | Rất nhanh, native stream | Việt tự nhiên hơn `tts-1` | [Docs](https://platform.openai.com/docs/models/gpt-4o-mini-tts) |
| Azure Speech Neural | $15/1M chars, free 0.5M/tháng | 200-400ms, SDK/WebSocket | 4+ bản xứ HoàiMy/NamMinh, chuẩn | [Giá](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services) / [Voice](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support) |
| Google Neural2 | $16/1M chars, free 4M/tháng | 300-500ms, gRPC/REST | ~4 giọng Việt chuẩn | [Giá](https://cloud.google.com/text-to-speech/pricing) / [Voice](https://cloud.google.com/text-to-speech/docs/voices) |
| ElevenLabs Flash/Turbo v2.5 | $40-50/1M chars, free 10k/tháng | 250-400ms, WebSocket song công | Multilingual v2 cảm xúc nhất, clone tốt | [Giá](https://elevenlabs.io/pricing) / [Stream](https://elevenlabs.io/docs/eleven-api/guides/how-to/text-to-speech/streaming) |
| FPT.AI | ~500k VNĐ/500k chars (~$40/1M), free 100k/tháng | 500ms-1s, chunk API | Ban Mai/Thu Minh/Gia Hưng bản xứ | [Giá](https://docs.fpt.ai/docs/vi/speech/documentation/tts-pricing) / [Docs](https://docs.fpt.ai/) |
| Vbee | 200-500k VNĐ theo gói | Trung bình, API | Nhiều vùng Bắc/Trung/Nam | [Giá](https://vbee.vn/pricing) |
| Viettel AI | Theo hợp đồng/tháng | Tốt, cloud/on-premise | Giọng truyền hình/tổng đài | [Giá](https://viettelai.vn/en/bang-gia) |

**Rẻ nhất:** **Google Neural2** hoặc **Azure Neural**. 
**Nhanh nhất realtime:** **ElevenLabs Flash v2.5**, kinh tế hơn là **Azure Streaming**.

## 3. Đọc chat TikTok LIVE

| Lib | Ngôn ngữ | Auth | Ổn định / rate-limit | Rủi ro ToS | Link |
|---|---|---|---|---|---|
| TikTok-Live-Connector | Node/TS | Public chỉ cần `uniqueId→roomId`, cookie `sessionid` tùy chọn, `signApiKey` | Trung bình-yếu, sign Euler free quota thấp, gãy khi đổi proto | Trung bình khi đọc, cao khi `authenticateWs`/`sendMessage` | [Repo](https://github.com/zerodytrash/TikTok-Live-Connector) / [Demo](https://github.com/zerodytrash/TikTok-Chat-Reader) |
| TikTokLive | Python | `TikTokLiveClient(unique_id)`, `web_client_cookies`, `tiktok_sign_api_key/url`, proxy | Trung bình-yếu, chung hạ tầng Euler | Như trên + proxy công cộng | [Repo](https://github.com/isaackogan/TikTokLive) / [Docs](https://isaackogan.github.io/TikTokLive/) |
| EulerStream API/SDK | Đa NN | API key + optional OAuth forward | Ổn định nhất, limit theo gói, SLA | Thấp kỹ thuật, vẫn third-party | [API](https://github.com/EulerStream/TikTok-Live-Api) / [Docs](https://www.eulerstream.com/docs/quickstart) |
| Self-host `tiktok-sign` | Node/Python+QuickJS | Tự sinh `_signature`/`X-Bogus`/`msToken`/`ttwid` | Kém, hỏng mỗi lần đổi JS signer | Cao, coi là bypass | [Ref](https://github.com/xtekky/TikTok-Signature) |
| Port JVM/.NET/Go/Rust | Java/C#/Go/Rust | Kế thừa `uniqueId→roomId` + Euler | Yếu hơn gốc 1 nhịp | Tương đương gốc | [Java](https://github.com/jwdeveloper/TikTokLiveJava) / [C#](https://github.com/frankvHoof93/TikTokLiveSharp) / [Go](https://github.com/steampoweredtaco/gotiktoklive) |
| Playwright/Puppeteer CDP đọc DOM | Node/Python | Login thật seller, `storageState`, đọc `shop.tiktok.com/streamer/live/product/dashboard` | 1 shop trung bình, scale kém, gãy selector, tốn RAM | Rất cao, bay quyền live/shop | [Playwright](https://playwright.dev) / [Puppeteer](https://pptr.dev) |

> **Ghi chú:** Không tồn tại repo `zerody/truongpn`. Chỉ có `truong-pn` trống và fork `trilong0610/TikTokLiveConnector`. Đề xuất dùng `zerodytrash` + `isaackogan`.

### Cảnh báo pháp lý/kỹ thuật:
- Mọi lib đều unofficial, vi phạm ToS TikTok, Unaffiliated ByteDance. Test bằng acc clone, không dùng acc shop chính test sign lậu.
- Sign rotate `_signature`/`X-Bogus`/`msToken`/Webcast proto không báo trước, cả 2 lib gốc cùng gãy chờ Euler.
- CAPTCHA + bóp limit theo IP/device giờ cao điểm. Dấu hiệu `fetchRoomId` chập chờn, WS rớt. Giảm poll, dùng `ws_proxy` riêng.
- Không forward `sessionid`/OAuth seller cho sign server công cộng.
- Automation CDP acc shop rủi ro cao nhất: phát hiện là mất quyền live/shop. Tách luồng: đọc public bằng connector, thao tác shop bằng tay.

## 4. Desktop shell + audio queue

| Tiêu chí | Electron v33+ | Tauri v2 | Wails v2/v3 |
|---|---|---|---|
| Bundle | 85-140MB | 4-10MB | 10-18MB |
| RAM idle/phát | 130-260MB | 30-55MB | 35-70MB |
| Audio queue gapless | Howler/Web Audio, dễ throttle khi minimize | Rust `rodio`/`cpal` thread riêng, gapless chuẩn | Go `oto`/`beep`/`miniaudio-go` goroutine |
| Auto-start Win | `app.setLoginItemSettings` sẵn | `@tauri-apps/plugin-autostart` chính thức | Tự ghi `HKCU...Run` |
| Routing loa | `setSinkId()` Chromium | `cpal`/`rodio` ra Virtual Cable/OBS | `oto`/`miniaudio` WASAPI |
| Phân phối shop | Nặng, dễ drop OBS máy i3/4GB | NSIS 1-click + updater ECDSA, nhẹ nhất | 1 file exe portable |

**Pipeline queue đề xuất:** `Socket chat → Priority FIFO (Gift/Donate > chat) → Cache SHA256(voice+speed+text) tại %APPDATA%/auto-voice/cache (.mp3/.wav, LRU 500MB) → rodio::Sink append/skip → Loa + Virtual Cable OBS`. 
- **Dồn >10 câu:** drop chat cũ, giữ donate. 
- **Crossfade:** Web dùng 2 `AudioBufferSourceNode+gainNode`, Rust dùng `sink.append`.

## 5. 2 combo đề xuất

**Combo 1 — Rẻ nhất (0đ, offline-first):** `TikTokLive Python` hoặc `tiktok-live-connector` đọc public + `Piper vi_VN` local + cache SHA256 + `Tauri v2 + rodio`. Latency tổng <500ms, chạy CPU, không tốn API.

**Combo 2 — Nhanh + hay, vẫn rẻ:** `EulerStream` (prod) hoặc connector + `Azure Speech Neural vi-VN-HoaiMy/NamMinh` streaming + fallback `Edge-TTS` cache + `Tauri v2 + rodio`. $15/1M chars, free 0.5M/tháng, TTFB 200-400ms. Nâng cấp cảm xúc/clone thì đổi sang `ElevenLabs Flash v2.5`.

*(Tránh: Bark/XTTS gốc đọc Việt, self-host sign, CDP automation acc shop chính)*
