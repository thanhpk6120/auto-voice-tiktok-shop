# Tính năng Bán hàng tự động khi Live rảnh (Idle Auto-Pitch & Sales Conversion)

Tài liệu đặc tả kiến trúc, cơ chế vận hành và cấu hình của tính năng tự động tạo voice giới thiệu sản phẩm khi phiên livestream không có sự kiện tương tác.

---

## 1. Mục tiêu bài toán
- **Tránh khoảng lặng chết (Dead Air):** Khi phòng live vắng, không có người hỏi, hệ thống tự động bốc sản phẩm trong giỏ hàng ra giới thiệu để giữ nhịp livestream sống động.
- **Pre-render 10 Voice trong Cache (0ms Latency):** Không gọi LLM khi đang live, tạo sẵn 10 file âm thanh `.wav` ngẫu nhiên lưu trong bộ đệm `local_cache/auto_pitch/`.
- **Không ngắt đột ngột (No Abrupt Cutoffs):** Mọi câu thoại đều được phát trọn vẹn 100%, cộng thêm thời gian đệm xả buffer (`post_speech_padding_s = 0.35s`). Khi có khách bình luận hay tặng quà, câu trả lời của khách được xếp vào đầu hàng đợi ưu tiên để phát ngay sau khi câu hiện tại kết thúc tự nhiên.
- **Xoay tua không lặp lại & Tự động bù voice:** Khi phát xong 1 voice, hệ thống xoá file `.wav` đó ngay và tự động chọn 1 sản phẩm khác chưa lặp lại để tạo bù 1 voice mới, duy trì liên tục đúng 10 voice trong bộ đệm.
- **Hỗ trợ ra đơn thật:** Áp dụng 5 công thức tâm lý bán hàng livestream thực chiến (Khan hiếm, Kêu gọi ghim giỏ hàng, Freeship Extra, Đánh giá chất lượng, Tương tác đổi deal).

---

## 2. Kiến trúc luồng xử lý

```text
[Giỏ hàng Live context-live/] 
         │
         ▼
[AutoPitchManager] ──(Chọn SP chưa lặp)──► [5 Công thức chốt đơn]
         │                                          │
         ▼                                          ▼
[Refill Loop] ◄──(TTS VoiceStudio)────── [Phoneticize & Giọng Bắc]
         │
         ▼
[Bộ đệm 10 Voice: local_cache/auto_pitch/]
         │
         ▼ (Khi live rảnh 10s - 30s)
[PriorityAudioQueue (priority=3, kind='auto_pitch')]
         │
         ▼ (Phát trọn vẹn + đệm 0.35s)
[on_audio_finish] ──► Xoá file .wav ──► Kích hoạt Refill bù 1 voice mới
```

---

## 3. Các công thức chốt đơn livestream (Sales Conversion Formulas)

| STT | Tên công thức | Mục đích tâm lý | Mẫu câu ví dụ |
|---|---|---|---|
| 1 | **Scarcity & Urgency** | Tạo cảm giác khan hiếm, sợ bỏ lỡ mã giảm giá | *"Cả nhà ơi, mã [Tên SP] trên live hôm nay chỉ còn [Giá], shop chỉ trợ giá đúng 5 suất thôi ạ. Ai chưa kịp chốt thì bấm ngay giỏ hàng góc trái màn hình kẻo hết nhé!"* |
| 2 | **Direct CTA Cart** | Kêu gọi hành động trực tiếp vào giỏ hàng góc trái | *"Cả nhà mình ai đang xem live bấm vào giỏ hàng góc trái xem mã [Tên SP] đang có giá cực hời [Giá] nhé. Hàng chuẩn ngon, date mới tinh, bấm mua ngay nhé!"* |
| 3 | **Freeship & Bundle** | Đòn bẩy phí ship kích thích chốt đơn nhanh | *"Món [Tên SP] hôm nay được áp mã freeship extra và voucher sốc đó cả nhà. Giá chỉ có [Giá], cả nhà gom thêm cho đủ đơn để được miễn phí vận chuyển nhé!"* |
| 4 | **Social Proof & Trust** | Đánh giá tốt của khách hàng, tạo niềm tin | *"Khách nhà em nhận mã [Tên SP] ai cũng khen nức nở luôn cả nhà ơi. Giá hôm nay chỉ [Giá], hàng bao chuẩn bao ngon, cả nhà yên tâm bấm giỏ hàng đặt nhé!"* |
| 5 | **Engagement Hook** | Kéo tương tác thả tim thuật toán TikTok | *"Cả nhà mình đang xem live cho shop xin vài cái thả tim và follow nha! Đẩy tim lên mốc là shop tung deal [Tên SP] giá siêu ưu đãi [Giá] cho cả nhà săn liền tay nhé!"* |

---

## 4. Các tham số cấu hình (Settings)

Các trường có thể chỉnh sửa trực tiếp trên giao diện GUI (Tab **Bán hàng tự động (Auto-Pitch)**) hoặc trong file `config.json`:

```json
{
  "queue_max_per_kind": 3,
  "idle_pitch_enabled": true,
  "idle_pitch_buffer_size": 10,
  "idle_pitch_min_s": 10.0,
  "idle_pitch_max_s": 30.0,
  "post_speech_padding_s": 0.35,
  "remind_enabled": true,
  "remind_min_s": 60.0,
  "remind_max_s": 120.0
}
```

- `queue_max_per_kind` *(int, mặc định: 3)*: Giới hạn số lượng voice tối đa lưu trong hàng đợi cho mỗi loại sự kiện (`order`, `gift`, `sales`, `greeting`, `auto_pitch`). Khi có câu mới cùng loại vượt quá 3, hệ thống **tự động xoá câu CŨ NHẤT** của loại đó để ưu tiên phản hồi các sự kiện mới nhất, đảm bảo tính realtime như livestream thật.
- `idle_pitch_enabled` *(bool, mặc định: true)*: Bật/Tắt tính năng tự động giới thiệu sản phẩm khi live rảnh.
- `idle_pitch_buffer_size` *(int, mặc định: 10)*: Số lượng voice ngẫu nhiên các sản phẩm được tạo sẵn lưu trong cache.
- `idle_pitch_min_s` *(float, mặc định: 10.0s)*: Thời gian rảnh tối thiểu trước khi tự động phát voice giới thiệu.
- `idle_pitch_max_s` *(float, mặc định: 30.0s)*: Thời gian rảnh tối đa trước khi tự động phát voice giới thiệu.
- `post_speech_padding_s` *(float, mặc định: 0.35s)*: Thời gian đệm sau khi phát xong câu để tránh ngắt từ cuối và tạo nhịp nghỉ tự nhiên.

---

## 5. Cải tiến giao diện GUI

1. **Kích thước cửa sổ:** Mở rộng từ `1040x780` lên `1150x840` (kích thước tối thiểu `1020x720`).
2. **Khung Log thời gian thực co giãn linh hoạt (`ttk.PanedWindow`):**
   - Bọc Notebook (phần cấu hình trên) và Khung Log (dưới) vào `ttk.PanedWindow(orient='vertical')`.
   - Người dùng có thể rê chuột vào mép phân cách và **kéo lên / kéo xuống tự do** để mở rộng hoặc thu hẹp phần log theo ý muốn.
   - Chiều cao mặc định tăng lên 15 dòng, tự động co giãn theo tỷ lệ khi phóng to toàn màn hình.
   - Bổ sung bộ lọc: `[pitch]`, `[batch]`, `[app]`, `[cdp]`, `[doctor]`, `[run]`, `[check]`.
3. **Thanh nút bấm Action:**
   - Gom thành các cụm mạch lạc có dải phân cách:
     - **Cụm Vận hành:** `▶ Khởi động Live`, `⏹ Dừng Live`.
     - **Cụm Cấu hình:** `💾 Lưu cấu hình`, `🔄 Đọc lại`, `📂 Mở file config`.
     - **Cụm Kiểm tra:** `🔌 Kiểm tra kết nối`, `🩺 Chẩn đoán (doctor)`.
     - **Cụm Công cụ:** Checkbox `Mô phỏng (--sim)`.
4. **Cấu trúc Tab trong Notebook:**
   - Tab 1: **Trạng thái** (Thống kê realtime, đếm sự kiện, hàng đợi audio).
   - Tab 2: **Sản phẩm Live** (Danh sách sản phẩm giỏ hàng, đồng bộ giá khuyến mại).
   - Tab 3: **Quản lý Prompt** (Kịch bản thoại các loại sự kiện).
   - Tab 4: **Bán hàng tự động (Auto-Pitch)** (Cấu hình bộ đệm 10 voice, thời gian rảnh 10-30s, câu nhắc tương tác).
   - Tab 5: **Âm thanh & VoiceStudio** (Thiết bị ra, padding đuôi, model, voice ID).
   - Tab 6: **Mô hình AI (LLM)** (API keys, URLs, model chat, model analyst).
   - Tab 7: **Tương tác & Lọc sự kiện** (Batch window, cooldown chào, độ dài câu bán hàng).
   - Tab 8: **Kết nối & Trình duyệt** (WebSocket bridge, GoLogin profile, CDP).
   - Tab 9: **Hệ thống & Thư mục** (Các đường dẫn thư mục, log level).
   - Tab 10: **Hướng dẫn Clone Giọng** (Tài liệu hướng dẫn mẫu).
