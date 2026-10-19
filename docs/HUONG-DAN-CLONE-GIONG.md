# Hướng dẫn Clone Giọng Nói & Cấu hình vào Auto Voice TikTok Shop

Tài liệu này hướng dẫn chi tiết cách tạo một giọng đọc AI nhân bản (Voice Cloning) từ giọng thật của bạn hoặc của streamer, sau đó tích hợp vào ứng dụng Auto Voice TikTok Shop để tự động đọc bình luận, tư vấn sản phẩm và chốt đơn trên livestream.

---

## 1. Tổng quan về Voice Cloning với VoiceStudio

Ứng dụng Auto Voice TikTok Shop kết nối trực tiếp với **VoiceStudio Local API** (`http://127.0.0.1:3900`).
VoiceStudio hỗ trợ nhiều động cơ (engine) nhân bản giọng nói AI hàng đầu hiện nay:
- **CosyVoice 3 / CosyVoice 2:** Động cơ zero-shot voice cloning siêu nhanh, chất lượng phát âm tiếng Việt rất tốt, chỉ cần file mẫu từ 3 – 10 giây.
- **GPT-SoVITS:** Khả năng clone giọng chuẩn xác cao, biểu cảm giọng nói tự nhiên, phù hợp livestream bán hàng.
- **F5-TTS / IndexTTS:** Tốc độ tạo voice nhanh, không giật lag.

---

## 2. Bước 1: Chuẩn bị file mẫu âm thanh (Voice Sample)

Để giọng AI clone ra nghe tự nhiên và giống thật nhất, file ghi âm cần đạt các tiêu chuẩn sau:
1. **Thời lượng:** Từ **5 đến 15 giây** (tối ưu nhất là 8 – 10 giây). Không nên quá ngắn (< 3 giây) hoặc quá dài (> 30 giây).
2. **Nội dung câu nói:** Đọc một câu nói tự nhiên bằng tiếng Việt có ngữ điệu vui vẻ, hào hứng của streamer bán hàng.
   *Ví dụ mẫu:*
   > "Dạ em chào cả nhà đã vào xem phiên live của shop hôm nay nha! Mọi người đang quan tâm sản phẩm nào thì cứ bình luận để shop tư vấn nhiệt tình cho mình nhé!"
3. **Môi trường thu âm:**
   - Không gian yên tĩnh, không có tiếng ồn quạt gió, tiếng xe cộ ngoài đường.
   - **Tuyệt đối không bật nhạc nền** khi thu âm mẫu.
4. **Định dạng file:** Lưu dưới định dạng `.wav` hoặc `.mp3` (khuyến nghị WAV chất lượng cao 24.000 Hz hoặc 44.100 Hz). Đặt tên file đơn giản, không dấu: `giong_mau_streamer.wav`.

---

## 3. Bước 2: Tạo giọng Clone trong VoiceStudio

1. Mở phần mềm **VoiceStudio** trên máy tính hoặc truy cập giao diện web tại:
   `http://127.0.0.1:3900`
2. Chọn mục **Voice Design** hoặc **Voice Cloning** (tùy phiên bản VoiceStudio).
3. Chọn Engine: Khuyến nghị chọn **CosyVoice** hoặc **GPT-SoVITS**.
4. Tải file ghi âm `giong_mau_streamer.wav` lên hệ thống.
5. Nhập nội dung văn bản mà bạn đã nói trong file ghi âm vào ô *Prompt Text / Reference Transcript*.
6. Đặt tên đại diện cho giọng đọc (Voice Name), ví dụ:
   `streamer_nu_mien_nam` hoặc `my_clone_voice`.
   *(Lưu ý: Đặt tên viết liền hoặc dùng dấu gạch dưới, không dấu tiếng Việt).*
7. Bấm **Create / Save Voice** để lưu giọng đọc vào thư viện VoiceStudio.
8. Bấm **Test / Generate Preview** gõ thử một câu ngắn để nghe thử giọng AI vừa tạo.

---

## 4. Bước 3: Cấu hình vào ứng dụng Auto Voice TikTok Shop

Sau khi đã tạo xong giọng đọc trên VoiceStudio:

1. Mở ứng dụng **Auto Voice TikTok Shop**.
2. Chuyển sang tab **Cấu hình** (Settings).
3. Tìm đến phần **VoiceStudio TTS**:
   - **`voicestudio_url`**: Giữ nguyên `http://127.0.0.1:3900` (địa chỉ của VoiceStudio).
   - **`voicestudio_voice`**: Mở dropdown và chọn giọng bạn vừa clone. Danh sách được app
     đọc trực tiếp từ VoiceStudio, giọng clone hiển thị dạng `Ten  <voice_id>` (ví dụ `SonTungMTP  <ef920857>`).
     Bấm **🔄 Làm mới** cạnh ô này nếu bạn vừa tạo thêm giọng mới mà chưa thấy trong danh sách.
   - **`voicestudio_model`**: Chọn `tts-1` hoặc `tts-1-hd`.
4. Bấm nút **"Lưu cấu hình"** ở dưới cùng.
5. Bấm **"Khởi động lại ứng dụng"** hoặc chạy lệnh thử nghiệm.

> **Quan trọng — tên giọng vs mã giọng:** VoiceStudio 0.5.6 chỉ nhận **voice_id** của giọng clone
> (một mã ngắn như `ef920857`), **không nhận tên** (`SonTungMTP`). Nếu truyền tên, VoiceStudio
> **không báo lỗi** mà lặng lẽ đọc bằng giọng mặc định — đây là lý do phổ biến nhất khiến "clone
> rồi mà nghe không giống". App đã tự đổi tên thành voice_id khi tên khớp duy nhất, và cảnh báo
> nếu tên không tồn tại. Chạy `doctor` để kiểm tra dòng `voice='...' -> <voice_id>`.

---

## 5. Bước 4: Kiểm tra giọng đọc vừa clone

0. Xác nhận app đang dùng đúng mã giọng: chạy `AutoVoiceTikTokShop.exe doctor`, dòng
   `VoiceStudio` phải hiện `voice='...' -> <voice_id>`. Nếu thấy `CANH BAO: voice ... se bi doc
   bang giong MAC DINH`, quay lại chọn lại giọng trong dropdown.
1. Chuyển sang tab **Điều khiển** trên ứng dụng Auto Voice.
2. Bấm nút **"Chạy Simulator (Thử nghiệm)"**.
3. Quan sát khung nhật ký:
   - Hệ thống sẽ gọi VoiceStudio với tên giọng của bạn.
   - File âm thanh `.wav` được sinh ra và phát qua Loa / Virtual Cable.
   - Nghe thử xem âm lượng, tốc độ đọc và âm điệu đã vừa ý chưa.

---

## 6. Mẹo để giọng đọc livestream hay và bán hàng hiệu quả

- **Tốc độ đọc (Cadence):** Giọng clone bán hàng nên có độ nhanh vừa phải, dứt khoát ở câu chốt đơn.
- **Phiên âm tự động:** Ứng dụng đã tích hợp sẵn bộ phiên âm `phoneticize_vietnamese` tự động đổi `100k` -> `một trăm nghìn đồng`, `deal` -> `điu`, `live` -> `lai`, `freeship` -> `miễn phí vận chuyển`, giúp giọng clone đọc trơn tru không bị khựng.
- **Nhiều giọng đọc khác nhau:** Bạn có thể clone 2-3 giọng (1 giọng nam trầm ấm, 1 giọng nữ ngọt ngào) và thay đổi linh hoạt trong ô `voicestudio_voice` bất cứ lúc nào.
