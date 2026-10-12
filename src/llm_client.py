import json
import urllib.request
import urllib.error
from src.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


def chat(system: str, user: str, model: str | None = None, timeout: float = 20.0) -> str:
    url = f"{LLM_BASE_URL}/chat/completions"
    payload = {
        "model": model or LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"
    last_err: Exception | None = None
    for _ in range(2):  # retry 1 lan
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
    raise RuntimeError(f"LLM chat failed: {last_err}") from last_err

# ponytail: urllib only, no stream/tools; doi sang requests/openai SDK khi can mock/timeout tinh hon
