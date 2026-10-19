"""Phân tích event live -> kind/priority/speak_text."""
from __future__ import annotations

import os
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

# LLM doi khi tra kem "meta" cua chinh no (Tier:/Skills:/Rationale:/Action:) —
# doc len live la loi, phai loc bo.
_META_MARKERS = ("skills:", "rationale:", "pre-flight", "plugins/mcp")
_META_ACTION_RE = re.compile(r"action:\s*[A-Za-z/_\-]+(?![A-Za-z/_\-])\s*", re.IGNORECASE)


def strip_agent_meta(text: str) -> str:
    """Bo phan 'meta' do agent/LLM tu in ra (Pre-flight ... Action: Direct) truoc cau thoai."""
    if not text:
        return ""
    low = text.lower()
    if any(m in low for m in _META_MARKERS) or "action:" in low:
        m = _META_ACTION_RE.search(text)
        if m:
            return text[m.end():].lstrip(" .,;:-–—").strip()
    return text

# Tu khoa CTA (call-to-action) de giu lai khi phai cat bot cau dai.
_CTA_WORDS = ("giỏ hàng", "gio hang", "chốt đơn", "chot don", "bấm", "bam", "đặt hàng", "dat hang")


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
    body = strip_agent_meta(body)
    if not body:
        return ""
    words = body.split(" ")
    if len(words) > max_words:
        head = words[:max_words]
        # Neu bi cat mat CTA, giu lai DUNG cau chot don (ngan nhat co CTA) o cuoi.
        tail = " ".join(words[max_words:]).strip()
        cta = ""
        for s in re.split(r"(?<=[.!?])\s+", tail):
            s = s.strip()
            if s and any(w in s.lower() for w in _CTA_WORDS) and len(s.split()) <= 25:
                cta = s
        if not cta:
            # Tail khong co dau cau tach ro: cat tu tu khoa CTA dau tien, toi da 25 tu.
            low_tail = tail.lower()
            pos = min((low_tail.find(w) for w in _CTA_WORDS if w in low_tail), default=-1)
            if pos >= 0:
                cta = " ".join(tail[pos:].split()[:25]).rstrip(",;:. ") + "."
        cut = " ".join(head).rstrip(",;:. ")
        body = f"{cut}. {cta}".strip() if cta else cut + "."
        body = re.sub(r"\.{2,}", ".", body)
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
    # "shop"/"sop" phải đọc thành "sóp" (prompt đã yêu cầu, nhưng LLM hay trả về "shop")
    (re.compile(r"\b(shops|shop|sop|sóp)\b", re.I), "sóp"),
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

    def __init__(self, context_dir: str | Path = "context-data", live_dir: str | Path | None = None):
        p = Path(context_dir)
        if not p.is_absolute():
            try:
                import settings
                p = settings.resolve_path(p)
            except Exception:
                p = _project_root() / p
        self.context_dir = p
        
        self.live_dir = None
        l_dir = live_dir or os.getenv("CONTEXT_LIVE_DIR", "context-live")
        if l_dir:
            lp = Path(l_dir)
            if not lp.is_absolute():
                try:
                    import settings
                    lp = settings.resolve_path(lp)
                except Exception:
                    lp = _project_root() / lp
            self.live_dir = lp

        self.products: list[dict] = []
        self._load()
    def _load(self) -> None:
        self.products.clear()
        dirs_to_scan = [self.context_dir]
        if self.live_dir and self.live_dir.is_dir() and self.live_dir != self.context_dir:
            dirs_to_scan.append(self.live_dir)

        for target_dir in dirs_to_scan:
            if not target_dir.is_dir():
                continue
            for md in sorted(target_dir.glob("*.md")):
                if md.name.lower() in ("readme.md", "_index.md"):
                    continue
                try:
                    text = md.read_text(encoding="utf-8")
                except Exception:
                    continue
                name = ""
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("# "):
                        name = line[2:].strip()
                        m_clean = re.match(r"^sản phẩm\s*#?\d+\s*:\s*(.*)$", name, re.I)
                        if m_clean:
                            name = m_clean.group(1).strip()
                        break
                    if line.startswith("#"):
                        name = line.lstrip("#").strip()
                        m_clean = re.match(r"^sản phẩm\s*#?\d+\s*:\s*(.*)$", name, re.I)
                        if m_clean:
                            name = m_clean.group(1).strip()
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
                    m_price = re.match(
                        r"^-?\s*giá\s*(?:khuyến mại(?:\s*thực tế(?:\s*trên live)?)?|ưu đãi|niêm yết(?:\s*giỏ hàng)?)?\s*:\s*(.+)$",
                        line,
                        flags=re.I,
                    )
                    if m_price:
                        price = m_price.group(1).strip()
                        break
                # Trích xuất số thứ tự giỏ hàng (index) nếu có
                p_idx = None
                idx_match = (
                    re.search(r"(?:thứ tự\s*(?:trong giỏ hàng(?:\s*live)?|trên live)?:\s*(?:số\s*)?|#|sp-)(\d+)", text, re.I)
                    or re.search(r"sp-(\d+)", md.stem)
                )
                if idx_match:
                    try:
                        p_idx = int(idx_match.group(1))
                    except Exception:
                        p_idx = None

                # Tách mô tả / đánh giá / id / link từ file context để gửi kèm cho LLM
                description, reviews, pid, url = self._split_context_sections(text)

                self.products.append({
                    "name": name,
                    "keywords": keywords,
                    "bigrams": bigrams,
                    "price": price,
                    "index": p_idx,
                    "ctx": text,
                    "description": description,
                    "reviews": reviews,
                    "id": pid,
                    "url": url,
                    "file": md.name,
                    "live": bool(self.live_dir and target_dir == self.live_dir),
                })

    @staticmethod
    def _split_context_sections(text: str) -> tuple[str, list[str], str, str]:
        """Tách file context sản phẩm thành (mô tả, danh sách đánh giá, id, link)."""
        description_lines: list[str] = []
        reviews: list[str] = []
        pid = ""
        url = ""
        section = ""
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            low = line.lower()
            if line.startswith("#"):
                heading = low.lstrip("#").strip()
                if "mô tả" in heading or "mo ta" in heading:
                    section = "desc"
                elif "đánh giá" in heading or "danh gia" in heading or "bình luận" in heading:
                    section = "review"
                else:
                    section = "other"
                continue
            if low.startswith("- mã sản phẩm") or low.startswith("- ma san pham"):
                pid = line.split(":", 1)[1].strip() if ":" in line else ""
                if "không xác định" in pid.lower() or "khong xac dinh" in pid.lower():
                    pid = ""
                continue
            if low.startswith("- link sản phẩm") or low.startswith("- link san pham"):
                url = line.split(":", 1)[1].strip() if ":" in line else ""
                continue
            if section == "desc" and line:
                description_lines.append(line)
            elif section == "review" and line:
                m = re.match(r"^\d+[.)]\s*(.+)$", line)
                reviews.append(m.group(1).strip() if m else line)
        description = "\n".join(description_lines).strip()
        if description.startswith("(Chưa lấy được") or description.startswith("(Chua lay duoc"):
            description = ""
        reviews = [r for r in reviews if r and not r.startswith("(Sản phẩm chưa có")]
        return description, reviews, pid, url

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

            # Khớp theo số thứ tự giỏ hàng nếu câu hỏi nhắc đến mã/số (vd: "mã 1", "áo số 2", "sp 3")
            idx_q = re.search(r"(?:m[aã]|s[oố]|sản phẩm|san pham|sp|item)\s*#?(\d+)", tl)
            if idx_q and prod.get("index") is not None:
                if int(idx_q.group(1)) == prod["index"]:
                    score += 250

            if p_name_lower in tl:
                score += 150
            matched_bigrams = prod.get("bigrams", set()).intersection(q_bigrams)
            score += len(matched_bigrams) * 40
            matched_kws = prod.get("keywords", set()).intersection(q_tokens)
            score += len(matched_kws) * 10

            # San pham doc tu context-live (gio hang hien tai) thang khi hoa diem
            if score > best_score or (
                score == best_score
                and score > 0
                and prod.get("live")
                and not (best_prod or {}).get("live")
            ):
                best_score = score
                best_prod = prod

        return best_prod if best_score >= 20 else None
    def answer(self, question: str) -> str | None:
        prod = self.match(question)
        if prod is None:
            return None
        system = get_prompt("system_sales")
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
            # Prompt yêu cầu only-JSON -> đọc speak_text từ JSON trước khi chuẩn hoá
            try:
                import intent_router as _ir
                speak = _ir.parse_speak_reply(raw_reply, fallback_kind="sales").get("speak_text") or ""
            except Exception:
                speak = str(raw_reply or "")
            speak = strip_agent_meta(speak)
            reply = phoneticize_vietnamese(clean_speak_text(speak, max_words=_MAX_WORDS))
            if reply:
                return reply
            # LLM trả rỗng / JSON không có speak_text -> rơi xuống câu trả lời dựng sẵn
            raise ValueError("LLM trả về nội dung rỗng")
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
_PROMPTS_DIR: str = "prompts"
_CONTEXT_DIR: str = "context-data"
_CONTEXT_LIVE_DIR: str = "context-live"
_MAX_BATCH: int = _DEFAULT_MAX_BATCH
_MAX_WORDS: int = int(os.getenv("SALES_MAX_WORDS", "75"))


def get_prompt(name: str, prompts_dir: str | Path | None = None) -> str:
    """Đọc file prompt markdown từ prompts_dir theo tên. Fallback về prompt mặc định nếu thiếu."""
    p_dir = Path(prompts_dir or _PROMPTS_DIR)
    try:
        import settings
        resolved = settings.resolve_path(p_dir)
    except Exception:
        resolved = _project_root() / p_dir

    target_file = resolved / f"{name}.md"
    if target_file.is_file():
        try:
            content = target_file.read_text(encoding="utf-8").strip()
            if content:
                return content
        except Exception:
            pass

    # Fallback built-in prompts
    if name == "system_greeting":
        return (
            "Bạn là streamer bán hàng livestream TikTok Shop, thân thiện và năng động.\n"
            "Khách vừa vào phòng hoặc vừa chào shop. Hãy sinh MỘT câu chào lại thật tự nhiên.\n"
            "Quy tắc:\n"
            "1. Toàn bộ là tiếng Việt có dấu đầy đủ, dài 15-30 từ.\n"
            "2. LUÔN tự xưng là 'sóp' (bắt buộc có chữ 'sóp'). KHÔNG tự gọi mình là 'trợ lý' hay 'AI'.\n"
            "3. Gọi đúng tên khách, mời khách ở lại xem live và bấm giỏ hàng.\n"
            "4. PHIÊN ÂM 100% chữ số thành chữ; phiên âm từ mượn (shop -> sóp, live -> lai, deal -> điu).\n"
            "5. Không markdown, không bullet, không emoji.\n"
            "CHỈ trả về DUY NHẤT một object JSON hợp lệ, không thêm lời dẫn, không ```json.\n"
            'JSON mẫu: {"speak_text": "Xin chào Minh Tuấn đã ghé thăm gian hàng, sóp vui lắm, bạn ở lại xem lai nhé!", "kind": "greeting", "priority": 3}'
        )
    if name == "system_order":
        return (
            "Bạn là streamer bán hàng livestream TikTok Shop. Khách vừa chốt đơn thành công.\n"
            "Quy tắc:\n"
            "1. Toàn bộ là tiếng Việt có dấu đầy đủ, dài 20-45 từ, giọng phấn khích, biết ơn.\n"
            "2. LUÔN tự xưng là 'sóp' (bắt buộc có chữ 'sóp'). KHÔNG tự gọi mình là 'trợ lý' hay 'AI'.\n"
            "3. Chúc mừng đúng tên khách, xác nhận đúng tên sản phẩm và giá ưu đãi trong dữ liệu được cấp.\n"
            "4. PHIÊN ÂM 100% chữ số và tiền tệ thành chữ (150000 -> 'một trăm năm mươi nghìn đồng').\n"
            "CHỈ trả về DUY NHẤT một object JSON hợp lệ, không thêm lời dẫn, không ```json.\n"
            'JSON mẫu: {"speak_text": "Chúc mừng chị Lan Anh đã chốt đơn, sóp cảm ơn chị nhiều lắm!", "kind": "order", "priority": 1}'
        )
    if name == "system_gift":
        return (
            "Bạn là streamer bán hàng livestream TikTok Shop. Khách vừa tặng quà cho phiên live.\n"
            "Quy tắc:\n"
            "1. Toàn bộ là tiếng Việt có dấu đầy đủ, dài 20-40 từ, giọng vui vẻ, biết ơn.\n"
            "2. LUÔN tự xưng là 'sóp' (bắt buộc có chữ 'sóp'). KHÔNG tự gọi mình là 'trợ lý' hay 'AI'.\n"
            "3. Cảm ơn đúng tên khách và đúng tên quà trong dữ liệu được cấp, không bịa.\n"
            "4. PHIÊN ÂM 100% chữ số thành chữ (10 -> 'mười').\n"
            "CHỈ trả về DUY NHẤT một object JSON hợp lệ, không thêm lời dẫn, không ```json.\n"
            'JSON mẫu: {"speak_text": "Sóp cảm ơn bạn Minh Tuấn đã tặng quà, thương bạn nhiều lắm!", "kind": "gift", "priority": 1}'
        )
    if name == "system_analyzer":
        return (
            "Bạn là bộ phân loại ý định bình luận livestream bán hàng TikTok Shop.\n"
            "Nhãn hợp lệ: greeting, product_question, order, gift, chat, other.\n"
            "CHỈ trả về DUY NHẤT một object JSON hợp lệ, không thêm lời dẫn, không ```json.\n"
            'JSON mẫu: {"intent": "product_question", "product_hint": "áo thun nam", "confidence": 0.92}'
        )
    if name == "system_sales":
        return (
            "Bạn là trợ lý bán hàng livestream TikTok Shop, chuyên sinh câu trả lời tư vấn sản phẩm để tạo giọng đọc Text-To-Speech (TTS).\n"
            "Quy tắc bắt buộc:\n"
            "1. TOÀN BỘ câu trả lời PHẢI là tiếng Việt có dấu đầy đủ.\n"
            "2. TUYỆT ĐỐI KHÔNG viết số dạng chữ số hay ký hiệu tiền tệ. BẮT BUỘC PHIÊN ÂM TOÀN BỘ THÀNH CHỮ TIẾNG VIỆT (ví dụ: 1₫ -> 'một đồng', 28.900₫ -> 'hai mươi tám nghìn chín trăm đồng', 1kg -> 'một cân').\n"
            "3. TẤT CẢ từ tiếng Anh, từ mượn BẮT BUỘC PHIÊN ÂM (live -> lai, shop -> sóp, deal -> điu, snack -> xì-nách).\n"
            "4. LUÔN tự xưng là 'sóp' (bắt buộc có chữ 'sóp'). KHÔNG tự gọi mình là 'trợ lý' hay 'AI'.\n"
            "5. Trả lời nhiệt tình, dài 50-80 từ, tập trung chốt đơn vào giỏ hàng.\n"
            "6. Không dùng markdown, bullet, emoji.\n"
            "CHỈ trả về DUY NHẤT một object JSON hợp lệ, không thêm lời dẫn, không ```json.\n"
            'JSON mẫu: {"speak_text": "Chị Lan Anh ơi, sóp xác nhận đúng mẫu áo thun nam Cốt-tần Com-pắc, giá ưu đãi một trăm năm mươi nghìn đồng, chị bấm giỏ hàng chốt đơn nhé!", "kind": "sales", "priority": 2}'
        )
    elif name == "system_chat":
        return (
            "Bạn là streamer bán hàng livestream TikTok Shop thân thiện, năng động, dễ thương.\n"
            "Khách xem live vừa bình luận trong khung chat. Hãy đáp lại khách thật tự nhiên như đang nói trực tiếp trên livestream.\n"
            "Quy tắc:\n"
            "1. Luôn xưng hô tên khách một cách thân thiết (ví dụ: 'Chào {user}', 'Dạ {user} ơi').\n"
            "2. Trả lời tự nhiên, dài 15-40 từ, hướng khách xem giỏ hàng hoặc tương tác.\n"
            "3. LUÔN tự xưng là 'sóp' (bắt buộc có chữ 'sóp'). KHÔNG tự gọi mình là 'trợ lý' hay 'AI'.\n"
            "4. Toàn bộ là tiếng Việt có dấu, không emoji, không viết số, phiên âm từ tiếng Anh sang tiếng Việt (shop -> sóp, live -> lai).\n"
            "CHỈ trả về DUY NHẤT một object JSON hợp lệ, không thêm lời dẫn, không ```json.\n"
            'JSON mẫu: {"speak_text": "Dạ sóp chào bạn, sóp đang lai món ăn vặt cực ngon, bạn ở lại xem thử nhé!", "kind": "chat", "priority": 2}'
        )
    elif name == "system_batch":
        return (
            "Bạn là hệ thống AI điều khiển giọng đọc livestream TikTok Shop tự động.\n"
            "Dưới đây là danh sách các sự kiện diễn ra trong 5 giây vừa qua kèm thông tin sản phẩm.\n"
            "Nhiệm vụ: Phân tích và sinh ra danh sách câu nói ngắn gọn để tạo giọng đọc.\n"
            "BẮT BUỘC CHỈ TRẢ VỀ DUY NHẤT 1 MẢNG JSON HỢP LỆ:\n"
            "[\n"
            "  {\"type\": \"order|sales|chat|greeting\", \"user\": \"Tên\", \"text\": \"Câu thoại tiếng Việt có dấu, phiên âm 100% số và tiếng Anh\", \"priority\": 1|2|3}\n"
            "]\n"
            "Tuyệt đối không thêm bất kỳ văn bản nào ngoài JSON!"
        )
    return ""


def configure(prompts_dir=None, context_dir=None, cooldown=None, max_batch=None, max_words=None) -> None:
    """Ap cau hinh runtime; tham so None giu gia tri hien tai."""
    global _PROMPTS_DIR, _CONTEXT_DIR, _MAX_BATCH, _MAX_WORDS, _intent, _batcher
    if prompts_dir is not None:
        _PROMPTS_DIR = str(prompts_dir)
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
_intent: ChatIntent | None = None
_batcher: GreetingBatcher | None = None


def configure(
    prompts_dir=None,
    context_dir=None,
    context_live_dir=None,
    cooldown=None,
    max_batch=None,
    max_words=None,
) -> None:
    """Ap cau hinh runtime; tham so None giu gia tri hien tai."""
    global _PROMPTS_DIR, _CONTEXT_DIR, _CONTEXT_LIVE_DIR, _MAX_BATCH, _MAX_WORDS, _intent, _batcher
    if prompts_dir is not None:
        _PROMPTS_DIR = str(prompts_dir)
    if context_dir is not None:
        _CONTEXT_DIR = str(context_dir)
        _intent = None
    if context_live_dir is not None:
        _CONTEXT_LIVE_DIR = str(context_live_dir)
        _intent = None
    if max_batch is not None:
        _MAX_BATCH = max(1, int(max_batch))
    if max_words is not None:
        _MAX_WORDS = max(1, int(max_words))
    _batcher = GreetingBatcher(
        cooldown=_DEFAULT_COOLDOWN if cooldown is None else float(cooldown),
        max_batch=_MAX_BATCH,
    )


def reload_intent() -> None:
    """Làm mới bộ nhớ đệm ChatIntent để đọc lại các file context mới nhất."""
    global _intent
    _intent = None


def _get_intent() -> ChatIntent:
    global _intent
    if _intent is None:
        _intent = ChatIntent(_CONTEXT_DIR, live_dir=_CONTEXT_LIVE_DIR)
    return _intent


def get_batcher() -> GreetingBatcher:
    global _batcher
    if _batcher is None:
        _batcher = GreetingBatcher(cooldown=_DEFAULT_COOLDOWN, max_batch=_MAX_BATCH)
    return _batcher


def generate_by_intent(
    user: str,
    text: str,
    intent: str,
    product: dict | None = None,
    context_note: str = "",
) -> str:
    """Gọi LLM sinh câu thoại theo ĐÚNG loại prompt ứng với ý định.

    Luồng: phân loại ý định (intent_router, dùng model AI cấu hình `analyst_llm_model`)
    -> chọn prompt tương ứng trong prompts/*.md -> ép LLM trả ONLY JSON
    -> đọc JSON bằng json_utils (chịu được JSON lỗi) -> chuẩn hoá câu thoại.

    Luôn trả về câu thoại tiếng Việt (dự phòng bằng luật khi LLM lỗi).
    """
    try:
        import intent_router
    except ImportError:
        intent_router = None  # type: ignore[assignment]

    u = user if user and user not in ("Khách", "bạn mới") else "bạn"
    intent = (intent or "chat").strip().lower()

    # Câu chào hỏi rất ngắn vẫn gọi LLM với system_greeting.md; các mẫu cứng chỉ dùng
    # làm dự phòng khi LLM lỗi (xem _greeting_fallback bên dưới).

    # 1. Chọn prompt theo đúng loại ý định
    prompt_name = intent_router.prompt_for_intent(intent) if intent_router else "system_chat"
    priority = {"order": 1, "gift": 1, "product_question": 2, "chat": 2}.get(intent, 3)
    base_prompt = get_prompt(prompt_name)
    system = (
        intent_router.build_speak_prompt(base_prompt, intent, priority)
        if intent_router
        else base_prompt
    )
    if "{user}" in system or "{u}" in system:
        system = system.replace("{user}", u).replace("{u}", u)

    # 3. Dựng ngữ cảnh gửi kèm (sản phẩm khách đang hỏi + ghi chú)
    ctx_parts = []
    if product:
        ctx_parts.append("NGỮ CẢNH SẢN PHẨM KHÁCH ĐANG HỎI:")
        ctx_parts.append(f"- Tên: {product.get('name', '')}")
        if product.get("price"):
            ctx_parts.append(f"- Giá ưu đãi: {product.get('price')}")
        if product.get("index") is not None:
            ctx_parts.append(f"- Thứ tự trong giỏ hàng: số {product.get('index')}")
        if product.get("url"):
            ctx_parts.append(f"- Link: {product.get('url')}")
        desc = (product.get("description") or "").strip()
        if not desc:
            # File context-data cũ không có section mô tả -> dùng toàn bộ nội dung file
            desc = (product.get("ctx") or "").strip()
        if desc:
            ctx_parts.append(f"- Mô tả: {desc[:1500]}")
        revs = product.get("reviews") or []
        if not revs and not product.get("description"):
            # Suy ra đánh giá từ phần cuối nội dung thô nếu có
            revs = []
        if isinstance(revs, list) and revs:
            ctx_parts.append("- Đánh giá của khách trước đó: " + " | ".join(str(r) for r in revs[:5]))
        ctx_parts.append(f"- Nguồn dữ liệu: {'context-live' if product.get('live') else 'context-data'}")
    if context_note:
        ctx_parts.append(context_note)
    ctx_parts.append(f'Khách "{u}" vừa bình luận: "{text}"')

    user_prompt = "\n".join(ctx_parts)

    # 4. Gọi LLM, đọc JSON chịu lỗi
    try:
        import llm_client

        reply = llm_client.chat(system, user_prompt)
        if intent_router:
            data = intent_router.parse_speak_reply(reply, fallback_kind=intent)
            speak = data.get("speak_text") or ""
        else:
            speak = str(reply or "")
    except Exception:
        speak = ""

    speak = strip_agent_meta(speak)
    if not speak:
        if intent == "greeting":
            return _greeting_fallback(u)
        return answer_general_chat(user, text)
    return phoneticize_vietnamese(clean_speak_text(speak, max_words=_MAX_WORDS))


def _greeting_fallback(user: str) -> str:
    """Câu chào dự phòng khi LLM lỗi/không trả về nội dung."""
    templates = [
        f"Chào {user}, sóp đây! Bạn đang ngắm món ăn vặt nào thế nè?",
        f"Dạ sóp chào {user}, sóp nghe đây ạ! Bạn bấm giỏ hàng góc trái xem món ngon nhé!",
        f"Chào {user}, sóp đây ạ! Bạn cần sóp tư vấn món gì cứ nhắn lên đây nha!",
        f"Chào {user}, sóp đây! Vào xem lai nhớ thả tim và bấm giỏ hàng ủng hộ sóp nha!",
    ]
    return phoneticize_vietnamese(random.choice(templates))


def answer_by_intent(user: str, text: str, products: list[dict] | None = None) -> dict:
    """Phân loại ý định rồi sinh câu thoại phù hợp.

    Trả về {"intent", "source", "prompt", "speak_text", "product"}.
    Sản phẩm tra trong context-live trước, fallback context-data (ChatIntent đã gộp cả hai).
    """
    try:
        import intent_router
    except ImportError:
        intent_router = None  # type: ignore[assignment]

    if intent_router is None:
        return {
            "intent": "chat", "source": "rule", "prompt": "system_chat",
            "speak_text": answer_general_chat(user, text), "product": None,
        }

    prods = products if products is not None else _get_intent().products
    cls = intent_router.classify_intent(text, products=prods)
    intent = cls.get("intent") or "chat"

    product = None
    if intent == "product_question":
        hint = (cls.get("product_hint") or "").strip() or text
        product = _get_intent().match(hint)
        if product is None:
            product = _get_intent().match(text)

    speak = generate_by_intent(user, text, intent, product=product)
    return {
        "intent": intent,
        "source": cls.get("source", "rule"),
        "prompt": intent_router.prompt_for_intent(intent),
        "speak_text": speak,
        "product": product,
    }


def answer_general_chat(user: str, text: str) -> str:
    """Tự động đáp lại các câu chào hỏi, gọi shop hoặc giao tiếp ngoài lề của người xem live."""
    s = (text or "").lower().strip()
    u = user if user and user not in ("Khách", "bạn mới") else "bạn"

    # 1. Các câu chào hỏi / gọi shop phổ biến (alo, shop ơi, chào shop, hello shop...) -> đáp ngay lập tức
    if (
        re.search(
            r"^(alo|a lô|a lo|hê lô|helo|hello|hi|chào|chao)?\s*(shop|sóp|sop|shop ơi|sóp ơi|ơi|oi)?\s*(\?|\!|\.)*$",
            s,
        )
        or s in ("alo", "alo shop", "shop ơi", "sóp ơi", "chào shop", "hello shop", "hi shop", "có ai không")
    ):
        fast_replies = [
            f"Chào {u}, sóp đây! Bạn đang ngắm món ăn vặt nào thế nè?",
            f"Dạ sóp chào {u}, sóp nghe đây ạ! Bạn bấm giỏ hàng góc trái xem món ngon nhé!",
            f"Chào {u}, sóp đây ạ! Bạn cần sóp tư vấn món gì cứ nhắn lên đây nha!",
            f"Chào {u}, sóp đây! Vào xem lai nhớ thả tim và bấm giỏ hàng ủng hộ sóp nha!",
        ]
        return phoneticize_vietnamese(random.choice(fast_replies))

    # 2. Các bình luận giao tiếp khác -> gọi LLM đóng vai streamer đáp lại tự nhiên
    system = get_prompt("system_chat")
    if "{user}" in system or "{u}" in system:
        system = system.replace("{user}", u).replace("{u}", u)
    user_prompt = f"Khách tên: {u}\nBình luận: {text}"
    try:
        try:
            from src import llm_client as _llm
        except Exception:
            try:
                from . import llm_client as _llm
            except Exception:
                import llm_client as _llm  # type: ignore
        raw = _llm.chat(system, user_prompt)
        # Prompt yêu cầu only-JSON -> đọc speak_text trong JSON
        try:
            import intent_router as _ir
            speak = _ir.parse_speak_reply(raw, fallback_kind="chat").get("speak_text") or ""
        except Exception:
            speak = str(raw or "")
        speak = strip_agent_meta(speak)
        reply = clean_speak_text(speak, max_words=_MAX_WORDS)
        if reply:
            return phoneticize_vietnamese(reply)
    except Exception:
        pass

    return phoneticize_vietnamese(f"Chào {u}, sóp nghe đây ạ! Bạn bấm vào giỏ hàng góc trái xem các món ăn vặt ngon nhé!")

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
        res = answer_by_intent(user, text)
        intent = res["intent"]
        kind = "sales" if intent == "product_question" else ("greeting" if intent == "greeting" else "chat")
        # Bình luận của khách luôn là ưu tiên vừa (2); riêng chốt đơn/quà tặng lên 1.
        # (Chào hỏi hạ xuống 3 chỉ áp dụng cho sự kiện join, không phải bình luận.)
        priority = 1 if intent in ("order", "gift") else 2
        return {
            "kind": kind,
            "priority": priority,
            "speak_text": res["speak_text"],
            "intent": intent,
            "intent_source": res["source"],
            "prompt": res["prompt"],
            "product": (res["product"] or {}).get("name"),
        }

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


    if typ in ("viewing_product", "viewing", "view_product", "xem_san_pham"):
        product = ev.get("product") or ev.get("product_name") or ""
        raw_text = str(ev.get("text") or ev.get("raw") or "").strip()
        if not product and raw_text:
            m_v = re.search(r"(?:đang xem|xem sản phẩm|viewing)\s*(.*)", raw_text, re.I)
            if m_v:
                product = m_v.group(1).strip()
        
        # Đối chiếu context-live trước, fallback context-data (ChatIntent gộp cả hai)
        matched = _get_intent().match(product) if product else None
        p_display = matched["name"] if matched else (product or "sản phẩm trên live")

        # Sinh câu thoại bằng LLM với đúng prompt tư vấn sản phẩm
        reply = generate_by_intent(
            user,
            f"Khách đang xem sản phẩm: {p_display}"
            + (f' (khách viết: "{raw_text}")' if raw_text else ""),
            "product_question",
            product=matched,
        )
        if not reply:
            price_str = (
                f", giá ưu đãi chỉ {phoneticize_vietnamese(matched['price'])}"
                if matched and matched.get("price") else ""
            )
            reply = phoneticize_vietnamese(
                f"Dạ sóp chào {user}, mình đang xem {p_display}{price_str} đúng không ạ? "
                f"Sản phẩm này đang bán rất chạy, bạn bấm vào giỏ hàng chốt đơn kẻo hết nhé!"
            )
        return {
            "kind": "viewing_product",
            "priority": 1,
            "speak_text": reply,
            "product": p_display,
        }
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
