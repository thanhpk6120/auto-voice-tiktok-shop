# Báo cáo Khảo sát & Cài đặt VoiceStudio (debpalash/VoiceStudio)

## 1. Môi trường thực thi (Bằng chứng)
- **Hệ điều hành**: Windows 11 (x64)
- **Python**: `3.11.15 (main, Jul 18 2026, 17:06:27) [MSC v.1944 64 bit (AMD64)]`
- **GPU**: NVIDIA GeForce RTX 3060 (12GB VRAM), CUDA Driver 13.3 (Driver-Model WDDM)
- **Công cụ phụ trợ**: `uv 0.12.3`, `ffmpeg version 8.1.2-full_build`

## 2. Các bước đã thực hiện & Kết quả (OK/FAIL)
1. **Clone Repository (OK)**: Đã tải mã nguồn với cờ `--depth 1` vào `vendor/VoiceStudio` thành công.
2. **Khởi tạo môi trường ảo (OK)**: Đã tạo `vendor/voicestudio-venv` biệt lập để không làm nhiễu hệ thống chính.
3. **Cài đặt Dependency (OK)**: 
   - Đã dùng `uv pip install -e vendor/VoiceStudio/` cài đặt thành công 223 packages (bao gồm `torch`, `fastapi`, `sherpa-onnx`, `transformers`, v.v.).
   - Thời gian cài đặt rất nhanh (~1 phút), không gặp lỗi biên dịch C++ hay CUDA wheel trên Windows, không có lỗi thiếu `ffmpeg`.
4. **Khởi động Backend API :3900 (Partial FAIL)**:
   - Đã chạy lệnh: `vendor/voicestudio-venv/Scripts/uvicorn main:app --app-dir vendor/VoiceStudio/backend --host 127.0.0.1 --port 3900`
   - **Kết quả**: Uvicorn đã bind thành công port `3900`. 
   - **Lỗi phát sinh**: Mặc dù backend đã start, gọi API `curl http://127.0.0.1:3900/system/info` trả về mã lỗi HTTP `503 Service Unavailable`.
   - **Nguyên nhân log**: Ghi nhận liên tiếp các dòng `ERROR [omnivoice.settings_store] settings_store.get_secret: SQLite read failed`. Có thể VoiceStudio cần thiết lập database `.omnivoice/` hoặc `data_dir` qua script setup mặc định của Node.js mà cài đặt thuần Python bỏ sót.

## 3. NEXT STEP
- Do timebox hạn chế, không đi sâu debug lỗi SQLite của core OmniVoice trong chu trình này.
- **Để tích hợp ngay vào pipeline Event Analyzer**:
  - Tạm thời gán `VOICESTUDIO_OK=false` trong log (như contract yêu cầu).
  - Tích hợp hàm sinh file `.wav` rỗng (câm) giả lập thời gian trễ của TTS để UI / event queue không bị block.

## 4. Giải pháp Fallback (Đề xuất)
Trong trường hợp VoiceStudio (OmniVoice) tiếp tục báo lỗi hoặc model quá nặng làm chậm pipeline realtime của livestream TikTok, sử dụng các giải pháp thay thế sau:
- **Edge-TTS**: Chạy không cần GPU local, API gọi thẳng sang Microsoft Edge TTS, chất lượng giọng tự nhiên, độ trễ rất thấp, dễ dàng cài qua `pip install edge-tts`.
- **Piper TTS**: Local TTS với model ONNX cực nhẹ (~20-50MB), chạy cực nhanh trên CPU/GPU, xuất trực tiếp WAV qua command line/Python API, rất lý tưởng cho bot livestream nhẹ.
