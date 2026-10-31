"""Test: cau hinh trong settings.apply() phai thuc su co tac dung len runtime.

Config da duoc don ve 1 nguon: settings.get() (DEFAULTS -> config.json -> .env).
apply() ghi gia tri cuoi cung vao os.environ cho module doc env.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "src"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import settings  # noqa: E402
import pytest


@pytest.fixture(autouse=True)
def clean_settings():
    saved = dict(settings.get())
    yield
    settings.reset()
    settings.apply(saved)
def test_apply_sets_tts_client():
    import tts_client

    cfg = settings.get()
    cfg["voicestudio_url"] = "http://10.9.9.9:4321"
    cfg["tts_timeout_s"] = 77.0
    cfg["voicestudio_voice"] = "voice-x"
    settings.apply(cfg)

    assert tts_client.VOICE_URL == "http://10.9.9.9:4321"
    assert float(tts_client.TTS_TIMEOUT) == 77.0
    assert tts_client.VOICE_NAME == "voice-x"


def test_apply_sets_llm_config_and_env():
    """apply() phai ghi gia tri LLM vao os.environ va settings.get() dung khi goi."""
    import os

    cfg = settings.get()
    cfg["llm_base_url"] = "http://10.1.1.1:1111/v1"
    cfg["llm_model"] = "model-abc"
    cfg["llm_api_key"] = "sk-live-abcdefghijkl"
    cfg["llm_disable_thinking"] = False
    cfg["analyst_llm_url"] = "http://10.2.2.2:2222/v1"
    cfg["analyst_llm_api_key"] = "sk-analyst-12345"
    settings.apply(cfg)

    assert os.environ["LLM_BASE_URL"] == "http://10.1.1.1:1111/v1"
    assert os.environ["LLM_MODEL"] == "model-abc"
    assert os.environ["LLM_API_KEY"] == "sk-live-abcdefghijkl"
    assert os.environ["LLM_DISABLE_THINKING"] == "0"
    assert os.environ["ANALYST_LLM_URL"] == "http://10.2.2.2:2222/v1"
    assert os.environ["ANALYST_LLM_API_KEY"] == "sk-analyst-12345"

def test_llm_client_reads_config_at_call_time():
    """llm_client.chat() phai doc base url luc goi, khong bind cung luc import."""
    import inspect

    import src.llm_client as llm_client

    src = inspect.getsource(llm_client.chat)
    assert "_llm_cfg()" in src
    assert "import src.config" not in inspect.getsource(llm_client)


def test_analyzer_configure_applies_cooldown_and_batch():
    import event_analyzer

    event_analyzer.configure(cooldown=1.0, max_batch=2, max_words=7)
    b = event_analyzer.get_batcher()
    assert float(b.cooldown) == 1.0
    assert int(b.max_batch) == 2

    # tra ve default de khong anh huong test khac
    event_analyzer.configure(cooldown=3.0, max_batch=5, max_words=45)


def test_masked_hides_api_key():
    cfg = settings.get()
    cfg["llm_api_key"] = "sk-live-verysecretvalue123"
    cfg["analyst_llm_api_key"] = "sk-analyst-verysecretvalue456"
    m = settings.masked(cfg)
    assert "verysecretvalue" not in m["llm_api_key"]
    assert m["llm_api_key"].startswith("sk-liv")
    assert "verysecretvalue" not in m["analyst_llm_api_key"]
    assert m["analyst_llm_api_key"].startswith("sk-ana")


def test_config_path_writable_location():
    p = settings.config_path()
    assert isinstance(p, Path)
    # khong nam trong thu muc app (de chay duoc tu Program Files)
    assert ".tmp" not in p.name


def test_apply_sets_browser_env():
    import os

    cfg = settings.get()
    cfg["gologin_dir"] = "my-custom-gologin"
    cfg["browser_mode"] = "gologin_cdp"
    settings.apply(cfg)

    assert os.environ.get("GOLOGIN_DIR") == "my-custom-gologin"
    assert os.environ.get("BROWSER_MODE") == "gologin_cdp"


def test_apply_sets_batch_and_prompts_env():
    import os

    cfg = settings.get()
    cfg["prompts_dir"] = "my-prompts"
    cfg["context_dir"] = "my-context"
    cfg["batch_window_s"] = 7.5
    cfg["batch_max_events"] = 15
    settings.apply(cfg)

    assert os.environ.get("PROMPTS_DIR") == "my-prompts"
    assert os.environ.get("CONTEXT_DIR") == "my-context"
    assert os.environ.get("BATCH_WINDOW_S") == "7.5"
    assert os.environ.get("BATCH_MAX_EVENTS") == "15"

def test_analyst_llm_custom_url_wired():
    """Kiem tra custom analyst_llm_url duoc intent_router va llm_client truyen dung."""
    import intent_router
    from unittest.mock import patch

    cfg = settings.get()
    cfg["analyst_llm_url"] = "http://192.168.1.99:9999/v1"
    cfg["analyst_llm_model"] = "test-analyst-model"
    cfg["analyst_llm_api_key"] = "sk-analyst-key-456"
    settings.apply(cfg)

    assert intent_router._analyst_url() == "http://192.168.1.99:9999/v1"
    assert intent_router._analyst_api_key() == "sk-analyst-key-456"

    captured = {}
    def fake_chat(sys_p, usr_p, model=None, timeout=None, base_url=None, api_key=None):
        captured["base_url"] = base_url
        captured["model"] = model
        captured["api_key"] = api_key
        return '{"intent": "greeting", "confidence": 0.9}'

    with patch("llm_client.chat", side_effect=fake_chat):
        intent_router.clear_intent_cache()
        res = intent_router.classify_intent("xin chao shop nhe")
        assert res.get("intent") == "greeting"
        assert captured.get("base_url") == "http://192.168.1.99:9999/v1"
        assert captured.get("model") == "test-analyst-model"
        assert captured.get("api_key") == "sk-analyst-key-456"
