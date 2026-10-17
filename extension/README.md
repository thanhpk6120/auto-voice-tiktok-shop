# TikTok Shop Live Event Bridge — Chrome Extension

Extension (Manifest V3) bắt sự kiện thật từ khung chat TikTok Shop LIVE Dashboard và gửi về app desktop qua WebSocket local.

## Cài đặt

1. Mở Chrome/Edge → `chrome://extensions` (hoặc `edge://extensions`).
2. Bật **Developer mode** (góc trên phải).
3. Bấm **Load unpacked** → chọn thư mục `extension/` này.
4. Mở `https://shop.tiktok.com/streamer/live/product/dashboard` và đăng nhập tài khoản Shop.

## Kiến trúc

```
[TikTok Shop LIVE Dashboard]
        │  (DOM MutationObserver + hook window.WebSocket)
        ▼
  content.js  ──postMessage──►  background.js
                                      │  WebSocket
                                      ▼
                    ws://127.0.0.1:8765/ws?role=source
                                      │
                                      ▼
                            src/event_bridge.py
```

- `content.js`: chạy trong page context, hook `window.WebSocket` để bắt frame chat gốc, đồng thời `MutationObserver` theo dõi khung chat DOM (nhiều fallback selector, không phụ thuộc 1 class duy nhất).
- `background.js`: service worker giữ kết nối tới bridge, tự reconnect khi mất kết nối.
- `host_permissions`: `https://shop.tiktok.com/*`, `https://*.tiktok.com/*`.

## Schema event gửi đi

```json
{"type": "join",  "user": "Lan Anh", "ts": 1792222929.193}
{"type": "chat",  "user": "Minh Tuấn", "text": "Áo thun cotton có size XL không shop?", "ts": 1792222929.193}
{"type": "gift",  "user": "Thu Trang", "gift": "Hoa hồng", "count": 10, "ts": 1792222929.194}
{"type": "order", "user": "user_hong", "text": "chốt đơn SP01", "ts": 1792222929.194}
```

Bridge trả `ack` cho mỗi event: `{"type":"ack","seq":N,"events":["chat"],"counts":{"join":1,"chat":1}}`.

## Chạy thử không cần dashboard thật

```powershell
# Terminal 1 — bridge
python scripts/run_bridge.py

# Terminal 2 — gửi 3 event mẫu
python scripts/send_test_events.py
```

## Ghi chú độ bền

- Selector DOM dùng nhiều tầng fallback (`data-e2e`, `role=listitem`, text pattern) vì class của TikTok Shop đổi thường xuyên.
- Nếu chỉ hook WebSocket đã đủ dữ liệu, DOM observer là lớp dự phòng.
- Extension dùng chính phiên đăng nhập của người dùng, không gửi cookie ra ngoài.
