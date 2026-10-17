"""Check TTS thật: warmup + 3 câu tiếng Việt + phát ra loa. Ghi bằng chứng docs/TEST-TTS-REAL.md.

Chạy: python scripts/check_tts.py
"""
from __future__ import annotations

import sys
import time
import wave
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.tts_client import VOICE_NAME, health, speech_endpoint, synthesize, warmup  # noqa: E402
from src.audio_player import PLAYER_BACKEND, list_output_devices, play_wav  # noqa: E402

SENTENCES = [
    "Xin chào, cảm ơn bạn đã ghé thăm gian hàng của chúng tôi.",
    "Chiếc áo thun này làm từ cotton 100 phần trăm, form rộng, giá chỉ một trăm năm mươi nghìn đồng.",
    "Cảm ơn bạn đã đặt hàng, đơn hàng sẽ được giao trong hai đến ba ngày tới.",
]

OUT_DIR = ROOT / "out" / "tts_check"
LOG: list[str] = []


def log(line: str = "") -> None:
    print(line, flush=True)
    LOG.append(line)


def wav_info(path: Path) -> dict:
    raw = path.read_bytes()
    info = {
        "path": str(path),
        "bytes": len(raw),
        "magic": raw[:4].decode("ascii", "replace"),
        "is_riff": raw[:4] == b"RIFF",
        ">20KB": len(raw) > 20 * 1024,
    }
    try:
        with wave.open(str(path), "rb") as w:
            info.update(
                channels=w.getnchannels(),
                sampwidth=w.getsampwidth() * 8,
                framerate=w.getframerate(),
                frames=w.getnframes(),
                seconds=round(w.getnframes() / w.getframerate(), 2),
            )
    except Exception as e:  # noqa: BLE001
        info["wave_error"] = f"{type(e).__name__}: {e}"
    return info


def main() -> int:
    t_script = time.perf_counter()
    started = datetime.now()
    log("# TEST TTS REAL — VoiceStudio /v1/audio/speech")
    log()
    log(f"- Thời điểm chạy: {started.isoformat(timespec='seconds')}")
    log(f"- Endpoint: `{speech_endpoint()}`")
    log(f"- Voice: `{VOICE_NAME}` | model: OpenAI-compatible `tts-1` | response_format: `wav`")
    log(f"- Lệnh: `python scripts/check_tts.py`")
    log()

    log("## 1. health()")
    h = health()
    log(f"```json\n{h}\n```")
    log()

    log("## 2. warmup() — preload model")
    w = warmup()
    log(f"```json\n{w}\n```")
    log()

    log("## 3. synthesize 3 câu tiếng Việt thật")
    log()
    log("| # | Câu | latency (ms) | bytes | RIFF | >20KB | giây audio | file |")
    log("|---|---|---|---|---|---|---|---|")
    import src.tts_client as tts_mod

    results = []
    for i, sentence in enumerate(SENTENCES, 1):
        t0 = time.perf_counter()
        path = synthesize(sentence, out_dir=OUT_DIR)
        latency_ms = round((time.perf_counter() - t0) * 1000)
        info = wav_info(Path(path))
        results.append({"sentence": sentence, "latency_ms": latency_ms, "ok": tts_mod.VOICESTUDIO_OK, **info})
        log(
            f"| {i} | {sentence} | {latency_ms} | {info['bytes']} | {info['is_riff']} | {info['>20KB']} "
            f"| {info.get('seconds', '?')} | `{Path(path).name}` |"
        )
    log()
    log(f"- VOICESTUDIO_OK sau khi synthesize: **{tts_mod.VOICESTUDIO_OK}**")
    log()

    log("## 4. play_wav() — phát câu cuối ra loa")
    log(f"- Backend ưu tiên: `{PLAYER_BACKEND}`")
    devices = list_output_devices()
    log(f"- Thiết bị phát khả dụng ({len(devices)}):")
    for d in devices:
        log(f"  - [{d['index']}] {d['name']} ({d['channels']}ch, {d['samplerate']}Hz, {d['hostapi']})")
    last = Path(results[-1]["path"])
    t0 = time.perf_counter()
    played = play_wav(last, blocking=True)
    log(f"- Kết quả `play_wav({last.name})` = **{played}** (mất {time.perf_counter() - t0:.2f}s)")
    if not played:
        log("- KHÔNG PHÁT ĐƯỢC: xem log `[AUDIO]` ở mục 5 để biết lý do.")
    log()

    log("## 5. Log thô stdout")
    log("```text")
    log(f"[tts_client] health={h}")
    log(f"[tts_client] warmup={w}")
    for r in results:
        log(
            f"[tts_client] synth ok={r['ok']} latency_ms={r['latency_ms']} bytes={r['bytes']} "
            f"riff={r['is_riff']} >20KB={r['>20KB']} file={r['path']}"
        )
    log(f"[audio_player] backend={PLAYER_BACKEND} devices={len(devices)} play_wav={played}")
    log("```")
    log()

    log("## 6. Kết luận")
    ok_all = all(r["ok"] and r["is_riff"] and r[">20KB"] for r in results)
    log(f"- 3/3 câu: `VOICESTUDIO_OK=true` + magic RIFF + > 20KB: **{ok_all}**")
    log(f"- Latency đo được (ms): {[r['latency_ms'] for r in results]}")
    log(f"- play_wav trả về: **{played}**")
    if not played:
        log(f"- Lý do không phát được: ghi ở log `[AUDIO]`; thiết bị phát khả dụng: {len(devices)}")
    log()
    log(f"_(Tổng thời gian script: {time.perf_counter() - t_script:.1f}s)_")

    out_md = ROOT / "docs" / "TEST-TTS-REAL.md"
    out_md.write_text("\n".join(LOG) + "\n", encoding="utf-8")
    print(f"\n[check_tts] wrote {out_md}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
