import os
from pathlib import Path

def _env_candidates() -> list[Path]:
    """Ung vien file .env: canh .exe truoc (frozen), roi goc repo khi chay source."""
    import sys

    out: list[Path] = []
    if getattr(sys, "frozen", False):
        out.append(Path(sys.executable).resolve().parent / ".env")
    out.append(Path(__file__).resolve().parent.parent / ".env")
    return out


def _load_dotenv():
    # Simple .env loader without external dependencies
    env_path = next((p for p in _env_candidates() if p.is_file()), None)
    if env_path is None:
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass

_load_dotenv()

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://192.168.1.68:20130/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "20"))
ANALYST_LLM_MODEL = os.getenv("ANALYST_LLM_MODEL", "openrouter/typesafe/jev-router")
ANALYST_LLM_TIMEOUT_S = float(os.getenv("ANALYST_LLM_TIMEOUT_S", "12"))
PROMPTS_DIR = os.getenv("PROMPTS_DIR", "prompts")
CONTEXT_DIR = os.getenv("CONTEXT_DIR", "context-data")
CONTEXT_LIVE_DIR = os.getenv("CONTEXT_LIVE_DIR", "context-live")
BATCH_WINDOW_S = float(os.getenv("BATCH_WINDOW_S", "3.0"))
BATCH_MAX_EVENTS = int(os.getenv("BATCH_MAX_EVENTS", "10"))
GREETING_COOLDOWN_S = float(os.getenv("GREETING_COOLDOWN_S", "3.0"))
GREETING_USER_COOLDOWN_S = float(os.getenv("GREETING_USER_COOLDOWN_S", "180.0"))
GREETING_MAX_BATCH = int(os.getenv("GREETING_MAX_BATCH", "5"))
SALES_MAX_WORDS = int(os.getenv("SALES_MAX_WORDS", "75"))
REMIND_ENABLED = os.getenv("REMIND_ENABLED", "true").lower() in ("1", "true", "yes", "on")
REMIND_MIN_S = float(os.getenv("REMIND_MIN_S", "60.0"))
REMIND_MAX_S = float(os.getenv("REMIND_MAX_S", "120.0"))
REMIND_TEXT = os.getenv(
    "REMIND_TEXT",
    "Mọi người xem lai nhớ cho sốp xin một tim và com men sản phẩm cần tư vấn nhé, sốp cảm ơn",
)
# ponytail: minimal config reader; replace with pydantic-settings when validation needed
