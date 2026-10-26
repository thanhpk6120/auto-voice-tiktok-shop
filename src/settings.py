"""Cau hinh tap trung cho app (doc/ghi JSON, ap dung runtime vao cac module).

Thu tu uu tien khi lay gia tri (thap -> cao):
  1. DEFAULTS trong file nay
  2. File config JSON (AUTO_VOICE_CONFIG env hoac %APPDATA%/AutoVoiceTikTokShop/config.json)
  3. File .env (canh .exe hoac goc repo) - CHI secret (llm_api_key)

  .env chi thang cho secret: neu no thang cao hon config.json cho TAT CA key,
  moi thay doi trong GUI se bi .env che ngay -> vo hieu.
  KHONG doc os.environ trong load(): apply() ghi gia tri vao os.environ cho module
  doc env, neu load() cung doc env thi vong lap gia tri cu se thang file config.
  Muon tro sang file config khac: dat bien moi truong AUTO_VOICE_CONFIG.

API:
  config_path() -> Path          duong dan file config dang dung
  load() -> dict                 doc config (da merge defaults + json + .env secret)
  get() -> dict                  ban sao config da cache trong process
  apply(cfg=None) -> dict        ap cau hinh vao cac module runtime (tts_client, event_bridge, os.environ)
  reset() -> dict                xoa cache, doc lai tu dia

Config luu o %APPDATA% (khong phai thu muc app) de app chay duoc tren may khac,
ke ca khi dat trong Program Files (khong ghi duoc).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_DIR_NAME = "AutoVoiceTikTokShop"
CONFIG_FILE_NAME = "config.json"

DEFAULTS: dict = {
    # LLM (OpenAI-compatible)
    "llm_base_url": "http://192.168.1.68:20128/v1",
    "llm_api_key": "",
    "llm_model": "claude-opus-5",
    "llm_timeout_s": 20,
    # Tat thinking cua model khi server ho tro -> LLM tra loi nhanh hon nhieu.
    "llm_disable_thinking": True,
    # Model AI chuyên phân tích bình luận/hoạt động để chọn đúng loại prompt.
    # Để trống "" = tắt phân tích bằng AI, dùng luật từ khoá dự phòng.
    "analyst_llm_model": "openrouter/typesafe/jev-1.13",
    "analyst_llm_timeout_s": 12,
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
    "context_live_dir": "context-live",
    "batch_window_s": 3.0,
    "batch_max_events": 10,
    "out_dir": "out",
    "greeting_cooldown_s": 3.0,
    "greeting_user_cooldown_s": 180.0,
    "greeting_max_batch": 5,
    "sales_max_words": 75,
    "remind_enabled": True,
    "remind_min_s": 60.0,
    "remind_max_s": 120.0,
    "remind_text": "Mọi người xem lai nhớ cho sốp xin một tim và com men sản phẩm cần tư vấn nhé, sốp cảm ơn",
    "gologin_dir": "gologin-basic-offline",
    "gologin_profiles_dir": "",
    "gologin_active_version": "",
    "gologin_profile_id": "",
    "browser_mode": "gologin_cdp",
    # Nho luong hoi thoai khach hang (phut)
    "chat_history_ttl_minutes": 10.0,
    # UI
    "log_level": "INFO",
}

# Cac key duoc phep sua qua GUI. Nhom lai de GUI render theo section.
SECTIONS: dict = {
    "LLM": [
        "llm_base_url",
        "llm_api_key",
        "llm_model",
        "llm_timeout_s",
        "llm_disable_thinking",
        "analyst_llm_model",
        "analyst_llm_timeout_s",
    ],
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
        "context_live_dir",
        "batch_window_s",
        "batch_max_events",
        "audio_device",
        "no_play",
        "interrupt_mode",
        "sales_max_words",
        "remind_enabled",
        "remind_min_s",
        "remind_max_s",
        "remind_text",
        "out_dir",
        "greeting_cooldown_s",
        "greeting_user_cooldown_s",
        "greeting_max_batch",
        "chat_history_ttl_minutes",
    ],
    "Trình duyệt / GoLogin": [
        "gologin_dir",
        "gologin_profiles_dir",
        "gologin_active_version",
        "gologin_profile_id",
        "browser_mode",
    ],
    "Khác": ["log_level"],
}

# Key bi mat - GUI hien thi dang che.
SECRET_KEYS = {"llm_api_key"}

_cache: dict | None = None

# Cac lua chon san cho cac truong dropdown
FIELD_OPTIONS: dict[str, list[str]] = {
    "interrupt_mode": ["finish", "interrupt"],
    "browser_mode": ["gologin_cdp", "extension"],
    "log_level": ["INFO", "DEBUG", "WARNING", "ERROR"],
    "voicestudio_model": ["tts-1", "tts-1-hd"],
    # Chi la mac dinh tinh: GUI thay bang danh sach dong tu VoiceStudio (ke ca giong da clone).
    "voicestudio_voice": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
}

# Giai thich chi tiet / chu thich tooltip cho tung bien cau hinh
FIELD_DOCS: dict[str, str] = {
    "llm_base_url": "Địa chỉ API LLM tương thích chuẩn OpenAI (ví dụ: http://192.168.1.68:20130/v1 hoặc http://localhost:11434/v1).",
    "llm_api_key": "API Key để xác thực với server LLM (nếu server local không cần key thì để trống).",
    "llm_model": "Tên model LLM sinh lời thoại (ví dụ: claude-sonnet-5, gpt-4o-mini, qwen2.5-7b).",
    "llm_timeout_s": "Thời gian chờ tối đa (giây) cho mỗi yêu cầu gọi LLM trước khi tự động fallback.",
    "analyst_llm_model": "Model AI chuyên PHÂN TÍCH bình luận/hoạt động để biết khách đang chào hỏi, hỏi sản phẩm, chốt đơn hay tặng quà, từ đó chọn đúng loại prompt. Ví dụ: openrouter/typesafe/jev-router. Bấm nút 'Tải danh sách model' ở tab Quản lý Prompt để chọn từ danh sách thật của server. Để trống để tắt phân tích bằng AI và dùng luật từ khoá dự phòng.",
    "analyst_llm_timeout_s": "Thời gian chờ tối đa (giây) cho bước phân tích ý định. Nếu quá hạn sẽ tự động dùng luật từ khoá dự phòng.",
    "llm_disable_thinking": "Tắt chế độ suy luận (thinking) của model LLM khi server hỗ trợ — câu trả lời ra nhanh hơn, chất lượng câu không đổi. Tắt nếu server báo lỗi 400 khi thấy tham số 'thinking'.",
    "voicestudio_url": "Địa chỉ VoiceStudio Local API (mặc định: http://127.0.0.1:3900).",
    "voicestudio_voice": "Giọng đọc. Danh sách lấy trực tiếp từ VoiceStudio: alias OpenAI (alloy, echo...) và các giọng bạn đã clone. Với giọng clone, chọn mục có dạng 'Tên  <voice_id>'.",
    "voicestudio_model": "Model TTS trong VoiceStudio (tts-1 tốc độ nhanh hoặc tts-1-hd chất lượng cao).",
    "tts_timeout_s": "Thời gian chờ tối đa (giây) cho quá trình tạo file âm thanh từ text.",
    "bridge_url": "Địa chỉ WebSocket bridge nhận sự kiện từ Chrome Extension (ws://127.0.0.1:8765/ws?role=app).",
    "bridge_port": "Cổng mạng để khởi chạy WebSocket server tiếp nhận event từ extension.",
    "prompts_dir": "Thư mục chứa các file prompt .md (system_greeting.md, system_sales.md, system_order.md, system_gift.md, system_chat.md, system_batch.md, system_analyzer.md). Sửa được ngay trong tab Quản lý Prompt.",
    "context_dir": "Thư mục chứa các file thông tin sản phẩm mẫu .md để AI học và tư vấn bán hàng.",
    "context_live_dir": "Thư mục lưu context sản phẩm lấy trực tiếp từ trình duyệt (tên, mô tả, 10 đánh giá đầu tiên) qua nút 'Load context-live'.",
    "batch_window_s": "Thời gian cửa sổ gom sự kiện (giây, mặc định 5.0s). Sự kiện ưu tiên cao sẽ được tạo voice ngay.",
    "batch_max_events": "Số lượng sự kiện tối đa được xử lý trong 1 batch để tránh quá tải bộ nhớ.",
    "audio_device": "Thiết bị âm thanh đầu ra để phát voice (Loa máy tính hoặc CABLE Input để đưa vào OBS).",
    "no_play": "Chế độ chạy thử nghiệm: sinh text và audio đầy đủ nhưng không phát ra loa.",
    "interrupt_mode": "Chính sách ngắt: 'finish' (đọc trọn vẹn câu hiện tại rồi mới đọc câu tiếp); 'interrupt' (ngắt ngay khi có đơn hàng/quà).",
    "sales_max_words": "Độ dài tối đa của câu tư vấn sản phẩm (50-100 từ) giúp câu trả lời đầy đủ thông tin chi tiết.",
    "remind_enabled": "Bật/Tắt tính năng đọc định kỳ câu nhắc người xem thả tim và bình luận.",
    "remind_min_s": "Thời gian ngẫu nhiên tối thiểu (giây) giữa 2 lần đọc câu nhắc tương tác.",
    "greeting_user_cooldown_s": "Thời gian không chào lại cùng một người xem (giây, mặc định 180s = 3 phút), tránh bị đọc lặp lại tên người xem nhiều lần.",
    "chat_history_ttl_minutes": "Thời gian (phút) lưu giữ lịch sử hội thoại của mỗi khách hàng (mặc định 10 phút), hết hạn sẽ tự động xoá ngữ cảnh.",
    "remind_max_s": "Thời gian ngẫu nhiên tối đa (giây) giữa 2 lần đọc câu nhắc tương tác.",
    "remind_text": "Nội dung câu thoại nhắc nhở khán giả thả tim và tương tác trên live.",
    "out_dir": "Thư mục lưu trữ các file âm thanh .wav được tạo ra.",
    "greeting_cooldown_s": "Thời gian cooldown (giây) giữa các lần chào hỏi người xem mới vào phòng.",
    "greeting_max_batch": "Số người vào phòng tối đa được gom chung trong 1 câu chào.",
    "gologin_dir": "Đường dẫn thư mục chứa phần mềm GoLogin offline trên máy.",
    "gologin_profiles_dir": "Đường dẫn thư mục lưu các profile trình duyệt GoLogin.",
    "gologin_active_version": "Phiên bản Chrome/Orbita đang được chọn để khởi chạy trình duyệt.",
    "gologin_profile_id": "ID profile GoLogin được chọn để tự động đăng nhập TikTok Shop live.",
    "browser_mode": "Chế độ trình duyệt: 'gologin_cdp' (trực tiếp qua CDP debug) hoặc 'extension' (qua Chrome Extension).",
    "log_level": "Mức độ chi tiết ghi log của hệ thống: INFO, DEBUG, WARNING, ERROR.",
}


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


def _dotenv_path() -> Path | None:
    """File .env canh .exe truoc (frozen), roi goc repo khi chay source."""
    cands: list[Path] = []
    if getattr(sys, "frozen", False):
        cands.append(Path(sys.executable).resolve().parent / ".env")
    cands.append(Path(__file__).resolve().parent.parent / ".env")
    return next((p for p in cands if p.is_file()), None)


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse file .env (KEY=VALUE moi dong) -> dict. Khong nem loi."""
    out: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k:
                out[k] = v
    except Exception:
        pass
    return out


def _coerce(key: str, raw: str):
    """Chuyen gia tri chuoi (tu .env / os.environ) sang dung kieu cua DEFAULTS."""
    default = DEFAULTS.get(key)
    try:
        if isinstance(default, bool):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(default, int) and not isinstance(default, bool):
            return int(float(raw))
        if isinstance(default, float):
            return float(raw)
    except (TypeError, ValueError):
        return raw
    return raw


def _overrides_from(source: dict[str, str], only: set[str] | None = None) -> dict:
    """Lay cac key co trong `source` (ten UPPER) roi chuyen kieu theo DEFAULTS.

    `only` = chi lay cac key nay (vd SECRET_KEYS). None = lay tat ca.
    """
    out: dict = {}
    for key in DEFAULTS:
        if only is not None and key not in only:
            continue
        env_val = source.get(key.upper())
        if env_val is None or env_val == "":
            continue
        out[key] = _coerce(key, env_val)
    return out


def _env_overrides() -> dict:
    """Bien moi truong (os.environ) -> override. Dat trong process nen thang cao nhat."""
    return _overrides_from(dict(os.environ))


def _dotenv_overrides(only: set[str] | None = None) -> dict:
    """File .env -> override.

    Mac dinh CHI lay secret (llm_api_key): .env ton tai de giu key khoi %APPDATA%
    va de chinh nhanh tay. Neu .env thang cao hon config.json cho TAT CA key,
    moi thay doi trong GUI se bi .env che ngay lap tuc -> vo hieu.
    """
    path = _dotenv_path()
    if path is None:
        return {}
    return _overrides_from(_parse_env_file(path), only if only is not None else SECRET_KEYS)


def load(use_cache: bool = False) -> dict:
    """Doc config, merge DEFAULTS -> config.json -> .env (secret).

    Khong nem loi neu file hong.

    KHONG doc os.environ: settings.apply() ghi gia tri vao os.environ cho module
    doc env, neu load() cung doc env thi vong lap gia tri cu se thang file config
    (doi config trong GUI khong co hieu luc). Bien moi truong chi dung qua
    AUTO_VOICE_CONFIG de tro sang file config khac.
    """
    global _cache
    if use_cache and _cache is not None:
        return dict(_cache)

    cfg = dict(DEFAULTS)

    # 1) File config JSON (GUI ghi, user sua tay) - thang .env cho key thuong.
    path = config_path()
    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if v is not None and k in DEFAULTS})
        except Exception as e:  # file hong / khong doc duoc -> dung tiep
            print(f"[settings] không đọc được {path}: {e}", file=sys.stderr)

    # 2) File .env - CHI secret (llm_api_key). Secret thuong o file rieng de
    # khong lo key vao %APPDATA%; cac key khac do GUI/config.json quyet dinh.
    # Dat sau config.json de secret trong .env thang ban cu trong config.json.
    cfg.update(_dotenv_overrides(SECRET_KEYS))

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
    # Cache phai phan anh thu tu uu tien sau khi ghi: DEFAULTS -> file -> .env(secret)
    cached = dict(DEFAULTS)
    cached.update(clean)
    cached.update(_dotenv_overrides(SECRET_KEYS))
    _cache = cached
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
    merged = dict(DEFAULTS)
    if cfg is not None:
        merged.update(cfg)
    else:
        merged.update(get())
    cfg = merged
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

    # LLM: gia tri cuoi cung -> os.environ (llm_client doc settings.get() truc tiep,
    # env chi de module khac doc, va de process con (app) co cung gia tri).
    os.environ["LLM_BASE_URL"] = str(cfg["llm_base_url"]).rstrip("/")
    os.environ["LLM_MODEL"] = str(cfg["llm_model"])
    os.environ["LLM_API_KEY"] = str(cfg["llm_api_key"])
    os.environ["LLM_TIMEOUT_S"] = str(float(cfg["llm_timeout_s"]))
    os.environ["LLM_DISABLE_THINKING"] = "1" if cfg.get("llm_disable_thinking", True) else "0"
    os.environ["ANALYST_LLM_MODEL"] = str(cfg.get("analyst_llm_model", ""))
    os.environ["ANALYST_LLM_TIMEOUT_S"] = str(float(cfg.get("analyst_llm_timeout_s", 12)))
    os.environ["PROMPTS_DIR"] = str(cfg.get("prompts_dir", "prompts"))
    os.environ["CONTEXT_DIR"] = str(cfg.get("context_dir", "context-data"))
    os.environ["CONTEXT_LIVE_DIR"] = str(cfg.get("context_live_dir", "context-live"))
    os.environ["BATCH_WINDOW_S"] = str(float(cfg.get("batch_window_s", 3.0)))
    os.environ["BATCH_MAX_EVENTS"] = str(int(cfg.get("batch_max_events", 10)))
    os.environ["GREETING_COOLDOWN_S"] = str(float(cfg.get("greeting_cooldown_s", 3.0)))
    os.environ["GREETING_USER_COOLDOWN_S"] = str(float(cfg.get("greeting_user_cooldown_s", 180.0)))
    os.environ["GREETING_MAX_BATCH"] = str(int(cfg.get("greeting_max_batch", 5)))
    os.environ["CHAT_HISTORY_TTL_MINUTES"] = str(float(cfg.get("chat_history_ttl_minutes", 10.0)))
    os.environ["SALES_MAX_WORDS"] = str(int(cfg.get("sales_max_words", 75)))
    os.environ["REMIND_ENABLED"] = "true" if cfg.get("remind_enabled", True) else "false"
    os.environ["REMIND_MIN_S"] = str(float(cfg.get("remind_min_s", 60.0)))
    os.environ["REMIND_MAX_S"] = str(float(cfg.get("remind_max_s", 120.0)))
    os.environ["REMIND_TEXT"] = str(cfg.get("remind_text", ""))

    # audio_player doc os.environ moi lan phat -> set env la du (process moi thua huong)
    os.environ["AUDIO_OUTPUT_DEVICE"] = str(cfg["audio_device"])
    os.environ["INTERRUPT_MODE"] = str(cfg.get("interrupt_mode", "finish"))
    # analyzer
    try:
        import event_analyzer  # type: ignore

        event_analyzer.configure(
            prompts_dir=cfg.get("prompts_dir", "prompts"),
            context_dir=cfg.get("context_dir", "context-data"),
            context_live_dir=cfg.get("context_live_dir", "context-live"),
            cooldown=float(cfg.get("greeting_cooldown_s", 3.0)),
            max_batch=int(cfg.get("greeting_max_batch", 5)),
            max_words=int(cfg.get("sales_max_words", 75)),
            user_cooldown=float(cfg.get("greeting_user_cooldown_s", 180.0)),
        )
    except Exception:
        pass
    # browser & gologin env
    os.environ["GOLOGIN_DIR"] = str(cfg.get("gologin_dir", "gologin-basic-offline"))
    os.environ["GOLOGIN_PROFILES_DIR"] = str(cfg.get("gologin_profiles_dir", ""))
    os.environ["GOLOGIN_ACTIVE_VERSION"] = str(cfg.get("gologin_active_version", ""))
    os.environ["GOLOGIN_PROFILE_ID"] = str(cfg.get("gologin_profile_id", ""))
    os.environ["BROWSER_MODE"] = str(cfg.get("browser_mode", "gologin_cdp"))

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
    print(f"tồn tại      = {_p.is_file()}")
    print(json.dumps(masked(), ensure_ascii=False, indent=2))
