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
    assert "Chào" in flushed or "Hello" in flushed or "Xin chào" in flushed or "What'up" in flushed

def test_price_reply():
    intent = ChatIntent(os.path.join(os.path.dirname(__file__), "..", "context-data"))
    intent._load()
    assert len(intent.products) > 0
    
    ans = intent.answer("cái áo thun này giá bao nhiêu")
    assert ans is not None
    assert "150000" in ans or "150.000" in ans or "150k" in ans.lower()
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
