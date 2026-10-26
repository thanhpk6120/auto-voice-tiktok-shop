import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import user_chat_memory as ucm


def test_user_chat_memory_basic():
    ucm.clear_all()
    user = "NguyenVanA"

    # 1. Thêm tin nhắn từ khách
    ucm.add_user_message(user, "Bánh gấu có ngọt không shop?")
    history = ucm.get_conversation_history(user)
    assert len(history) == 1
    assert history[0]["user_text"] == "Bánh gấu có ngọt không shop?"
    assert history[0]["reply_text"] is None

    # 2. Thêm phản hồi của bot
    ucm.add_bot_reply(user, "Dạ bánh ngọt thanh dịu nhẹ bạn nhé.")
    history2 = ucm.get_conversation_history(user)
    assert len(history2) == 1
    assert history2[0]["reply_text"] == "Dạ bánh ngọt thanh dịu nhẹ bạn nhé."

    # 3. Thêm câu hỏi thứ 2 từ cùng khách
    ucm.add_user_message(user, "Thế có vị phô mai không?")
    history3 = ucm.get_conversation_history(user)
    assert len(history3) == 2
    assert history3[1]["user_text"] == "Thế có vị phô mai không?"

    # 4. Format prompt phải chứa cả câu trước và lời đáp trước
    prompt_str = ucm.format_history_for_prompt(user, "Thế có vị phô mai không?")
    assert "Bánh gấu có ngọt không shop?" in prompt_str
    assert "Dạ bánh ngọt thanh dịu nhẹ bạn nhé." in prompt_str


def test_user_chat_memory_ttl_expiration(monkeypatch):
    ucm.clear_all()
    user = "TestExpireUser"

    # Giả lập TTL cực ngắn 0.05s
    monkeypatch.setattr(ucm, "get_ttl_seconds", lambda: 0.05)

    ucm.add_user_message(user, "Câu hỏi 1")
    ucm.add_bot_reply(user, "Trả lời 1")
    assert len(ucm.get_conversation_history(user)) == 1

    # Đợi quá hạn TTL
    time.sleep(0.08)

    # Lấy lại -> đã tự động xoá
    assert len(ucm.get_conversation_history(user)) == 0
    assert ucm.format_history_for_prompt(user) == ""


def test_invalid_users_ignored():
    ucm.clear_all()
    for bad in ["", "Khách", "khach", "bạn mới", "người dùng", "sóp"]:
        ucm.add_user_message(bad, "Hello")
        assert len(ucm.get_conversation_history(bad)) == 0
