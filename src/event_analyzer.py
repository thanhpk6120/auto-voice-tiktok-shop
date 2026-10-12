"""Phân tích event live -> kind/priority/speak_text."""
from __future__ import annotations

import random
import re
import time
from pathlib import Path


class GreetingBatcher:
    """Gộp user join trong window cooldown thành một câu chào."""

    def __init__(self, cooldown: float = 3.0, templates: list[str] | None = None):
        self.cooldown = cooldown
        self.templates = templates or ["Chào", "Hello", "Xin chào", "What'up"]
        self._users: list[str] = []
        self._window_start: float | None = None

    def add(self, user: str) -> str | None:
        now = time.monotonic()
        if self._window_start is not None and self._users:
            if now - self._window_start >= self.cooldown:
                done = self.flush()
                self._users = [user]
                self._window_start = now
                return done
        if self._window_start is None:
            self._window_start = now
        self._users.append(user)
        return None

    def flush(self) -> str | None:
        if not self._users:
            return None
        template = random.choice(self.templates)
        users = list(self._users)
        self._users.clear()
        self._window_start = None
        return f"{template} {', '.join(users)}!"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


class ChatIntent:
    """Detect câu hỏi về SP từ context-data/*.md và trả lời RAG."""

    def __init__(self, context_dir: str | Path = "context-data"):
        p = Path(context_dir)
        if not p.is_absolute():
            p = _project_root() / p
        self.context_dir = p
        self.products: list[dict] = []
        self._load()

    def _load(self) -> None:
        self.products.clear()
        if not self.context_dir.is_dir():
            return
        for md in sorted(self.context_dir.glob("*.md")):
            try:
                text = md.read_text(encoding="utf-8")
            except Exception:
                continue
            name = ""
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("# "):
                    name = line[2:].strip()
                    break
                if line.startswith("#"):
                    name = line.lstrip("#").strip()
                    break
            if not name:
                continue
            tokens = [t.lower() for t in re.findall(r"\w+", name, flags=re.UNICODE)]
            keywords = {t for t in tokens if len(t) >= 2}
            price = ""
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("Giá:"):
                    price = line.split(":", 1)[1].strip()
                    break
            self.products.append({"name": name, "keywords": keywords, "ctx": text, "price": price})

    def match(self, text: str) -> dict | None:
        tl = (text or "").lower()
        for prod in self.products:
            if prod["name"].lower() in tl:
                return prod
            for kw in prod["keywords"]:
                if kw and kw in tl:
                    return prod
        return None

    def answer(self, question: str) -> str | None:
        prod = self.match(question)
        if prod is None:
            return None
        system = "Bạn là trợ lý bán hàng live, trả lời ≤35 từ tiếng Việt"
        user_prompt = f"Context: {prod['ctx']}\nCâu hỏi: {question}"
        try:
            try:
                from src import llm_client as _llm
            except Exception:
                try:
                    from . import llm_client as _llm
                except Exception:
                    import llm_client as _llm  # type: ignore
            return _llm.chat(system, user_prompt)
        except Exception:
            price_val = prod.get('price', '')
            if price_val:
                price_display = price_val if ("đ" in price_val or "k" in price_val.lower()) else f"{price_val}đ"
                price_str = f", giá {price_display}"
            else:
                price_str = ", giá ưu đãi hôm nay"
            return f"Dạ anh/chị ơi, {prod['name']} hiện shop vẫn còn hàng{price_str}, mình chốt đơn giúp shop nhé!"


_intent: ChatIntent | None = None
_batcher: GreetingBatcher | None = None


def _get_intent() -> ChatIntent:
    global _intent
    if _intent is None:
        _intent = ChatIntent()
    return _intent


def get_batcher() -> GreetingBatcher:
    global _batcher
    if _batcher is None:
        _batcher = GreetingBatcher(cooldown=3.0)
    return _batcher


def analyze(event: dict, use_batcher: bool = True) -> dict:
    """Map event -> {kind, priority, speak_text}."""
    ev = event or {}
    typ = str(ev.get("kind") or ev.get("type") or "").lower()
    user = str(ev.get("user") or ev.get("username") or "bạn mới")

    if typ in ("join", "joined", "greeting"):
        if use_batcher:
            batched_text = get_batcher().add(user)
            if batched_text:
                return {"kind": "greeting", "priority": 3, "speak_text": batched_text}
            return {"kind": "greeting", "priority": 3, "speak_text": None}
        template = random.choice(["Chào", "Hello", "Xin chào", "What'up"])
        return {"kind": "greeting", "priority": 3, "speak_text": f"{template} {user}!"}

    if typ in ("chat", "comment", "message"):
        text = str(ev.get("text") or ev.get("message") or ev.get("content") or "")
        ans = _get_intent().answer(text)
        if ans is not None:
            return {"kind": "sales", "priority": 2, "speak_text": ans}
        return {"kind": "chat", "priority": 3, "speak_text": text}

    if typ == "gift":
        gift = ev.get("gift") or ev.get("gift_name") or "quà"
        return {"kind": "gift", "priority": 1, "speak_text": f"Cảm ơn {user} đã tặng {gift}!"}

    if typ == "order":
        return {"kind": "order", "priority": 1, "speak_text": f"Cảm ơn {user} đã chốt đơn!"}

    return {"kind": typ or "unknown", "priority": 3, "speak_text": str(ev.get("text") or "")}
