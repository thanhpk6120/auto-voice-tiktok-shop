"""Quản lý bộ đệm 10 voice tự động giới thiệu sản phẩm khi Live rảnh (Idle Auto-Pitch).

Đặc điểm chính:
1. Duy trì bộ đệm đúng 10 voice ngẫu nhiên các sản phẩm trong cache (local_cache/auto_pitch/).
2. Không sinh sẵn nhiều câu trên mỗi sản phẩm; xoay tua ngẫu nhiên không lặp lại sản phẩm vừa nói.
3. Khi phát xong 1 voice: xoá file wav đó ngay và tự động tạo bù 1 voice cho sản phẩm khác để luôn đủ 10 voice.
4. Khoảng cách thời gian cho phép cấu hình (mặc định 10 - 30 giây).
5. Ứng dụng các công thức chốt sale livestream thực chiến (Scarcity, Freeship, CTA giỏ hàng, Social Proof, Engagement)
   giúp hỗ trợ ra đơn thật hiệu quả.
"""
from __future__ import annotations

import collections
import os
import random
import re
import sys
import threading
import time
from pathlib import Path

# Thêm đường dẫn src nếu cần
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

try:
    from event_analyzer import northernize_vietnamese, phoneticize_vietnamese
except Exception:
    def phoneticize_vietnamese(t: str) -> str:
        return t
    def northernize_vietnamese(t: str) -> str:
        return t


# Các mẫu câu chốt sale thực chiến theo 5 công thức livestream
_PITCH_FORMULAS = {
    # 1. Khan hiếm & Trợ giá chớp nhoáng (Scarcity & Urgency)
    "scarcity": [
        "Cả nhà ơi, mã {name} trên live hôm nay đang có giá ưu đãi chỉ {price}, shop chỉ trợ giá đúng 5 suất thôi ạ. Ai chưa kịp chốt thì bấm ngay giỏ hàng góc trái màn hình kẻo hết nhé!",
        "Duy nhất trong phiên live này, {name} được giảm giá còn {price}. Số lượng giá sale có hạn thôi cả nhà ơi, ai ưng ý thì bấm góc trái chốt ngay kẻo lỡ nhé!",
        "Mã {name} giá gốc cao hơn nhiều, hôm nay trợ giá đặc biệt chỉ còn {price}. Cả nhà nhanh tay bấm giỏ hàng kẻo hết quà tặng và mã giảm giá nhé!",
    ],
    # 2. Kêu gọi hành động trực tiếp vào giỏ hàng (Direct CTA)
    "cta_cart": [
        "Cả nhà mình ai đang xem live bấm vào giỏ hàng góc trái xem mã {name} đang có giá cực hời {price} nhé. Hàng chuẩn ngon, date mới tinh, bấm mua ngay nhé!",
        "Mã {name} đang có sẵn ở góc trái màn hình với giá chỉ {price}. Cả nhà ghé xem ưng món nào thì bấm chốt liền tay để bên em đóng gói gửi sớm nhé!",
        "Anh chị em đang theo dõi live nhớ ghé qua giỏ hàng góc trái, mã {name} giá chỉ {price} đang được rất nhiều khách lựa chọn trong hôm nay đó ạ!",
    ],
    # 3. Kích thích Freeship & Gom đơn (Freeship & Bundle Incentive)
    "freeship": [
        "Món {name} hôm nay được áp mã freeship extra và voucher sốc đó cả nhà. Giá chỉ có {price}, cả nhà gom thêm cho đủ đơn rồi bấm giỏ hàng góc trái để được miễn phí vận chuyển nhé!",
        "Đặt {name} hôm nay có trợ giá {price} lại được thêm mã giảm phí ship, cả nhà bấm góc trái đặt luôn kẻo hết mã vận chuyển nhé!",
    ],
    # 4. Đánh giá tốt & Uy tín chất lượng (Social Proof & Trust)
    "social_proof": [
        "Khách nhà em nhận mã {name} ai cũng khen nức nở luôn cả nhà ơi. Giá hôm nay chỉ {price}, hàng bao chuẩn bao ngon, cả nhà yên tâm bấm giỏ hàng đặt nhé!",
        "Món {name} này là best seller của shop em đó ạ, khách ăn quen quay lại mua liên tục. Hôm nay ưu đãi trợ giá chỉ còn {price}, cả nhà tranh thủ bấm giỏ hàng đặt sớm nhé!",
    ],
    # 5. Kêu gọi tương tác thuật toán đẩy deal (Engagement Hook)
    "engagement": [
        "Cả nhà mình đang xem live cho shop xin vài cái thả tim và follow nha! Đẩy tim lên mốc là shop tung deal {name} giá siêu ưu đãi {price} cho cả nhà săn liền tay nhé!",
        "Mọi người cùng bấm tim màn hình ủng hộ shop nhé! Tiện tay bấm luôn giỏ hàng góc trái xem {name} giá chỉ {price} cực ngon hôm nay ạ!",
    ],
}

# Các câu thoại tương tác khi chưa có sản phẩm trong context-live
_GENERIC_ENGAGEMENT_PITCHES = [
    "Cả nhà đang xem live bấm thả tim màn hình và nhấn theo dõi shop để không bỏ lỡ các deal hot hôm nay nhé, sốp cảm ơn cả nhà rất nhiều!",
    "Ai đang tìm đồ ăn vặt hay cần tư vấn món gì cứ thoải mái bình luận dưới live nhé, shop sẽ tư vấn nhiệt tình cho từng bạn ngay ạ!",
    "Các mã giảm giá freeship và voucher hôm nay đang có sẵn trong giỏ hàng góc trái màn hình, cả nhà bấm vào săn ngay kẻo hết nhé!",
    "Cả nhà xem live nhớ nhấn theo dõi kênh và cho shop xin một tim nhé, lát nữa shop sẽ tung thêm deal cực sốc trợ giá cho cả nhà luôn ạ!",
]


class AutoPitchManager:
    """Quản lý bộ đệm 10 voice tự động giới thiệu sản phẩm ngẫu nhiên khi live rảnh."""

    def __init__(
        self,
        context_live_dir: str | Path = "context-live",
        context_dir: str | Path = "context-data",
        cache_dir: str | Path = "local_cache/auto_pitch",
        buffer_size: int = 10,
        min_s: float = 10.0,
        max_s: float = 30.0,
        enabled: bool = True,
    ) -> None:
        self.context_live_dir = Path(context_live_dir)
        self.context_dir = Path(context_dir)
        self.cache_dir = Path(cache_dir)
        self.buffer_size = max(2, int(buffer_size))
        self.min_s = max(3.0, float(min_s))
        self.max_s = max(self.min_s + 1.0, float(max_s))
        self.enabled = bool(enabled)

        self._buffer: list[dict] = []
        self._recent_products: collections.deque[str] = collections.deque(maxlen=15)
        self._lock = threading.Lock()
        self._refill_thread: threading.Thread | None = None
        self._refill_active = False

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def update_config(self, cfg: dict) -> None:
        """Cập nhật cấu hình động từ settings."""
        with self._lock:
            if "idle_pitch_enabled" in cfg:
                self.enabled = bool(cfg["idle_pitch_enabled"])
            if "idle_pitch_buffer_size" in cfg:
                self.buffer_size = max(2, int(cfg["idle_pitch_buffer_size"]))
            if "idle_pitch_min_s" in cfg:
                self.min_s = max(3.0, float(cfg["idle_pitch_min_s"]))
            if "idle_pitch_max_s" in cfg:
                self.max_s = max(self.min_s + 1.0, float(cfg["idle_pitch_max_s"]))
            if "context_live_dir" in cfg:
                self.context_live_dir = Path(cfg["context_live_dir"])
            if "context_dir" in cfg:
                self.context_dir = Path(cfg["context_dir"])

    def load_products(self) -> list[dict]:
        """Tải danh sách sản phẩm từ context-live (hoặc fallback context-data)."""
        products: list[dict] = []
        target_dir = self.context_live_dir if self.context_live_dir.is_dir() else None
        if not target_dir or not any(target_dir.glob("*.md")):
            target_dir = self.context_dir if self.context_dir.is_dir() else None

        if not target_dir:
            return []

        for md in sorted(target_dir.glob("*.md")):
            if md.name.lower() in ("readme.md", "_index.md"):
                continue
            try:
                content = md.read_text(encoding="utf-8")
            except Exception:
                continue

            name = ""
            price = ""
            for line in content.splitlines():
                line = line.strip()
                if not name and (line.startswith("# ") or line.startswith("#")):
                    name = line.lstrip("#").strip()
                    m_clean = re.match(r"^sản phẩm\s*#?\d+\s*:\s*(.*)$", name, re.I)
                    if m_clean:
                        name = m_clean.group(1).strip()
                elif not price and re.search(r"giá\s*(?:khuyến mại|ưu đãi|niêm yết)?\s*:\s*(.+)", line, re.I):
                    m_p = re.search(r"giá\s*(?:khuyến mại|ưu đãi|niêm yết)?\s*:\s*(.+)", line, re.I)
                    if m_p:
                        price = m_p.group(1).strip()

            if name:
                # Làm gọn tên sản phẩm nếu quá dài (bỏ bớt từ khoá SEO)
                clean_name = re.sub(r"^(deal|tặng|combo|hộp|túi|gói)\s*\d+[^:]*:\s*", "", name, flags=re.I).strip()
                if not clean_name:
                    clean_name = name
                # Giới hạn độ dài tên sản phẩm trong câu nói để phát tự nhiên
                if len(clean_name.split()) > 10:
                    clean_name = " ".join(clean_name.split()[:10])

                products.append({
                    "id": md.stem,
                    "name": clean_name,
                    "full_name": name,
                    "price": price or "cực hời",
                    "path": str(md),
                })
        return products

    def pick_next_product(self, products: list[dict]) -> dict | None:
        """Chọn 1 sản phẩm ngẫu nhiên, không trùng các sản phẩm đang có trong buffer hoặc vừa nói."""
        if not products:
            return None

        with self._lock:
            buffered_names = {item.get("product_name") for item in self._buffer if item.get("product_name")}
            recent = set(self._recent_products)

            # Ứng viên là sản phẩm không nằm trong buffer và không nằm trong recent
            candidates = [p for p in products if p["name"] not in buffered_names and p["name"] not in recent]

            # Nếu hết ứng viên, cho phép reset danh sách recent (nhưng vẫn loại các món đang có trong buffer)
            if not candidates:
                candidates = [p for p in products if p["name"] not in buffered_names]

            # Nếu vẫn không có (ví dụ số sản phẩm ít hơn buffer_size), lấy bất kỳ sản phẩm nào
            if not candidates:
                candidates = products

            chosen = random.choice(candidates)
            self._recent_products.append(chosen["name"])
            return chosen

    def generate_pitch_text(self, product: dict | None) -> tuple[str, str]:
        """Tạo câu thoại bán hàng chốt đơn dựa trên thông tin sản phẩm và công thức livestream."""
        if product and product.get("name"):
            name = product["name"]
            price = product.get("price") or "ưu đãi"
            # Chọn ngẫu nhiên 1 công thức bán hàng
            formula_key = random.choice(list(_PITCH_FORMULAS.keys()))
            templates = _PITCH_FORMULAS[formula_key]
            template = random.choice(templates)
            raw_text = template.format(name=name, price=price)
        else:
            formula_key = "generic"
            raw_text = random.choice(_GENERIC_ENGAGEMENT_PITCHES)

        # Chuyển đổi ngữ âm & chuẩn giọng miền Bắc cho TTS
        spoken_text = northernize_vietnamese(phoneticize_vietnamese(raw_text))
        return spoken_text, formula_key

    def generate_pitch_item(self, synthesize_fn, products: list[dict] | None = None) -> dict | None:
        """Sinh 1 voice mới và trả về dict item kèm file .wav trong cache."""
        if products is None:
            products = self.load_products()

        product = self.pick_next_product(products)
        spoken_text, formula = self.generate_pitch_text(product)

        ts = int(time.time() * 1000)
        rand_suffix = random.randint(1000, 9999)
        pitch_id = f"pitch_{ts}_{rand_suffix}"
        target_wav = self.cache_dir / f"{pitch_id}.wav"

        try:
            # Gọi TTS tạo wav (hỗ trợ cả out_path và fallback out_dir)
            try:
                out_path = synthesize_fn(spoken_text, out_path=str(target_wav))
            except TypeError:
                out_path = synthesize_fn(spoken_text, out_dir=str(self.cache_dir))
            if not out_path or not Path(out_path).is_file():
                return None
            return {
                "id": pitch_id,
                "product_name": product["name"] if product else "",
                "product_id": product.get("id", "") if product else "",
                "speak_text": spoken_text,
                "wav": str(out_path),
                "wav_path": str(out_path),
                "formula": formula,
                "created_at": time.time(),
            }
        except Exception as e:
            print(f"[auto_pitch] Lỗi sinh voice: {e}", flush=True)
            return None

    def trigger_refill(self, synthesize_fn) -> None:
        """Khởi chạy tiến trình bù thêm voice trong nền nếu buffer chưa đủ."""
        with self._lock:
            if self._refill_active:
                return
            if len(self._buffer) >= self.buffer_size:
                return
            self._refill_active = True

        def _worker():
            try:
                products = self.load_products()
                while True:
                    with self._lock:
                        if not self.enabled or len(self._buffer) >= self.buffer_size:
                            break
                    item = self.generate_pitch_item(synthesize_fn, products)
                    if item:
                        with self._lock:
                            self._buffer.append(item)
                    time.sleep(0.3)
            finally:
                with self._lock:
                    self._refill_active = False

        self._refill_thread = threading.Thread(target=_worker, daemon=True, name="auto-pitch-refill")
        self._refill_thread.start()

    def pop_pitch(self) -> dict | None:
        """Lấy 1 voice từ đầu buffer để phát (FIFO)."""
        with self._lock:
            if not self.enabled or not self._buffer:
                return None
            return self._buffer.pop(0)

    def on_pitch_finished(self, pitch_item: dict, synthesize_fn) -> None:
        """Khi voice đã phát xong trọn vẹn: xoá file wav và kích hoạt tạo bù voice mới."""
        wav_path = pitch_item.get("wav_path") or pitch_item.get("wav")
        if wav_path:
            p = Path(wav_path)
            try:
                if p.is_file():
                    p.unlink()
            except Exception as e:
                print(f"[auto_pitch] Lỗi xoá file wav sau phát: {e}", flush=True)

        # Lập tức bù 1 voice mới để duy trì đủ buffer_size (10 cái)
        self.trigger_refill(synthesize_fn)
    def clean_cache(self) -> None:
        """Dọn dẹp các file wav cũ trong cache folder khi app khởi động."""
        with self._lock:
            self._buffer.clear()
        if self.cache_dir.is_dir():
            for f in self.cache_dir.glob("pitch_*.wav"):
                try:
                    f.unlink()
                except Exception:
                    pass

    @property
    def buffer_count(self) -> int:
        with self._lock:
            return len(self._buffer)
