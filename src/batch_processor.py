"""Xử lý gộp sự kiện theo cửa sổ 5 giây (Batch Event Processor).

Cơ chế:
1. Gom toàn bộ sự kiện diễn ra trong 5 giây vào hàng đợi.
2. Nếu KHÔNG có sự kiện nào mới -> KHÔNG gửi LLM (tiết kiệm 100% tài nguyên).
3. Nếu có quá nhiều sự kiện -> Tự động lọc bớt chống tràn:
   - Giữ 100% sự kiện Đơn hàng (order) và Quà tặng (gift).
   - Lọc bỏ các bình luận chat trùng lặp nội dung.
   - Gom toàn bộ người vào phòng (join) thành một danh sách chào chung.
   - Giữ tối đa `max_events` sự kiện quan trọng nhất.
4. Gọi LLM với prompt system_batch.md và ép trả về DUY NHẤT mảng JSON:
   [
     {"type": "order|sales|chat|greeting", "user": "...", "text": "...", "priority": 1|2|3}
   ]
5. Tách mảng JSON thành từng mục audio sẵn sàng đưa vào PriorityAudioQueue.
6. Fallback tự động: nếu LLM lỗi mạng/timeout, tự động xử lý cục bộ qua event_analyzer.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import user_chat_memory as ucm
except Exception:
    try:
        from . import user_chat_memory as ucm
    except Exception:
        from src import user_chat_memory as ucm

def _current_time_str() -> str:
    """Ngữ cảnh ngày giờ thực tế để trả lời chính xác khi khách hỏi hôm nay ngày mấy."""
    now = datetime.now()
    days = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
    day_name = days[now.weekday()]
    return f"Thời điểm hiện tại trên phiên live: {day_name}, ngày {now.day:02d}/{now.month:02d}/{now.year}, lúc {now.hour:02d}:{now.minute:02d}"

from event_analyzer import (
    analyze,
    get_batcher,
    get_prompt,
    phoneticize_vietnamese,
    clean_speak_text,
    _get_intent,
    ChatIntent,
)

try:
    import intent_router as ir
except ImportError:  # frozen/onedir: package phang
    import intent_router as ir  # type: ignore[no-redef]


def filter_batch_events(
    events: list[dict],
    max_events: int = 10,
) -> tuple[list[dict], list[str]]:
    """Lọc và chống tràn sự kiện trong 5 giây.

    Trả về: (danh sách sự kiện đã lọc, danh sách tên người dùng join phòng).
    """
    if not events:
        return [], []

    orders_and_gifts: list[dict] = []
    chats: list[dict] = []
    joined_users: list[str] = []
    seen_chat_texts: set[str] = set()

    for ev in events:
        typ = str(ev.get("type") or ev.get("kind") or "").lower()
        usr = str(ev.get("user") or ev.get("username") or "Khách").strip()
        txt = str(ev.get("text") or ev.get("content") or "").strip()

        if typ in ("order", "gift", "viewing_product", "viewing", "view_product", "xem_san_pham"):
            orders_and_gifts.append(ev)
        elif typ in ("join", "joined", "greeting"):
            if usr and usr not in ("Khách", "bạn mới") and usr not in joined_users:
                joined_users.append(usr)
        else:
            # chat / comment: lọc trùng nội dung
            key = f"{usr.lower()}:{txt.lower()}"
            if key not in seen_chat_texts:
                seen_chat_texts.add(key)
                chats.append(ev)

    # Ưu tiên: đơn hàng, quà tặng & đang xem sản phẩm trước, sau đó đến chat
    filtered: list[dict] = list(orders_and_gifts)
    remaining_slots = max(0, max_events - len(filtered))
    filtered.extend(chats[:remaining_slots])

    return filtered, joined_users


def _extract_complete_json_objects(text: str) -> list[dict]:
    """Cứu các object {...} hoàn chỉnh nếu mảng JSON bị cắt cụt giữa chừng."""
    out: list[dict] = []
    pos = 0
    try:
        import json_utils
    except ImportError:
        json_utils = None

    while True:
        start = text.find("{", pos)
        if start < 0:
            break
        depth = 0
        in_str = False
        escaped = False
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end > 0:
            chunk = text[start:end + 1]
            obj = json_utils.parse_json_loose(chunk, default=None) if json_utils else None
            if not isinstance(obj, dict):
                try:
                    obj = json.loads(chunk)
                except Exception:
                    obj = None
            if isinstance(obj, dict):
                out.append(obj)
            pos = end + 1
        else:
            break
    return out


def parse_llm_json_response(raw_text: str, fallback_events: list[dict] | None = None) -> list[dict]:
    """Bóc tách và chuẩn hóa mảng JSON từ phản hồi của LLM."""
    if not raw_text:
        return []

    # Dùng json_utils để chịu được mọi kiểu JSON lỗi của LLM
    # (code fence, nháy đơn, key/giá trị không nháy, dấu phẩy thừa, xuống dòng trong chuỗi...).
    try:
        import json_utils
    except ImportError:
        json_utils = None  # type: ignore[assignment]

    data = None
    if json_utils is not None:
        data = json_utils.parse_json_loose(raw_text, default=None)
        if isinstance(data, dict):
            data = json_utils.as_list(data)
    else:
        cleaned = raw_text.strip()
        if "```" in cleaned:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, flags=re.I)
            if m:
                cleaned = m.group(1).strip()
        m_arr = re.search(r"\[\s*\{[\s\S]*\}\s*\]", cleaned)
        if m_arr:
            cleaned = m_arr.group(0)
        try:
            data = json.loads(cleaned)
        except Exception:
            fixed = re.sub(r",\s*([\]\}])", r"\1", cleaned)
            try:
                data = json.loads(fixed)
            except Exception:
                data = None

    if not isinstance(data, list) or not data:
        # Cứu các object {...} hoàn chỉnh nếu mảng JSON bị cắt cụt giữa chừng
        data = _extract_complete_json_objects(raw_text)

    # Nếu vẫn không ra object nào mà raw_text là câu thoại tiếng Việt thông thường (LLM quên format JSON):
    if not data and raw_text and fallback_events:
        cleaned = raw_text.strip()
        if "```" in cleaned:
            cleaned = re.sub(r"```[a-zA-Z]*\n?|```", "", cleaned).strip()
        if "{" not in cleaned and "[" not in cleaned and len(cleaned) >= 10:
            first_ev = fallback_events[0]
            data = [{
                "type": first_ev.get("type") or first_ev.get("kind") or "chat",
                "user": first_ev.get("user") or "Khách",
                "text": cleaned,
                "priority": first_ev.get("priority", 2),
            }]
    valid_items: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        # Prompt theo ý định trả khoá "speak_text"; prompt batch cũ trả "text".
        # Đọc cả hai (và vài biến thể) để không mất câu thoại do LLM đổi tên khoá.
        raw_text_val = str(
            item.get("text")
            or item.get("speak_text")
            or item.get("speakText")
            or item.get("content")
            or item.get("message")
            or item.get("reply")
            or item.get("response")
            or item.get("answer")
            or item.get("noi_dung")
            or item.get("cau_tra_loi")
            or ""
        ).strip()
        if not raw_text_val:
            continue

        item_type = str(item.get("type") or item.get("kind") or "chat").lower()
        # Chuẩn hoá tên loại: prompt theo ý định dùng "product_question",
        # hệ thống âm thanh dùng "sales" -> map về đúng tên nội bộ.
        item_type = {
            "product_question": "sales",
            "product": "sales",
            "question": "sales",
            "other": "chat",
            "view": "viewing_product",
        }.get(item_type, item_type)
        if item_type not in ("order", "gift", "sales", "chat", "greeting", "viewing_product", "remind"):
            item_type = "chat"

        # Độ ưu tiên chuẩn hóa: 1 (order/gift/viewing_product), 2 (sales/chat), 3 (greeting/remind)
        priority = item.get("priority")
        if priority not in (1, 2, 3):
            if item_type in ("order", "gift", "viewing_product"):
                priority = 1
            elif item_type in ("sales", "chat"):
                priority = 2
            else:
                priority = 3

        # Đảm bảo phiên âm 100% tiếng Việt có dấu cho TTS
        max_w = int(os.getenv("SALES_MAX_WORDS", "75"))
        speak_text = phoneticize_vietnamese(clean_speak_text(raw_text_val, max_words=max_w))

        valid_items.append({
            "type": item_type,
            "user": str(item.get("user") or "Khách").strip(),
            "text": speak_text,
            "priority": int(priority),
        })

    return valid_items


class BatchEventCollector:
    """Thu gom sự kiện từ các luồng (thread-safe) với cơ chế overwriting buffer.

    - Hoạt động vào phòng (join/follow): chỉ giữ danh sách người mới nhất, đè lên cái cũ
      để tránh lưu nhiều trong bộ nhớ.
    - Hoạt động đang xem sản phẩm: lưu sự kiện xem mới nhất theo từng user (đè lên cũ).
    - Sự kiện ưu tiên cao (order, gift, viewing_product, chat): kích hoạt trigger ngay
      để tạo voice nhanh nhất có thể (không phải đợi hết batch_window_s).
    """

    def __init__(
        self,
        max_join_history: int = 5,
        max_high_priority: int = 20,
        greeting_user_cooldown_s: float = 180.0,
        on_event=None,
    ):
        self._lock = threading.Lock()
        self._high_priority: list[dict] = []
        self._latest_joins: list[str] = []
        self._latest_viewing: dict[str, dict] = {}
        self._other_activities: list[dict] = []
        self._user_greeting_history: dict[str, float] = {}
        self._greeting_user_cooldown_s = max(0.0, float(greeting_user_cooldown_s))
        self._event_trigger = threading.Event()
        self._max_join_history = max_join_history
        self._max_high_priority = max(1, int(max_high_priority))
        self._on_event = on_event

    def set_user_cooldown(self, cooldown_s: float) -> None:
        with self._lock:
            self._greeting_user_cooldown_s = max(0.0, float(cooldown_s))

    def set_max_join_history(self, count: int) -> None:
        with self._lock:
            self._max_join_history = max(1, int(count))
    def wake(self) -> None:
        """Danh thuc worker dang cho (vd: vua phat xong audio, co su kien moi cho san)."""
        self._event_trigger.set()

    def add(self, event: dict) -> None:
        if not event or not isinstance(event, dict):
            return
        typ = str(event.get("type") or event.get("kind") or "").lower()
        usr = str(event.get("user") or event.get("username") or "Khách").strip()

        notify = False
        with self._lock:
            if typ in ("order", "gift"):
                # De len ban cu cung (loai, nguoi dung): chi giu su kien moi nhat
                self._high_priority = [
                    e for e in self._high_priority
                    if not (e.get("type") == typ and e.get("user") == usr)
                ]
                self._high_priority.append(dict(event))
                notify = True
            elif typ in ("viewing_product", "viewing", "view_product", "xem_san_pham"):
                self._latest_viewing[usr] = dict(event)   # ghi de theo tung user
                notify = True
            elif typ in ("chat", "comment", "message"):
                # Chat: de len ban cu cua cung nguoi dung, giu cau moi nhat
                self._high_priority = [
                    e for e in self._high_priority
                    if not (e.get("type") in ("chat", "comment", "message") and e.get("user") == usr)
                ]
                self._high_priority.append(dict(event))
                notify = True
            elif typ in ("join", "joined", "greeting"):
                now = time.monotonic()
                if self._greeting_user_cooldown_s > 0 and len(self._user_greeting_history) > 500:
                    cutoff = now - self._greeting_user_cooldown_s
                    self._user_greeting_history = {
                        u: t for u, t in self._user_greeting_history.items() if t >= cutoff
                    }
                last_g = self._user_greeting_history.get(usr)
                if last_g is not None and (now - last_g < self._greeting_user_cooldown_s):
                    # Da chao trong vong cooldown -> bo qua, tranh chao lap lai
                    pass
                elif usr and usr not in ("Khách", "bạn mới"):
                    if usr in self._latest_joins:
                        self._latest_joins.remove(usr)
                    self._latest_joins.append(usr)
                    if len(self._latest_joins) > self._max_join_history:
                        self._latest_joins.pop(0)
                    # Neu da gom du nguoi cho 1 batch chao -> thuc day ngay de phat
                    if len(self._latest_joins) >= self._max_join_history:
                        notify = True
            else:
                self._other_activities = [dict(event)]
            self._enforce_cap_locked()

        if notify:
            self._event_trigger.set()
            if self._on_event is not None:
                try:
                    self._on_event()
                except Exception:
                    pass

    def _enforce_cap_locked(self) -> None:
        """Chan tran bo nho (goi khi da giu lock): giu 100% order/gift, cat bot phan con lai."""
        limit = self._max_high_priority
        if len(self._high_priority) <= limit:
            return
        keep: list[dict] = []
        tail: list[dict] = []
        for e in self._high_priority:
            (keep if e.get("type") in ("order", "gift") else tail).append(e)
        room = max(0, limit - len(keep))
        self._high_priority = (keep[:limit] + (tail[-room:] if room else []))

    def wait_for_batch(self, timeout: float = 5.0) -> bool:
        """Chờ sự kiện: nếu có sự kiện ưu tiên cao thì thức dậy ngay (fast-track),
        ngược lại chờ hết timeout của batch window."""
        triggered = self._event_trigger.wait(timeout=timeout)
        if triggered:
            time.sleep(0.15)
        return triggered

    def drain(self) -> list[dict]:
        """Lấy toàn bộ sự kiện mới nhất và giải phóng bộ nhớ ngay lập tức."""
        with self._lock:
            # Clear TRUOC khi doc: su kien den sau thoi diem nay se set lai trigger
            # -> khong bi mat tin hieu danh thuc (lost wakeup).
            self._event_trigger.clear()
            events: list[dict] = []
            events.extend(self._high_priority)
            self._high_priority.clear()

            for v in self._latest_viewing.values():
                events.append(v)
            self._latest_viewing.clear()

            now = time.monotonic()
            for u in self._latest_joins:
                self._user_greeting_history[u] = now
                events.append({"type": "join", "user": u, "text": f"{u} vừa vào phòng"})
            self._latest_joins.clear()

            events.extend(self._other_activities)
            self._other_activities.clear()

            return events

    def drain_latest(self) -> list[dict]:
        return self.drain()

    def size(self) -> int:
        with self._lock:
            return (
                len(self._high_priority)
                + len(self._latest_viewing)
                + len(self._latest_joins)
                + len(self._other_activities)
            )

    def has_high_priority(self) -> bool:
        with self._lock:
            return bool(self._high_priority or self._latest_viewing)

def group_events_by_intent(
    events: list[dict],
    products: list[dict] | None = None,
) -> dict[str, list[dict]]:
    """Nhóm sự kiện theo Ý DỊNH để gửi LLM với đúng loại prompt cho từng nhóm.

    Nhóm giúp KHÔNG tăng số lần gọi LLM: mỗi intent có mặt trong lô chỉ cần
    duy nhất 1 lời gọi với prompt tương ứng (system_greeting / system_sales /
    system_order / system_gift / system_chat).

    Trả về dict: intent -> danh sách sự kiện thuộc nhóm đó.
    Chat/hoạt động phân loại bằng intent_router (model AI cấu hình `analyst_llm_model`,
    lỗi/trễ thì tự động dùng luật từ khoá dự phòng).
    """
    out: dict[str, list[dict]] = {}
    for ev in (events or []):
        typ = str(ev.get("type") or ev.get("kind") or "chat").lower()
        if typ in ("viewing_product", "viewing", "view_product", "xem_san_pham"):
            intent = "product_question"          # đang xem sản phẩm = quan tâm sản phẩm
        elif typ == "order":
            intent = "order"
        elif typ == "gift":
            intent = "gift"
        elif typ == "join":
            intent = "greeting"
        else:  # chat / comment / message / remind ... -> phân loại theo nội dung
            text = str(ev.get("text") or ev.get("message") or ev.get("content") or "")
            intent = ""
            # 1. Khớp nhanh sản phẩm trong giỏ hàng (chuối, bim bim, bánh...) -> hỏi sản phẩm ngay (0ms)
            if products:
                try:
                    from event_analyzer import _get_intent
                    ci = _get_intent()
                    if ci:
                        p = ci.match(text)
                        if not p and ev.get("user") and ucm.is_valid_user(ev["user"]):
                            for turn in reversed(ucm.get_conversation_history(ev["user"])):
                                p = ci.match(turn.get("user_text") or "")
                                if p:
                                    break
                                p = ci.match(turn.get("reply_text") or "")
                                if p:
                                    break
                        if p:
                            intent = "product_question"
                except Exception:
                    pass
            # 2. Khớp nhanh bằng luật từ khoá (giá, ship, chốt đơn, chào...) (0ms)
            if not intent:
                try:
                    rule = ir.classify_intent_rules(text)
                    if rule.get("intent") in ("product_question", "order", "gift", "greeting"):
                        intent = rule["intent"]
                except Exception:
                    pass
            # 3. Câu trò chuyện xã giao khác -> mới gọi model AI phân loại sâu
            if not intent:
                intent = (ir.classify_intent(text, products=products)).get("intent") or "other"
        out.setdefault(intent, []).append(ev)
    return out


def _local_fallback_items(events: list[dict]) -> list[dict]:
    """Dựng câu thoại cục bộ (không gọi LLM) cho một nhóm sự kiện khi LLM lỗi."""
    items: list[dict] = []
    for ev in (events or []):
        res = analyze(ev, use_batcher=False)
        spk = res.get("speak_text")
        if not spk:
            continue
        items.append({
            "type": res.get("kind", ev.get("type", "chat")),
            "user": ev.get("user", "Khách"),
            "text": spk,
            "priority": int(res.get("priority", 2)),
        })
    return items


def process_event_batch(
    events: list[dict],
    max_events: int = 10,
    prompts_dir: str | Path | None = None,
    context_dir: str | Path | None = None,
    context_live_dir: str | Path | None = None,
) -> list[dict]:
    """Xử lý 1 lô sự kiện tích lũy trong 5 giây:

    - Nếu rỗng -> trả về [] (KHÔNG gọi LLM).
    - Lọc sự kiện chống tràn.
    - Gửi LLM kèm prompt system_batch.md.
    - Nhận mảng JSON và trả về danh sách audio items.
    - Tự động fallback xử lý cục bộ nếu LLM offline.
    """
    if not events:
        return []

    filtered_events, joined_users = filter_batch_events(events, max_events=max_events)
    if not filtered_events and not joined_users:
        return []

    # Người vào phòng được gom thành 1 sự kiện chào chung (không nằm trong filtered_events)
    join_event: dict | None = None
    if joined_users:
        names = ", ".join(joined_users[:6])
        if len(joined_users) > 6:
            names = f"{', '.join(joined_users[:5])} và {len(joined_users) - 5} người khác"
        join_event = {
            "type": "join",
            "user": names,
            "text": f"{names} vừa vào phòng live",
            "users": joined_users,
        }

    # Đọc ngữ cảnh sản phẩm từ context-live (nguồn duy nhất khi đã đồng bộ giỏ hàng live).
    # CHỈ sản phẩm được nhắc tới trong chính sự kiện mới vào prompt. Trước đây khi không
    # match được gì, code nhồi 5 sản phẩm đầu tiên, nên một câu "Alo" bị LLM đọc thành lời
    # chào kèm quảng cáo kem dưỡng ẩm — sản phẩm khách không hề nhắc.
    intent = ChatIntent(context_dir, live_dir=context_live_dir) if context_dir is not None else _get_intent()
    matched_products: list[dict] = []
    seen_prods: set[str] = set()

    def _match_event_or_history(ev: dict) -> dict | None:
        txt = ev.get("text") or ev.get("product") or ""
        p = intent.match(txt)
        if p:
            return p
        user = ev.get("user")
        if user and ucm.is_valid_user(user):
            for turn in reversed(ucm.get_conversation_history(user)):
                p = intent.match(turn.get("user_text") or "")
                if p:
                    return p
                p = intent.match(turn.get("reply_text") or "")
                if p:
                    return p
        return None

    for ev in filtered_events:
        prod = _match_event_or_history(ev)
        if prod and prod["name"] not in seen_prods:
            seen_prods.add(prod["name"])
            matched_products.append(prod)

    # ===== Nhóm sự kiện theo Ý DỊNH rồi gọi LLM với ĐÚNG prompt cho từng nhóm =====
    # Số lời gọi LLM <= số intent có mặt trong lô (không tăng theo số sự kiện).
    events_for_grouping = list(filtered_events)
    if join_event is not None:
        events_for_grouping.append(join_event)   # -> nhóm "greeting"
    grouped = group_events_by_intent(events_for_grouping, products=intent.products)

    all_items: list[dict] = []
    for group_intent, group_events in grouped.items():
        prompt_name = ir.prompt_for_intent(group_intent)
        group_priority = {"order": 1, "gift": 1, "product_question": 2, "chat": 2}.get(group_intent, 3)
        base_prompt = get_prompt(prompt_name, prompts_dir=prompts_dir)
        system_prompt = ir.build_speak_prompt(base_prompt, group_intent, group_priority)

        group_payload: list[dict] = []
        for ev in group_events:
            item = {
                "type": ev.get("type", ev.get("kind", group_intent)),
                "user": ev.get("user", "Khách"),
                "text": ev.get("text", ""),
            }
            if ev.get("product"):
                item["product"] = ev["product"]
            if ev.get("gift"):
                item["gift"] = ev["gift"]
                item["count"] = ev.get("count", 1)
            group_payload.append(item)

        # Ngữ cảnh sản phẩm RIÊNG cho nhóm này: chỉ những sản phẩm chính các sự kiện
        # trong nhóm nhắc tới. Nhóm greeting/chào hỏi KHÔNG nhận ngữ cảnh sản phẩm —
        # chào hỏi không cần bán hàng, và trước đây chính nó kéo kem dưỡng ẩm vào câu chào.
        group_products: list[dict] = []
        if group_intent != "greeting":
            gseen: set[str] = set()
            for ev in group_events:
                gprod = _match_event_or_history(ev)
                if gprod and gprod["name"] not in gseen:
                    gseen.add(gprod["name"])
                    group_products.append(gprod)
            if not group_products:
                group_products = matched_products

        if group_products:
            matched_info = "\n".join(
                f"- Tên: {pp['name']} | Giá: {pp.get('price') or 'ưu đãi'} | Mã số: {pp.get('index') or '-'}\n"
                f"  Mô tả: {(pp.get('description') or (pp.get('ctx') or '')).strip()[:400]}"
                for pp in group_products[:3]
            )
            ctx_str = f"Sản phẩm khớp với câu hỏi của khách:\n{matched_info}"
        elif group_intent != "greeting":
            # Dua tom tat danh sach gio hang de LLM tu doi chieu neu khach goi tat (chuoi, ga, bim bim...)
            live_prods = [
                f"- Mã {p.get('index', '-')}: {p['name'][:60]} | Giá: {p.get('price', 'ưu đãi')}"
                for p in getattr(intent, "products", [])[:12]
            ]
            ctx_str = "KHÔNG CÓ SẢN PHẨM NÀO KHỚP TRỰC TIẾP.\nDanh sách sản phẩm đang có trên giỏ hàng live (để đối chiếu):\n" + ("\n".join(live_prods) if live_prods else "(chưa có sản phẩm)")
        else:
            ctx_str = "(câu chào không cần nhắc sản phẩm, KHÔNG quảng cáo món nào)"

        # Thu thập lịch sử trò chuyện gần nhất theo từng khách hàng (trong 10 phút)
        history_blocks: list[str] = []
        for ev in group_events:
            u = ev.get("user")
            t = ev.get("text")
            if u and t and ucm.is_valid_user(u):
                h = ucm.format_history_for_prompt(u, t)
                if h and h not in history_blocks:
                    history_blocks.append(h)
                ucm.add_user_message(u, t)
        history_ctx = ("\n\n" + "\n\n".join(history_blocks)) if history_blocks else ""
        time_ctx = _current_time_str()
        if group_intent == "greeting":
            try:
                import phrase_cache
                avoid_ctx = phrase_cache.avoid_block("greeting")
            except Exception:
                avoid_ctx = ""
            if avoid_ctx:
                ctx_str = f"{ctx_str}\n\n{avoid_ctx}"
            user_prompt = (
                f"Ngữ cảnh: {ctx_str}\n\n"
                f"Nhóm ý định: greeting (khách vừa vào phòng / vừa chào shop)\n"
                f"Danh sách sự kiện thuộc nhóm này:\n"
                f"{json.dumps(group_payload, ensure_ascii=False, indent=2)}\n\n"
                f"YÊU CẦU: chỉ chào hỏi ngắn gọn, vui vẻ và mời khách ở lại xem lai. Xưng hô tự nhiên, linh hoạt (mình, tớ, sóp, em, tôi... tuỳ bạn chọn). "
                f"TUYỆT ĐỐI không giới thiệu, không quảng cáo, không nêu tên sản phẩm hay giá — khách chưa hỏi.\n\n"
                f"BẮT BUỘC chỉ trả về DUY NHẤT 1 MẢNG JSON, mỗi phần tử là 1 sự kiện trong danh sách trên,\n"
                f"dùng đúng các khoá: {{\"type\": \"greeting\", \"user\": \"tên khách\", "
                f"\"text\": \"câu chào tiếng Việt đã phiên âm\", \"priority\": {group_priority}}}\n"
                f"Không thêm lời dẫn, không markdown, không ```json."
            )
        else:
            user_prompt = (
                f"{time_ctx}\n\n"
                f"Ngữ cảnh giỏ hàng trên phiên live:\n{ctx_str}{history_ctx}\n\n"
                f"Nhóm ý định: {group_intent}\n"
                f"Danh sách sự kiện thuộc nhóm này:\n"
                f"{json.dumps(group_payload, ensure_ascii=False, indent=2)}\n\n"
                f"HƯỚNG DẪN TRẢ LỜI:\n"
                f"1. TRẢ LỜI TRỰC TIẾP, ĐÚNG VÀO CÂU HỎI của khách trước:\n"
                f"   - Nếu khách hỏi ngày/giờ: dùng đúng ngày tháng trong '{time_ctx}'.\n"
                f"   - Nếu khách hỏi thời tiết: trả lời tự nhiên, vui vẻ, mời khách ở nhà nhâm nhi đồ ăn xem lai.\n"
                f"   - Nếu khách hỏi thời tiết mưa gió giao bao lâu: trả lời thật lòng là mưa gió shipper có thể chậm hơn 1-2 ngày (tầm 2-3 ngày nhận được), nhưng hàng luôn được đóng gói bọc kỹ chống nước cẩn thận, đảm bảo giòn ngon.\n"
                f"   - Nếu có lịch sử trò chuyện với khách ở trên: trả lời liền mạch, ăn khớp câu chuyện trước đó.\n"
                f"2. Xưng hô linh hoạt, có duyên: tự xưng là 'mình', 'tớ', 'sóp', 'em', 'tôi', hoặc 'tấm thân nhỏ bé này'... KHÔNG bắt buộc câu nào cũng phải xưng 'sóp'. Gọi khách là 'bạn', 'cả nhà', 'anh/chị/em' hoặc tên khách.\n"
                f"3. Xoay quanh sản phẩm trong giỏ hàng: KHÔNG bịa tên sản phẩm, chất liệu hay giá. Nếu khách hỏi sản phẩm có trong giỏ hàng (kể cả gọi tắt như chuối, gà, bánh...), hãy đối chiếu và tư vấn đúng món đó. Chỉ khi khách hỏi món hoàn toàn không liên quan (như hỏi đồ điện tử, quần áo khi shop bán đồ ăn) thì mới lịch sự báo shop chưa có món này.\n"
                f"4. Nhẹ nhàng mời khách bấm giỏ hàng góc trái màn hình để xem thêm ưu đãi.\n\n"
                f"BẮT BUỘC chỉ trả về DUY NHẤT 1 MẢNG JSON, mỗi phần tử là 1 sự kiện trong danh sách trên,\n"
                f"dùng đúng các khoá: {{\"type\": \"{group_intent}\", \"user\": \"tên khách\", "
                f"\"text\": \"câu thoại tiếng Việt đã phiên âm\", \"priority\": {group_priority}}}\n"
                f"Không thêm lời dẫn, không markdown, không ```json."
            )

        try:
            from src import llm_client as _llm
        except Exception:
            try:
                from . import llm_client as _llm  # type: ignore
            except Exception:
                import llm_client as _llm  # type: ignore

        try:
            needed_tokens = max(600, len(group_payload) * 220)
            try:
                raw_response = _llm.chat(system_prompt, user_prompt, max_tokens=needed_tokens)
            except TypeError:
                raw_response = _llm.chat(system_prompt, user_prompt)
            items = parse_llm_json_response(raw_response, fallback_events=group_events)
            if items:
                # Ghi lại đúng loại/priority theo nhóm intent (LLM đôi khi nhầm)
                for it in items:
                    if group_intent == "product_question":
                        it.setdefault("type", "sales")
                    elif it.get("type") == "chat" and group_intent in ("order", "gift", "greeting"):
                        it["type"] = {"order": "order", "gift": "gift", "greeting": "greeting"}[group_intent]
                    # priority nhóm cao không thể thấp hơn ưu tiên nhóm
                    if int(it.get("priority", 3)) > group_priority:
                        it["priority"] = group_priority
                    u = it.get("user")
                    spk = it.get("text")
                    if u and spk:
                        ucm.add_bot_reply(u, spk)
                ucm.cleanup_expired()
                all_items.extend(items)
            else:
                snippet = (raw_response or "").strip().replace("\n", " ")[:150]
                print(f"[batch_processor] LLM nhóm '{group_intent}' trả về rỗng / không parse được JSON (raw: {snippet!r}), dùng fallback cục bộ", flush=True)
                for fallback in _local_fallback_items(group_events):
                    all_items.append(fallback)
        except Exception as e:
            print(f"[batch_processor] LLM nhóm '{group_intent}' lỗi ({e}), dùng fallback cục bộ", flush=True)
            for fallback in _local_fallback_items(group_events):
                all_items.append(fallback)

    if all_items:
        return all_items

    # Fallback cuối cùng: toàn bộ lô đều lỗi -> xử lý cục bộ, không gọi LLM
    print("[batch_processor] Toàn bộ lô sự kiện dùng fallback cục bộ", flush=True)
    return _local_fallback_items(events_for_grouping)
