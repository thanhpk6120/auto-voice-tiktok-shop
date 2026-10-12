"""Client tổng hợp giọng nói qua VoiceStudio (fallback sine 440Hz)."""
from __future__ import annotations

import hashlib
import json
import math
import struct
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

VOICESTUDIO_OK: bool = True
VOICE_URL: str = "http://127.0.0.1:3900"


def _project_root() -> Path:
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


def synthesize(text: str, out_dir: str | Path = "out") -> Path:
    """Gửi text sang VoiceStudio; fail thì fallback tạo sine wav."""
    global VOICESTUDIO_OK
    p = Path(out_dir)
    if not p.is_absolute():
        p = _project_root() / p
    p.mkdir(parents=True, exist_ok=True)

    ts = int(time.time() * 1000)
    h = hashlib.md5((text or "").encode("utf-8")).hexdigest()[:8]
    wav_path = p / f"tts_{ts}_{h}.wav"

    data = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{VOICE_URL.rstrip('/')}/tts",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            content = resp.read()
            if not content:
                raise ValueError("empty response")
            wav_path.write_bytes(content)
            VOICESTUDIO_OK = True
            return wav_path
    except Exception:
        VOICESTUDIO_OK = False
        print("VOICESTUDIO_OK=false fallback")
        _generate_sine_wav(wav_path, freq=440.0, duration=1.0)
        return wav_path
