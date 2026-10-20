"""Phân loại ý định bình luận/hoạt động live -> chọn đúng loại prompt.

Luồng:
  1. Model AI phân tích (cấu hình `analyst_llm_model`, vd jev) đọc bình luận ->
     trả JSON {"intent": "...", "product_hint": "...", "confidence": 0.x}
  2. Module này map intent -> tên prompt tương ứng trong prompts/*.md
  3. Nếu là câu hỏi sản phẩm -> dò sản phẩm trong context-live trước,
     fallback sang context-data.

Mọi prompt đều bắt LLM trả ONLY JSON; phần đọc kết quả dùng json_utils để chịu
được JSON lỗi (fence, nháy đơn, key không nháy, dấu phẩy thừa...).
"""
from __future__ import annotations

import os
import re
import time

try:
    import json_utils
except ImportError:  # frozen/onedir: package phang
    import json_utils  # type: ignore[no-redef]

# intent -> (tên prompt, mô tả tiếng Việt để hiện trong log/GUI)
INTENT_PROMPTS: dict[str, str] = {
    "greeting": "system_greeting",
    "product_question": "system_sales",
    "order": "system_order",
    "gift": "system_gift",
    "chat": "system_chat",
    "other": "system_chat",
}

INTENT_LABELS: dict[str, str] = {
    "greeting": "Chào hỏi",
    "product_question": "Hỏi về sản phẩm",
    "order": "Chốt đơn / mua hàng",
    "gift": "Tặng quà",
    "chat": "Trò chuyện thường",
    "other": "Khác",
}

VALID_INTENTS = tuple(INTENT_PROMPTS.keys())

# Cache phan loai intent theo text binh thuong.
# Comment trung lap rat pho bien tren live ("con hang khong shop?" lap lai nhieu lan)
# -> goi lai model la ton tai request. Cache theo (text, model) + TTL.
_CACHE_TTL_S: float = 300.0     # 5 phut: hang trong live hay doi -> phan loai cu theo hang
_CACHE_MAX: int = 500
_intent_cache: dict[str, tuple[float, dict]] = {}


def _cache_key(text: str, model: str = "") -> str:
    """Khoa cache: bo khoang trang thua + chuan hoa chu thuong.

    KE include model analyst: app hot-reload config (app.py) doi model ma khong
    xoa cache (GUI chay process khac) -> khoa theo text don thuan se tra ket qua
    cua model cu trong toi 300s. Khoa theo (text, model) tu chua lanh.
    """
    body = re.sub(r"\s+", " ", str(text or "").strip().lower())
    return f"{model}\x00{body}"


def clear_intent_cache() -> None:
    """Xoa cache phan loai (goi khi doi model analyst)."""
    _intent_cache.clear()


# Lý do thất bại gần nhất của bước phân tích bằng AI (để chẩn đoán trong log/GUI).
_LAST_ANALYZE_ERROR: str = ""

# Backoff nhẹ khi model phân tích bị giới hạn tần suất (HTTP 429):
# tạm bỏ qua AI trong vài giây để không dội thêm request vào server đang rate-limit.
_RATE_LIMIT_COOLDOWN_S: float = 30.0
_rate_limited_until: float = 0.0


def _in_rate_limit_cooldown() -> bool:
    """True nếu đang trong thời gian tạm hoãn gọi model phân tích do bị 429."""
    return time.monotonic() < _rate_limited_until


def rate_limit_remaining_s() -> float:
    """Số giây còn lại của thời gian tạm hoãn gọi model phân tích (0 nếu không hoãn)."""
    return max(0.0, _rate_limited_until - time.monotonic())


def last_analyze_error() -> str:
    """Lý do bước phân tích bằng AI thất bại ở lần gọi gần nhất ("" nếu không lỗi)."""
    return _LAST_ANALYZE_ERROR

# Từ khoá dự phòng khi không gọi được model phân tích (offline/LLM lỗi).
# Thu tu QUAN TRONG: cau hoi san pham / don hang / qua tang duoc xet TRUOC greeting,
# de cau "shop ơi size XL còn không" khong bi nham thanh chao hoi.
_FALLBACK_RULES: list[tuple[str, str]] = [
    ("product_question", r"\b(mã|ma|số|so|sp|item)\s*#?\d+\b"),
    ("product_question", r"\b(giá|bao nhiêu|size|còn hàng|mua|đặt|ship|freeship|mẫu|màu|chất liệu|bảo hành|có sẵn)\b"),
    ("order", r"\b(chốt đơn|đặt hàng|đã mua|thanh toán|xác nhận đơn)\b"),
    ("gift", r"\b(tặng quà|tặng|gửi tặng|thả tim)\b"),
    ("greeting", r"^\s*(alo|a lô|a lo|hê lô|helo|hello|hi|chào|chao|goắt-sắp)\b.*$"),
    ("greeting", r"\b(chào shop|chào sóp|shop ơi|sóp ơi|shop oi|có ai không|ai đó không)\b"),
]

_SYSTEM_PROMPT = """Bạn là bộ phân loại ý định bình luận livestream bán hàng TikTok Shop.

Nhiệm vụ: đọc bình luận/hoạt động của khách và xác định ĐÚNG MỘT ý định.

Các nhãn hợp lệ:
- "greeting": chào hỏi, gọi shop, hello, alo, chào mọi người.
- "product_question": hỏi về sản phẩm (giá, size, chất liệu, còn hàng, mẫu mã, bảo hành, ship).
- "order": chốt đơn, đặt hàng, xác nhận mua.
- "gift": tặng quà, gửi quà, thả tim.
- "chat": trò chuyện xã giao khác.
- "other": không thuộc các nhóm trên.

BẮT BUỘC CHỈ TRẢ VỀ DUY NHẤT MỘT OBJECT JSON HỢP LỆ, không thêm lời dẫn, không markdown.

JSON mẫu (trả đúng các khoá này):
{"intent": "greeting", "product_hint": "", "confidence": 0.95}

Quy tắc:
- "intent": một trong các nhãn hợp lệ ở trên, viết thường.
- "product_hint": nếu khách nhắc tới sản phẩm cụ thể thì ghi lại ĐÚNG cụm từ khách dùng (chép nguyên văn, không thay bằng tên khác); nếu không nhắc thì để chuỗi rỗng "".
- "confidence": số thực từ 0 đến 1.
""" 

_USER_TEMPLATE = """Danh sách sản phẩm đang bán (chỉ để tham chiếu, không bắt buộc nêu tên):
{products}

Bình luận/Hoạt động cần phân loại:
\"\"\"{text}\"\"\"
"""


def _is_decision_model(model: str) -> bool:
    """Model 'decision' (TypeSafe/jev) goi endpoint '/systemone', khong phai chat/completions."""
    m = str(model or "").lower()
    return "jev" in m or "decision" in m or "typesafe" in m


def _decision_questions() -> dict:
    """Cau hoi cho decision model: chon 1 nhan intent trong 6 nhan hop le."""
    return {
        "intent": {
            "type": "choice",
            "instructions": (
                "Phan loai y dich cua binh luan khach trong livestream ban hang TikTok Shop."
            ),
            "options": list(VALID_INTENTS),
            "criteria": {
                "greeting": "khach chao shop, goi shop, hoi co ai khong",
                "product_question": "khach hoi ve san pham: gia, size, con hang, mau, chat lieu, bao hanh, ship",
                "order": "khach chot don, dat hang, da mua, thanh toan",
                "gift": "khach tang qua, gui qua, tha tim cho shop",
                "chat": "tro chuyen xa giao, hoi thoi, cam on",
                "other": "khong thuoc nhom nao o tren",
            },
        }
    }


def classify_intent(
    text: str,
    products: list[dict] | None = None,
    model: str | None = None,
    timeout: float | None = None,
) -> dict:
    """Phân loại ý định bằng model AI cấu hình (`analyst_llm_model`).

    Trả về dict {"intent", "product_hint", "confidence", "source"}.
    `source` = "llm" (model trả kết quả), "cache" (lấy lại từ cache phân loại)
    hoặc "rule" (LLM lỗi/không cấu hình - dùng luật từ khoá).
    """
    global _LAST_ANALYZE_ERROR, _rate_limited_until

    raw = str(text or "").strip()
    if not raw:
        return {"intent": "other", "product_hint": "", "confidence": 0.0, "source": "rule"}

    _LAST_ANALYZE_ERROR = ""

    cfg_model = model
    if cfg_model is None:
        cfg_model = _analyst_model()
    if timeout is None:
        timeout = _analyst_timeout()

    # Cache: comment trung lap -> tra ket qua da phan loai, khong goi lai model.
    # Khoa gom model: doi model analyst (app hot-reload config) -> khoa doi -> goi lai.
    cache_key = _cache_key(raw, cfg_model or "")
    hit = _intent_cache.get(cache_key)
    if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_S:
        cached = dict(hit[1])
        cached["source"] = "cache"
        return cached
    if hit:
        _intent_cache.pop(cache_key, None)   # het TTL -> xoa

    def _remember(result: dict) -> dict:
        """Luu ket qua phan loai vao cache (chi khi dinh danh, khong luu loi)."""
        # CHI cache ket qua tu model. Ket qua luat tu khoa thi ton tai 0ms (khong
        # ton request) va co the stale: neu model loi roi hoi phuc, text do van
        # duoc tra tu cache thay vi goi lai model.
        if result.get("source") == "llm" and result.get("intent"):
            if len(_intent_cache) >= _CACHE_MAX:
                # Bo phan tu cu nhat.
                oldest = min(_intent_cache.items(), key=lambda kv: kv[1][0])[0]
                _intent_cache.pop(oldest, None)
            _intent_cache[cache_key] = (time.monotonic(), {
                "intent": result["intent"],
                "product_hint": result.get("product_hint", ""),
                "confidence": result.get("confidence", 0.5),
                "source": result.get("source", "rule"),
            })
        return result
    # Đang tạm hoãn do lần trước bị 429 -> dùng luật ngay, không dội thêm request
    if cfg_model and _in_rate_limit_cooldown():
        _LAST_ANALYZE_ERROR = (
            f"tạm hoãn gọi model phân tích còn {rate_limit_remaining_s():.0f}s (do bị giới hạn tần suất)"
        )
        result = classify_intent_rules(raw)
        result["error"] = _LAST_ANALYZE_ERROR
        return result

    if cfg_model and _is_decision_model(cfg_model):
        # Decision model (TypeSafe/jev): goi endpoint '/systemone', khong phai chat/completions.
        try:
            import llm_client
            answers = llm_client.decide(
                cfg_model, raw[:600], _decision_questions(), timeout=timeout)
            ans = answers.get("intent") or {}
            intent = str(ans.get("choice") or "").strip().lower()
            if intent in VALID_INTENTS:
                return _remember({
                    "intent": intent,
                    "product_hint": "",
                    "confidence": _to_float(ans.get("confidence"), 0.8),
                    "source": "llm",
                })
            _LAST_ANALYZE_ERROR = f"decision model tra intent khong hop le: {intent!r}"
        except Exception as e:
            _LAST_ANALYZE_ERROR = f"{type(e).__name__}: {e}"
        # Decision model khong dung duoc voi /chat/completions -> luật từ khoá.
        result = classify_intent_rules(raw)
        result["error"] = _LAST_ANALYZE_ERROR
        return result

    if cfg_model:
        try:
            import llm_client
            names = []
            for p in (products or [])[:20]:
                n = str(p.get("name") or "").strip()
                if n:
                    names.append(f"- {n}")
            sys_p = _SYSTEM_PROMPT
            usr_p = _USER_TEMPLATE.format(
                products="\n".join(names) or "(chưa có danh sách)",
                text=raw[:600],
            )
            reply = llm_client.chat(sys_p, usr_p, model=cfg_model, timeout=timeout)
            data = json_utils.as_dict(json_utils.parse_json_loose(reply, default={}))
            intent = str(data.get("intent") or "").strip().lower()
            intent = re.sub(r"[^a-z_]", "", intent.replace(" ", "_"))
            aliases = {
                "chao_hoi": "greeting", "chao": "greeting", "hello": "greeting",
                "hoi_san_pham": "product_question", "product": "product_question",
                "san_pham": "product_question", "question": "product_question",
                "sales": "product_question", "mua_hang": "order", "don_hang": "order",
                "qua_tang": "gift", "comment": "chat", "binh_luan": "chat",
            }
            intent = aliases.get(intent, intent)
            if intent not in VALID_INTENTS:
                intent = ""
            if intent:
                return _remember({
                    "intent": intent,
                    "product_hint": str(data.get("product_hint") or "").strip(),
                    "confidence": _to_float(data.get("confidence"), 0.8),
                    "source": "llm",
                })
            _LAST_ANALYZE_ERROR = f"model trả về intent không hợp lệ: {data.get('intent')!r}"
        except Exception as e:
            _LAST_ANALYZE_ERROR = f"{type(e).__name__}: {e}"
            # 429 -> tạm hoãn gọi AI một lúc (backoff nhẹ, không cache/retry phức tạp)
            if "429" in str(e) or "rate" in type(e).__name__.lower():
                _rate_limited_until = time.monotonic() + _RATE_LIMIT_COOLDOWN_S

    # Fallback luat tu khoa: khong cache (ton 0ms, va co the stale neu hang doi).
    result = classify_intent_rules(raw)
    result["error"] = _LAST_ANALYZE_ERROR
    return result


def _to_float(v, default: float) -> float:
    try:
        f = float(str(v).replace(",", ".").strip())
        return min(1.0, max(0.0, f))
    except Exception:
        return default


def _analyst_timeout() -> float:
    """Thời gian chờ tối đa cho bước phân tích (cấu hình `analyst_llm_timeout_s`)."""
    try:
        import settings
        return float(settings.get().get("analyst_llm_timeout_s", 12) or 12)
    except Exception:
        return float(os.getenv("ANALYST_LLM_TIMEOUT_S", "12") or 12)


def _analyst_model() -> str:
    """Model dùng cho bước phân tích (rỗng = tắt, dùng luật dự phòng)."""
    try:
        import settings
        return str(settings.get().get("analyst_llm_model") or "").strip()
    except Exception:
        return os.getenv("ANALYST_LLM_MODEL", "").strip()


def classify_intent_rules(text: str) -> dict:
    """Phân loại dự phòng bằng regex khi không có model phân tích."""
    s = str(text or "").lower().strip()
    for intent, pattern in _FALLBACK_RULES:
        if re.search(pattern, s, flags=re.IGNORECASE):
            return {"intent": intent, "product_hint": "", "confidence": 0.5, "source": "rule"}
    return {"intent": "other", "product_hint": "", "confidence": 0.3, "source": "rule"}


def prompt_for_intent(intent: str) -> str:
    """Tên file prompt (không gồm .md) tương ứng với ý định."""
    return INTENT_PROMPTS.get(str(intent or "").strip().lower(), "system_chat")


def intent_label(intent: str) -> str:
    """Nhãn tiếng Việt có dấu của ý định (hiển thị trong log/GUI)."""
    return INTENT_LABELS.get(str(intent or "").strip().lower(), "Khác")


# Prompt dùng để LLM sinh câu thoại, chia theo đúng loại ý định.
SPEAK_SYSTEM_TEMPLATE = """{base_prompt}

## Yêu cầu định dạng đầu ra (BẮT BUỘC)
1. CHỈ trả về DUY NHẤT một OBJECT JSON hợp lệ.
2. KHÔNG thêm lời dẫn, giải thích, hay khối markdown ```json.
3. Giữ đúng các khoá trong JSON mẫu sau:
{{"speak_text": "câu thoại tiếng Việt có dấu đầy đủ để đọc thành giọng nói", "kind": "{intent}", "priority": {priority}}}
4. "speak_text" chỉ chứa lời để ĐỌC, không chứa markdown, không chứa emoji, không chứa số dạng chữ số.
"""


def build_speak_prompt(base_prompt: str, intent: str, priority: int) -> str:
    """Ghép prompt nền (theo loại ý định) với yêu cầu only-JSON."""
    return SPEAK_SYSTEM_TEMPLATE.format(
        base_prompt=str(base_prompt or "").strip(),
        intent=str(intent or "chat"),
        priority=int(priority),
    )


def parse_speak_reply(reply: str, fallback_kind: str = "chat") -> dict:
    """Đọc phản hồi only-JSON của LLM -> {"speak_text", "kind", "priority"}."""
    data = json_utils.as_dict(json_utils.parse_json_loose(reply, default={}))
    if not data:
        # Model không trả JSON (hoặc JSON hỏng hẳn) -> coi cả phản hồi là câu thoại
        text = json_utils.strip_code_fence(reply)
        return {"speak_text": str(text or "").strip(), "kind": fallback_kind, "priority": 2}
    return {
        "speak_text": json_utils.get_str(data, "speak_text", "speakText", "text", "noi_dung", "noi dung"),
        "kind": json_utils.get_str(data, "kind", "type", "loai", default=fallback_kind) or fallback_kind,
        "priority": json_utils.get_int(data, "priority", "uu_tien", default=2),
    }
