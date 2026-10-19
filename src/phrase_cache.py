"""Nhớ 10 câu gần nhất theo từng loại (greeting / remind) để LLM không sinh trùng.

Lưu ở `local_cache/recent_<kind>.json` (đã nằm trong .gitignore), ghi nguyên tử bằng
file tạm + os.replace để tiến trình đọc không thấy JSON dở dang.
"""
from __future__ import annotations

import json
import os
import random
import re
import threading
from pathlib import Path

LIMIT = 10
_lock = threading.Lock()


def _store_path(kind: str) -> Path:
    env_dir = os.getenv("PHRASE_CACHE_DIR")
    if env_dir:
        base = Path(env_dir)
    else:
        try:
            import settings

            base = settings.resolve_path("local_cache")
        except Exception:
            base = Path(__file__).resolve().parent.parent / "local_cache"
    base.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^a-z0-9_]", "", str(kind or "phrase").lower()) or "phrase"
    return base / f"recent_{name}.json"


def normalize(text: str) -> str:
    """Chuẩn hoá để so trùng: bỏ dấu câu, gộp khoảng trắng, lowercase."""
    cleaned = re.sub(r"[^0-9a-zà-ỹđ]+", " ", str(text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _read(kind: str) -> list[str]:
    path = _store_path(kind)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data if str(x).strip()]


def recent(kind: str, limit: int = LIMIT) -> list[str]:
    """Danh sách câu gần nhất, cũ -> mới."""
    return _read(kind)[-limit:]


def remember(kind: str, text: str) -> None:
    """Ghi nhận một câu vừa phát; giữ tối đa LIMIT câu."""
    clean = str(text or "").strip()
    if not clean:
        return
    with _lock:
        items = _read(kind)
        # Bo qua neu cau vua phat trung voi cau cuoi (tranh ghi trung khi nhieu noi cung goi)
        if items and normalize(items[-1]) == normalize(clean):
            return
        items.append(clean)
        items = items[-LIMIT:]
        path = _store_path(kind)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, path)
        except Exception:
            pass


def is_repeat(kind: str, text: str, limit: int = LIMIT) -> bool:
    """Câu này đã nằm trong N câu gần nhất chưa."""
    key = normalize(text)
    if not key:
        return False
    return any(normalize(x) == key for x in recent(kind, limit))


def avoid_block(kind: str, limit: int = LIMIT) -> str:
    """Khối text chèn vào user prompt để LLM tránh lặp lại."""
    used = recent(kind, limit)
    if not used:
        return ""
    lines = "\n".join(f"- {t}" for t in used)
    return (
        f"{len(used)} CÂU GẦN NHẤT ĐÃ DÙNG (TUYỆT ĐỐI KHÔNG lặp lại, kể cả chỉ đổi vài từ):\n"
        f"{lines}\n"
        "Hãy tạo câu MỚI khác rõ rệt về từ ngữ, cách mở đầu và cách kết câu."
    )


def pick_unused(kind: str, candidates: list[str], rng: random.Random | None = None) -> str | None:
    """Chọn ngẫu nhiên một câu chưa dùng; hết thì chọn câu dùng lâu nhất."""
    pool = [str(c).strip() for c in (candidates or []) if str(c).strip()]
    if not pool:
        return None
    used = {normalize(x) for x in recent(kind)}
    fresh = [c for c in pool if normalize(c) not in used]
    if fresh:
        return (rng or random).choice(fresh)
    order = recent(kind)
    rank = {normalize(t): i for i, t in enumerate(order)}
    return min(pool, key=lambda c: rank.get(normalize(c), -1))


def _pool_path(kind: str) -> Path:
    return _store_path(kind).with_name(f"pool_{_store_path(kind).stem[7:]}.json")


def cached_pool(kind: str, signature: str, generator, size: int = 10) -> list[str]:
    """Sinh & cache một bộ câu mẫu gắn với `signature` (vd nội dung remind gốc).

    Chỉ gọi lại `generator` khi signature đổi hoặc cache hỏng/ngắn hơn 2 câu.
    """
    path = _pool_path(kind)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("signature") == signature:
            items = [str(x).strip() for x in data.get("items") or [] if str(x).strip()]
            if len(items) >= 2:
                return items[:size]
    except Exception:
        pass

    try:
        items = [str(x).strip() for x in (generator(size) or []) if str(x).strip()]
    except Exception:
        items = []
    if not items:
        return []
    items = list(dict.fromkeys(items))[:size]
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(
            json.dumps({"signature": signature, "items": items}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        os.replace(tmp, path)
    except Exception:
        pass
    return items
