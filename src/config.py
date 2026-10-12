import os
from pathlib import Path

def _load_dotenv():
    # Simple .env loader without external dependencies
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
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

# ponytail: minimal config reader; replace with pydantic-settings when validation needed
