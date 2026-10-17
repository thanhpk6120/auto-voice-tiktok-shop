"""Auto Voice TikTok Shop LIVE - CLI chinh.

Lenh:
  simulate           Chay mo phong 10 event (analyzer -> tts -> queue), khong phat tieng.
  run                Vong lap that: event (bridge/sim) -> analyzer -> tts -> queue -> loa.
  doctor             Chan doan: VoiceStudio, LLM, thiet bi loa, bridge/event, hang doi.
  live / stop        Giu nguyen (chua implement).
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

# Ensure src + project root trong sys.path (llm_client dung `from src.xxx import`)
_SRC = os.path.dirname(os.path.abspath(__file__))
for _p in (_SRC, os.path.dirname(_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audio_player
import event_bridge as bridge_mod
import tts_client
from audio_queue import PriorityAudioQueue
from event_analyzer import analyze, get_batcher
from event_simulator import iter_events
from tts_client import synthesize

DEFAULT_BRIDGE = os.getenv("BRIDGE_URL", bridge_mod.DEFAULT_BRIDGE_URL)


def process_event(event, queue, no_play: bool = False) -> bool:
    """1 event -> speak_text -> wav -> hang doi. Tra True neu da xu ly (co speak_text)."""
    res = analyze(event)
    speak_text = res.get("speak_text")
    if not speak_text:
        return False
    wav = synthesize(speak_text)
    kind = res.get("kind", "unknown")
    priority = res.get("priority", 3)
    queue.put(kind, priority, speak_text, wav)
    print(
        f"event={event.get('type', event.get('kind', ''))} -> speak_text='{speak_text}' "
        f"-> wav={wav.name} -> priority={priority} -> queue-size={queue.qsize()}"
        f"{' [no-play]' if no_play else ''}",
        flush=True,
    )
    return True


def handle_simulate(args=None) -> None:
    interrupt_mode = os.getenv("INTERRUPT_MODE", "finish")
    no_play = bool(getattr(args, "no_play", False))
    print(f"Starting simulation... (no_play={no_play}, interrupt_mode={interrupt_mode})")
    queue = PriorityAudioQueue(interrupt_mode=interrupt_mode)
    gen = iter_events(seed=42)
    # Lấy 10 sự kiện (4 join batch + vài cái sau)
    events = [next(gen) for _ in range(10)]
    for e in events:
        process_event(e, queue, no_play)

    # Force flush batch nếu còn
    batched = get_batcher().flush()
    if batched:
        wav = synthesize(batched)
        queue.put("greeting", 3, batched, wav)
        print(f"event=join(flushed) -> speak_text='{batched}' -> wav={wav.name} -> queue-size={queue.qsize()}")

    print(f"Simulation done. queue-size={queue.qsize()}")
    # Layout theo thu tu uu tien de kiem chung 1/2/3
    drained = []
    while not queue.empty():
        item = queue.get()
        drained.append(f"p{item['priority']}:{item['kind']}")
    print("Drain order (priority): " + ", ".join(drained))


def _stream_events(args, stop_event: threading.Event):
    """Nguon event: bridge WebSocket that, hoac simulator noi bo (--sim)."""
    if getattr(args, "sim", False):
        print("[run] nguon event: simulator noi bo (--sim)")
        gen = iter_events(seed=42)
        prev_ts = None
        speed = getattr(args, "speed", 1.0)
        for ev in gen:
            if stop_event.is_set():
                return
            ts = ev.get("ts")
            if prev_ts is not None and ts is not None:
                time.sleep(max(0.0, (ts - prev_ts)) * speed)
            prev_ts = ts
            yield ev
    else:
        print(f"[run] nguon event: bridge {args.bridge}")
        yield from bridge_mod.iter_events(args.bridge, stop_event)


def handle_run(args) -> int:
    interrupt_mode = os.getenv("INTERRUPT_MODE", "finish")
    no_play = bool(getattr(args, "no_play", False))
    play = audio_player.noop_play if no_play else audio_player.play_wav
    queue = PriorityAudioQueue(
        on_play=play, dry_run=no_play, interrupt_mode=interrupt_mode
    ).start()
    stop_event = threading.Event()
    stats = {"spoke": 0, "tts_ok": 0, "tts_fail": 0, "lat_ms": []}

    def worker(ev: dict) -> None:
        spoke = False
        try:
            spoke = process_event(ev, queue, no_play)
            if spoke:
                stats["spoke"] += 1
        except Exception as e:  # 1 event loi khong duoc giet vong lap
            print(f"[run] event error: {type(e).__name__}: {e}", flush=True)
        if not spoke:
            return  # join gop batch: khong goi TTS -> khong tinh latency
        if tts_client.VOICESTUDIO_OK:
            stats["tts_ok"] += 1
        else:
            stats["tts_fail"] += 1
        stats["lat_ms"].append(tts_client.last_latency_ms())

    print(
        f"[run] bat dau (no_play={no_play}, interrupt_mode={interrupt_mode}, "
        f"seconds={args.seconds or 'vo han'}). Ctrl+C de dung."
    )
    t0 = time.monotonic()
    received = 0  # dem o vong lap nhan: stats do worker tang nen bi tre
    try:
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="event-proc") as pool:
            for ev in _stream_events(args, stop_event):
                pool.submit(worker, ev)
                received += 1
                if args.seconds and (time.monotonic() - t0) >= args.seconds:
                    break
                if args.max_events and received >= args.max_events:
                    break
    except KeyboardInterrupt:
        print("\n[run] Ctrl+C -> dung")
    except Exception as e:
        print(f"[run] nguon event loi: {type(e).__name__}: {e}", file=sys.stderr)
        stop_event.set()

    stop_event.set()
    # Flush batch chao con lai
    try:
        batched = get_batcher().flush()
        if batched:
            queue.put("greeting", 3, batched, synthesize(batched))
            print(f"[run] flush greeting: '{batched}'")
    except Exception:
        pass

    # Cho worker phat not hang doi (toi da 15s) de so lieu summary chinh xac
    deadline = time.monotonic() + 15
    while not queue.empty() and time.monotonic() < deadline:
        time.sleep(0.1)
    queue.stop(drain=False)

    lat = stats["lat_ms"]
    lat_txt = f"min={min(lat):.0f}ms max={max(lat):.0f}ms avg={sum(lat) / len(lat):.0f}ms" if lat else "n/a"
    print("=== RUN SUMMARY ===")
    print(f"events_nhan={received} cau_da_doc={stats['spoke']}")
    print(f"tts: ok={stats['tts_ok']} fallback={stats['tts_fail']} engine={tts_client.LAST_ENGINE}")
    print(f"tts_latency: {lat_txt}")
    print(f"queue: {queue.stats} qsize_con_lai={queue.qsize()}")
    print(f"play: {'no-play (khong phat tieng)' if no_play else 'da phat ra loa'} "
          f"device={audio_player.output_device_name()}")
    return 0


# ---------- doctor ----------

def _check_voicestudio() -> tuple[bool, str]:
    h = tts_client.health()
    if h["ok"]:
        return True, f"OK {h['url']} v{h['version']} ({h['voices']} voices)"
    return False, f"FAIL {h['url']} -> {h['error']}"


def _check_llm() -> tuple[bool, str]:
    try:
        from config import LLM_BASE_URL, LLM_MODEL
        from llm_client import chat

        t0 = time.perf_counter()
        reply = chat("Tra loi dung 1 tu.", "OK?", timeout=float(os.getenv("LLM_DOCTOR_TIMEOUT", "20")))
        ms = (time.perf_counter() - t0) * 1000
        return True, f"OK {LLM_BASE_URL} model={LLM_MODEL} latency={ms:.0f}ms reply='{reply.strip()[:40]}'"
    except Exception as e:
        return False, f"FAIL {type(e).__name__}: {e}"


def _check_audio_device() -> tuple[bool, str]:
    name = audio_player.output_device_name()
    ok = not name.startswith(("unavailable", "error"))
    return ok, name


def _check_bridge(url: str, window: float) -> tuple[bool, str]:
    n = 0
    t0 = time.monotonic()
    stop = threading.Event()
    try:
        # Deadline dat bang thread rieng: neu bridge song nhung khong co event nao
        # thi vong for block mai mai neu chi dua vao break trong loop body.
        timer = threading.Timer(window, stop.set)
        timer.daemon = True
        timer.start()
        try:
            for _ in bridge_mod.iter_events(url, stop_event=stop, open_timeout=3.0, recv_timeout=0.5):
                n += 1
                if (time.monotonic() - t0) >= window:
                    stop.set()
                    break
        finally:
            timer.cancel()
    except Exception as e:
        return False, f"FAIL {url} -> {type(e).__name__}: {e}"
    return True, f"OK {url} events={n} trong {time.monotonic() - t0:.1f}s"


def _check_queue() -> tuple[bool, str]:
    interrupt_mode = os.getenv("INTERRUPT_MODE", "finish")
    q = PriorityAudioQueue(dry_run=True, interrupt_mode=interrupt_mode)
    q.put("order", 1, "cam on", "b.wav")
    size_after = q.qsize()
    order = [q.get()["priority"], q.get()["priority"]]
    ok = size_after == 2 and order == [1, 3] and q.empty()
    return ok, (f"OK uu tien dung p1 truoc p3 (order={order}), size 0->{size_after}->0"
                if ok else f"FAIL order={order} size={size_after}")


def handle_doctor(args) -> int:
    print("[doctor] Auto Voice TikTok Shop - chan doan")
    checks = [
        ("VoiceStudio", _check_voicestudio()),
        ("LLM", _check_llm()),
        ("Audio output", _check_audio_device()),
        ("Bridge", _check_bridge(getattr(args, "bridge", DEFAULT_BRIDGE), getattr(args, "window", 2.0))),
        ("Audio queue", _check_queue()),
        ("Event simulator", (True, f"OK {sum(1 for _ in zip(range(10), iter_events(seed=42)))} event(s) sinh duoc")),
    ]
    failed = []
    for name, (ok, detail) in checks:
        tag = "OK  " if ok else "FAIL"
        print(f"  {tag} {name:<15}: {detail}")
        if not ok:
            failed.append(name)
    if failed:
        print(f"[doctor] ket qua: CO VAN DE ({', '.join(failed)})")
        return 1
    print("[doctor] ket qua: TAT CA OK")
    return 0


def handle_live():
    print("Live mode not fully implemented yet.")


def handle_stop():
    print("Stopping app...")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auto Voice TikTok Shop LIVE CLI")
    subparsers = parser.add_subparsers(dest="command")

    p_sim = subparsers.add_parser("simulate", help="Simulate events (khong phat tieng)")
    p_sim.add_argument("--no-play", action="store_true", help="Khong phat tieng ra loa")

    p_run = subparsers.add_parser("run", help="Vong lap that: event -> tts -> hang doi -> loa")
    p_run.add_argument("--bridge", default=DEFAULT_BRIDGE, help=f"URL bridge WebSocket (mac dinh {DEFAULT_BRIDGE})")
    p_run.add_argument("--sim", action="store_true", help="Dung simulator noi bo thay vi bridge")
    p_run.add_argument("--speed", type=float, default=1.0, help="He so toc do khi --sim")
    p_run.add_argument("--seconds", type=float, default=0, help="Tu dung sau N giay (0 = vo han)")
    p_run.add_argument("--max-events", type=int, default=0, help="Tu dung sau N event")
    p_run.add_argument("--no-play", action="store_true", help="Test khong phat tieng (khong mo loa)")

    p_doc = subparsers.add_parser("doctor", help="Chan doan VoiceStudio / LLM / loa / bridge / hang doi")
    p_doc.add_argument("--bridge", default=DEFAULT_BRIDGE)
    p_doc.add_argument("--window", type=float, default=2.0, help="So giay nghe event tu bridge")

    subparsers.add_parser("live", help="Start live mode")
    subparsers.add_parser("stop", help="Stop app")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "simulate":
        handle_simulate(args)
    elif args.command == "run":
        return handle_run(args)
    elif args.command == "doctor":
        return handle_doctor(args)
    elif args.command == "live":
        handle_live()
    elif args.command == "stop":
        handle_stop()
        return 0
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
