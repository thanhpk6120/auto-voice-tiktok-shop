"""Regression: cache phan loai intent theo text (comment trung lap -> khong goi lai model)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import intent_router as ir  # noqa: E402
import llm_client  # noqa: E402


def _reset() -> None:
    ir.clear_intent_cache()


def test_cache_key_normalizes_whitespace_and_case():
    assert ir._cache_key("  Còn   hàng không shop?  ", "m1") == ir._cache_key("còn hàng không shop?", "m1")
    assert ir._cache_key("CÒN HÀNG KHÔNG SHOP?", "m1") == ir._cache_key("còn hàng không shop?", "m1")


def test_cache_key_differs_per_model():
    """Đổi analyst model -> khoá khác -> không dùng kết quả của model cũ."""
    assert ir._cache_key("còn hàng không shop?", "model-a") != ir._cache_key("còn hàng không shop?", "model-b")


def test_changing_model_bypasses_cache(monkeypatch):
    """App hot-reload đổi model: cùng text phải gọi lại model (khoá gồm model)."""
    _reset()
    calls = []

    def fake_decide(model, state, questions, timeout=None):
        calls.append(model)
        return {"intent": {"type": "choice", "choice": "product_question", "confidence": 0.9}}

    monkeypatch.setattr(llm_client, "decide", fake_decide)
    r1 = ir.classify_intent("còn hàng không shop?", model="openrouter/typesafe/jev-a")
    r2 = ir.classify_intent("còn hàng không shop?", model="openrouter/typesafe/jev-a")
    r3 = ir.classify_intent("còn hàng không shop?", model="openrouter/typesafe/jev-b")
    assert r1["source"] == "llm"
    assert r2["source"] == "cache"
    assert r3["source"] == "llm", "đổi model phải gọi lại, không dùng cache của model cũ"
    assert calls == ["openrouter/typesafe/jev-a", "openrouter/typesafe/jev-b"]


def test_repeated_text_hits_cache(monkeypatch):
    _reset()
    calls = []

    def fake_decide(model, state, questions, timeout=None):
        calls.append(state)
        return {"intent": {"type": "choice", "choice": "product_question", "confidence": 0.9}}

    monkeypatch.setattr(llm_client, "decide", fake_decide)
    r1 = ir.classify_intent("còn hàng không shop?", model="openrouter/typesafe/jev-1.13")
    r2 = ir.classify_intent("còn hàng không shop?", model="openrouter/typesafe/jev-1.13")
    assert r1["source"] == "llm"
    assert r2["source"] == "cache"
    assert r2["intent"] == "product_question"
    assert len(calls) == 1, "comment trùng chỉ được gọi model 1 lần"


def test_cache_key_ignores_case_and_extra_spaces(monkeypatch):
    _reset()
    calls = []

    def fake_decide(model, state, questions, timeout=None):
        calls.append(state)
        return {"intent": {"type": "choice", "choice": "gift", "confidence": 1.0}}

    monkeypatch.setattr(llm_client, "decide", fake_decide)
    ir.classify_intent("Tặng quà nè", model="openrouter/typesafe/jev-1.13")
    ir.classify_intent("  tặng quà   nè ", model="openrouter/typesafe/jev-1.13")
    assert len(calls) == 1


def test_cache_expires_after_ttl(monkeypatch):
    _reset()
    calls = []

    def fake_decide(model, state, questions, timeout=None):
        calls.append(state)
        return {"intent": {"type": "choice", "choice": "order", "confidence": 1.0}}

    monkeypatch.setattr(llm_client, "decide", fake_decide)
    monkeypatch.setattr(ir, "_CACHE_TTL_S", 0.0)
    ir.classify_intent("chốt đơn nha", model="openrouter/typesafe/jev-1.13")
    ir.classify_intent("chốt đơn nha", model="openrouter/typesafe/jev-1.13")
    assert len(calls) == 2, "hết TTL thì phải gọi lại model"


def test_error_result_is_not_cached(monkeypatch):
    _reset()
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("HTTP 500")

    monkeypatch.setattr(llm_client, "decide", boom)
    r1 = ir.classify_intent("chào shop", model="openrouter/typesafe/jev-1.13")
    r2 = ir.classify_intent("chào shop", model="openrouter/typesafe/jev-1.13")
    assert r1["source"] == "rule"
    assert r2["source"] == "rule"
    assert len(calls) == 2, "kết quả lỗi không được cache"


def test_chat_model_fallback_to_rules_is_not_cached(monkeypatch):
    """Nhánh chat model lỗi -> rơi về luật từ khoá: kết quả luật KHÔNG được cache.

    Luật từ khoá tốn 0ms nên cache vô ích, và cache có thể giữ intent sai sau khi
    đổi hàng (sau khi model hồi phục, text đó vẫn được trả từ cache thay vì gọi lại).
    """
    _reset()
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("HTTP 500")

    monkeypatch.setattr(llm_client, "chat", boom)
    r1 = ir.classify_intent("còn hàng không shop?", model="claude-haiku-4-5-20251001")
    r2 = ir.classify_intent("còn hàng không shop?", model="claude-haiku-4-5-20251001")
    assert r1["source"] == "rule"
    assert r2["source"] == "rule", "kết quả luật không được cache (source phải là 'rule')"
    assert len(calls) == 2, "phải gọi lại model mỗi lần khi trước đó rơi về luật"


def test_rule_result_does_not_fill_cache(monkeypatch):
    """Model không bật (analyst rỗng) -> luật từ khoá, cache phải rỗng."""
    _reset()
    ir.classify_intent("chào shop", model="")
    assert ir._intent_cache == {}


def test_cache_is_bounded(monkeypatch):
    _reset()
    monkeypatch.setattr(ir, "_CACHE_MAX", 3)

    def fake_decide(model, state, questions, timeout=None):
        return {"intent": {"type": "choice", "choice": "chat", "confidence": 1.0}}

    monkeypatch.setattr(llm_client, "decide", fake_decide)
    for i in range(10):
        ir.classify_intent(f"comment số {i}", model="openrouter/typesafe/jev-1.13")
    assert len(ir._intent_cache) <= 3


def test_clear_intent_cache_empties_cache():
    _reset()
    ir._intent_cache["x"] = (0.0, {"intent": "chat"})
    ir.clear_intent_cache()
    assert ir._intent_cache == {}
