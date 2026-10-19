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
from batch_processor import BatchEventCollector, process_event_batch
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
    if str(kind).lower() == "greeting":
        try:
            import phrase_cache
            phrase_cache.remember("greeting", speak_text)
        except Exception:
            pass
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
    print(f"Bắt đầu mô phỏng... (no_play={no_play}, interrupt_mode={interrupt_mode})")
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

    print(f"Mô phỏng xong. hàng-đợi={queue.qsize()}")
    # Layout theo thu tu uu tien de kiem chung 1/2/3
    drained = []
    while not queue.empty():
        item = queue.get()
        drained.append(f"p{item['priority']}:{item['kind']}")
    print("Thứ tự lấy ra khỏi hàng đợi (theo ưu tiên): " + ", ".join(drained))


def _stream_events(args, stop_event: threading.Event):
    """Nguon event: bridge WebSocket that, hoac simulator noi bo (--sim), hoac truc tiep GoLogin CDP."""
    mode = getattr(args, "browser_mode", None) or os.getenv("BROWSER_MODE", "extension")
    if getattr(args, "sim", False):
        print("[run] nguồn sự kiện: simulator nội bộ (--sim)")
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
    elif mode == "gologin_cdp":
        cdp_port = getattr(args, "cdp_port", None) or int(os.getenv("CDP_PORT", "30899"))
        print(f"[run] nguồn sự kiện: kết nối trực tiếp GoLogin CDP (cổng {cdp_port})")
        import browser_manager
        yield from browser_manager.stream_cdp_events(stop_event, cdp_port=cdp_port)
    else:
        print(f"[run] nguồn sự kiện: bridge {args.bridge}")
        yield from bridge_mod.iter_events(args.bridge, stop_event)

def handle_run(args) -> int:
    interrupt_mode = os.getenv("INTERRUPT_MODE", "finish")
    no_play = bool(getattr(args, "no_play", False))
    play = audio_player.noop_play if no_play else audio_player.play_wav
    greeting_user_cooldown_s = float(os.getenv("GREETING_USER_COOLDOWN_S", "180.0"))
    greeting_max_batch = int(os.getenv("GREETING_MAX_BATCH", "5"))
    collector = BatchEventCollector(
        max_join_history=greeting_max_batch,
        greeting_user_cooldown_s=greeting_user_cooldown_s,
    )
    def on_audio_finish(item):
        # Vua phat xong audio -> danh thuc worker lay ngay su kien moi nhat da gom.
        # Cac su kien den trong luc dang phat/tao voice khong bi mat, chi giu ban moi nhat.
        collector.wake()

    queue = PriorityAudioQueue(
        on_play=play,
        on_finish=on_audio_finish,
        dry_run=no_play,
        interrupt_mode=interrupt_mode,
    ).start()
    stop_event = threading.Event()
    stats = {"spoke": 0, "tts_ok": 0, "tts_fail": 0, "lat_ms": []}

    batch_window_s = float(
        getattr(args, "batch_window_s", None)
        if getattr(args, "batch_window_s", None) is not None
        else os.getenv("BATCH_WINDOW_S", "3.0")
    )
    batch_max_events = int(
        getattr(args, "batch_max_events", None)
        if getattr(args, "batch_max_events", None) is not None
        else os.getenv("BATCH_MAX_EVENTS", "10")
    )
    use_batch = batch_window_s > 0

    prompts_dir = os.getenv("PROMPTS_DIR", "prompts")
    context_dir = os.getenv("CONTEXT_DIR", "context-data")
    context_live_dir = os.getenv("CONTEXT_LIVE_DIR", "context-live")

    def batch_worker():
        nonlocal batch_window_s, batch_max_events, prompts_dir, context_dir, context_live_dir
        last_cfg_mtime = 0.0
        cfg_path = None
        try:
            import settings
            cfg_path = settings.config_path()
            if cfg_path.is_file():
                last_cfg_mtime = cfg_path.stat().st_mtime
        except Exception:
            pass

        while not stop_event.is_set():
            # Kiem tra neu nguoi dung bam 'Luu cau hinh' tu GUI trong khi tien trinh dang chay
            if cfg_path and cfg_path.is_file():
                try:
                    curr_mtime = cfg_path.stat().st_mtime
                    if curr_mtime > last_cfg_mtime:
                        last_cfg_mtime = curr_mtime
                        import settings
                        new_cfg = settings.load()
                        settings.apply(new_cfg)
                        batch_window_s = float(new_cfg.get("batch_window_s", batch_window_s))
                        batch_max_events = int(new_cfg.get("batch_max_events", batch_max_events))
                        prompts_dir = str(new_cfg.get("prompts_dir", prompts_dir))
                        context_dir = str(new_cfg.get("context_dir", context_dir))
                        context_live_dir = str(new_cfg.get("context_live_dir", context_live_dir))
                        collector.set_user_cooldown(float(new_cfg.get("greeting_user_cooldown_s", 180.0)))
                        collector.set_max_join_history(int(new_cfg.get("greeting_max_batch", 5)))
                        queue.interrupt_mode = str(new_cfg.get("interrupt_mode", queue.interrupt_mode))
                        queue._dry_run = bool(new_cfg.get("no_play", queue._dry_run))
                        print(f"[config] Đã cập nhật và áp dụng cấu hình mới nhất từ {cfg_path.name}", flush=True)
                except Exception:
                    pass

            # Thuc day khi: (a) co su kien uu tien cao vao hang doi, (b) vua phat xong
            # audio -> lay ngay su kien moi nhat, hoac (c) het cua so batch_window_s.
            collector.wait_for_batch(timeout=batch_window_s)
            evs = collector.drain()
            if not evs:
                continue  # Không có sự kiện mới -> KHÔNG gọi LLM
            print(f"[run/batch] Gom {len(evs)} sự kiện mới nhất -> gửi AI LLM", flush=True)
            try:
                items = process_event_batch(
                    evs,
                    max_events=batch_max_events,
                    prompts_dir=prompts_dir,
                    context_dir=context_dir,
                    context_live_dir=context_live_dir,
                )
                for it in items:
                    txt = it.get("text", "")
                    if not txt:
                        continue
                    if str(it.get("type", "")).lower() == "greeting":
                        try:
                            import phrase_cache
                            phrase_cache.remember("greeting", txt)
                        except Exception:
                            pass
                    wav = synthesize(txt)
                    prio = int(it.get("priority", 2))
                    k = str(it.get("type", "chat"))
                    queue.put(k, prio, txt, wav)
                    stats["spoke"] += 1
                    if tts_client.VOICESTUDIO_OK:
                        stats["tts_ok"] += 1
                    else:
                        stats["tts_fail"] += 1
                    stats["lat_ms"].append(tts_client.last_latency_ms())
                    print(
                        f"[run/batch] event={k} ({it.get('user', 'Khách')}) -> speak_text='{txt}' "
                        f"-> wav={wav.name} -> priority={prio} -> queue-size={queue.qsize()}"
                        f"{' [no-play]' if no_play else ''}",
                        flush=True,
                    )
            except Exception as e:
                print(f"[run/batch] lỗi xử lý batch: {e}", flush=True)

    if use_batch:
        b_thread = threading.Thread(target=batch_worker, daemon=True, name="batch-processor")
        b_thread.start()

    remind_enabled = os.getenv("REMIND_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    remind_min_s = float(os.getenv("REMIND_MIN_S", "60.0"))
    remind_max_s = float(os.getenv("REMIND_MAX_S", "120.0"))
    remind_text = os.getenv(
        "REMIND_TEXT",
        "Mọi người xem lai nhớ cho sốp xin một tim và com men sản phẩm cần tư vấn nhé, sốp cảm ơn",
    )

    def remind_worker():
        import random
        from event_analyzer import phoneticize_vietnamese
        while not stop_event.is_set():
            # Doc dong thoi cau hinh nhac nho tu settings (neu vua duoc Luu tu GUI)
            r_en = remind_enabled
            r_txt = remind_text
            r_min = remind_min_s
            r_max = remind_max_s
            try:
                import settings
                cur_cfg = settings.get()
                r_en = bool(cur_cfg.get("remind_enabled", r_en))
                r_txt = str(cur_cfg.get("remind_text", r_txt))
                r_min = float(cur_cfg.get("remind_min_s", r_min))
                r_max = float(cur_cfg.get("remind_max_s", r_max))
            except Exception:
                pass

            delay = random.uniform(r_min, r_max)
            elapsed = 0.0
            while elapsed < delay and not stop_event.is_set():
                time.sleep(0.5)
                elapsed += 0.5
            if stop_event.is_set() or not r_en:
                continue

            # Chỉ đọc nhắc nhở khi hàng đợi rảnh (không chen ngang khách hỏi hàng/đơn hàng)
            if queue.qsize() <= 1 and not collector.has_high_priority():
                try:
                    import remind_text as _remind
                    spoken_text = _remind.pick(r_txt) or phoneticize_vietnamese(r_txt)
                except Exception:
                    spoken_text = phoneticize_vietnamese(r_txt)
                try:
                    wav = synthesize(spoken_text)
                    if wav:
                        queue.put("remind", 3, spoken_text, wav)
                        print(f"[run/remind] Nhắc tương tác: '{spoken_text}'", flush=True)
                except Exception as e:
                    print(f"[run/remind] Lỗi nhắc tương tác: {e}", flush=True)

    # Luon khoi chay remind_worker (ben trong kiem tra dong r_en tu config de ho tro hot-reload)
    r_thread = threading.Thread(target=remind_worker, daemon=True, name="remind-loop")
    r_thread.start()
    def worker(ev: dict) -> None:
        spoke = False
        try:
            spoke = process_event(ev, queue, no_play)
            if spoke:
                stats["spoke"] += 1
        except Exception as e:
            print(f"[run] lỗi sự kiện: {type(e).__name__}: {e}", flush=True)
        if not spoke:
            return
        if tts_client.VOICESTUDIO_OK:
            stats["tts_ok"] += 1
        else:
            stats["tts_fail"] += 1
        stats["lat_ms"].append(tts_client.last_latency_ms())

    print(
        f"[run] bắt đầu (no_play={no_play}, batch={batch_window_s}s, interrupt_mode={interrupt_mode}, "
        f"seconds={args.seconds or 'vô hạn'}). Ctrl+C để dừng."
    )
    t0 = time.monotonic()
    received = 0
    try:
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="event-proc") as pool:
            for ev in _stream_events(args, stop_event):
                if use_batch:
                    collector.add(ev)
                    received += 1
                else:
                    pool.submit(worker, ev)
                    received += 1
                if args.seconds and (time.monotonic() - t0) >= args.seconds:
                    break
                if args.max_events and received >= args.max_events:
                    break
    except KeyboardInterrupt:
        print("\n[run] Ctrl+C -> dừng")
    except Exception as e:
        print(f"[run] nguồn sự kiện lỗi: {type(e).__name__}: {e}", file=sys.stderr)
        stop_event.set()

    stop_event.set()
    if use_batch:
        remaining = collector.drain()
        if remaining:
            try:
                items = process_event_batch(remaining, max_events=batch_max_events)
                for it in items:
                    txt = it.get("text", "")
                    if txt:
                        queue.put(str(it.get("type", "chat")), int(it.get("priority", 2)), txt, synthesize(txt))
            except Exception:
                pass
    # Flush batch chao con lai
    try:
        batched = get_batcher().flush()
        if batched:
            queue.put("greeting", 3, batched, synthesize(batched))
            print(f"[run] xả câu chào đang gom: '{batched}'")
    except Exception:
        pass

    # Cho worker phat not hang doi (toi da 15s) de so lieu summary chinh xac
    deadline = time.monotonic() + 15
    while not queue.empty() and time.monotonic() < deadline:
        time.sleep(0.1)
    queue.stop(drain=False)

    lat = stats["lat_ms"]
    lat_txt = f"min={min(lat):.0f}ms max={max(lat):.0f}ms avg={sum(lat) / len(lat):.0f}ms" if lat else "n/a"
    print("=== TỔNG KẾT PHIÊN CHẠY ===")
    print(f"sự_kiện_nhận={received} câu_đã_đọc={stats['spoke']}")
    print(f"TTS: ok={stats['tts_ok']} fallback={stats['tts_fail']} engine={tts_client.LAST_ENGINE}")
    print(f"độ_trễ_TTS: {lat_txt}")
    print(f"hàng_đợi: {queue.stats} hàng_đợi_còn_lại={queue.qsize()}")
    print(f"phát: {'no-play (không phát tiếng)' if no_play else 'đã phát ra loa'} "
          f"device={audio_player.output_device_name()}")
    return 0


# ---------- doctor ----------

def _check_voicestudio() -> tuple[bool, str]:
    h = tts_client.health()
    if not h["ok"]:
        return False, f"FAIL {h['url']} -> {h['error']}"
    msg = f"OK {h['url']} v{h['version']} ({h['voices']} voices)"
    # Canh bao khi ten giong cau hinh khong ton tai: VoiceStudio se lang le doc giong mac dinh.
    try:
        vid, warn = tts_client.resolve_voice(getattr(tts_client, "VOICE_NAME", ""))
        msg += f" voice='{tts_client.VOICE_NAME}' -> {vid}"
        if warn:
            return False, f"{msg}\n       CANH BAO: {warn}"
    except Exception:
        pass
    return True, msg


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

def _check_cdp(port: int = 30899) -> tuple[bool, str]:
    try:
        import browser_manager
        target = browser_manager.get_cdp_target(cdp_port=port)
        if target:
            title = str(target.get("title") or "")[:45]
            url = str(target.get("url") or "")[:60]
            return True, f"OK kết nối cổng {port} -> '{title}' ({url})"
        return False, f"FAIL không tìm thấy tab TikTok Shop trên cổng CDP {port}"
    except Exception as e:
        return False, f"FAIL CDP {port} -> {type(e).__name__}: {e}"



def _check_queue() -> tuple[bool, str]:
    interrupt_mode = os.getenv("INTERRUPT_MODE", "finish")
    q = PriorityAudioQueue(dry_run=True, interrupt_mode=interrupt_mode)
    q.put("greeting", 3, "hi", "a.wav")
    q.put("order", 1, "cam on", "b.wav")
    size_after = q.qsize()
    order = [q.get(timeout=1.0)["priority"], q.get(timeout=1.0)["priority"]]
    ok = size_after == 2 and order == [1, 3] and q.empty()
    return ok, (f"OK uu tien dung p1 truoc p3 (order={order}), size 0->{size_after}->0"
                if ok else f"FAIL order={order} size={size_after}")


def handle_doctor(args) -> int:
    print("[doctor] Auto Voice TikTok Shop — chẩn đoán")
    mode = getattr(args, "browser_mode", None) or os.getenv("BROWSER_MODE")
    if not mode:
        try:
            import settings
            mode = settings.load().get("browser_mode", "gologin_cdp")
        except Exception:
            mode = "gologin_cdp"
    cdp_port = getattr(args, "cdp_port", None) or int(os.getenv("CDP_PORT", "30899"))
    checks = [
        ("VoiceStudio", _check_voicestudio()),
        ("LLM", _check_llm()),
        ("Audio output", _check_audio_device()),
    ]
    if mode == "gologin_cdp":
        checks.append(("Browser (CDP)", _check_cdp(cdp_port)))
    else:
        checks.append(("Bridge", _check_bridge(getattr(args, "bridge", DEFAULT_BRIDGE), getattr(args, "window", 2.0))))

    checks.extend([
        ("Audio queue", _check_queue()),
        ("Event simulator", (True, f"OK {sum(1 for _ in zip(range(10), iter_events(seed=42)))} event(s) sinh duoc")),
    ])
    failed = []
    for name, (ok, detail) in checks:
        tag = "OK  " if ok else "FAIL"
        print(f"  {tag} {name:<15}: {detail}")
        if not ok:
            failed.append(name)
    if failed:
        print(f"[doctor] kết quả: CÓ VẤN ĐỀ ({', '.join(failed)})")
        return 1
    print("[doctor] kết quả: TẤT CẢ ĐỀU ỔN")
    return 0


def handle_live():
    print("Chế độ live chưa hoàn thiện đầy đủ.")


def handle_stop():
    print("Đang dừng ứng dụng...")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auto Voice TikTok Shop LIVE CLI")
    subparsers = parser.add_subparsers(dest="command")

    p_sim = subparsers.add_parser("simulate", help="Mô phỏng sự kiện (không phát tiếng)")
    p_sim.add_argument("--no-play", action="store_true", help="Không phát tiếng ra loa")

    p_run = subparsers.add_parser("run", help="Vòng lặp thật: event -> TTS -> hàng đợi -> loa")
    p_run.add_argument("--bridge", default=DEFAULT_BRIDGE, help=f"URL bridge WebSocket (mặc định {DEFAULT_BRIDGE})")
    p_run.add_argument("--sim", action="store_true", help="Dùng simulator nội bộ thay vì bridge")
    p_run.add_argument("--speed", type=float, default=1.0, help="Hệ số tốc độ khi chạy --sim")
    p_run.add_argument("--seconds", type=float, default=0, help="Tự dừng sau N giây (0 = vô hạn)")
    p_run.add_argument("--max-events", type=int, default=0, help="Tự dừng sau N sự kiện")
    p_run.add_argument("--no-play", action="store_true", help="Chạy thử không phát tiếng (không mở loa)")

    p_run.add_argument("--browser-mode", choices=["extension", "gologin_cdp"], default=None, help="Chế độ kết nối trình duyệt (extension hoặc gologin_cdp)")
    p_run.add_argument("--cdp-port", type=int, default=30899, help="Cổng CDP remote debugging (mặc định 30899)")
    p_run.add_argument("--batch-window-s", type=float, default=None, help="Cửa sổ gom sự kiện (giây, mặc định 5.0)")
    p_run.add_argument("--batch-max-events", type=int, default=None, help="Số sự kiện tối đa mỗi batch (mặc định 10)")
    p_doc = subparsers.add_parser("doctor", help="Chẩn đoán VoiceStudio / LLM / loa / bridge / hàng đợi")
    p_doc.add_argument("--bridge", default=DEFAULT_BRIDGE)
    p_doc.add_argument("--window", type=float, default=2.0, help="Số giây nghe sự kiện từ bridge")

    p_doc.add_argument("--browser-mode", choices=["extension", "gologin_cdp"], default=None, help="Chế độ kết nối trình duyệt")
    p_doc.add_argument("--cdp-port", type=int, default=None, help="Cổng CDP remote debugging")
    subparsers.add_parser("live", help="Khởi chạy chế độ live")
    subparsers.add_parser("stop", help="Dừng ứng dụng")
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
