"""Phân tích event live -> kind/priority/speak_text."""
from __future__ import annotations

import random
import re
import time
from pathlib import Path


class GreetingBatcher:
    """Gộp user join trong window cooldown thành một câu chào."""

    def __init__(self, cooldown: float = 3.0, max_batch: int = 5, templates: list[str] | None = None):
        self.cooldown = cooldown
        self.max_batch = max(1, int(max_batch))
        self.templates = templates or ["Chào", "Xin chào", "Hê-lô", "Goắt-sắp"]
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
        if len(self._users) >= self.max_batch:
            return self.flush()
        return None
    def check_timeout(self) -> str | None:
        """Nếu cửa sổ cooldown đã qua và có người đang chờ, flush ngay."""
        now = time.monotonic()
        if self._window_start is not None and self._users:
            if now - self._window_start >= self.cooldown:
                return self.flush()
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
    """Goc repo (source) hoac thu muc canh .exe (frozen). Xem settings._project_root()."""
    try:
        import settings

        return settings._project_root()
    except Exception:
        return Path(__file__).resolve().parent.parent


# prefix la bullet markdown: bat buoc co khoang trang sau dau (khac "**bold**")
_BULLET_RE = re.compile(r"^([-*•]|\d+[.)])\s+")
_NOTE_PREFIXES = ("→", "->", "=>", "#", "ghi chú", "note:", "lưu ý:")
_NOTE_WORDS = ("cần xác nhận", "cần kiểm tra", "nếu shop")


def clean_speak_text(text: str, max_words: int = 45) -> str:
    """Bo ghi chu noi bo / markdown khoi cau LLM truoc khi dua cho TTS.

    LLM doi khi tra kem dong huong dan ("-> Can xac nhan...") hoac bullet; doc len live
    la loi. Giu lai toi da `max_words` tu cua cau thoai dau tien.
    """
    if not text:
        return ""
    lines = []
    for raw in str(text).splitlines():
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        low = line.lower()
        if _BULLET_RE.match(line) or low.startswith(_NOTE_PREFIXES) or any(w in low for w in _NOTE_WORDS):
            continue
        lines.append(line)
    body = " ".join(l for l in lines if l).strip()
    body = body.replace("**", "").replace("__", "").replace("`", "")
    body = re.sub(r'\s+', " ", body).strip().strip('"').strip("'").strip()
    if not body:
        return ""
    words = body.split(" ")
    if len(words) > max_words:
        body = " ".join(words[:max_words]).rstrip(",;:") + "."
    return body

_DIGITS_VI = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]


def _read_3_digits(n: int, has_higher: bool = False) -> str:
    tram = n // 100
    chuc = (n % 100) // 10
    donvi = n % 10
    res = []
    if tram > 0 or has_higher:
        res.append(f"{_DIGITS_VI[tram]} trăm")
    if chuc == 0:
        if donvi > 0 and (tram > 0 or has_higher):
            res.append("linh")
    elif chuc == 1:
        res.append("mười")
    else:
        res.append(f"{_DIGITS_VI[chuc]} mươi")

    if chuc == 0 and donvi > 0:
        res.append(_DIGITS_VI[donvi])
    elif chuc == 1 and donvi == 1:
        res.append("một")
    elif chuc > 1 and donvi == 1:
        res.append("mốt")
    elif chuc > 0 and donvi == 5:
        res.append("lăm")
    elif chuc > 0 and donvi > 0 and donvi != 1 and donvi != 5:
        res.append(_DIGITS_VI[donvi])
    return " ".join(res)


def num_to_vi_words(n: int) -> str:
    """Chuyển số nguyên thành chữ tiếng Việt có dấu tự nhiên."""
    if n == 0:
        return "không"
    units = ["", "nghìn", "triệu", "tỷ"]
    groups = []
    temp = abs(n)
    while temp > 0:
        groups.append(temp % 1000)
        temp //= 1000
    res = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g > 0:
            words = _read_3_digits(g, has_higher=(i < len(groups) - 1))
            res.append(f"{words} {units[i]}".strip())
    prefix = "âm " if n < 0 else ""
    return prefix + " ".join(res).strip()


_PHONETIC_DICT = [
    (re.compile(r"\bwhat['’]?s?\s*up\b", re.I), "goắt sắp"),
    (re.compile(r"\bhello\b", re.I), "hê lô"),
    (re.compile(r"\bflash\s*sale\b", re.I), "phờ-lát sêu"),
    (re.compile(r"\bsale\b", re.I), "sêu"),
    (re.compile(r"\bfreeship\b", re.I), "miễn phí vận chuyển"),
    (re.compile(r"\blivestream\b", re.I), "lai-sờ-trim"),
    (re.compile(r"\blive\b", re.I), "lai"),
    (re.compile(r"\bsnack\b", re.I), "xì-nách"),
    (re.compile(r"\bcombo\b", re.I), "com-bô"),
    (re.compile(r"\bdeal\b", re.I), "điu"),
    (re.compile(r"\border\b", re.I), "chốt đơn"),
    (re.compile(r"\bsize\b", re.I), "sai"),
]


def phoneticize_vietnamese(text: str) -> str:
    """Phiên âm toàn bộ số, đơn vị tiền, từ tiếng Anh sang tiếng Việt có dấu chuẩn cho TTS."""
    if not text:
        return ""
    res = str(text)
    for pattern, repl in _PHONETIC_DICT:
        res = pattern.sub(repl, res)

    def _replace_currency_dong(m):
        raw_num = m.group(1).replace(".", "").replace(",", "")
        if raw_num.isdigit():
            return num_to_vi_words(int(raw_num)) + " đồng"
        return m.group(0)
    res = re.sub(r"(\d[\d.,]*)\s*(?:đ|₫|VND|vnd|dong|đồng)", _replace_currency_dong, res)

    def _replace_currency_k(m):
        val = int(m.group(1)) * 1000
        return num_to_vi_words(val) + " đồng"
    res = re.sub(r"\b(\d+)\s*[kK]\b", _replace_currency_k, res)

    def _replace_pct(m):
        raw_num = m.group(1).replace(".", "").replace(",", "")
        if raw_num.isdigit():
            return num_to_vi_words(int(raw_num)) + " phần trăm"
        return m.group(0)
    res = re.sub(r"(\d[\d.,]*)\s*%", _replace_pct, res)

    def _replace_kg(m):
        raw_num = m.group(1).replace(".", "").replace(",", "")
        if raw_num.isdigit():
            return num_to_vi_words(int(raw_num)) + " ki-lô-gam"
        return m.group(0)
    res = re.sub(r"\b(\d[\d.,]*)\s*(?:kg|kí|cân)\b", _replace_kg, res, flags=re.I)

    def _replace_gram(m):
        raw_num = m.group(1).replace(".", "").replace(",", "")
        if raw_num.isdigit():
            return num_to_vi_words(int(raw_num)) + " gam"
        return m.group(0)
    res = re.sub(r"\b(\d[\d.,]*)\s*(?:g|gr|gram)\b", _replace_gram, res, flags=re.I)

    def _replace_standalone_num(m):
        raw_num = m.group(1)
        if raw_num.isdigit() and len(raw_num) <= 6:
            return num_to_vi_words(int(raw_num))
        return m.group(0)
    res = re.sub(r"\b(\d+)\b", _replace_standalone_num, res)

    return re.sub(r"\s+", " ", res).strip()

_VI_STOPWORDS = {
    # Danh từ / Định lượng chung
    "ăn", "vặt", "đồ", "nhẹ", "món", "sản", "phẩm", "hàng", "loại", "giá",
    "deal", "túi", "hộp", "shop", "tiền", "bịch", "gói", "lon", "hũ", "set",
    "1kg", "500g", "250g", "food", "snack", "combo", "vị", "hạn", "sl", "id",
    "chuẩn", "chất", "lượng", "loại",
    # Quan hệ từ / Đại từ xưng hô
    "cho", "của", "và", "các", "những", "này", "kia", "đó", "với", "rất",
    "thực", "khô", "tặng", "mua", "bán", "nhà", "ơi", "ạ", "nhé", "hôm", "nay",
    "mình", "bạn", "em", "anh", "chị", "cô", "bác", "thế", "nào", "gì", "ai",
    "sao", "đâu", "được", "nhiều", "ít", "quá", "lắm", "thì", "là", "mà", "ở",
    # Từ hỏi / Trợ từ
    "có", "không", "chưa", "hả", "chăng", "phải", "bao", "nhiêu", "vậy",
    # Tính từ chung
    "ngon", "giòn", "thơm", "cay", "siêu", "mát", "đẹp", "tốt",
    # Động từ / Hoạt động chung
    "làm", "từ", "miễn", "phí", "vận", "chuyển", "ship", "gửi", "đặt", "chốt",
    "xem", "hỏi", "thử", "thấy", "biết", "xin"
}


class ChatIntent:
    """Detect câu hỏi về SP từ context-data/*.md và trả lời RAG."""

    def __init__(self, context_dir: str | Path = "context-data"):
        p = Path(context_dir)
        if not p.is_absolute():
            # frozen: context-data nam trong _internal (_MEIPASS), co the bi ghi de
            # bang ban copy canh .exe -> settings.resolve_path lo thu tu do.
            try:
                import settings

                p = settings.resolve_path(p)
            except Exception:
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
            raw_tokens = [t.lower() for t in re.findall(r"\w+", name, flags=re.UNICODE)]
            keywords = {t for t in raw_tokens if len(t) >= 2 and t not in _VI_STOPWORDS}
            bigrams = set()
            for i in range(len(raw_tokens) - 1):
                w1, w2 = raw_tokens[i], raw_tokens[i + 1]
                if w1 not in _VI_STOPWORDS or w2 not in _VI_STOPWORDS:
                    bigrams.add(f"{w1} {w2}")
            price = ""
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("Giá:"):
                    price = line.split(":", 1)[1].strip()
                    break
            self.products.append({"name": name, "keywords": keywords, "bigrams": bigrams, "ctx": text, "price": price})

    def match(self, text: str) -> dict | None:
        tl = (text or "").lower()
        q_raw_tokens = [t.lower() for t in re.findall(r"\w+", tl, flags=re.UNICODE)]
        q_tokens = set(q_raw_tokens) - _VI_STOPWORDS
        q_bigrams = {f"{q_raw_tokens[i]} {q_raw_tokens[i + 1]}" for i in range(len(q_raw_tokens) - 1)}
        best_prod = None
        best_score = 0

        for prod in self.products:
            score = 0
            p_name_lower = prod["name"].lower()
            if p_name_lower in tl:
                score += 150
            matched_bigrams = prod.get("bigrams", set()).intersection(q_bigrams)
            score += len(matched_bigrams) * 40
            matched_kws = prod.get("keywords", set()).intersection(q_tokens)
            score += len(matched_kws) * 10

            if score > best_score:
                best_score = score
                best_prod = prod

        return best_prod if best_score >= 20 else None

    def answer(self, question: str) -> str | None:
        prod = self.match(question)
        if prod is None:
            return None
        system = (
            "Bạn là trợ lý bán hàng livestream TikTok Shop, chuyên sinh câu trả lời để tạo giọng đọc Text-To-Speech (TTS).\n"
            "Quy tắc BẮT BUỘC để giọng đọc phát âm chuẩn và tự nhiên:\n"
            "1. TOÀN BỘ câu trả lời PHẢI là tiếng Việt có dấu đầy đủ.\n"
            "2. TUYỆT ĐỐI KHÔNG viết số dạng chữ số (0-9) hay ký hiệu tiền tệ (đ, ₫, k, %, /). BẮT BUỘC PHIÊN ÂM TOÀN BỘ THÀNH CHỮ TIẾNG VIỆT:\n"
            "   - Ví dụ: 10000 đ -> 'mười nghìn đồng', 1₫ -> 'một đồng', 28.900₫ -> 'hai mươi tám nghìn chín trăm đồng', 1kg -> 'một cân' hoặc 'một ki-lô-gam', 99% -> 'chín mươi chín phần trăm'.\n"
            "3. TẤT CẢ các từ tiếng Anh, từ mượn BẮT BUỘC PHIÊN ÂM SANG TIẾNG VIỆT CÓ DẤU:\n"
            "   - Ví dụ: what's up -> 'goắt sắp', hello -> 'hê lô', sale -> 'sêu', live -> 'lai', snack -> 'xì-nách', deal -> 'điu', combo -> 'com-bô'.\n"
            "4. Trả lời nhiệt tình, ngắn gọn dưới 35 từ, tập trung chốt đơn vào giỏ hàng.\n"
            "5. Không dùng markdown, bullet, emoji, hay bất kỳ ký tự đặc biệt nào."
        )
        user_prompt = f"Context: {prod['ctx']}\nCâu hỏi: {question}"
        try:
            try:
                from src import llm_client as _llm
            except Exception:
                try:
                    from . import llm_client as _llm
                except Exception:
                    import llm_client as _llm  # type: ignore
            raw_reply = _llm.chat(system, user_prompt)
            reply = phoneticize_vietnamese(clean_speak_text(raw_reply, max_words=_MAX_WORDS))
            return reply or None
        except Exception:
            price_val = prod.get('price', '')
            if price_val:
                price_display = phoneticize_vietnamese(price_val if ("đ" in price_val or "k" in price_val.lower() or "₫" in price_val) else f"{price_val} đồng")
                price_str = f", giá {price_display}"
            else:
                price_str = ", giá ưu đãi hôm nay"
            return phoneticize_vietnamese(f"Dạ anh/chị ơi, {prod['name']} hiện shop vẫn còn hàng{price_str}, mình chốt đơn giúp shop nhé!")


# Cau hinh runtime (settings.apply() ghi vao day)
_DEFAULT_COOLDOWN: float = 3.0
_DEFAULT_MAX_BATCH: int = 5
_DEFAULT_MAX_WORDS: int = 45
_CONTEXT_DIR: str = "context-data"
_MAX_BATCH: int = _DEFAULT_MAX_BATCH
_MAX_WORDS: int = _DEFAULT_MAX_WORDS

_intent: ChatIntent | None = None
_batcher: GreetingBatcher | None = None


def configure(context_dir=None, cooldown=None, max_batch=None, max_words=None) -> None:
    """Ap cau hinh runtime; tham so None giu gia tri hien tai.

    Ep singleton ve None de lan goi ke tiep rebuild voi tham so moi.
    """
    global _CONTEXT_DIR, _MAX_BATCH, _MAX_WORDS, _intent, _batcher
    if context_dir is not None:
        _CONTEXT_DIR = str(context_dir)
        _intent = None
    if max_batch is not None:
        _MAX_BATCH = max(1, int(max_batch))
    if max_words is not None:
        _MAX_WORDS = max(1, int(max_words))
    _batcher = GreetingBatcher(
        cooldown=_DEFAULT_COOLDOWN if cooldown is None else float(cooldown),
        max_batch=_MAX_BATCH,
    )


def _get_intent() -> ChatIntent:
    global _intent
    if _intent is None:
        _intent = ChatIntent(_CONTEXT_DIR)
    return _intent


def get_batcher() -> GreetingBatcher:
    global _batcher
    if _batcher is None:
        _batcher = GreetingBatcher(cooldown=_DEFAULT_COOLDOWN, max_batch=_MAX_BATCH)
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
        template = random.choice(["Chào", "Xin chào", "Hê-lô", "Goắt-sắp"])
        return {"kind": "greeting", "priority": 3, "speak_text": phoneticize_vietnamese(f"{template} {user}!")}

    if typ in ("chat", "comment", "message"):
        text = str(ev.get("text") or ev.get("message") or ev.get("content") or "").strip()
        ans = _get_intent().answer(text)
        if ans is not None:
            return {"kind": "sales", "priority": 2, "speak_text": ans}
        if user and user not in ("Khách", "bạn mới"):
            if "?" in text or any(w in text.lower() for w in ("không", "sao", "nào", "bao nhiêu", "được không", "gì")):
                speak = f"{user} hỏi: {text}"
            else:
                speak = f"{user} bình luận: {text}"
        else:
            speak = text
        return {"kind": "chat", "priority": 2, "speak_text": phoneticize_vietnamese(speak)}

    if typ == "gift":
        gift = ev.get("gift") or ev.get("gift_name") or "quà"
        count = ev.get("count") or ev.get("quantity") or 1
        raw_text = str(ev.get("text") or ev.get("raw") or ev.get("content") or "").strip()
        if (not user or user in ("Khách", "bạn mới")) and raw_text:
            m = re.search(r"([^\s]+(?:\s+[^\s]+){0,3})\s+(?:đã tặng|gửi tặng|tặng)", raw_text, re.I)
            if m:
                user = m.group(1).strip()
        try:
            count_int = int(count)
        except (ValueError, TypeError):
            count_int = 1
        gift_str = f"{count_int} {gift}" if count_int > 1 else str(gift)
        return {"kind": "gift", "priority": 1, "speak_text": phoneticize_vietnamese(f"Cảm ơn {user} đã tặng {gift_str}!")}

    if typ == "order":
        product = ev.get("product") or ev.get("product_name") or ev.get("item")
        raw_text = str(ev.get("text") or ev.get("raw") or ev.get("content") or "").strip()
        if (not user or user in ("Khách", "bạn mới")) and raw_text:
            m = re.search(
                r"(?:khách hàng|người mua)?\s*([^\s]+(?:\s+[^\s]+){0,3})\s+(?:đã chốt đơn|đã đặt hàng|đã mua|chốt đơn)",
                raw_text,
                re.I,
            )
            if m:
                user = m.group(1).strip()
            rest = re.sub(r"^.*?(?:đã chốt đơn|đã đặt hàng|đã mua|chốt đơn)\s*", "", raw_text, flags=re.I).strip()
            if rest and not product:
                product = rest
        if product:
            return {"kind": "order", "priority": 1, "speak_text": phoneticize_vietnamese(f"Cảm ơn {user} đã chốt đơn {product}!")}
        return {"kind": "order", "priority": 1, "speak_text": phoneticize_vietnamese(f"Cảm ơn {user} đã chốt đơn!")}
    return {"kind": typ or "unknown", "priority": 3, "speak_text": phoneticize_vietnamese(str(ev.get("text") or ""))}
