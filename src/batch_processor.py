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
from pathlib import Path

from event_analyzer import (
    analyze,
    get_batcher,
    get_prompt,
    phoneticize_vietnamese,
    clean_speak_text,
    _get_intent,
    ChatIntent,
)


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


def parse_llm_json_response(raw_text: str) -> list[dict]:
    """Bóc tách và chuẩn hóa mảng JSON từ phản hồi của LLM."""
    if not raw_text:
        return []

    cleaned = raw_text.strip()
    # Loại bỏ markdown code block nếu có
    if "```" in cleaned:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, flags=re.I)
        if m:
            cleaned = m.group(1).strip()

    # Tìm mảng JSON [ ... ]
    m_arr = re.search(r"\[\s*\{[\s\S]*\}\s*\]", cleaned)
    if m_arr:
        cleaned = m_arr.group(0)

    try:
        data = json.loads(cleaned)
    except Exception:
        # Fallback thử sửa các lỗi JSON thường gặp (ví dụ dấu phẩy thừa ở cuối)
        fixed = re.sub(r",\s*([\]\}])", r"\1", cleaned)
        try:
            data = json.loads(fixed)
        except Exception:
            return []

    if not isinstance(data, list):
        return []

    valid_items: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        raw_text_val = str(item.get("text") or "").strip()
        if not raw_text_val:
            continue

        item_type = str(item.get("type") or "chat").lower()
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
        on_event=None,
    ):
        self._lock = threading.Lock()
        self._high_priority: list[dict] = []
        self._latest_joins: list[str] = []
        self._latest_viewing: dict[str, dict] = {}
        self._other_activities: list[dict] = []
        self._event_trigger = threading.Event()
        self._max_join_history = max_join_history
        self._max_high_priority = max(1, int(max_high_priority))
        self._on_event = on_event

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
                if usr and usr not in ("Khách", "bạn mới"):
                    if usr in self._latest_joins:
                        self._latest_joins.remove(usr)
                    self._latest_joins.append(usr)
                    if len(self._latest_joins) > self._max_join_history:
                        self._latest_joins.pop(0)
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

            for u in self._latest_joins:
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

    # Chuẩn bị payload danh sách sự kiện gửi cho LLM
    batch_payload: list[dict] = []
    if joined_users:
        batch_payload.append({
            "type": "join",
            "users": joined_users,
            "note": f"Có {len(joined_users)} người vừa vào phòng live"
        })
    for ev in filtered_events:
        item = {
            "type": ev.get("type", "chat"),
            "user": ev.get("user", "Khách"),
            "text": ev.get("text", ""),
        }
        if ev.get("product"):
            item["product"] = ev["product"]
        if ev.get("gift"):
            item["gift"] = ev["gift"]
            item["count"] = ev.get("count", 1)
        batch_payload.append(item)

    # Đọc prompt hệ thống system_batch.md
    system_prompt = get_prompt("system_batch", prompts_dir=prompts_dir)

    # Thu thập ngữ cảnh sản phẩm từ context-data/*.md và context-live/*.md
    intent = ChatIntent(context_dir, live_dir=context_live_dir) if context_dir is not None else _get_intent()
    matched_products: list[str] = []
    seen_prods: set[str] = set()

    for ev in filtered_events:
        txt = ev.get("text") or ev.get("product") or ""
        prod = intent.match(txt)
        if prod and prod["name"] not in seen_prods:
            seen_prods.add(prod["name"])
            price_val = prod.get("price", "Liên hệ")
            matched_products.append(f"- {prod['name']}: Giá {price_val}. Chi tiết: {prod.get('ctx', '')}")

    if not matched_products and intent.products:
        for p in intent.products[:5]:
            matched_products.append(f"- {p['name']}: Giá {p.get('price', 'ưu đãi')}. Chi tiết: {p.get('ctx', '')[:300]}")

    context_str = "\n".join(matched_products) if matched_products else "Chưa có thông tin sản phẩm cụ thể."

    user_prompt = (
        f"Thông tin các sản phẩm trên live:\n{context_str}\n\n"
        f"Danh sách các sự kiện diễn ra trong 5 giây vừa qua:\n"
        f"{json.dumps(batch_payload, ensure_ascii=False, indent=2)}\n\n"
        f"BẮT BUỘC chỉ trả về 1 mảng JSON duy nhất. Không thêm bất kỳ văn bản nào ngoài JSON!"
    )

    try:
        try:
            from src import llm_client as _llm
        except Exception:
            try:
                from . import llm_client as _llm
            except Exception:
                import llm_client as _llm  # type: ignore

        raw_response = _llm.chat(system_prompt, user_prompt)
        items = parse_llm_json_response(raw_response)
        if items:
            return items
    except Exception as e:
        print(f"[batch_processor] LLM batch lỗi ({e}), chuyển sang fallback cục bộ", flush=True)

    # Fallback xử lý cục bộ nếu LLM không trả JSON hoặc lỗi mạng
    fallback_items: list[dict] = []
    if joined_users:
        if len(joined_users) <= 3:
            names_str = ", ".join(joined_users)
        else:
            names_str = f"{', '.join(joined_users[:2])} và {len(joined_users) - 2} người khác"
        fallback_items.append({
            "type": "greeting",
            "user": names_str,
            "text": phoneticize_vietnamese(f"Xin chào {names_str} đã vào xem lai!"),
            "priority": 3,
        })

    for ev in filtered_events:
        res = analyze(ev, use_batcher=False)
        spk = res.get("speak_text")
        if spk:
            fallback_items.append({
                "type": res.get("kind", ev.get("type", "chat")),
                "user": ev.get("user", "Khách"),
                "text": spk,
                "priority": int(res.get("priority", 2)),
            })

    return fallback_items
