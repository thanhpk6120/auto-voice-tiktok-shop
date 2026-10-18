"""Test lam sach cau LLM truoc khi TTS (chan markdown/ghi chu noi bo doc len live)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from event_analyzer import clean_speak_text, phoneticize_vietnamese  # noqa: E402


def test_strips_internal_note_lines():
    raw = (
        "Dạ em chưa có size XL ạ. Anh chị để lại số đo nhé.\n\n"
        "→ Cần xác nhận size thật từ shop; nếu shop đã biết có XL, đổi câu trả lời."
    )
    assert clean_speak_text(raw) == "Dạ em chưa có size XL ạ. Anh chị để lại số đo nhé."


def test_strips_bullets_and_markdown():
    assert clean_speak_text("**Áo cotton** giá 150.000đ") == "Áo cotton giá 150.000đ"
    assert clean_speak_text("- bullet ghi chu") == ""


def test_keeps_single_line_qa():
    assert clean_speak_text("Dạ áo thun Cotton Compact giá 150.000đ, còn 120 áo.") == (
        "Dạ áo thun Cotton Compact giá 150.000đ, còn 120 áo."
    )


def test_truncates_long_reply():
    out = clean_speak_text(" ".join(["từ"] * 60))
    assert len(out.split(" ")) == 45
    assert out.endswith(".")


def test_empty_and_none():
    assert clean_speak_text("") == ""
    assert clean_speak_text(None) == ""


def test_note_in_middle_line_is_dropped_but_others_kept():
    raw = "Dòng một.\nLưu ý: đừng đọc dòng này.\nDòng ba."
    assert "Lưu ý" not in clean_speak_text(raw)
    assert "Dòng một." in clean_speak_text(raw)


def test_phoneticize_currency_and_numbers():
    assert phoneticize_vietnamese("Giá 10000 đ") == "Giá mười nghìn đồng"
    assert phoneticize_vietnamese("Deal chỉ 1₫ hôm nay") == "điu chỉ một đồng hôm nay"
    assert phoneticize_vietnamese("Snack 28.900₫") == "xì-nách hai mươi tám nghìn chín trăm đồng"
    assert phoneticize_vietnamese("Giảm 99% nhé") == "Giảm chín mươi chín phần trăm nhé"


def test_phoneticize_english_loanwords():
    assert phoneticize_vietnamese("hello cả nhà what's up") == "hê lô cả nhà goắt sắp"
    assert phoneticize_vietnamese("Hôm nay flash sale và freeship 1kg") == "Hôm nay phờ-lát sêu và miễn phí vận chuyển một ki-lô-gam"
