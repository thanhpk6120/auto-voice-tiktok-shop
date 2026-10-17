"""Test E2E that cho pipeline: event -> analyzer -> tts -> hang doi -> player (fake)."""
from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from audio_queue import PriorityAudioQueue  # noqa: E402


def _fake_player(delay: float, log: list, name: str):
    def play(wav, stop_event) -> bool:
        log.append(("start", name, time.monotonic()))
        t0 = time.monotonic()
        while time.monotonic() - t0 < delay:
            if stop_event is not None and stop_event.is_set():
                log.append(("interrupted", name, time.monotonic()))
                return False
            time.sleep(0.01)
        log.append(("end", name, time.monotonic()))
        return True

    return play


def test_worker_plays_in_priority_order():
    log: list = []
    q = PriorityAudioQueue(on_play=_fake_player(0.05, log, "x"))
    q._on_play = lambda wav, stop: (log.append(("play", wav, time.monotonic())), time.sleep(0.02), True)[-1]
    q.start()
    q.put("greeting", 3, "hi", "g.wav")
    q.put("order", 1, "thanks", "o.wav")
    time.sleep(0.5)
    q.stop()
    played = [w for (a, w, _) in log if a == "play"]
    assert played[:2] == ["o.wav", "g.wav"], played
    assert q.stats["played"] == 2


def test_interrupt_when_priority1_arrives():
    """p1 (order) den khi dang phat p3 (greeting) -> item dang phat bi ngat."""
    log: list = []
    q = PriorityAudioQueue(on_play=_fake_player(2.0, log, "greeting"), interrupt_mode="interrupt")
    q.start()
    q.put("greeting", 3, "cau chao dai", "g.wav")
    time.sleep(0.3)  # de worker bat dau phat
    assert q.current() is not None and q.current()["priority"] == 3
    q.put("order", 1, "cam on don", "o.wav")
    time.sleep(0.6)
    q.stop()
    kinds = [entry[0] for entry in log]
    assert "interrupted" in kinds, log
    assert q.stats["interrupted"] == 1, q.stats


def test_no_interrupt_on_priority2():
    """p2 (chat) khong duoc phep ngat p1 dang phat, va p1 khong ngat p2."""
    log: list = []
    q = PriorityAudioQueue(on_play=_fake_player(0.3, log, "chat"), interrupt_mode="interrupt")
    q.start()
    q.put("sales", 2, "tu van", "s.wav")
    time.sleep(0.1)
    q.put("gift", 1, "cam on qua", "o.wav")
    time.sleep(1.2)
    q.stop()
    assert q.stats["interrupted"] == 1, q.stats  # p2 bi p1 ngat
    assert q.stats["played"] == 1  # p1 phat tron ven


def test_dry_run_does_not_call_player():
    calls = []
    q = PriorityAudioQueue(on_play=lambda w, s: calls.append(w) or True, dry_run=True)
    q.start()
    q.put("order", 1, "thanks", "o.wav")
    time.sleep(0.4)
    q.stop()
    assert calls == []
    assert q.stats["played"] == 1


def test_overflow_drops_low_priority():
    q = PriorityAudioQueue(dry_run=True)
    for i in range(60):
        q.put("greeting", 3, f"hi{i}", f"{i}.wav")
    assert q.qsize() <= 51
    assert q.stats["dropped_overflow"] > 0
