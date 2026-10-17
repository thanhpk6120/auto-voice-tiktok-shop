"""Test event_bridge: normalize + hub + server/client that (khong can extension)."""
from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import event_bridge as eb  # noqa: E402


def test_normalize_accepts_valid_types():
    ev = eb.normalize('{"type":"Chat","user":"Lan","text":"gia bao nhieu"}')
    assert ev["type"] == "chat"
    assert ev["user"] == "Lan"
    assert "ts" in ev


def test_normalize_rejects_junk():
    assert eb.normalize("khong phai json") is None
    assert eb.normalize('{"type":"unknown_type"}') is None
    assert eb.normalize(12345) is None
    assert eb.normalize(b'{"type":"gift","user":"a"}')["type"] == "gift"


def test_hub_feed_and_next_event():
    hub = eb.Hub()
    hub.feed({"type": "order", "user": "a"})
    assert hub.received == 1
    assert hub.next_event(1.0)["type"] == "order"
    assert hub.next_event(0.05) is None


def test_server_client_roundtrip():
    stop = threading.Event()
    eb.serve(host="127.0.0.1", port=8123, sim=True, speed=0.05, stop=stop)
    time.sleep(0.5)
    got = []
    try:
        for ev in eb.iter_events("ws://127.0.0.1:8123/ws?role=app", stop_event=stop, recv_timeout=1.0):
            got.append(ev)
            if len(got) >= 2:
                break
    finally:
        stop.set()
    assert len(got) >= 2, got
    assert {"type", "ts"}.issubset(got[0].keys())
