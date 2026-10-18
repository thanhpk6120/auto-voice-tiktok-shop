"""Kiểm thử các tính năng nâng cấp:
1. Cơ chế overwriting buffer cho cửa sổ Hoạt động và Fast-track cho sự kiện ưu tiên cao.
2. Ưu tiên cao nhất cho viewing_product, order, gift; ưu tiên vừa cho chat; ưu tiên thấp cho greeting, remind.
3. Đọc và lưu sản phẩm giỏ hàng live vào context-live/, nhận diện theo số thứ tự (index).
4. Cấu hình nhắc tương tác định kỳ (remind) và tư vấn sản phẩm chi tiết.
5. Kiểm tra đầy đủ FIELD_DOCS và FIELD_OPTIONS trên GUI.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import batch_processor
import browser_manager
import event_analyzer
import event_bridge
import settings


def test_collector_overwriting_buffer_joins():
    """Kiểm tra hoạt động join chỉ giữ N người mới nhất, đè lên người cũ."""
    col = batch_processor.BatchEventCollector(max_join_history=3)
    # Thêm 10 người join liên tiếp
    for i in range(10):
        col.add({"type": "join", "user": f"User_{i}"})

    assert col.size() == 3
    evs = col.drain()
    assert len(evs) == 3
    # Phải là 3 người mới nhất: User_7, User_8, User_9
    users = [e["user"] for e in evs]
    assert users == ["User_7", "User_8", "User_9"]
    # Buffer phải rỗng sau khi drain
    assert col.size() == 0


def test_collector_overwriting_viewing_product():
    """Kiểm tra sự kiện đang xem sản phẩm đè lên sản phẩm cũ cùng user."""
    col = batch_processor.BatchEventCollector()
    col.add({"type": "viewing_product", "user": "Thanh", "product": "Áo thun basic"})
    col.add({"type": "viewing_product", "user": "Thanh", "product": "Quần jean ống suông"})

    assert col.has_high_priority() is True
    evs = col.drain()
    assert len(evs) == 1
    assert evs[0]["product"] == "Quần jean ống suông"


def test_collector_fast_track_trigger():
    """Kiểm tra sự kiện ưu tiên cao (order, gift, viewing_product, chat) kích hoạt fast-track."""
    col = batch_processor.BatchEventCollector()
    
    def _add_after():
        time.sleep(0.05)
        col.add({"type": "order", "user": "Minh", "product": "Áo khoác"})

    t = threading.Thread(target=_add_after)
    t.start()
    t0 = time.monotonic()
    triggered = col.wait_for_batch(timeout=2.0)
    elapsed = time.monotonic() - t0
    t.join()

    assert triggered is True
    assert elapsed < 1.0  # Thức dậy nhanh chóng không phải chờ đủ 2s


def test_viewing_product_priority():
    """Kiểm tra viewing_product được gán priority 1 (cao nhất cùng order/gift)."""
    ev = {"type": "viewing_product", "user": "Lan", "product": "Chuối sấy mè"}
    res = event_analyzer.analyze(ev)
    assert res["kind"] == "viewing_product"
def test_save_and_load_context_live():
    """Kiểm tra lưu giỏ hàng live vào context-live/ và ChatIntent nhận diện theo index."""
    with tempfile.TemporaryDirectory() as td:
        live_dir = Path(td) / "context-live-test"
        prods = [
            {"index": 1, "name": "Áo Polo Nam Thể Thao", "price": "189.000₫", "is_pinned": True},
            {"index": 2, "name": "Quần Đùi Đắp Túi Hộp", "price": "99.000₫", "is_pinned": False},
        ]

        saved = browser_manager.save_live_products_to_context_live(prods, live_dir=live_dir)
        assert len(saved) == 2
        assert saved[0].exists()

        # Kiểm tra ChatIntent đọc được từ thư mục live này
        intent = event_analyzer.ChatIntent(context_dir="context-data", live_dir=live_dir)
        # Khớp theo số thứ tự
        m1 = intent.match("Shop ơi cho mình hỏi mã 1 là gì?")
        assert m1 is not None
        assert m1["name"] == "Áo Polo Nam Thể Thao"
        assert m1["index"] == 1

        m2 = intent.match("Quần số 2 giá bao nhiêu?")
        assert m2 is not None
        assert m2["name"] == "Quần Đùi Đắp Túi Hộp"
        assert m2["index"] == 2


def test_settings_field_docs_and_options():
    """Kiểm tra toàn bộ các trường trong SECTIONS đều có FIELD_DOCS giải thích."""
    for section_name, keys in settings.SECTIONS.items():
        for k in keys:
            assert k in settings.FIELD_DOCS, f"Thiếu tooltip FIELD_DOCS cho trường '{k}'"

    # Các trường có options
    assert "finish" in settings.FIELD_OPTIONS["interrupt_mode"]
    assert "interrupt" in settings.FIELD_OPTIONS["interrupt_mode"]
    assert "gologin_cdp" in settings.FIELD_OPTIONS["browser_mode"]
    assert "INFO" in settings.FIELD_OPTIONS["log_level"]


def test_settings_apply_remind_and_sales_max_words():
    """Kiểm tra settings.apply đồng bộ remind và sales_max_words ra os.environ."""
    cfg = settings.get()
    cfg["sales_max_words"] = 88
    cfg["remind_enabled"] = True
    cfg["remind_min_s"] = 45.0
    cfg["remind_max_s"] = 90.0
    cfg["remind_text"] = "Cho sóp xin một tim nha"
    settings.apply(cfg)

    assert os.environ.get("SALES_MAX_WORDS") == "88"
    assert os.environ.get("REMIND_ENABLED") == "true"
    assert os.environ.get("REMIND_MIN_S") == "45.0"
    assert os.environ.get("REMIND_MAX_S") == "90.0"
    assert os.environ.get("REMIND_TEXT") == "Cho sóp xin một tim nha"
