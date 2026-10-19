"""Phát WAV ra loa, hỗ trợ ngắt giữa chừng (interrupt) cho priority=1."""
from __future__ import annotations

import os
import time
import wave
from pathlib import Path

_SD_OK = True
try:
    import numpy as np
    import sounddevice as sd
except Exception:  # pragma: no cover - thieu sounddevice/numpy
    _SD_OK = False

# ponytail: fallback winsound khong ngat duoc (da test: SND_PURGE cross-thread khong an).
# Nang cap: cai `sounddevice` de co interrupt that.
try:
    import winsound
except Exception:  # pragma: no cover - non-Windows
    winsound = None


def _read_wav(path: str | Path):
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError(
                f"chi ho tro mono 16-bit wav, got ch={w.getnchannels()} width={w.getsampwidth()}"
            )
        rate = w.getframerate()
        raw = w.readframes(w.getnframes())
    data = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    return data, rate


def _resolve_device():
    """AUDIO_OUTPUT_DEVICE = index (so) hoac chuoi con cua ten thiet bi."""
    if not _SD_OK:
        return None
    spec = os.getenv("AUDIO_OUTPUT_DEVICE", "").strip()
    if not spec:
        return None
    if spec.lstrip("-").isdigit():
        return int(spec)
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_output_channels", 0) > 0 and spec.lower() in str(dev.get("name", "")).lower():
            return idx
    return None


def list_output_devices() -> list[dict]:
    """Danh sach thiet bi ra: [{'index': int, 'name': str}]. Rong neu thieu sounddevice."""
    if not _SD_OK:
        return []
    try:
        return [
            {"index": idx, "name": str(dev.get("name", ""))}
            for idx, dev in enumerate(sd.query_devices())
            if dev.get("max_output_channels", 0) > 0
        ]
    except Exception:
        return []

def output_device_name() -> str:
    """Ten thiet bi loa dang dung (cho lenh `doctor`)."""
    if not _SD_OK:
        return "unavailable (chua cai sounddevice/numpy)"
    try:
        dev = _resolve_device()
        if dev is None:
            dev = sd.default.device[1]
        info = sd.query_devices(dev, "output")
        return f"{info['name']} (index={dev})"
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"


def play_wav(wav_path: str | Path, stop_event=None, tail_padding_s: float = 0.25) -> bool:
    """Phat file wav. Tra False neu bi ngat (stop_event duoc set) giua chung.
    tail_padding_s: them khoang lang o cuoi buffer va doi buffer driver xa het
    de dam bao tu cuoi cung khong bi cat cut boi hardware / driver buffer."""
    if stop_event is not None and stop_event.is_set():
        return False

    if _SD_OK:
        try:
            data, rate = _read_wav(wav_path)
            # Chen them khoang lang vao cuoi data de buffer phan cung / driver
            # khong cat cut tu cuoi truoc khi kip phat het
            if tail_padding_s > 0:
                pad_frames = int(rate * tail_padding_s)
                if getattr(data, "ndim", 1) == 1:
                    pad = np.zeros(pad_frames, dtype=data.dtype)
                else:
                    pad = np.zeros((pad_frames, data.shape[1]), dtype=data.dtype)
                data = np.concatenate([data, pad])

            sd.play(data, rate, device=_resolve_device())
            stream = sd.get_stream()
            while stream is not None and stream.active:
                if stop_event is not None and stop_event.is_set():
                    sd.stop()
                    return False
                time.sleep(0.02)
            # Cho them mot chut de driver/hardware xa sach audio buffer
            if tail_padding_s > 0:
                time.sleep(min(0.12, tail_padding_s))
            return True
        except Exception:
            pass  # roi ve winsound

    if winsound is None:
        return False
    # winsound khong ngat duoc giua chung -> chi la duong lui khi thieu sounddevice.
    winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
    return True


def noop_play(wav_path: str | Path, stop_event=None) -> bool:
    """Player gia cho `--no-play` (test khong phat tieng)."""
    return not (stop_event is not None and stop_event.is_set())
