"""Event simulator cho phien live TikTok Shop.

Sinh chuoi event gia lap: join (don dap de test batch 3s), chat (hoi SP/gia/size),
gift, order. Co ho tro seed de tai lap ket qua.
"""
from __future__ import annotations

import random
import time
from typing import Iterator


DEFAULT_USERS = [
    "Lan Anh", "Minh Tuấn", "Hoàng Nam", "Thu Trang", "Phương Thảo",
    "Đức Huy", "Ngọc Mai", "Thanh Tùng", "Khánh Linh", "Văn Hậu"
]

CHAT_TEMPLATES = [
    "Áo thun cotton có size XL không shop?",
    "Shop ơi kem dưỡng da da dầu dùng được không?",
    "Tai nghe bass boost có bảo hành không ạ?",
    "Cho em hỏi giá áo thun hôm nay bao nhiêu?",
    "Kem dưỡng ẩm còn hàng không shop?",
    "Tai nghe bluetooth này dùng được mấy tiếng vậy?",
    "Có freeship không ạ?",
]

GIFTS = [
    {"gift_name": "Hoa hồng", "count": 1},
    {"gift_name": "Trái tim", "count": 10},
    {"gift_name": "Mũ bóng chày", "count": 1},
    {"gift_name": "Tên lửa", "count": 1},
]

ORDERS = [
    {"product": "Áo thun nam Cotton Compact", "amount": 150000},
    {"product": "Kem dưỡng da cấp ẩm Water Gel", "amount": 350000},
    {"product": "Tai nghe True Wireless Bass Boost", "amount": 450000},
]


def iter_events(
    seed: int | None = 42,
    base_ts: float | None = None,
    burst_join_count: int = 4
) -> Iterator[dict]:
    """Generator sinh chuỗi event vô hạn (hoặc lấy theo n) có tính lặp lại theo seed."""
    rng = random.Random(seed)
    current_ts = base_ts if base_ts is not None else time.time()

    # Phase 1: Tạo cụm join dồn dập trong khoảng 3s để test batching
    for i in range(burst_join_count):
        user = rng.choice(DEFAULT_USERS)
        yield {
            "type": "join",
            "user": user,
            "ts": round(current_ts + (i * 0.4), 2),
        }
    current_ts += 3.5

    # Phase 2: Vòng lặp phát sinh hỗn hợp đủ 4 loại type (join, chat, gift, order)
    # Đảm bảo phân bổ đều cả 4 loại
    event_pool = ["chat", "gift", "order", "join", "chat"]

    while True:
        ev_type = rng.choice(event_pool)
        user = rng.choice(DEFAULT_USERS)
        current_ts += rng.uniform(0.5, 2.5)
        ts = round(current_ts, 2)

        if ev_type == "join":
            yield {
                "type": "join",
                "user": user,
                "ts": ts,
            }
        elif ev_type == "chat":
            yield {
                "type": "chat",
                "user": user,
                "text": rng.choice(CHAT_TEMPLATES),
                "ts": ts,
            }
        elif ev_type == "gift":
            gift_info = rng.choice(GIFTS)
            yield {
                "type": "gift",
                "user": user,
                "gift_name": gift_info["gift_name"],
                "count": gift_info["count"],
                "ts": ts,
            }
        elif ev_type == "order":
            order_info = rng.choice(ORDERS)
            yield {
                "type": "order",
                "user": user,
                "product": order_info["product"],
                "amount": order_info["amount"],
                "ts": ts,
            }

# ponytail: generator iterator, co the mo rong them event follow/share khi can
