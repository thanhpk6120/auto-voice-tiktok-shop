import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from event_analyzer import GreetingBatcher, ChatIntent, analyze, get_batcher
from audio_queue import PriorityAudioQueue
import time

def test_greeting_batch():
    batcher = get_batcher()
    # Reset state
    batcher._users.clear()
    batcher._window_start = None
    
    # Send users fast
    res1 = batcher.add("user1")
    res2 = batcher.add("user2")
    assert res1 is None
    assert res2 is None
    
    # Force flush
    flushed = batcher.flush()
    assert "user1, user2" in flushed
    assert any(x in flushed for x in ["Chào", "Hello", "Xin chào", "What'up", "Hê-lô", "Goắt-sắp"])

def test_price_reply():
    intent = ChatIntent(os.path.join(os.path.dirname(__file__), "..", "context-data"))
    intent._load()
    assert len(intent.products) > 0
    
    ans = intent.answer("cái áo thun này giá bao nhiêu")
    assert ans is not None
    assert any(x in ans.lower() for x in ["150000", "150.000", "150k", "một trăm năm mươi nghìn", "năm mươi nghìn"])
def test_queue_priority():
    q = PriorityAudioQueue()
    q.put("greeting", 3, "Hello", "join.wav")
    q.put("order", 1, "Thank you", "order.wav")
    
    # Pop
    item1 = q.get()
    assert item1["wav"] == "order.wav"
    assert item1["priority"] == 1
    
    item2 = q.get()
    assert item2["wav"] == "join.wav"
    assert item2["priority"] == 3

def test_greeting_batcher_check_timeout():
    b = GreetingBatcher(cooldown=1.0, max_batch=5)
    assert b.add("An") is None
    assert b.add("Bình") is None
    # Chua qua cooldown -> None
    assert b.check_timeout() is None
    # Gia lap qua cooldown
    b._window_start = time.monotonic() - 1.5
    flushed = b.check_timeout()
    assert flushed is not None
    assert "An, Bình" in flushed

def test_analyze_order_with_product_and_user_extraction():
    # Raw sentence tu TikTok khong co colon
    raw_ev = {
        "type": "order",
        "raw": "Khách hàng Đức Thắng đã chốt đơn 1 Áo thun Polo",
        "user": "Khách",
        "text": "Khách hàng Đức Thắng đã chốt đơn 1 Áo thun Polo"
    }
    res = analyze(raw_ev, use_batcher=False)
    assert res["kind"] == "order"
    assert res["priority"] == 1
    assert "Đức Thắng" in res["speak_text"]
    assert "Áo thun Polo" in res["speak_text"]

def test_analyze_chat_priority_and_formatting():
    ev_question = {"type": "chat", "user": "Mai Phương", "text": "Hôm nay mấy giờ shop đóng cửa vậy?"}
    res1 = analyze(ev_question, use_batcher=False)
    assert res1["priority"] == 2
    assert "Mai Phương hỏi: Hôm nay mấy giờ shop đóng cửa vậy?" in res1["speak_text"]

    ev_comment = {"type": "chat", "user": "Tuấn", "text": "Hôm nay vui vẻ nhé cả nhà"}
    res2 = analyze(ev_comment, use_batcher=False)
    assert res2["priority"] == 2
    assert "Tuấn bình luận: Hôm nay vui vẻ nhé cả nhà" in res2["speak_text"]
