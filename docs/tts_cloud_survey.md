# Khảo sát các nhà cung cấp Text-to-Speech (TTS) Cloud thay thế VoiceStudio

## 1. Bảng so sánh chi tiết các nhà cung cấp TTS

| Provider | Giá (USD / ký tự hoặc token) | Latency & Streaming | Giọng Việt (Chất lượng & Số lượng) | Link Docs & Pricing |
| :--- | :--- | :--- | :--- | :--- |
| **OpenAI (tts-1)** | $15 / 1M ký tự (~$0.015/1k chars) | Siêu thấp (<400ms TTFB), có chunk streaming qua REST chunked transfer | 6 giọng đa ngữ (Alloy, Echo, Fable, Onyx, Nova, Shimmer). Đọc tiếng Việt tạm ổn nhưng hơi lơ lớ | [Docs](https://platform.openai.com/docs/guides/text-to-speech) \| [Pricing](https://openai.com/pricing) |
| **OpenAI (tts-1-hd)** | $30 / 1M ký tự (~$0.030/1k chars) | Trung bình (~800ms - 1.2s), hỗ trợ streaming | Chất lượng âm thanh cao hơn, ít artifact, vẫn âm điệu hơi ngoại quốc | [Docs](https://platform.openai.com/docs/models/tts-1-hd) \| [Pricing](https://openai.com/pricing) |
| **OpenAI (gpt-4o-mini-tts)** | ~$0.6 input text / $12 output audio cho 1M token | Rất nhanh, hỗ trợ audio response streaming natively qua Chat Completions | Hỗ trợ tiếng Việt tự nhiên hơn tts-1 nhờ mô hình multimodal, ngữ điệu linh hoạt | [Docs](https://platform.openai.com/docs/models/gpt-4o-mini-tts) |
| **Azure Speech (Neural)** | $15 / 1M ký tự (~$0.015/1k chars). **Free tier: 0.5M chars/tháng** | Rất thấp (200-400ms), hỗ trợ streaming audio chunk qua SDK/WebSocket | 4+ giọng bản xứ (HoàiMy, NamMinh...), ngữ điệu chuẩn tiếng Việt tự nhiên, không bị lơ lớ | [Pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services) \| [Voice Support](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support) |
| **Google Cloud TTS (Neural2)** | $16 / 1M ký tự (~$0.016/1k chars). **Free tier: 4M chars/tháng** | Thấp (~300-500ms), hỗ trợ streaming gRPC/REST | ~4 giọng Neural2 tiếng Việt, tự nhiên, phát âm chính xác | [Pricing](https://cloud.google.com/text-to-speech/pricing) \| [Voices](https://cloud.google.com/text-to-speech/docs/voices) |
| **ElevenLabs (Flash v2.5 / Turbo v2.5)** | $40 - $50 / 1M ký tự ($0.04 - $0.05/1k chars). **Free tier: 10k chars/tháng** | Cực thấp (~250-400ms), hỗ trợ WebSocket streaming song công | Đọc tiếng Việt qua Multilingual v2 rất giàu cảm xúc, tự nhiên nhất thị trường, hỗ trợ clone giọng | [Pricing](https://elevenlabs.io/pricing) \| [Streaming Docs](https://elevenlabs.io/docs/eleven-api/guides/how-to/text-to-speech/streaming) |
| **FPT.AI Text to Speech** | ~500.000 VNĐ / 500k ký tự (~$40 / 1M chars). **Free tier: 100k chars/tháng** | Có streaming chunk qua API/SDK, latency ~500ms - 1s | Các giọng đọc chuẩn bản xứ (Ban Mai, Thu Minh, Gia Hưng...), phù hợp tin tức, đọc chat | [Pricing](https://docs.fpt.ai/docs/vi/speech/documentation/tts-pricing) \| [Docs](https://docs.fpt.ai/) |
| **Vbee AI Voice** | Bán theo gói gói/ký tự (~200k - 500k VNĐ tùy hạn mức). | Có API, độ trễ vừa phải cho app | Rất nhiều giọng đa vùng miền (Bắc, Trung, Nam: Ngọc Huyền, Mai Ngọc...), phát âm tự nhiên | [Pricing & Docs](https://vbee.vn/pricing) |
| **Viettel AI Text to Speech** | Bán theo gói tháng/năm hoặc lượt gọi API theo hợp đồng. | Khá tốt, triển khai cloud hoặc on-premise | Giọng đọc truyền hình, tổng đài, phát âm tiếng Việt chuẩn xác | [Pricing](https://viettelai.vn/en/bang-gia) |

---

## 2. Kết luận cho Realtime Đọc Chat TikTok LIVE

- **Rẻ nhất:** **Google Cloud TTS (Neural2)** (free 4M ký tự/tháng, sau đó $16/1M) hoặc **Azure Speech Neural** ($15/1M, free 0.5M ký tự/tháng) — chi phí cực thấp, phát âm chuẩn tiếng Việt tự nhiên không bị lơ lớ.
- **Nhanh nhất (đáp ứng realtime streaming tốt nhất):** **ElevenLabs Flash/Turbo v2.5** (WebSocket streaming độ trễ ~250ms, cảm xúc tự nhiên vượt trội) hoặc **Azure Speech Neural** qua Speech SDK Streaming (độ trễ ~300ms, mạng ổn định, kinh tế hơn rất nhiều).
