"""Cau hinh tap trung cho app (doc/ghi JSON, ap dung runtime vao cac module).

Thu tu uu tien khi lay gia tri:
  1. File config JSON (AUTO_VOICE_CONFIG env hoac %APPDATA%/AutoVoiceTikTokShop/config.json)
  2. Bien moi truong (.env / os.environ) - chi khi config file khong co key do
  3. DEFAULTS

API:
  config_path() -> Path          duong dan file config dang dung
  load() -> dict                 doc config (da merge defaults + env)
  save(cfg) -> Path              ghi config ra dia, tra ve duong dan
  get() -> dict                  ban sao config da cache trong process
  apply(cfg=None) -> dict        ap cau hinh vao cac module runtime (tts_client, event_bridge, config)
  reset() -> dict                xoa cache, doc lai tu dia

Config luu o %APPDATA% (khong phai thu muc app) de app chay duoc tren may khac,
ke ca khi dat trong Program Files (khong ghi duoc).
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

APP_DIR_NAME = "AutoVoiceTikTokShop"
CONFIG_FILE_NAME = "config.json"

DEFAULTS: dict = {
    # LLM (OpenAI-compatible)
    "llm_base_url": "http://192.168.1.68:20130/v1",
    "llm_api_key": "",
    "llm_model": "claude-sonnet-5",
    "llm_timeout_s": 20,
    # VoiceStudio TTS
    "voicestudio_url": "http://127.0.0.1:3900",
    "voicestudio_voice": "alloy",
    "voicestudio_model": "tts-1",
    "tts_timeout_s": 300,
    # Event bridge WebSocket
    "bridge_url": "ws://127.0.0.1:8765/ws?role=app",
    "bridge_port": 8765,
    # Audio
    "audio_device": "",
    "no_play": False,
    "interrupt_mode": "finish",
    # Analyzer
    "prompts_dir": "prompts",
    "context_dir": "context-data",
    "batch_window_s": 5.0,
    "batch_max_events": 10,
    "out_dir": "out",
    "greeting_cooldown_s": 3.0,
    "greeting_max_batch": 5,
    "sales_max_words": 35,
    "gologin_dir": "gologin-basic-offline",
    "gologin_profiles_dir": "",
    "gologin_active_version": "",
    "gologin_profile_id": "",
    "browser_mode": "gologin_cdp",
    # UI
    "log_level": "INFO",
}

# Cac key duoc phep sua qua GUI. Nhom lai de GUI render theo section.
SECTIONS: dict = {
    "LLM": ["llm_base_url", "llm_api_key", "llm_model", "llm_timeout_s"],
    "VoiceStudio TTS": [
        "voicestudio_url",
        "voicestudio_voice",
        "voicestudio_model",
        "tts_timeout_s",
    ],
    "Event Bridge": ["bridge_url", "bridge_port"],
    "Audio & Analyzer": [
        "prompts_dir",
        "context_dir",
        "batch_window_s",
        "batch_max_events",
        "audio_device",
        "no_play",
        "interrupt_mode",
        "out_dir",
        "greeting_cooldown_s",
        "greeting_max_batch",
        "sales_max_words",
    ],
    "Trình duyệt / GoLogin": [
        "gologin_dir",
        "gologin_profiles_dir",
        "gologin_active_version",
        "gologin_profile_id",
        "browser_mode",
    ],
    "Khac": ["log_level"],
}

# Key bi mat - GUI hien thi dang che.
SECRET_KEYS = {"llm_api_key"}

_cache: dict | None = None


def _project_root() -> Path:
    """Thu muc goc: canh .exe khi da dong goi, hoac goc repo khi chay source.

    Day la thu muc GHI duoc (config/out/log do nguoi dung tao ra).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    """Thu muc data read-only di kem build.

    Frozen onedir: sys._MEIPASS tro vao _internal/ (chua context-data/, ui/).
    Chay source: goc repo.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass and Path(meipass).is_dir():
        return Path(meipass)
    return _project_root()


def resolve_path(path: "str | Path") -> Path:
    """Doi duong dan tuong doi thanh tuyet doi theo thu tu: canh .exe -> _MEIPASS -> goc repo.

    Uu tien canh .exe de nguoi dung co the sua context-data/*.md ngay trong dist.
    """
    p = Path(path)
    if p.is_absolute():
        return p
    cand = _project_root() / p
    if cand.exists():
        return cand
    alt = data_root() / p
    return alt if alt.exists() else cand


def config_path() -> Path:
    env = os.getenv("AUTO_VOICE_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    base = os.getenv("APPDATA") or os.getenv("XDG_CONFIG_HOME")
    if base:
        return Path(base) / APP_DIR_NAME / CONFIG_FILE_NAME
    return Path.home() / f".{APP_DIR_NAME.lower()}" / CONFIG_FILE_NAME


def _env_overrides() -> dict:
    """Doc bien moi truong theo ten key (vd LLM_BASE_URL -> llm_base_url)."""
    out = {}
    for key in DEFAULTS:
        env_val = os.getenv(key.upper())
        if env_val is None or env_val == "":
            continue
        default = DEFAULTS[key]
        try:
            if isinstance(default, bool):
                out[key] = env_val.strip().lower() in ("1", "true", "yes", "on")
            elif isinstance(default, int) and not isinstance(default, bool):
                out[key] = int(float(env_val))
            elif isinstance(default, float):
                out[key] = float(env_val)
            else:
                out[key] = env_val
        except (TypeError, ValueError):
            continue
    return out


def load(use_cache: bool = False) -> dict:
    """Doc config tu file, merge DEFAULTS + env. Khong nem loi neu file hong."""
    global _cache
    if use_cache and _cache is not None:
        return dict(_cache)

    cfg = dict(DEFAULTS)
    cfg.update(_env_overrides())

    path = config_path()
    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if v is not None})
        except Exception as e:  # file hong / khong doc duoc -> dung defaults
            print(f"[settings] khong doc duoc {path}: {e}", file=sys.stderr)

    _cache = dict(cfg)
    return dict(cfg)


def save(cfg: dict) -> Path:
    """Ghi config ra dia (chi ghi cac key da biet). Tra ve duong dan."""
    global _cache
    clean = {k: cfg[k] for k in DEFAULTS if k in cfg}
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    _cache = dict(DEFAULTS)
    _cache.update(clean)
    return path


def get() -> dict:
    return load(use_cache=True)


def reset() -> dict:
    global _cache
    _cache = None
    return load()


def _bridge_port_from_url(url: str, fallback: int) -> int:
    try:
        rest = url.split("://", 1)[1]
        hostpart = rest.split("/", 1)[0]
        if ":" in hostpart:
            return int(hostpart.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        pass
    return fallback


def apply(cfg: dict | None = None) -> dict:
    """Ap cau hinh vao cac module runtime. An toan neu module chua import duoc."""
    cfg = dict(cfg) if cfg is not None else get()

    # tts_client
    try:
        import tts_client  # type: ignore

        tts_client.VOICE_URL = str(cfg["voicestudio_url"]).rstrip("/")
        tts_client.VOICE_NAME = str(cfg["voicestudio_voice"])
        tts_client.VOICE_MODEL = str(cfg["voicestudio_model"])
        tts_client.TTS_TIMEOUT = float(cfg["tts_timeout_s"])
        if hasattr(tts_client, "OUT_DIR"):
            tts_client.OUT_DIR = str(cfg["out_dir"])
    except Exception:
        pass

    # event_bridge
    try:
        import event_bridge  # type: ignore

        event_bridge.DEFAULT_BRIDGE_URL = str(cfg["bridge_url"])
        event_bridge.DEFAULT_PORT = _bridge_port_from_url(
            str(cfg["bridge_url"]), int(cfg["bridge_port"])
        )
    except Exception:
        pass

    # llm config: llm_client doc `src.config`, app.py co the import `config`.
    # Hai ten nay la hai module object khac nhau -> phai set CA HAI.
    for _name in ("src.config", "config"):
        try:
            _mod = importlib.import_module(_name)
            _mod.LLM_BASE_URL = str(cfg["llm_base_url"]).rstrip("/")
            _mod.LLM_MODEL = str(cfg["llm_model"])
            _mod.LLM_API_KEY = str(cfg["llm_api_key"])
            _mod.LLM_TIMEOUT_S = float(cfg["llm_timeout_s"])
            _mod.PROMPTS_DIR = str(cfg.get("prompts_dir", "prompts"))
            _mod.CONTEXT_DIR = str(cfg.get("context_dir", "context-data"))
            _mod.BATCH_WINDOW_S = float(cfg.get("batch_window_s", 5.0))
            _mod.BATCH_MAX_EVENTS = int(cfg.get("batch_max_events", 10))
        except Exception:
            pass

    # audio_player doc os.environ moi lan phat -> set env la du (process moi thua huong)
    os.environ["AUDIO_OUTPUT_DEVICE"] = str(cfg["audio_device"])
    os.environ["INTERRUPT_MODE"] = str(cfg.get("interrupt_mode", "finish"))
    # analyzer
    try:
        import event_analyzer  # type: ignore

        event_analyzer.configure(
            prompts_dir=cfg.get("prompts_dir", "prompts"),
            context_dir=cfg.get("context_dir", "context-data"),
            cooldown=float(cfg["greeting_cooldown_s"]),
            max_batch=int(cfg["greeting_max_batch"]),
            max_words=int(cfg["sales_max_words"]),
        )
    except Exception:
        pass
    # browser & gologin env
    os.environ["GOLOGIN_DIR"] = str(cfg.get("gologin_dir", "gologin-basic-offline"))
    os.environ["GOLOGIN_PROFILES_DIR"] = str(cfg.get("gologin_profiles_dir", ""))
    os.environ["GOLOGIN_ACTIVE_VERSION"] = str(cfg.get("gologin_active_version", ""))
    os.environ["GOLOGIN_PROFILE_ID"] = str(cfg.get("gologin_profile_id", ""))
    os.environ["BROWSER_MODE"] = str(cfg.get("browser_mode", "gologin_cdp"))
    os.environ["PROMPTS_DIR"] = str(cfg.get("prompts_dir", "prompts"))
    os.environ["CONTEXT_DIR"] = str(cfg.get("context_dir", "context-data"))
    os.environ["BATCH_WINDOW_S"] = str(cfg.get("batch_window_s", 5.0))
    os.environ["BATCH_MAX_EVENTS"] = str(cfg.get("batch_max_events", 10))

    return cfg


def masked(cfg: dict | None = None) -> dict:
    """Ban sao config da che cac key bi mat (dung de in log / hien GUI)."""
    cfg = dict(cfg) if cfg is not None else get()
    for k in SECRET_KEYS:
        v = str(cfg.get(k) or "")
        cfg[k] = (v[:6] + "***" + v[-4:]) if len(v) > 12 else ("***" if v else "")
    return cfg


if __name__ == "__main__":  # chan doan nhanh: python src/settings.py
    _p = config_path()
    print(f"config_path = {_p}")
    print(f"ton tai      = {_p.is_file()}")
    print(json.dumps(masked(), ensure_ascii=False, indent=2))
