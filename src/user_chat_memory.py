"""Quản lý luồng hội thoại (chat history) theo từng khách hàng.

Mục đích:
- Nhớ ngữ cảnh trao đổi với từng khách trong phiên livestream.
- Tránh việc khách chat câu trước, câu sau hỏi tiếp thì AI lại quên và trả lời lạc quẻ.
- Mặc định lưu trong 10 phút (TTL có thể cấu hình qua settings hoặc biến môi trường).
- Tự động dọn dẹp các phiên chat quá hạn.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any

# Khóa luồng đảm bảo thread-safe
_lock = threading.Lock()

# Cấu trúc: {user_key: [{"user_text": str, "reply_text": str | None, "ts": float}, ...]}
_conversations: dict[str, list[dict[str, Any]]] = {}

# Mặc định: 10 phút, tối đa 5 lượt trao đổi gần nhất
DEFAULT_TTL_MINUTES = 10.0
DEFAULT_MAX_TURNS = 5


def get_ttl_seconds() -> float:
    """Thời gian hết hạn của luồng chat (tính bằng giây)."""
    try:
        import settings
        mins = float(settings.get().get("chat_history_ttl_minutes", DEFAULT_TTL_MINUTES) or DEFAULT_TTL_MINUTES)
    except Exception:
        mins = float(os.getenv("CHAT_HISTORY_TTL_MINUTES", str(DEFAULT_TTL_MINUTES)))
    return max(1.0, mins) * 60.0


def _clean_user_key(user: str) -> str:
    """Chuẩn hoá tên khách để làm khoá tra cứu."""
    return str(user or "").strip().lower()


def is_valid_user(user: str) -> bool:
    """Kiểm tra tên khách có hợp lệ để nhớ luồng không."""
    u = _clean_user_key(user)
    if not u or u in ("khách", "khach", "bạn mới", "ban moi", "người dùng", "ai", "bot", "sóp", "shop"):
        return False
    return True


def add_user_message(user: str, text: str) -> None:
    """Ghi nhận câu nhắn mới của khách hàng vào luồng hội thoại."""
    if not is_valid_user(user) or not text or not str(text).strip():
        return

    key = _clean_user_key(user)
    now = time.monotonic()
    ttl = get_ttl_seconds()

    with _lock:
        turns = _conversations.get(key, [])
        # Lọc bỏ các lượt đã quá hạn TTL
        valid_turns = [t for t in turns if (now - t["ts"]) <= ttl]
        # Thêm lượt mới
        valid_turns.append({
            "user_text": str(text).strip(),
            "reply_text": None,
            "ts": now,
        })
        # Giữ tối đa số lượt gần nhất
        if len(valid_turns) > DEFAULT_MAX_TURNS:
            valid_turns = valid_turns[-DEFAULT_MAX_TURNS:]
        _conversations[key] = valid_turns


def add_bot_reply(user: str, reply: str) -> None:
    """Ghi nhận câu trả lời của AI/streamer vào lượt trao đổi gần nhất của khách."""
    if not is_valid_user(user) or not reply or not str(reply).strip():
        return

    key = _clean_user_key(user)
    with _lock:
        turns = _conversations.get(key)
        if not turns:
            return
        # Cập nhật vào lượt gần nhất chưa có reply hoặc lượt cuối
        for t in reversed(turns):
            if t.get("reply_text") is None:
                t["reply_text"] = str(reply).strip()
                return
        turns[-1]["reply_text"] = str(reply).strip()


def get_conversation_history(user: str) -> list[dict[str, Any]]:
    """Lấy danh sách các lượt trao đổi gần nhất của khách còn trong hạn TTL."""
    if not is_valid_user(user):
        return []

    key = _clean_user_key(user)
    now = time.monotonic()
    ttl = get_ttl_seconds()

    with _lock:
        turns = _conversations.get(key)
        if not turns:
            return []
        valid_turns = [t for t in turns if (now - t["ts"]) <= ttl]
        if not valid_turns:
            _conversations.pop(key, None)
            return []
        _conversations[key] = valid_turns
        return list(valid_turns)


def format_history_for_prompt(user: str, current_text: str | None = None) -> str:
    """Định dạng lịch sử hội thoại thành đoạn văn bản ngữ cảnh cho prompt của LLM."""
    history = get_conversation_history(user)
    if not history:
        return ""

    lines: list[str] = []
    # Chỉ lấy các lượt trước đó (có cả lời khách và câu trả lời của bot)
    # Lượt cuối cùng nếu chưa có reply_text và trùng với current_text thì không in trùng
    for t in history:
        u_txt = t.get("user_text", "")
        r_txt = t.get("reply_text")
        if u_txt == current_text and r_txt is None:
            continue
        lines.append(f'- Khách: "{u_txt}"')
        if r_txt:
            lines.append(f'- Streamer đã trả lời: "{r_txt}"')

    if not lines:
        return ""

    header = (
        f"LỊCH SỬ TRAO ĐỔI GẦN ĐÂY VỚI KHÁCH HÀNG ({user}) TRONG VÒNG 10 PHÚT QUA:\n"
        + "\n".join(lines)
        + "\n* Lưu ý: Khách đang nói tiếp câu chuyện ở trên, hãy trả lời liền mạch, ăn khớp với ngữ cảnh đã trao đổi!"
    )
    return header


def cleanup_expired() -> int:
    """Quét và xoá toàn bộ các phiên hội thoại đã hết hạn TTL."""
    now = time.monotonic()
    ttl = get_ttl_seconds()
    removed = 0
    with _lock:
        keys_to_remove = []
        for key, turns in _conversations.items():
            valid_turns = [t for t in turns if (now - t["ts"]) <= ttl]
            if not valid_turns:
                keys_to_remove.append(key)
            else:
                _conversations[key] = valid_turns
        for k in keys_to_remove:
            _conversations.pop(k, None)
            removed += 1
    return removed


def clear_all() -> None:
    """Xoá toàn bộ lịch sử (dùng cho test hoặc reset)."""
    with _lock:
        _conversations.clear()
