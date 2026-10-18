# Thư mục Prompt

Mỗi file `.md` trong đây là prompt hệ thống (system prompt) cho một loại ý định.
Có thể sửa trực tiếp các file này, hoặc sửa ngay trong app ở tab **Quản lý Prompt**.

## Danh sách prompt

| File | Dùng khi | Bước phân loại |
|---|---|---|
| `system_analyzer.md` | Model AI phân tích đọc bình luận và phân loại ý định | Bước 1 (phân tích) |
| `system_greeting.md` | Khách chào hỏi / vào phòng | Sinh câu thoại |
| `system_sales.md` | Khách hỏi về sản phẩm | Sinh câu thoại |
| `system_order.md` | Khách chốt đơn, mua hàng | Sinh câu thoại |
| `system_gift.md` | Khách tặng quà | Sinh câu thoại |
| `system_chat.md` | Trò chuyện xã giao khác | Sinh câu thoại |
| `system_batch.md` | Gộp nhiều sự kiện trong một cửa sổ thời gian | Sinh câu thoại (hàng loạt) |

## Quy ước bắt buộc

1. **Mọi prompt phải yêu cầu LLM chỉ trả về JSON** và phải kèm **JSON mẫu** để model bám theo.
2. Phần đọc kết quả dùng `src/json_utils.py` để chuẩn hoá JSON lỗi
   (bỏ ```json fence, nháy đơn, key/giá trị không nháy, dấu phẩy thừa, xuống dòng trong chuỗi...).
3. Prompt sinh câu thoại phải yêu cầu **phiên âm 100% chữ số và từ tiếng Anh** vì câu trả lời được đưa thẳng vào TTS.

## Ánh xạ ý định -> prompt

Xem `src/intent_router.py` (`INTENT_PROMPTS`):

| Ý định | Prompt |
|---|---|
| `greeting` | `system_greeting` |
| `product_question` | `system_sales` |
| `order` | `system_order` |
| `gift` | `system_gift` |
| `chat` / `other` | `system_chat` |
