"""Kiểm thử bộ xử lý gom sự kiện theo batch 5 giây (BatchEventProcessor)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from batch_processor import (
    BatchEventCollector,
    filter_batch_events,
    parse_llm_json_response,
    process_event_batch,
)
from event_analyzer import get_prompt, configure


def test_filter_batch_empty():
    evs, joins = filter_batch_events([])
    assert evs == []
    assert joins == []


def test_filter_batch_dedupes_and_aggregates_joins():
    raw_events = [
        {"type": "join", "user": "Thanh"},
        {"type": "join", "user": "Thanh"},  # Trùng join
        {"type": "join", "user": "Lan Anh"},
        {"type": "chat", "user": "Minh", "text": "Áo này size gì?"},
        {"type": "chat", "user": "Minh", "text": "Áo này size gì?"},  # Trùng chat
        {"type": "order", "user": "Huy", "product": "Áo thun"},
        {"type": "gift", "user": "Trang", "gift": "Hoa hồng"},
    ]
    filtered, joins = filter_batch_events(raw_events, max_events=10)

    # Joins gom thành 2 người không trùng
    assert joins == ["Thanh", "Lan Anh"]

    # Đơn hàng và quà tặng giữ nguyên
    types = [e["type"] for e in filtered]
    assert "order" in types
    assert "gift" in types

    # Chat chỉ giữ 1 câu
    chat_events = [e for e in filtered if e["type"] == "chat"]
    assert len(chat_events) == 1
    assert chat_events[0]["user"] == "Minh"


def test_filter_batch_overflow_protection():
    # 2 đơn hàng + 15 bình luận
    raw_events = [
        {"type": "order", "user": f"Khách {i}", "product": "Bánh tráng"}
        for i in range(2)
    ]
    raw_events += [
        {"type": "chat", "user": f"User {i}", "text": f"Câu hỏi {i}"}
        for i in range(15)
    ]

    filtered, _ = filter_batch_events(raw_events, max_events=5)
    # Tối đa 5 sự kiện: 2 order bắt buộc giữ, chỉ lấy thêm 3 chat
    assert len(filtered) == 5
    order_count = sum(1 for e in filtered if e["type"] == "order")
    assert order_count == 2


def test_parse_llm_json_response_clean():
    sample_json = json.dumps([
        {
            "type": "order",
            "user": "Đức Thắng",
            "text": "Cảm ơn Đức Thắng đã chốt đơn 1 Áo thun giá 150000 đ!",
            "priority": 1,
        },
        {
            "type": "sales",
            "user": "Hồng Nhung",
            "text": "Chuối sấy mè giá 1₫ ưu đãi hôm nay!",
            "priority": 2,
        },
        {
            "type": "greeting",
            "user": "Thanh",
            "text": "Xin chào Thanh nhé what's up!",
            "priority": 3,
        }
    ])
    items = parse_llm_json_response(sample_json)
    assert len(items) == 3

    # Kiểm tra tự động phiên âm số và tiếng Anh
    order_item = items[0]
    assert order_item["type"] == "order"
    assert "một trăm năm mươi nghìn đồng" in order_item["text"]

    sales_item = items[1]
    assert "một đồng" in sales_item["text"]

    greeting_item = items[2]
    assert "goắt sắp" in greeting_item["text"]


def test_parse_llm_json_response_with_markdown_blocks():
    raw = (
        "Dưới đây là kết quả:\n"
        "```json\n"
        "[\n"
        '  {"type": "chat", "user": "Thanh", "text": "Chào Thanh, sóp đây!", "priority": 2}\n'
        "]\n"
        "```\n"
        "Chúc bạn livestream vui vẻ!"
    )
    items = parse_llm_json_response(raw)
    assert len(items) == 1
    assert items[0]["user"] == "Thanh"
    assert items[0]["text"] == "Chào Thanh, sóp đây!"


def test_batch_event_collector():
    col = BatchEventCollector()
    assert col.size() == 0

    col.add({"type": "chat", "text": "hello"})
    col.add({"type": "order", "user": "An"})
    assert col.size() == 2

    drained = col.drain()
    assert len(drained) == 2
    assert col.size() == 0


def test_get_prompt_from_prompts_dir():
    # Kiểm tra đọc từ thư mục prompts/
    p_sales = get_prompt("system_sales")
    assert len(p_sales) > 100
    assert "livestream" in p_sales.lower() or "bán hàng" in p_sales.lower()

    p_chat = get_prompt("system_chat")
    assert len(p_chat) > 100
    assert "streamer" in p_chat.lower()

    p_batch = get_prompt("system_batch")
    assert len(p_batch) > 100
    assert "json" in p_batch.lower()
