# TEST-BRIDGE — Bằng chứng bridge nhận sự kiện thật

Ngày chạy: kiểm chứng lại bằng `python -m pytest tests/test_bridge_parse.py` + chạy bridge thật.

## 1. Parse DOM sample → event

`python -m pytest tests/test_bridge_parse.py -q` → **8 passed**.

Fixtures tại `tests/fixtures/raw_dom_samples/`:
- `dashboard_sample_1_comment_list.html`
- `dashboard_sample_2_role_listitem.html`
- `dashboard_sample_3_plain_text.html`

## 2. Bridge nhận event thật qua WebSocket

Cách chạy:
```powershell
# Terminal 1
python scripts/run_bridge.py

# Terminal 2
python scripts/send_test_events.py
```

Output client (sender):
```text
[client] ket noi ws://127.0.0.1:8765
[client] -> #1 {"type": "join", "user": "Lan Anh", "ts": 1792222929.193, "source": "send_test_events"}
[client] <- {"type": "ack", "seq": 1, "events": ["join"], "counts": {"join": 1}}
[client] -> #2 {"type": "chat", "user": "Minh Tuấn", "text": "Áo thun cotton có size XL không shop?", "ts": 1792222929.193, "source": "send_test_events"}
[client] <- {"type": "ack", "seq": 2, "events": ["chat"], "counts": {"join": 1, "chat": 1}}
[client] -> #3 {"type": "gift", "user": "Thu Trang", "gift": "Hoa hồng", "count": 10, "ts": 1792222929.194, "source": "send_test_events"}
[client] <- {"type": "ack", "seq": 3, "events": ["gift"], "counts": {"join": 1, "chat": 1, "gift": 1}}
[client] <- {"type": "pong", "ts": 1792222929.195078}

[client] ack=3 error=0
```

Output bridge (server):
```text
14:42:09 INFO websockets.server: connection open
14:42:09 INFO event_bridge: client ket noi: ('127.0.0.1', 57047)
14:42:09 INFO event_bridge: event #1 type=join user=Lan Anh
[14:42:09] EVENT #1 {"type": "join", "user": "Lan Anh", "source": "send_test_events", "_seq": 1}
14:42:09 INFO event_bridge: event #2 type=chat user=Minh Tuấn
[14:42:09] EVENT #2 {"type": "chat", "user": "Minh Tuấn", "text": ...
```

Kết luận: bridge nhận đủ 3/3 event (join, chat, gift), ack=3, error=0, heartbeat `pong` hoạt động.

## 3. Endpoint

- WebSocket: `ws://127.0.0.1:8765/ws?role=source` (extension) | `?role=app` (app desktop)
- CLI: `python src/event_bridge.py serve --port 8765 [--sim] [--speed 1.0]`

## Chưa làm / khi nào cần

- Chưa test với dashboard TikTok Shop thật (cần tài khoản seller đang live). Thêm khi có phiên live thật để hiệu chỉnh selector.
- `InvalidUpgrade: missing Connection header` xuất hiện khi có client không chuẩn handshake kết nối vào port — chỉ là noise log, không ảnh hưởng client hợp lệ.
