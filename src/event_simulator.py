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

# Cau hoi chung, khong gan voi san pham cu the nao (simulator khong nen fix cung SP).
CHAT_TEMPLATES = [
    "Sản phẩm này còn hàng không shop?",
    "Có freeship không ạ?",
    "Sản phẩm này giá bao nhiêu vậy shop?",
    "Còn size này không shop?",
    "Bảo hành thế nào ạ?",
    "Có ship tỉnh không shop?",
]

GIFTS = [
    {"gift_name": "Hoa hồng", "count": 1},
    {"gift_name": "Trái tim", "count": 10},
    {"gift_name": "Mũ bóng chày", "count": 1},
    {"gift_name": "Tên lửa", "count": 1},
]

def _live_products() -> list[dict]:
    """Doc gio hang live tu context-live. Rong neu chua dong bo duoc."""
    try:
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from event_analyzer import ChatIntent

        return ChatIntent("context-data", live_dir="context-live").products
    except Exception:
        return []


def _order_pool() -> list[dict]:
    prods = _live_products()
    if not prods:
        return [{"product": "Sản phẩm trong giỏ hàng", "amount": 0}]
    return [{"product": p["name"], "amount": _price_int(p)} for p in prods[:8]]


def _viewing_pool() -> list[str]:
    prods = _live_products()
    return [p["name"] for p in prods[:8]] or ["Sản phẩm trong giỏ hàng"]


def _price_int(prod: dict) -> int:
    """Gia dang chu ('5.000₫') -> so nguyen; 0 neu khong doc duoc."""
    import re

    digits = re.sub(r"[^\d]", "", str(prod.get("price") or ""))
    try:
        return int(digits) if digits else 0
    except ValueError:
        return 0


def iter_events(
    seed: int | None = 42,
    base_ts: float | None = None,
    burst_join_count: int = 4
) -> Iterator[dict]:
    """Generator sinh chuỗi event vô hạn (hoặc lấy theo n) có tính lặp lại theo seed."""
    rng = random.Random(seed)
    current_ts = base_ts if base_ts is not None else time.time()
    # Lay san pham tu gio hang live hien tai thay vi danh sach fix cung.
    order_pool = _order_pool()
    viewing_pool = _viewing_pool()

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
    event_pool = ["chat", "gift", "order", "join", "chat", "viewing_product"]

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
        elif ev_type == "viewing_product":
            product = rng.choice(viewing_pool)
            yield {
                "type": "viewing_product",
                "user": user,
                "product": product,
                "text": f"{user} đang xem sản phẩm {product}",
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
            order_info = rng.choice(order_pool)
            yield {
                "type": "order",
                "user": user,
                "product": order_info["product"],
                "amount": order_info["amount"],
                "ts": ts,
            }

# ponytail: generator iterator, co the mo rong them event follow/share khi can
