"""Sinh bộ câu nhắc tương tác (remind) đa dạng và phát ngẫu nhiên, không lặp 10 câu gần nhất.

- `pool(base_text)` trả danh sách 10 câu (1 câu gốc + 9 câu do LLM sinh), cache theo nội dung gốc.
- LLM lỗi/offline -> dùng bộ mẫu dựng sẵn từ chính câu gốc.
- `pick(base_text)` chọn câu chưa dùng gần đây (phrase_cache), ghi nhận sau khi phát.
"""
from __future__ import annotations

import random
import re

import phrase_cache

_ACTIONS = [
    "thả tim cho sóp",
    "bấm tim ủng hộ sóp",
    "để lại một like cho sóp",
    "thả tim vàng cho sóp nha",
]
_COMMENTS = [
    "bình luận món bạn muốn tư vấn",
    "com men tên món bạn thích",
    "để lại bình luận để sóp tư vấn",
    "nhắn lên đây món bạn cần",
]
_TAILS = [
    "sóp cảm ơn cả nhà",
    "sóp cám ơn mọi người nhiều",
    "sóp biết ơn cả nhà lắm",
    "sóp cảm ơn bạn trước nha",
]
_OPENERS = [
    "Mọi người ơi",
    "Cả nhà ơi",
    "Cả nhà thân yêu ơi",
    "Mọi người xem lai ơi",
]


def _local_variants(base: str, count: int = 9) -> list[str]:
    """Dựng biến thể cục bộ (không gọi LLM) từ chính câu nhắc gốc."""
    core = re.sub(r"^(mọi người|cả nhà)[^,]*,\s*", "", (base or "").strip(), flags=re.I).strip(" ,.")
    topic = core or "nhớ thả tim và bình luận cho sóp nhé"
    topic = topic[0].upper() + topic[1:] if topic else topic
    out: list[str] = []
    for opener in _OPENERS:
        for action in _ACTIONS[:2]:
            out.append(f"{opener}, {action} nha, {random.choice(_COMMENTS)}, {random.choice(_TAILS)}.")
    while len(out) < count:
        out.append(
            f"{random.choice(_OPENERS)} ơi, {topic}, nhớ {random.choice(_ACTIONS)} "
            f"và {random.choice(_COMMENTS)} nhé, {random.choice(_TAILS)}."
        )
    # Giữ câu tự nhiên, bỏ trùng
    uniq: list[str] = []
    for line in out:
        if line not in uniq:
            uniq.append(line)
    return uniq[:count]


def _llm_variants(base: str, count: int = 9) -> list[str]:
    """Nhờ LLM viết lại câu nhắc thành nhiều cách nói khác nhau."""
    system = (
        "Bạn là streamer bán hàng livestream TikTok Shop, giọng thân thiện, tự nhiên.\n"
        "Nhiệm vụ: viết lại câu nhắc khán giả tương tác thành nhiều cách nói KHÁC NHAU.\n"
        "Quy tắc:\n"
        "1. Tiếng Việt có dấu đầy đủ, mỗi câu 12-30 từ, tự xưng 'sóp' (bắt buộc có chữ 'sóp').\n"
        "2. Không markdown, không bullet, không emoji, không đánh số.\n"
        "3. Mỗi dòng là MỘT câu hoàn chỉnh, khác nhau rõ về cách mở đầu, từ ngữ và kết câu.\n"
        "4. Phiên âm chữ số và từ mượn: 'like' -> 'lai', 'comment' -> 'com men', 'live' -> 'lai'.\n"
        f"5. Trả về ĐÚNG {count} dòng, không thêm lời dẫn."
    )
    user = (
        f"Câu nhắc gốc: {base}\n\n"
        f"Viết lại thành {count} câu nhắc khác nhau, giữ nguyên ý: xin tương tác (tim, bình luận) "
        f"và mời khán giả để lại món cần tư vấn."
    )
    try:
        import llm_client

        raw = llm_client.chat(system, user)
    except Exception:
        return []

    out: list[str] = []
    for line in str(raw or "").splitlines():
        clean = re.sub(r"^[\s\-\*\d\.\)]+", "", line).strip().strip('"').strip()
        if len(clean) < 12:
            continue
        if "sóp" not in clean.lower() and "shop" not in clean.lower():
            continue
        out.append(clean)
    return out[:count]


def pool(base_text: str, size: int = 10) -> list[str]:
    """Bộ câu nhắc: 1 câu gốc + (size-1) biến thể; cache theo nội dung gốc."""
    base = str(base_text or "").strip()
    if not base:
        return []

    def _build(n: int) -> list[str]:
        variants = _llm_variants(base, n) or _local_variants(base, n)
        return [base] + [v for v in variants if v != base]

    items = phrase_cache.cached_pool("remind", base, _build, size)
    return items or [base]


def pick(base_text: str) -> str:
    """Chọn một câu nhắc chưa dùng trong 10 lần gần nhất (tự ghi nhận sau khi trả về)."""
    import event_analyzer

    items = [event_analyzer.phoneticize_vietnamese(x) for x in pool(base_text)]
    chosen = phrase_cache.pick_unused("remind", items) or (items[0] if items else "")
    if chosen:
        phrase_cache.remember("remind", chosen)
    return chosen
