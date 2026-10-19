"""Client tổng hợp giọng nói qua VoiceStudio (/v1/audio/speech, OpenAI-compatible).

Fallback: tạo sine 440Hz nếu VoiceStudio không chạy (để pipeline không gãy).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
import threading
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

VOICE_URL: str = os.getenv("VOICE_URL", "http://127.0.0.1:3900").rstrip("/")
VOICE_MODEL: str = os.getenv("VOICE_MODEL", "omnivoice")
VOICE_NAME: str = os.getenv("VOICE_NAME", "default")
TTS_TIMEOUT: float = float(os.getenv("TTS_TIMEOUT", "60"))

VOICESTUDIO_OK: bool = True
LAST_ENGINE: str = "unknown"
# thread-local: `run` xu ly nhieu event song song, bien global se doc lan nhau
_local = threading.local()


def last_latency_ms() -> float:
    """Latency cua lan synthesize gan nhat TRONG THREAD hien tai."""
    return float(getattr(_local, "latency_ms", 0.0))


def _project_root() -> Path:
    """Thu muc GHI duoc: canh .exe khi frozen, goc repo khi chay source.

    Khong dung _MEIPASS vi do la thu muc read-only (co the bi xoa khi thoat).
    """
    try:
        import settings

        return settings._project_root()
    except Exception:
        return Path(__file__).resolve().parent.parent


def _generate_sine_wav(path: Path, freq: float = 440.0, duration: float = 1.0, sample_rate: int = 16000) -> None:
    n_samples = int(duration * sample_rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            val = int(16000 * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
            frames.extend(struct.pack("<h", val))
        w.writeframes(frames)


def health(timeout: float = 3.0) -> dict:
    """Kiem tra VoiceStudio song + lay version (cho lenh `doctor`)."""
    out = {"ok": False, "url": VOICE_URL, "version": None, "voices": 0, "error": None}
    try:
        with urllib.request.urlopen(f"{VOICE_URL}/system/info", timeout=timeout) as resp:
            out["version"] = json.loads(resp.read().decode("utf-8")).get("app_version")
        with urllib.request.urlopen(f"{VOICE_URL}/v1/audio/voices", timeout=timeout) as resp:
            out["voices"] = len(json.loads(resp.read().decode("utf-8")).get("voices") or [])
        out["ok"] = True
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


_voices_cache: dict = {"url": "", "aliases": set(), "by_name": {}, "profiles": []}


def list_voices(force: bool = False) -> dict:
    """Danh sach voice cua VoiceStudio: alias OpenAI + profile da clone.

    Tra {"aliases": set[str], "by_name": {ten_thuong: voice_id}, "profiles": [dict]}.
    Cache theo URL de khong goi lai moi lan synthesize.
    """
    if not force and _voices_cache["url"] == VOICE_URL and _voices_cache["by_name"] is not None:
        return _voices_cache
    aliases: set[str] = set()
    by_name: dict[str, str] = {}
    profiles: list[dict] = []
    url = f"{VOICE_URL}/v1/audio/voices"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        for v in data.get("voices") or []:
            vid = str(v.get("voice_id") or "").strip()
            if not vid:
                continue
            if str(v.get("type")) == "profile":
                profiles.append(v)
                nm = str(v.get("name") or "").strip().casefold()
                if nm:
                    by_name.setdefault(nm, vid)
            else:
                aliases.add(vid.casefold())
        _voices_cache.update(url=VOICE_URL, aliases=aliases, by_name=by_name, profiles=profiles)
    except Exception:
        pass
    return _voices_cache


def resolve_voice(name: str) -> tuple[str, str]:
    """Doi `voicestudio_voice` thanh voice_id ma VoiceStudio hieu.

    VoiceStudio 0.5.6 chi nhan voice_id cua profile (vd `ef920857`), KHONG nhan ten
    (vd `SonTungMTP`) va KHONG bao loi — ten la se bi lang le dung giong mac dinh.
    Tra (voice_id, canh_bao); canh_bao rong khi resolve duoc hoac la alias hop le.
    """
    raw = str(name or "").strip()
    # Dropdown GUI hien "Ten  <voice_id>" -> uu tien voice_id trong ngoac nho
    m = re.search(r"<([^<>]+)>\s*$", raw)
    if m:
        raw = m.group(1).strip()
    if not raw:
        return "default", ""
    key = raw.casefold()
    info = list_voices()
    if not info["aliases"] and not info["by_name"]:
        return raw, ""          # khong doc duoc danh sach -> giu nguyen, khong doan
    if key in info["aliases"] or key == "default":
        return raw, ""
    if any(key == str(p.get("voice_id") or "").strip().casefold() for p in info["profiles"]):
        return raw, ""          # da la voice_id hop le
    vid = info["by_name"].get(key)
    if vid:
        return vid, ""
    return raw, (
        f"voice '{raw}' khong co trong VoiceStudio — se bi doc bang giong MAC DINH. "
        f"Danh sach dung duoc: {', '.join(sorted(info['aliases'])[:6])}"
        + (f" hoac voice_id profile: {', '.join(p['voice_id'] for p in info['profiles'])}" if info["profiles"] else "")
    )


def synthesize(text: str, out_dir: str | Path = "out") -> Path:
    """Gửi text sang VoiceStudio; fail thì fallback tạo sine wav."""
    global VOICESTUDIO_OK, LAST_ENGINE
    p = Path(out_dir)
    if not p.is_absolute():
        p = _project_root() / p
    p.mkdir(parents=True, exist_ok=True)

    ts = int(time.time() * 1000)
    h = hashlib.md5((text or "").encode("utf-8")).hexdigest()[:8]
    wav_path = p / f"tts_{ts}_{h}.wav"

    voice_id, _warn = resolve_voice(VOICE_NAME)
    if _warn:
        print(f"[tts] {_warn}", flush=True)
    data = json.dumps({
        "model": VOICE_MODEL,
        "input": text,
        "voice": voice_id,
        "response_format": "wav",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{VOICE_URL}/v1/audio/speech",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TTS_TIMEOUT) as resp:
            content = resp.read()
            if not content or not content.startswith(b"RIFF"):
                raise ValueError("response khong phai WAV")
            wav_path.write_bytes(content)
            VOICESTUDIO_OK = True
            LAST_ENGINE = VOICE_MODEL
            _local.latency_ms = (time.perf_counter() - t0) * 1000
            return wav_path
    except Exception as e:
        VOICESTUDIO_OK = False
        LAST_ENGINE = "sine-fallback"
        _local.latency_ms = (time.perf_counter() - t0) * 1000
        print(f"VOICESTUDIO_OK=false, dùng giọng dự phòng ({type(e).__name__}: {e})")
        _generate_sine_wav(wav_path, freq=440.0, duration=1.0)
        return wav_path

# ponytail: 1 request/text, khong stream, khong retry. Nang cap: stream SSE + retry
# khi can giam latency cho cau dai hoac VoiceStudio chap chon.
