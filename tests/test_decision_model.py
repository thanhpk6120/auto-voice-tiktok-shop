"""Regression: decision model (TypeSafe/jev) phai goi endpoint '/systemone', khong phai chat."""
from __future__ import annotations

import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import intent_router as ir  # noqa: E402
import llm_client  # noqa: E402


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def test_is_decision_model_detects_jev():
    assert ir._is_decision_model("openrouter/typesafe/jev-1.13")
    assert ir._is_decision_model("oc/jev-1.13-free")
    assert not ir._is_decision_model("claude-haiku-4-5-20251001")
    assert not ir._is_decision_model("gpt-4o-mini")


def test_decision_questions_shape():
    q = ir._decision_questions()
    assert set(q) == {"intent"}
    spec = q["intent"]
    assert spec["type"] == "choice"
    assert set(spec["options"]) == set(ir.VALID_INTENTS)
    # 'criteria' phai la record (dict) kem key cho tung option -> server moi nhan.
    assert isinstance(spec["criteria"], dict)
    assert set(spec["criteria"]) == set(ir.VALID_INTENTS)


def test_classify_intent_uses_decide_for_decision_model(monkeypatch):
    calls = {}

    def fake_decide(model, state, questions, timeout=None):
        calls["model"] = model
        calls["state"] = state
        calls["questions"] = questions
        return {"intent": {"type": "choice", "choice": "gift", "confidence": 0.93}}

    monkeypatch.setattr(llm_client, "decide", fake_decide)
    r = ir.classify_intent("tặng quà cho shop nè", model="openrouter/typesafe/jev-1.13")
    assert r["intent"] == "gift"
    assert r["source"] == "llm"
    assert calls["model"] == "openrouter/typesafe/jev-1.13"
    assert "tặng quà" in calls["state"]
    assert calls["questions"] == ir._decision_questions()


def test_classify_intent_falls_back_to_rules_on_decide_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("HTTP 401 Unauthorized")

    monkeypatch.setattr(llm_client, "decide", boom)
    r = ir.classify_intent("còn hàng không shop?", model="openrouter/typesafe/jev-1.13")
    # Decision model loi -> dung luat tu khoa (khong goi /chat/completions).
    assert r["source"] == "rule"
    assert r["intent"] == "product_question"
    assert r.get("error")


def test_decide_posts_to_systemone_endpoint(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp(json.dumps({
            "answers": {"intent": {"type": "choice", "choice": "order", "confidence": 1}},
        }).encode("utf-8"))

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)
    ans = llm_client.decide("openrouter/typesafe/jev-1.13", "chốt đơn", {"q": {"type": "noul"}})
    assert captured["url"].endswith("/v1/systemone")
    assert captured["body"]["model"] == "openrouter/typesafe/jev-1.13"
    assert captured["body"]["state"] == "chốt đơn"
    assert ans["intent"]["choice"] == "order"
