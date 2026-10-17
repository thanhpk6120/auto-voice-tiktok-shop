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

# ponytail: minimal config reader; replace with pydantic-settings when validation needed
