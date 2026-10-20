"""Regression: payload LLM phai tat thinking theo setting + fallback khi server strict (400).

Tham so tat thinking khac nhau theo backend (server tra 'thinkingFormat' trong /v1/models),
nen test kiem tra 'co tham so tat thinking' chung chung, va kiem tra thu tu fallback.
"""
from __future__ import annotations

import io
import json
import os
import sys
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import llm_client  # noqa: E402

_THINKING_KEYS = ("thinking", "reasoning_effort", "enable_thinking")


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def _install(monkeypatch, responses, captured):
    """responses: list of (exc | body bytes). captured: list of request payloads."""

    def fake_urlopen(req, timeout=None):
        captured.append(json.loads(req.data.decode("utf-8")))
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return _FakeResp(item)

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)


def _body(content: str) -> bytes:
    return (json.dumps({"choices": [{"message": {"content": content}}]})
            + "data: [DONE]\n\n").encode("utf-8")


def _reset(monkeypatch, meta=None):
    """Reset cache module + giu metadata model gia dinh (khong goi network)."""
    llm_client._thinking_cache.clear()
    llm_client._model_meta.clear()
    llm_client._model_meta_loaded = True
    if meta is not None:
        llm_client._model_meta.update(meta)


def _set_thinking(monkeypatch, enabled: bool) -> None:
    """Bat/tat thinking trong config (llm_client doc settings.get() luc goi)."""
    import settings

    real_get = settings.get

    def fake_get():
        cfg = dict(real_get())
        cfg["llm_disable_thinking"] = enabled
        return cfg

    monkeypatch.setattr(settings, "get", fake_get)

def test_thinking_off_payload_added_by_default(monkeypatch):
    _set_thinking(monkeypatch, True)
    _reset(monkeypatch, {"m1": {"thinkingCanDisable": True, "thinkingFormat": "openai"}})
    captured: list = []
    _install(monkeypatch, [_body("OK")], captured)
    assert llm_client.chat("sys", "user", model="m1") == "OK"
    assert any(k in captured[0] for k in _THINKING_KEYS), captured[0]


def test_no_thinking_payload_when_model_cannot_disable(monkeypatch):
    """Server noi ro model nay khong tat duoc thinking -> khong gui tham so la."""
    _set_thinking(monkeypatch, True)
    _reset(monkeypatch, {"m2": {"thinkingCanDisable": False, "thinkingFormat": "gemini-level"}})
    captured: list = []
    _install(monkeypatch, [_body("OK")], captured)
    assert llm_client.chat("sys", "user", model="m2") == "OK"
    assert not any(k in captured[0] for k in _THINKING_KEYS), captured[0]


def test_thinking_omitted_when_disabled_in_config(monkeypatch):
    _set_thinking(monkeypatch, False)
    _reset(monkeypatch, {"m3": {"thinkingCanDisable": True, "thinkingFormat": "openai"}})
    captured: list = []
    _install(monkeypatch, [_body("OK")], captured)
    assert llm_client.chat("sys", "user", model="m3") == "OK"
    assert not any(k in captured[0] for k in _THINKING_KEYS), captured[0]


def test_falls_back_to_next_shape_on_400(monkeypatch):
    """Server strict tra 400 voi tham so dau -> thu tham so tiep theo, van tra content."""
    _set_thinking(monkeypatch, True)
    _reset(monkeypatch, {"m4": {"thinkingCanDisable": True, "thinkingFormat": "openai"}})
    err = urllib.error.HTTPError(
        "http://x", 400, "Bad Request", {}, io.BytesIO(b'{"error":"unrecognized"}'))
    captured: list = []
    _install(monkeypatch, [err, _body("OK")], captured)
    assert llm_client.chat("sys", "user", model="m4") == "OK"
    assert len(captured) == 2
    assert any(k in captured[0] for k in _THINKING_KEYS)
    assert any(k in captured[1] for k in _THINKING_KEYS)


def test_accepted_shape_is_cached_for_next_call(monkeypatch):
    """Sau khi server chap nhan 1 shape, cac lan sau dung lai -> khong request 400 du thua."""
    _set_thinking(monkeypatch, True)
    _reset(monkeypatch, {"m5": {"thinkingCanDisable": True, "thinkingFormat": "openai"}})
    captured: list = []
    _install(monkeypatch, [_body("OK"), _body("OK")], captured)
    llm_client.chat("sys", "user", model="m5")
    first = {k: captured[0][k] for k in _THINKING_KEYS if k in captured[0]}
    llm_client.chat("sys", "user", model="m5")
    second = {k: captured[1][k] for k in _THINKING_KEYS if k in captured[1]}
    assert first == second and first


def test_http_error_400_without_thinking_raises_immediately(monkeypatch):
    """Khong co tham so tat thinking -> 400 la loi client thuc su,
    fail ngay khong retry vo ich (tiet kiem timeout)."""
    _set_thinking(monkeypatch, False)
    _reset(monkeypatch)
    err = urllib.error.HTTPError(
        "http://x", 400, "Bad Request", {}, io.BytesIO(b'{"error":"bad request"}'))
    captured: list = []
    _install(monkeypatch, [err], captured)
    try:
        llm_client.chat("sys", "user", model="m6")
    except RuntimeError:
        pass
    else:
        raise AssertionError("phai raise RuntimeError")
    # Fail fast ngay lan 1, khong gui lai
    assert len(captured) == 1


def test_http_error_401_raises_immediately(monkeypatch):
    """401 (sai key / model) -> fail ngay, khong retry vo ich."""
    _set_thinking(monkeypatch, True)
    _reset(monkeypatch, {"m7": {"thinkingCanDisable": True, "thinkingFormat": "openai"}})
    err = urllib.error.HTTPError(
        "http://x", 401, "Unauthorized", {}, io.BytesIO(b'{"error":"unauthorized"}'))
    captured: list = []
    _install(monkeypatch, [err], captured)
    try:
        llm_client.chat("sys", "user", model="m7")
    except RuntimeError:
        pass
    else:
        raise AssertionError("phai raise RuntimeError")
    assert len(captured) == 1
