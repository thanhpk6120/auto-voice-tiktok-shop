import json
import urllib.request
import urllib.error

# (cac shape tat thinking dinh nghia tai _THINKING_SHAPES)

# Cache: model -> chi so payload dung duoc (None = khong co payload nao chat).
_thinking_cache: dict[str, int | None] = {}


def _parse_response(raw: str) -> dict:
    """Parse body LLM. Server that tra SSE: 1 JSON object day du + 'data: [DONE]'.

    json.loads() se vỡ ("Extra data") -> dung raw_decode de lay object dau tien.
    Server co the bo tien to 'data: ' truoc moi chunk -> tach chunk ra roi parse.
    """
    text = (raw or "").lstrip()
    if not text:
        raise ValueError("empty LLM response")

    # Case 1: body bat dau bang JSON object (ke ca khi kem 'data: [DONE]' phia sau).
    start = text.find("{")
    if start >= 0:
        try:
            obj, _end = json.JSONDecoder().raw_decode(text[start:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # Case 2: SSE nhieu chunk 'data: {...}' -> lay chunk cuoi co message.content.
    chunks: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            chunks.append(obj)
    if not chunks:
        raise ValueError("khong doc duoc JSON tu body LLM")
    for ch in reversed(chunks):
        try:
            if (ch["choices"][0].get("message") or {}).get("content"):
                return ch
        except (KeyError, IndexError, TypeError):
            continue
    return chunks[-1]


def _extract_content(body: dict) -> str:
    """Lay noi dung text tu response. Ho tro ca chat.completion va stream chunk."""
    try:
        choice = body["choices"][0]
    except (KeyError, IndexError, TypeError):
        raise ValueError("LLM response khong co choices")
    msg = choice.get("message") or {}
    content = msg.get("content")
    if content is None:
        # Stream delta: gop cac delta.content
        delta = choice.get("delta") or {}
        content = delta.get("content")
    return content or ""

def _thinking_index(model: str) -> int | None:
    """Chi so payload tat thinking da bi server chap nhan cho model nay (None = chua biet)."""
    return _thinking_cache.get(model)


# Cache: model -> co the tat thinking khong? (doc tu /v1/models cua server).
_model_meta: dict[str, dict] = {}
_model_meta_loaded = False


def _load_model_meta() -> dict[str, dict]:
    """Doc danh sach model tu server, lay 'thinkingCanDisable' + 'thinkingFormat'.

    Server that (192.168.1.68) tra metadata: model nao tat duoc thinking, va
    backend dung ten tham so gi. Dung de chon payload tat thinking ngay tu dau,
    tranh 1-2 request 400 thu lai.
    """
    global _model_meta_loaded
    if _model_meta_loaded:
        return _model_meta
    _model_meta_loaded = True
    try:  # chay tu goc repo (app.py them goc repo vao sys.path)
        import src.config as c
    except ImportError:
        import config as c  # type: ignore[no-redef]
    try:
        req = urllib.request.Request(
            f"{c.LLM_BASE_URL}/models",
            headers={"Content-Type": "application/json",
                     **({"Authorization": f"Bearer {c.LLM_API_KEY}"} if c.LLM_API_KEY else {})},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        for m in data.get("data") or []:
            mid = str(m.get("id") or "")
            if mid:
                _model_meta[mid] = m.get("capabilities") or {}
    except Exception:
        pass
    return _model_meta


# Cac tham so tat thinking, thu theo thu tu.
# Do duoc tren server that (2026-10): voi model dang dung,
#   {"thinking": {"type": "disabled"}}  -> nhanh nhat + chat luong tot nhat
#   {"reasoning_effort": "none"}       -> cham hon, it reasoning hon
# Server tra 400 neu khong chap nhan ten tham so -> tu thu shape tiep theo
# va cache shape da duoc chap nhan theo model id.
_THINKING_SHAPES: list[dict] = [
    {"thinking": {"type": "disabled"}},
    {"reasoning_effort": "none"},
]


def _preferred_payloads(model: str) -> list[dict]:
    """Thu tu payload tat thinking cho model nay (doc tu metadata server)."""
    meta = _load_model_meta().get(model) or {}
    if meta.get("thinkingCanDisable") is False:
        # Server noi ro model nay khong tat duoc thinking -> khong phai gay loi 400.
        return []
    return list(_THINKING_SHAPES)



def chat(system: str, user: str, model: str | None = None, timeout: float | None = None) -> str:
    # Doc dong tu config: settings.apply() doi key/url/model co tac dung ngay.
    try:  # chay tu goc repo (app.py them goc repo vao sys.path)
        import src.config as c
    except ImportError:  # frozen/onedir: chi con package phang `config`
        import config as c  # type: ignore[no-redef]

    timeout = float(getattr(c, "LLM_TIMEOUT_S", 20.0)) if timeout is None else timeout
    url = f"{c.LLM_BASE_URL}/chat/completions"
    model_name = model or c.LLM_MODEL
    base_payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {"Content-Type": "application/json"}
    if c.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {c.LLM_API_KEY}"

    # Tay thinking: server that ho tro, tat duoc -> nhanh hon nhieu.
    # Do duoc tren server that cua user: reasoning tokens 302 -> 0,
    # latency median 7056ms -> 4026ms, chat luong giong het (38 vs 37 tu).
    # Ten tham so khac nhau theo backend -> lay 'thinkingFormat' tu /v1/models
    # de chon dung thu tu, tranh request 400 thu lai.
    disable_thinking = bool(getattr(c, "LLM_DISABLE_THINKING", True))
    variants = _preferred_payloads(model_name) if disable_thinking else []
    if model_name in _thinking_cache:
        idx = _thinking_cache[model_name]
        if idx is None:
            disable_thinking = False
            variants = []
    else:
        # Chua biet server chap nhan tham so nao -> thu tu theo metadata.
        idx = 0

    last_err: Exception | None = None
    attempts = 0
    while attempts < 5:
        attempts += 1
        payload = dict(base_payload)
        if disable_thinking and variants and 0 <= idx < len(variants):
            payload.update(variants[idx])
        data = json.dumps(payload).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = _parse_response(resp.read().decode("utf-8", "replace"))
            if disable_thinking and variants and 0 <= idx < len(variants):
                _thinking_cache[model_name] = idx
            return _extract_content(body)
        except urllib.error.HTTPError as e:
            last_err = e
            # Server tra 400/422: thu tham so tat thinking tiep theo truoc khi bo cua.
            if e.code in (400, 422) and disable_thinking and variants:
                nxt = idx + 1
                if nxt < len(variants):
                    idx = nxt
                    continue
                # Het tham so -> server khong chap nhan gi -> danh dau va goi lai khong co.
                _thinking_cache[model_name] = None
                disable_thinking = False
                variants = []
                continue
            # Loi client khac (401, 403, 404): fail ngay, khong retry vo ich.
            if e.code < 500 and e.code != 429:
                raise RuntimeError(f"LLM chat failed: {e}") from e
        except Exception as e:
            last_err = e
    raise RuntimeError(f"LLM chat failed: {last_err}") from last_err


def decide(model: str, state: str, questions: dict, timeout: float | None = None) -> dict:
    """Goi endpoint '/systemone' (decision model) -> tra 'answers'.

    Decision model khong dung duoc voi /chat/completions. Payload:
    {"model": ..., "state": "<text>", "questions": {"ten": {...type: noul|choice...}}}
    """
    try:  # chay tu goc repo (app.py them goc repo vao sys.path)
        import src.config as c
    except ImportError:  # frozen/onedir: chi con package phang `config`
        import config as c  # type: ignore[no-redef]

    timeout = float(getattr(c, "LLM_TIMEOUT_S", 20.0)) if timeout is None else timeout
    base = str(c.LLM_BASE_URL).rstrip("/")
    payload = {"model": model, "state": state, "questions": questions}
    headers = {"Content-Type": "application/json"}
    if c.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {c.LLM_API_KEY}"
    req = urllib.request.Request(
        f"{base}/systemone", data=json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8", "replace"))
    return body.get("answers") or {}

# ponytail: urllib only, no stream/tools; doi sang requests/openai SDK khi can mock/timeout tinh hon
