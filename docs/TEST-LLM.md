# Test LLM Integration

## Bằng chứng chạy (`scripts/check_llm.py`)

Lệnh: `python scripts/check_llm.py`
Kết quả:
```text
[INFO] Checking LLM endpoint: http://192.168.1.68:20130/v1 with model: claude-sonnet-5
[STATUS] OK
[SAMPLE_RESPONSE] Tôi là trợ lý AI hỗ trợ bán hàng livestream TikTok.
EXIT_CODE:0
```

## Đánh giá
- `config.py` đọc cấu hình từ file `.env` thành công (ẩn key khỏi source code).
- `llm_client.py` request qua `urllib` gọi thành công model `claude-sonnet-5`.
- Script không lỗi cứng và trả về `[STATUS] OK` hợp lệ.
