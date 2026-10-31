"""Kiểm thử bộ đệm 10 voice tự động giới thiệu sản phẩm (AutoPitchManager)."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "src"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from auto_pitch import AutoPitchManager  # noqa: E402


def test_load_products_from_directory():
    with tempfile.TemporaryDirectory() as tmp_dir:
        d = Path(tmp_dir)
        (d / "sp-01-chuoi.md").write_text("# Chuối sấy dẻo\nGiá ưu đãi: 35.000đ\nNgon dẻo", encoding="utf-8")
        (d / "sp-02-khoai.md").write_text("# Khoai tây sấy phô mai\nGiá: 50.000đ\nGiòn rụm", encoding="utf-8")
        (d / "README.md").write_text("# Bo qua file nay", encoding="utf-8")

        mgr = AutoPitchManager(context_live_dir=d, context_dir=d, buffer_size=10)
        prods = mgr.load_products()
        assert len(prods) == 2
        names = {p["name"] for p in prods}
        assert "Chuối sấy dẻo" in names
        assert "Khoai tây sấy phô mai" in names


def test_pick_product_avoids_repetition():
    with tempfile.TemporaryDirectory() as tmp_dir:
        d = Path(tmp_dir)
        for i in range(5):
            (d / f"sp-{i}.md").write_text(f"# Món ăn vặt số {i}\nGiá: {i*10}.000đ", encoding="utf-8")

        mgr = AutoPitchManager(context_live_dir=d, context_dir=d, buffer_size=5)
        prods = mgr.load_products()
        assert len(prods) == 5

        # Chọn liên tiếp 5 lần: không được lặp lại bất kỳ món nào cho đến khi hết vòng
        chosen = []
        for _ in range(5):
            p = mgr.pick_next_product(prods)
            assert p is not None
            assert p["name"] not in chosen
            chosen.append(p["name"])

        assert len(set(chosen)) == 5


def test_generate_pitch_text_applies_sales_formulas():
    mgr = AutoPitchManager(buffer_size=10)
    prod = {"name": "Bánh tráng phô mai", "price": "25.000đ"}
    text, formula = mgr.generate_pitch_text(prod)
    assert formula in ("scarcity", "cta_cart", "freeship", "social_proof", "engagement")
    # Kêu gọi chốt đơn hoặc bấm giỏ hàng góc trái
    assert any(term in text.lower() for term in ("giỏ hàng", "chốt", "bấm", "ưu đãi", "freeship", "trợ giá", "săn", "tim"))

def test_buffer_refill_pop_and_finish_replenish():
    with tempfile.TemporaryDirectory() as tmp_cache, tempfile.TemporaryDirectory() as tmp_prods:
        c_dir = Path(tmp_cache)
        p_dir = Path(tmp_prods)
        for i in range(4):
            (p_dir / f"sp-{i}.md").write_text(f"# Món {i}\nGiá: 15.000đ", encoding="utf-8")

        # Fake hàm TTS synthesize
        def fake_synthesize(text: str, out_path: str = None) -> str:
            p = Path(out_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"RIFFFAKEWAVDATA")
            return str(p)

        mgr = AutoPitchManager(
            context_live_dir=p_dir,
            context_dir=p_dir,
            cache_dir=c_dir,
            buffer_size=3,
        )

        # 1. Refill lên 3 voice
        mgr.trigger_refill(fake_synthesize)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and mgr.buffer_count < 3:
            time.sleep(0.05)

        assert mgr.buffer_count == 3
        # Các file wav đã được tạo trong cache
        wav_files = list(c_dir.glob("pitch_*.wav"))
        assert len(wav_files) == 3

        # 2. Pop 1 voice ra để phát
        item = mgr.pop_pitch()
        assert item is not None
        assert mgr.buffer_count == 2
        assert Path(item["wav_path"]).is_file()

        # 3. Phát xong: xoá file wav và tự động tạo bù 1 voice mới
        mgr.on_pitch_finished(item, fake_synthesize)
        # File wav của item vừa phát phải bị xoá
        assert not Path(item["wav_path"]).is_file()

        # Đợi background thread bù thêm 1 voice mới để quay lại đủ 3
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and mgr.buffer_count < 3:
            time.sleep(0.05)

        assert mgr.buffer_count == 3


def test_clean_cache_removes_old_files():
    with tempfile.TemporaryDirectory() as tmp_cache:
        c_dir = Path(tmp_cache)
        old_file = c_dir / "pitch_old_123.wav"
        old_file.write_bytes(b"old")
        assert old_file.is_file()

        mgr = AutoPitchManager(cache_dir=c_dir, buffer_size=5)
        mgr.clean_cache()
        assert not old_file.is_file()
