"""Regression: thu tu uu tien config phai la DEFAULTS -> config.json -> .env.

Truoc day co 2 nguon song song (module `config` doc .env, settings.py doc
config.json) -> 3 noi gia tri khac nhau, app chay tu Explorer khac app chay
tu terminal. Bay config da duoc don ve 1 nguon trong settings.py.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "src"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import settings  # noqa: E402

# tmp_path khong dung duoc tren may nay (Temp bi chan permission) -> tu tao
# thu muc trong workspace va xoa sau moi test.
_TMP_ROOT = ROOT / "local_cache" / "_tmp_test_config"


def _tmp_dir(name: str) -> Path:
    d = _TMP_ROOT / name
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_dotenv_overrides_config_json(monkeypatch):
    """.env thang config.json (user tu quan ly .env, doi tay nhanh nhat)."""
    cfg_file = _tmp_dir("cfg") / "config.json"
    _write(cfg_file, json.dumps({
        "llm_base_url": "http://json-host:1111/v1",
        "llm_model": "json-model",
    }))
    env_file = _tmp_dir("env") / ".env"
    _write(env_file, "LLM_BASE_URL=http://env-host:2222/v1\nLLM_MODEL=env-model\n")

    monkeypatch.setenv("AUTO_VOICE_CONFIG", str(cfg_file))
    monkeypatch.setattr(settings, "_dotenv_path", lambda: env_file)

    cfg = settings.load()
    assert cfg["llm_base_url"] == "http://env-host:2222/v1"
    assert cfg["llm_model"] == "env-model"


def test_config_json_overrides_defaults(monkeypatch):
    """config.json thang DEFAULTS."""
    cfg_file = _tmp_dir("cfg") / "config.json"
    _write(cfg_file, json.dumps({"llm_model": "json-model"}))
    monkeypatch.setenv("AUTO_VOICE_CONFIG", str(cfg_file))
    monkeypatch.setattr(settings, "_dotenv_path", lambda: None)

    cfg = settings.load()
    assert cfg["llm_model"] == "json-model"
    # Key khong co trong file -> van lay DEFAULT.
    assert cfg["llm_base_url"] == settings.DEFAULTS["llm_base_url"]


def test_load_ignores_os_environment(monkeypatch):
    """os.environ KHONG duoc doc trong load().

    settings.apply() ghi gia tri vao os.environ cho module doc env. Neu load()
    cung doc env thi vong lap gia tri cu se thang file config vua sua -> doi
    config trong GUI khong co hieu luc.
    """
    cfg_file = _tmp_dir("cfg") / "config.json"
    _write(cfg_file, json.dumps({"llm_model": "json-model"}))
    monkeypatch.setenv("AUTO_VOICE_CONFIG", str(cfg_file))
    monkeypatch.setattr(settings, "_dotenv_path", lambda: None)
    monkeypatch.setenv("LLM_MODEL", "env-model-trong-process")

    cfg = settings.load()
    assert cfg["llm_model"] == "json-model"


def test_dotenv_values_are_typed(monkeypatch):
    """.env parse ra dung kieu: bool/int/float theo DEFAULTS."""
    env_file = _tmp_dir("env") / ".env"
    _write(env_file, "\n".join([
        "# comment",
        "LLM_DISABLE_THINKING=false",
        "BATCH_MAX_EVENTS=25",
        "REMIND_MIN_S=45.5",
        "",
    ]))
    monkeypatch.setenv("AUTO_VOICE_CONFIG", str(_tmp_dir("none") / "khong-co.json"))
    monkeypatch.setattr(settings, "_dotenv_path", lambda: env_file)

    cfg = settings.load()
    assert cfg["llm_disable_thinking"] is False
    assert cfg["batch_max_events"] == 25
    assert isinstance(cfg["batch_max_events"], int)
    assert cfg["remind_min_s"] == 45.5
    assert isinstance(cfg["remind_min_s"], float)


def test_dotenv_ignores_unknown_keys(monkeypatch):
    """Key trong .env ma khong co trong DEFAULTS -> bo qua."""
    env_file = _tmp_dir("env") / ".env"
    _write(env_file, "KHONG_CO_TRONG_DEFAULTS=xxx\nLLM_MODEL=env-model\n")
    monkeypatch.setenv("AUTO_VOICE_CONFIG", str(_tmp_dir("none") / "khong-co.json"))
    monkeypatch.setattr(settings, "_dotenv_path", lambda: env_file)

    cfg = settings.load()
    assert "KHONG_CO_TRONG_DEFAULTS" not in cfg
    assert cfg["llm_model"] == "env-model"


def test_save_keeps_dotenv_override(monkeypatch):
    """save() khong lam mat gia tri .env (cache phai theo dung thu tu uu tien)."""
    env_file = _tmp_dir("env") / ".env"
    _write(env_file, "LLM_MODEL=env-model\n")
    cfg_file = _tmp_dir("cfg") / "config.json"
    monkeypatch.setenv("AUTO_VOICE_CONFIG", str(cfg_file))
    monkeypatch.setattr(settings, "_dotenv_path", lambda: env_file)

    settings.save({"llm_model": "saved-model", "llm_base_url": "http://x/v1"})
    cfg = settings.get()
    assert cfg["llm_model"] == "env-model", ".env van phai thang sau khi save()"
    assert cfg["llm_base_url"] == "http://x/v1"


def test_module_config_removed():
    """Module `src/config.py` da bi xoa - chi con settings.py la nguon config."""
    assert not (ROOT / "src" / "config.py").exists()


def test_llm_client_reads_settings_not_config_module():
    """llm_client phai doc settings.get(), khong con import module config."""
    import inspect

    import llm_client

    src = inspect.getsource(llm_client)
    assert "import src.config" not in src
    assert "import config as c" not in src
    assert "_llm_cfg()" in src


def test_os_environ_not_sourced_into_config(monkeypatch):
    """settings.load() khong lay gia tri tu os.environ."""
    monkeypatch.setenv("LLM_MODEL", "env-only-model")
    monkeypatch.setattr(settings, "_dotenv_path", lambda: None)
    monkeypatch.setenv("AUTO_VOICE_CONFIG", str(Path(os.devnull)))
    cfg = settings.load()
    assert cfg["llm_model"] != "env-only-model"
