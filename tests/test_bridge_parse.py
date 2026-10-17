"""Test parse DOM dashboard -> event dung schema (stdlib assert, khong framework).

Chay: python tests/test_bridge_parse.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from event_bridge import classify_line, dom_to_events, normalize_event  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "raw_dom_samples"
REQUIRED = {"type", "user", "ts"}
VALID_TYPES = {"join", "chat", "gift", "order"}


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _check_schema(event: dict) -> None:
    assert REQUIRED <= set(event), f"thieu field bat buoc: {event}"
    assert event["type"] in VALID_TYPES, f"type sai: {event}"
    assert isinstance(event["user"], str) and event["user"].strip(), f"user rong: {event}"
    assert isinstance(event["ts"], (int, float)) and event["ts"] > 0, f"ts sai: {event}"
    if event["type"] == "chat":
        assert event.get("text"), f"chat thieu text: {event}"
    if event["type"] == "gift":
        assert event.get("gift"), f"gift thieu gift name: {event}"
        assert isinstance(event.get("count"), int) and event["count"] > 0, f"gift count sai: {event}"
    if event["type"] == "order":
        assert event.get("amount") is None or event["amount"] >= 0
    json.dumps(event, ensure_ascii=False)  # phai serialize duoc


def test_fixture_1_comment_list():
    events = dom_to_events(_load("dashboard_sample_1_comment_list.html"))
    assert len(events) == 3, events
    assert [e["type"] for e in events] == ["chat", "chat", "chat"]
    assert events[0]["user"] == "Lan Anh"
    assert "size XL" in events[0]["text"]
    assert events[2]["user"] == "Thu Trang"
    for event in events:
        _check_schema(event)
        assert event["source"] == "dom"


def test_fixture_2_role_listitem():
    events = dom_to_events(_load("dashboard_sample_2_role_listitem.html"))
    assert len(events) == 4, events
    by_type = {e["type"]: e for e in events}
    assert set(by_type) == VALID_TYPES, by_type.keys()
    assert by_type["chat"]["user"] == "Hoàng Nam"
    assert "bảo hành" in by_type["chat"]["text"]
    assert by_type["join"]["user"] == "Khánh Linh"
    assert by_type["gift"]["gift"] == "Hoa hồng" and by_type["gift"]["count"] == 10
    assert by_type["order"]["product"] == "Tai nghe True Wireless Bass Boost"
    assert by_type["order"]["amount"] == 450000
    for event in events:
        _check_schema(event)


def test_fixture_3_plain_text_fallback():
    events = dom_to_events(_load("dashboard_sample_3_plain_text.html"))
    assert len(events) == 5, events
    by_type: dict[str, dict] = {}
    for event in events:  # giu ban ghi dau tien cua moi type
        by_type.setdefault(event["type"], event)
    assert set(by_type) == VALID_TYPES, by_type.keys()
    assert by_type["chat"]["user"] == "Phương Thảo" and by_type["chat"]["text"] == "Có freeship không ạ?"
    assert by_type["join"]["user"] == "Thanh Tùng"
    assert by_type["gift"]["gift"] == "Tên lửa" and by_type["gift"]["count"] == 1
    assert by_type["order"]["product"] == "Áo thun nam Cotton Compact"
    assert by_type["order"]["amount"] == 150000
    for event in events:
        _check_schema(event)


def test_all_fixture_events_flow_into_analyzer():
    """Event parse ra phai duoc analyzer hien tai tieu thu duoc (khong vo pipeline)."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from event_analyzer import analyze

    for name in sorted(p.name for p in FIXTURES.glob("*.html")):
        for event in dom_to_events(_load(name)):
            result = analyze(event, use_batcher=False)
            assert result["kind"] in ("greeting", "chat", "sales", "gift", "order"), result
            assert "priority" in result and "speak_text" in result


def test_normalize_accepts_aliases():
    event = normalize_event({"event": "comment", "nickname": "Minh Tuấn", "content": "Còn hàng không?"})
    assert event["type"] == "chat" and event["user"] == "Minh Tuấn" and event["text"] == "Còn hàng không?"
    gift = normalize_event({"type": "gift", "username": "Thu Trang", "giftName": "Hoa hồng", "giftCount": "3"})
    assert gift["gift"] == "Hoa hồng" and gift["count"] == 3
    order = normalize_event({"kind": "order", "user": "Đức Huy", "productName": "Áo thun", "price": 150000})
    assert order["type"] == "order" and order["amount"] == 150000
    _check_schema(event)
    _check_schema(gift)
    _check_schema(order)


def test_normalize_rejects_bad_events():
    bad = [
        {},                                             # thieu type
        {"type": "unknown_thing", "user": "a"},         # type la
        {"type": "chat", "text": "hi"},                 # thieu user
        {"type": "chat", "user": "a"},                  # chat thieu text
        "not-an-object",
    ]
    for item in bad:
        try:
            normalize_event(item)
        except ValueError:
            continue
        raise AssertionError(f"phai raise ValueError: {item}")


def test_classify_line_variants():
    assert classify_line("Lan Anh đã tham gia")["type"] == "join"
    assert classify_line("Minh Tuấn: giá bao nhiêu shop?")["type"] == "chat"
    gift = classify_line("Thu Trang đã tặng Hoa hồng x10")
    assert gift["type"] == "gift" and gift["gift"] == "Hoa hồng" and gift["count"] == 10
    order = classify_line("Đức Huy đã chốt đơn Áo thun nam 150.000đ")
    assert order["type"] == "order" and order["amount"] == 150000
    assert classify_line("") is None
    assert classify_line("một dòng vô nghĩa") is None


def test_dedupe_same_event_in_one_batch():
    html = (
        '<div class="comment-item"><span>Lan Anh</span>: Có freeship không?</div>'
        '<div class="comment-item"><span>Lan Anh</span>: Có freeship không?</div>'
        '<div class="comment-item"><span>Lan Anh</span>: Size L còn không?</div>'
    )
    events = dom_to_events(html)
    assert len(events) == 2, events


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} test pass")
    sys.exit(1 if failed else 0)
