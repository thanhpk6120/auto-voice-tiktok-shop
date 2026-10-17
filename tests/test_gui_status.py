from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gui import StatusCounters, parse_event_line  # noqa: E402


def test_parse_event_line_real_sample():
    # Copy nguyen van 1 dong thuc te tu log app/simulation
    line = (
        "[app] event=chat -> speak_text='Shop chưa có dữ liệu size cho áo này' "
        "-> wav=tts_1792223195749_fa18591f.wav -> priority=2 -> queue-size=7"
    )
    parsed = parse_event_line(line)
    assert parsed is not None
    assert parsed["event"] == "chat"
    assert parsed["speak_text"] == "Shop chưa có dữ liệu size cho áo này"
    assert parsed["priority"] == 2
    assert parsed["queue_size"] == 7


def test_parse_event_line_non_matching():
    non_matches = [
        "",
        "[app] Starting simulation... (no_play=True)",
        "[app] tiến trình kết thúc (exit=0)",
        "config: C:\\Users\\Thanh\\AppData\\Local\\AutoVoiceTikTokShop\\settings.json",
        "--- doctor ---",
        "queue: {'played': 3, 'interrupted': 0, 'dropped_overflow': 0}",
    ]
    for line in non_matches:
        assert parse_event_line(line) is None, f"Expected None for: {line}"


def test_parse_event_line_variations():
    # Nhay kep va khong co priority (join flush)
    line1 = (
        "[app] event=join(flushed) -> speak_text=\"What'up Minh Tuấn!\" "
        "-> wav=tts_1.wav -> queue-size=7"
    )
    p1 = parse_event_line(line1)
    assert p1 is not None
    assert p1["event"] == "join(flushed)"
    assert p1["speak_text"] == "What'up Minh Tuấn!"
    assert p1["priority"] is None
    assert p1["queue_size"] == 7

    # Khong co tag [app], co [no-play]
    line2 = (
        "event=gift -> speak_text='Cảm ơn bạn đã tặng quà' "
        "-> wav=tts_2.wav -> priority=1 -> queue-size=3 [no-play]"
    )
    p2 = parse_event_line(line2)
    assert p2 is not None
    assert p2["event"] == "gift"
    assert p2["speak_text"] == "Cảm ơn bạn đã tặng quà"
    assert p2["priority"] == 1
    assert p2["queue_size"] == 3


def test_status_counters_counts_by_type_and_final_queue_size():
    counters = StatusCounters()

    lines = [
        "[app] event=chat -> speak_text='Hello shop' -> wav=1.wav -> priority=2 -> queue-size=1",
        "[app] event=chat -> speak_text='Giá bao nhiêu' -> wav=2.wav -> priority=2 -> queue-size=2",
        "[app] event=gift -> speak_text='Cảm ơn bông hoa' -> wav=3.wav -> priority=1 -> queue-size=3",
        "[app] event=order -> speak_text='Chốt đơn thành công' -> wav=4.wav -> priority=1 -> queue-size=4",
        "[app] event=join -> speak_text='Chào Minh' -> wav=5.wav -> priority=3 -> queue-size=5",
        "[app] event=join(flushed) -> speak_text='Chào các bạn' -> wav=6.wav -> queue-size=9",
    ]

    for line in lines:
        counters.feed(line)

    snap = counters.snapshot()

    assert snap["events"]["chat"] == 2
    assert snap["events"]["gift"] == 1
    assert snap["events"]["order"] == 1
    # join va join(flushed) gop vao 'join'
    assert snap["events"]["join"] == 2
    assert snap["total_events"] == 6
    assert snap["queue_size"] == 9  # queue_size cuoi cung


def test_status_counters_stats_and_reset():
    counters = StatusCounters()
    counters.feed("[app] event=chat -> speak_text='Hi' -> wav=1.wav -> priority=2 -> queue-size=2")
    counters.feed("queue: {'played': 5, 'interrupted': 2, 'dropped_overflow': 1}")

    snap = counters.snapshot()
    assert snap["played"] == 5
    assert snap["interrupted"] == 2
    assert snap["dropped"] == 1

    counters.reset()
    snap_after = counters.snapshot()
    assert snap_after["total_events"] == 0
    assert snap_after["queue_size"] == 0
    assert snap_after["played"] == 0
    assert snap_after["interrupted"] == 0
    assert snap_after["dropped"] == 0


def test_gui_notebook_tabs_and_actions():
    import gui
    import settings

    if gui.tk is None:
        import pytest
        pytest.skip("Tkinter not available in this environment")

    try:
        root = gui.tk.Tk()
    except Exception:
        import pytest
        pytest.skip("Cannot create Tk display")

    try:
        root.withdraw()
        app = gui.App(root, settings.DEFAULTS)

        # Xac nhan cac tab trong Notebook
        tab_names = [app.nb.tab(t, "text") for t in app.nb.tabs()]
        assert "Trạng thái" in tab_names
        assert "Log đang chạy" in tab_names
        assert set(settings.SECTIONS.keys()).issubset(set(tab_names))

        # Kiem tra toolbar log
        assert hasattr(app, "clear_log")
        assert hasattr(app, "copy_log")
        assert hasattr(app, "open_log_dir")
        assert hasattr(app, "autoscroll_var")
        assert hasattr(app, "log_filter_var")

        # Test luong log va filter
        app._write("[app] log dong 1")
        app._write("[doctor] log dong 2")
        app._poll_log()

        content = app.log.get("1.0", "end-1c")
        assert "[app] log dong 1" in content
        assert "[doctor] log dong 2" in content

        app.log_filter_var.set("[app]")
        app._on_filter_changed()
        filtered = app.log.get("1.0", "end-1c")
        assert "[app] log dong 1" in filtered
        assert "[doctor] log dong 2" not in filtered

        app.clear_log()
        assert app.log.get("1.0", "end-1c") == ""

        # Test cap nhat trang thai
        app.status_counters.feed(
            "[app] event=chat -> speak_text='test' -> wav=1.wav -> priority=2 -> queue-size=5"
        )
        app._update_status_ui()
        assert app.stat_chat_var.get() == "1"
        assert app.stat_qsize_var.get() == "5"
    finally:
        root.destroy()
