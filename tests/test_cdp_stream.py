"""Unit tests cho ket noi truc tiep GoLogin qua Chrome DevTools Protocol (CDP)."""
import io
import json
import os
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import app
import browser_manager as bm


def test_get_cdp_target_picks_tiktok_page():
    mock_targets = [
        {"type": "background_page", "url": "chrome-extension://...", "webSocketDebuggerUrl": "ws://1"},
        {"type": "page", "url": "https://google.com", "webSocketDebuggerUrl": "ws://google"},
        {
            "type": "page",
            "url": "https://shop.tiktok.com/streamer/live/product/dashboard",
            "webSocketDebuggerUrl": "ws://tiktok",
        },
    ]

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_targets).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        target = bm.get_cdp_target(cdp_port=30899)
        assert target is not None
        assert target["webSocketDebuggerUrl"] == "ws://tiktok"


def test_get_cdp_target_fallback_first_page():
    mock_targets = [
        {"type": "page", "url": "https://seller-us.tiktok.com", "webSocketDebuggerUrl": "ws://fallback"},
    ]
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_targets).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        target = bm.get_cdp_target(cdp_port=30899)
        assert target is not None
        assert target["webSocketDebuggerUrl"] == "ws://fallback"


def test_get_cdp_target_handles_error():
    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        target = bm.get_cdp_target(cdp_port=30899)
        assert target is None


def test_stream_cdp_events_yields_normalized_events():
    mock_target = {
        "type": "page",
        "url": "https://shop.tiktok.com",
        "webSocketDebuggerUrl": "ws://127.0.0.1:30899/devtools/page/test",
    }

    raw_events = [
        {"type": "chat", "user": "Bao Anh", "content": "Áo này có màu đen không shop?", "ts": 1700000000},
        {"type": "order", "user": "Minh Khang", "content": "Cam on Minh Khang da dat hang", "ts": 1700000001},
    ]

    class MockWebSocket:
        def __init__(self):
            self.call_count = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def send(self, data):
            pass

        def recv(self):
            self.call_count += 1
            if self.call_count == 1:
                # Response cho setup script
                return json.dumps({"id": 1, "result": {}})
            elif self.call_count == 2:
                # Response cho poll events
                return json.dumps({
                    "id": 2,
                    "result": {"result": {"value": json.dumps(raw_events)}},
                })
            else:
                # Poll tiep theo: rong
                return json.dumps({
                    "id": 3,
                    "result": {"result": {"value": "[]"}},
                })

    stop_event = threading.Event()

    with patch.object(bm, "get_cdp_target", return_value=mock_target):
        with patch("websockets.sync.client.connect", return_value=MockWebSocket()):
            generator = bm.stream_cdp_events(stop_event, cdp_port=30899, poll_interval_s=0.01)

            ev1 = next(generator)
            assert ev1["type"] == "chat"
            assert ev1["user"] == "Bao Anh"
            assert ev1["text"] == "Áo này có màu đen không shop?"

            ev2 = next(generator)
            assert ev2["type"] == "order"
            assert ev2["user"] == "Minh Khang"

            stop_event.set()


def test_app_stream_events_routes_to_gologin_cdp():
    stop_event = threading.Event()
    args = MagicMock()
    args.sim = False
    args.browser_mode = "gologin_cdp"
    args.cdp_port = 30899

    fake_events = [{"type": "chat", "user": "TestUser", "text": "Hello CDP", "ts": 123}]

    with patch.object(bm, "stream_cdp_events", return_value=iter(fake_events)):
        evs = list(app._stream_events(args, stop_event))
        assert len(evs) == 1
        assert evs[0]["text"] == "Hello CDP"
