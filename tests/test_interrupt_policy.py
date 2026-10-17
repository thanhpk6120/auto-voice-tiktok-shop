"""Tests cho chinh sach ngat audio (interrupt_mode: finish vs interrupt) va co che requeue."""
from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from audio_queue import PriorityAudioQueue  # noqa: E402
import settings  # noqa: E402


def test_finish_mode_plays_all_without_interrupt():
    """Che do 'finish' (mac dinh): dang phat p3 dai, put p1 -> p3 phat HET, roi p1 moi phat."""
    p3_started = threading.Event()
    p3_finish = threading.Event()
    played: list[str] = []

    def fake_player(wav, stop_event) -> bool:
        if wav == "p3.wav":
            p3_started.set()
            p3_finish.wait(timeout=2.0)
            played.append(wav)
            return True
        if wav == "p1.wav":
            played.append(wav)
            return True
        return True

    q = PriorityAudioQueue(on_play=fake_player, interrupt_mode="finish").start()
    try:
        q.put("greeting", 3, "cau chao dai", "p3.wav")
        assert p3_started.wait(timeout=2.0), "p3 khong bat dau dung han"
        assert q.current() is not None and q.current()["priority"] == 3

        q.put("order", 1, "cam on don hang", "p1.wav")
        time.sleep(0.05)
        p3_finish.set()

        t0 = time.monotonic()
        while len(played) < 2 and time.monotonic() - t0 < 2.0:
            time.sleep(0.02)
    finally:
        q.stop()

    assert q.stats["interrupted"] == 0, q.stats
    assert q.stats["played"] == 2, q.stats
    assert played == ["p3.wav", "p1.wav"]


def test_interrupt_mode_drops_current_item():
    """Che do 'interrupt': dang phat p3, put p1 -> p3 bi bo khi stop_event set, chi p1 phat."""
    p3_started = threading.Event()
    played: list[str] = []

    def fake_player(wav, stop_event) -> bool:
        if wav == "p3.wav":
            p3_started.set()
            t0 = time.monotonic()
            while time.monotonic() - t0 < 2.0:
                if stop_event is not None and stop_event.is_set():
                    return False
                time.sleep(0.01)
            played.append(wav)
            return True
        if wav == "p1.wav":
            played.append(wav)
            return True
        return True

    q = PriorityAudioQueue(on_play=fake_player, interrupt_mode="interrupt").start()
    try:
        q.put("greeting", 3, "cau chao dai", "p3.wav")
        assert p3_started.wait(timeout=2.0), "p3 khong bat dau dung han"
        assert q.current() is not None and q.current()["priority"] == 3

        q.put("order", 1, "cam on don hang", "p1.wav")
        t0 = time.monotonic()
        while len(played) < 1 and time.monotonic() - t0 < 2.0:
            time.sleep(0.02)
    finally:
        q.stop()

    assert q.stats["interrupted"] == 1, q.stats
    assert q.stats["played"] == 1, q.stats
    assert played == ["p1.wav"]


def test_requeue_drops_after_two_retries():
    """Test requeue khong vo han: player gia luon tra False -> item bi bo sau 2 lan requeue."""
    calls: list[str] = []

    def fake_player(wav, stop_event) -> bool:
        calls.append(wav)
        return False

    q = PriorityAudioQueue(on_play=fake_player, interrupt_mode="finish").start()
    try:
        q.put("greeting", 3, "chao", "fail.wav")
        t0 = time.monotonic()
        while q.stats["dropped_requeue"] < 1 and time.monotonic() - t0 < 2.0:
            time.sleep(0.02)
    finally:
        q.stop()

    assert len(calls) == 3, f"Goi player 3 lan (1 goc + 2 requeue), thuc te: {len(calls)}"
    assert q.stats["requeued"] == 2, q.stats
    assert q.stats["dropped_requeue"] >= 1, q.stats
    assert q.stats["dropped_requeue"] == 1, q.stats
    assert q.stats["interrupted"] == 3, q.stats
    assert q.stats["played"] == 0, q.stats


def test_settings_apply_sets_interrupt_mode_env():
    """settings.apply() phai set bien moi truong INTERRUPT_MODE."""
    cfg = settings.get()
    cfg["interrupt_mode"] = "interrupt"
    settings.apply(cfg)
    assert os.environ.get("INTERRUPT_MODE") == "interrupt"

    cfg["interrupt_mode"] = "finish"
    settings.apply(cfg)
    assert os.environ.get("INTERRUPT_MODE") == "finish"
