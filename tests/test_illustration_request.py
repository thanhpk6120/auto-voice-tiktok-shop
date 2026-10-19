"""Kiểm thử sự kiện 'yêu cầu minh họa sản phẩm' + bộ lọc junk của CDP.

Hai lỗi gốc:
1. isJunk khớp theo TIỀN TỐ nên nuốt cả comment thật
   ("Sản phẩm này còn hàng không shop?" bị coi là nhãn UI "sản phẩm").
2. Sự kiện khách bấm "Yêu cầu minh họa" không được nhận diện: rơi vào chat thường
   hoặc bị lọc mất, nên app không tư vấn đúng sản phẩm khách xin minh họa.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import browser_manager as bm
import event_analyzer as ea


# --------------------------------------------------------------- junk filter

@pytest.fixture()
def live_dir():
    """Gio hang live gia lap voi 2 san pham de kiem tra match.

    Dung tempfile thay tmp_path: Temp cua pytest bi chan quyen tren may nay.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bm.save_product_context(
            {"index": 1, "id": "111", "name": "Bánh Tráng Trộn Hành Phi 300Gr",
             "price": "29.000₫", "description": "Bánh tráng giòn, hành phi thơm"},
            live_dir=root,
        )
        bm.save_product_context(
            {"index": 2, "id": "222", "name": "Bánh Gấu Nhân Kem Ngon Mêly",
             "price": "38.000₫", "description": "Bánh quy gấu nhân kem vani"},
            live_dir=root,
        )
        yield root


def test_junk_filter_does_not_eat_real_comments():
    """Comment thật bắt đầu bằng chữ 'sản phẩm'/'quà tặng' phải được giữ lại."""
    js = bm.CDP_SETUP_JS
    junk_body = re.search(r"const JUNK_EXACT = \[(.*?)\];", js, re.S).group(1)
    junk_list = [s.strip().strip("'\"") for s in re.findall(r"'([^']+)'", junk_body)]
    prefix_max = int(re.search(r"const JUNK_PREFIX_MAX = (\d+);", js).group(1))

    def is_junk(text: str) -> bool:
        s = text.strip().lower()
        if len(s) < 2:
            return True
        for phrase in junk_list:
            if s == phrase:
                return True
            if s.startswith(phrase) and len(s) <= prefix_max:
                return True
        return False

    for real in (
        "Sản phẩm này còn hàng không shop?",
        "Sản phẩm bánh tráng giá bao nhiêu",
        "Quà tặng kèm gì vậy shop?",
        "Thanh muốn xem minh họa sản phẩm Sói 🐺",
    ):
        assert not is_junk(real), f"comment thật bị lọc mất: {real}"

    for label in ("Trò chuyện", "Hoạt động", "Tất cả hoạt động", "sản phẩm",
                  "quà tặng", "xem thêm", "đã yêu cầu minh họa", "0/100"):
        assert is_junk(label), f"nhãn UI lọt qua bộ lọc: {label}"


def test_cdp_script_detects_illustration_request():
    """Script CDP phải có nhánh nhận diện 'minh họa sản phẩm' -> viewing_product."""
    js = bm.CDP_SETUP_JS
    assert "minh\\s+họa\\s+sản\\s+phẩm" in js or "minh họa sản phẩm" in js
    assert "evType = 'viewing_product'" in js


# ------------------------------------------------------- analyze: minh hoạ

def test_illustration_with_unknown_product_does_not_invent(monkeypatch, live_dir):
    """Khách xin minh họa 'Sói' (không có trong giỏ live) -> nói chưa thấy, không bịa."""
    monkeypatch.setenv("PHRASE_CACHE_DIR", str(live_dir / "cache"))
    ea.configure(context_dir=str(live_dir), context_live_dir=str(live_dir))

    res = ea.analyze({"type": "chat", "user": "Thanh",
                      "text": "Thanh muốn xem minh họa sản phẩm Sói 🐺"}, use_batcher=False)

    assert res["kind"] == "sales"
    assert res["priority"] == 1
    text = res["speak_text"].lower()
    assert "chưa thấy" in text
    assert "sói" in text
    # Khong duoc bia chi tiet san pham
    for invented in ("giá", "chất liệu", "miễn phí vận chuyển"):
        assert invented not in text, f"bịa thông tin: {invented}"


def test_illustration_with_matching_product_uses_context(monkeypatch, live_dir):
    """Khách xin minh họa đúng món có trong giỏ live -> tư vấn đúng món đó."""
    monkeypatch.setenv("PHRASE_CACHE_DIR", str(live_dir / "cache"))
    ea.configure(context_dir=str(live_dir), context_live_dir=str(live_dir))

    res = ea.analyze({"type": "chat", "user": "Thanh",
                      "text": "muốn xem minh họa sản phẩm bánh tráng trộn"}, use_batcher=False)

    assert res["kind"] == "sales"
    assert res["priority"] == 1
    prod = res.get("product")
    assert prod is not None, "phải khớp được sản phẩm trong context-live"
    assert "Bánh Tráng Trộn" in prod["name"]


def test_illustration_without_product_name_asks_back(monkeypatch, live_dir):
    """Không nêu tên món -> hỏi lại, không bịa sản phẩm nào."""
    monkeypatch.setenv("PHRASE_CACHE_DIR", str(live_dir / "cache"))
    ea.configure(context_dir=str(live_dir), context_live_dir=str(live_dir))

    res = ea.analyze({"type": "chat", "user": "Thanh",
                      "text": "yêu cầu minh họa sản phẩm"}, use_batcher=False)
    text = res["speak_text"].lower()
    assert "chưa thấy" in text
    assert "món món" not in text


def test_product_question_without_match_does_not_invent(monkeypatch, live_dir):
    """Hỏi món không có trong context-live -> không gọi LLM, không bịa tên/giá."""
    monkeypatch.setenv("PHRASE_CACHE_DIR", str(live_dir / "cache"))
    ea.configure(context_dir=str(live_dir), context_live_dir=str(live_dir))

    res = ea.analyze({"type": "chat", "user": "Thanh",
                      "text": "áo thun cotton còn hàng không shop"}, use_batcher=False)
    text = res["speak_text"].lower()
    assert "chưa thấy" in text
    assert "cotton compact" not in text
    assert "150" not in text
