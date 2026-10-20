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


def test_greeting_prompt_has_no_product_context(monkeypatch):
    """Câu chào không được kéo sản phẩm vào prompt.

    Hồi quy: khi không match được sản phẩm nào, code cũ nhồi 5 sản phẩm đầu tiên vào
    ctx_str, nên một câu "Alo" bị LLM đọc thành lời chào kèm quảng cáo kem dưỡng ẩm.
    """
    import batch_processor as bp
    # Isolate phrase cache de khong doc nham lich su phat that tren may
    cache_dir = ROOT / "local_cache" / "_tmp_test_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for p in cache_dir.glob("*.json"):
        try:
            p.unlink()
        except OSError:
            pass
    monkeypatch.setenv("PHRASE_CACHE_DIR", str(cache_dir))
    seen_prompts: list[str] = []

    def fake_chat(system, user, model=None, timeout=None):
        # Bo qua prompt PHAN LOAI y dinh (no liet ke san pham de phan loai, hop le);
        # chi ghi lai prompt SINH CAU THOAI.
        if "MẢNG JSON" in user:
            seen_prompts.append(user)
        return '[{"type": "greeting", "user": "Thanh", "text": "Chào Thanh nhé!", "priority": 3}]'

    import llm_client
    import src.llm_client as src_llm

    # batch_processor import ca `src.llm_client` lan `llm_client` -> 2 module object khac nhau
    monkeypatch.setattr(llm_client, "chat", fake_chat)
    monkeypatch.setattr(src_llm, "chat", fake_chat)

    items = bp.process_event_batch(
        [{"type": "chat", "user": "Thanh", "text": "Alo"}],
        max_events=5,
        prompts_dir=str(ROOT / "prompts"),
        context_dir=str(ROOT / "context-data"),
        context_live_dir=str(ROOT / "context-live"),
    )
    assert items, "phải sinh được câu thoại"
    assert len(seen_prompts) == 1
    prompt = seen_prompts[0]
    for leak in ("kem dưỡng", "Giá:", "- Tên:", "Số thứ tự"):
        assert leak not in prompt, f"prompt greeting bị lẫn ngữ cảnh sản phẩm: {leak!r}"
    assert "không quảng cáo" in prompt.lower() or "không nêu tên sản phẩm" in prompt.lower()


def test_chat_product_question_still_gets_product_context(monkeypatch):
    """Nhóm không phải greeting vẫn phải nhận ngữ cảnh sản phẩm khách hỏi."""
    import batch_processor as bp
    import llm_client

    seen: list[str] = []

    def fake_chat(system, user, model=None, timeout=None):
        if "MẢNG JSON" in user:
            seen.append(user)
        return '[{"type": "sales", "user": "Minh", "text": "Áo thun này đây ạ.", "priority": 2}]'

    import src.llm_client as src_llm

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    monkeypatch.setattr(src_llm, "chat", fake_chat)
    items = bp.process_event_batch(
        [{"type": "chat", "user": "Minh", "text": "bánh tráng trộn giá bao nhiêu shop"}],
        max_events=5,
        prompts_dir=str(ROOT / "prompts"),
        context_dir=str(ROOT / "context-data"),
        context_live_dir=str(ROOT / "context-live"),
    )
    assert items
    assert seen, "phải gọi LLM"
    # Ngữ cảnh sản phẩm phải lấy từ context-live, đúng sản phẩm khách hỏi
    assert "Bánh Tráng Trộn" in seen[0], "câu hỏi sản phẩm phải có ngữ cảnh từ context-live"
    assert "Áo thun nam Cotton Compact" not in seen[0], "không được lẫn sản phẩm demo context-data"


def test_unmatched_product_gets_no_fabrication_warning(monkeypatch):
    """Khách hỏi món không có trong context-live -> prompt phải cấm bịa sản phẩm."""
    import batch_processor as bp
    import llm_client
    import src.llm_client as src_llm

    seen: list[str] = []

    def fake_chat(system, user, model=None, timeout=None):
        if "MẢNG JSON" in user:
            seen.append(user)
        return '[{"type": "sales", "user": "Thanh", "text": "Sóp chưa thấy món đó nha.", "priority": 2}]'

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    monkeypatch.setattr(src_llm, "chat", fake_chat)

    bp.process_event_batch(
        [{"type": "chat", "user": "Thanh", "text": "Áo thun còn không shop"}],
        max_events=5,
        prompts_dir=str(ROOT / "prompts"),
        context_dir=str(ROOT / "context-data"),
        context_live_dir=str(ROOT / "context-live"),
    )
    assert seen, "phải gọi LLM"
    prompt = seen[0]
    assert "KHÔNG CÓ SẢN PHẨM NÀO KHỚP" in prompt
    assert "KHÔNG bịa tên sản phẩm" in prompt
    # Không được lẫn sản phẩm demo từ context-data
    assert "Áo thun nam Cotton Compact" not in prompt
    assert "Kem dưỡng da cấp ẩm Water Gel" not in prompt


def test_context_live_is_the_only_source_when_present():
    """context-live có sản phẩm -> context-data (demo) không được nạp."""
    from event_analyzer import ChatIntent

    it = ChatIntent(str(ROOT / "context-data"), live_dir=str(ROOT / "context-live"))
    assert it.products, "phải nạp sản phẩm từ context-live"
    assert all(p.get("live") for p in it.products)
    names = " ".join(p["name"].lower() for p in it.products)
    for demo in ("áo thun nam cotton compact", "kem dưỡng da cấp ẩm water gel", "tai nghe true wireless"):
        assert demo not in names, f"lẫn sản phẩm demo: {demo}"
