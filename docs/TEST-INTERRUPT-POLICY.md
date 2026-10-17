# Bằng chứng Kiểm thử Chính sách Ngắt Audio (Audio Interrupt Policy)

## 1. Mô tả hai chế độ ngắt (`interrupt_mode`)

Trong `src/audio_queue.py`, hàng đợi `PriorityAudioQueue` hỗ trợ tham số cấu hình `interrupt_mode: str = "finish"` với hai hành vi:

1. **`finish` (MẶC ĐỊNH):**
   - **Hành vi:** Khi worker đang phát một câu thoại có độ ưu tiên thấp hơn (p2 - chat/tư vấn, p3 - chào hỏi) mà có sự kiện ưu tiên cao (p1 - đơn hàng / quà tặng) xuất hiện, worker **KHÔNG ngắt** câu hiện tại. Worker đợi phát xong trọn vẹn câu đang đọc rồi mới lấy và phát item p1 tiếp theo. Không bỏ bất kỳ item nào.
   - **Cơ chế Requeue:** Nếu một item đang phát bị gián đoạn ngoài ý muốn (player trả về `False` hoặc lỗi ngoại cảnh), item không bị vứt bỏ ngay mà được đẩy lại vào hàng đợi với cùng độ ưu tiên `priority` và số đếm vòng đời mới. Để chống vòng lặp vô hạn, payload gắn cờ `_requeue`. Nếu item đã bị requeue ≥ 2 lần, item sẽ bị bỏ hẳn và tăng bộ đếm `stats["dropped_requeue"]`.

2. **`interrupt`:**
   - **Hành vi:** Khi worker đang phát item có `priority > 1` (chat/chào hỏi) mà có item `priority == 1` (gift/order) mới vào hàng đợi, item đang phát bị **NGẮT NGAY LẬP TỨC và BỎ LUÔN** (không phát lại sau). Item p1 được phát ngay sau khi ngắt.
   - Thích hợp khi luồng live có mật độ sự kiện dồn dập và ưu tiên tối đa tính tức thì của thông báo quà tặng / chốt đơn hơn là tính toàn vẹn của câu chat.

---

## 2. Lý do chọn `finish` làm mặc định

- **Trải nghiệm người nghe trong livestream bán hàng (Voice TikTok Shop):**
  - Giọng đọc AI đóng vai trò như MC hoặc trợ lý bán hàng trên livestream. Khi đang nói dở một câu tư vấn hoặc câu chào (ví dụ: *"Chào bạn Nguyễn Văn A đã vào phòng live..."* hoặc *"Sản phẩm này hiện đang có mã giảm giá..."*), việc bị ngắt đột ngột giữa chừng khiến câu nói bị cụt, âm thanh giật cục, thiếu tự nhiên và gây khó chịu cho người xem.
  - Khách hàng có xu hướng đánh giá cao luồng nói liền mạch, rõ ràng. Việc câu p1 (cảm ơn đơn / quà) chờ một vài giây để câu hiện tại hoàn tất đọc trọn vẹn vẫn đảm bảo độ phản hồi tốt mà không phá vỡ tính tự nhiên của buổi phát trực tiếp.

---

## 3. Cấu hình tích hợp

- **`src/settings.py`:**
  - `DEFAULTS`: `"interrupt_mode": "finish"`
  - `SECTIONS["Audio & Analyzer"]`: bổ sung `"interrupt_mode"`
  - `apply()`: thiết lập biến môi trường `os.environ["INTERRUPT_MODE"] = str(cfg.get("interrupt_mode", "finish"))` để các tiến trình con thừa hưởng.
- **`src/app.py`:**
  - Khởi tạo `PriorityAudioQueue(..., interrupt_mode=os.getenv("INTERRUPT_MODE", "finish"))`.
  - In log thông báo chế độ hoạt động khi khởi động: `[run] audio queue: interrupt_mode=...`.

---

## 4. Bằng chứng kết quả kiểm thử (Test Output)

### 4.1. Unit tests chi tiết cho chính sách ngắt (`tests/test_interrupt_policy.py`)

Lệnh chạy: `python -m pytest tests/test_interrupt_policy.py -v --no-header -o "cache_dir=/tmp"`

```text
============================= test session starts =============================
collecting ... collected 4 items

tests/test_interrupt_policy.py::test_finish_mode_plays_all_without_interrupt PASSED [ 25%]
tests/test_interrupt_policy.py::test_interrupt_mode_drops_current_item PASSED [ 50%]
tests/test_interrupt_policy.py::test_requeue_drops_after_two_retries PASSED [ 75%]
tests/test_interrupt_policy.py::test_settings_apply_sets_interrupt_mode_env PASSED [100%]

============================== 4 passed in 0.77s ==============================
```

- `test_finish_mode_plays_all_without_interrupt`: Đang phát p3 dài, put p1 -> p3 phát hết (player trả True), rồi p1 mới phát. Xác nhận `stats["interrupted"] == 0` và cả 2 item đều `played`.
- `test_interrupt_mode_drops_current_item`: Chế độ `interrupt`, đang phát p3, put p1 -> p3 bị ngắt và bỏ, chỉ p1 phát. Xác nhận `stats["interrupted"] == 1`, `stats["played"] == 1`.
- `test_requeue_drops_after_two_retries`: Player giả luôn trả False -> item được requeue đúng 2 lần rồi bị hủy, xác nhận `stats["requeued"] == 2`, `stats["dropped_requeue"] == 1`, `stats["interrupted"] == 3`.
- `test_settings_apply_sets_interrupt_mode_env`: `settings.apply()` truyền đúng biến môi trường `INTERRUPT_MODE`.

### 4.2. Toàn bộ test suite dự án (`tests/`)

Lệnh chạy: `python -m pytest tests/ -q`

```text
..................................................                       [100%]
50 passed, 1 warning in 97.96s (0:01:37)
```

Tất cả 50/50 test cases đều passed.
