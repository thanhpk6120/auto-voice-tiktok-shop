import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import gui  # noqa: E402
import settings  # noqa: E402


def test_import_ok():
    assert hasattr(gui, "main")
    assert callable(gui.main)
    assert gui.TITLE == "Auto Voice TikTok Shop - Cấu hình"


def test_build_form_covers_sections():
    cfg = settings.load()
    form = gui.build_form(settings.SECTIONS, cfg, settings.SECRET_KEYS)

    assert [s["section"] for s in form] == list(settings.SECTIONS)
    flat = {f["key"]: f for s in form for f in s["fields"]}
    assert set(flat) == {k for keys in settings.SECTIONS.values() for k in keys}

    # api key che, khong lo gia tri that
    assert flat["llm_api_key"]["secret"] is True
    assert flat["llm_model"]["secret"] is False

    # kieu widget dung theo default
    assert flat["no_play"]["kind"] == "bool"
    assert flat["bridge_port"]["kind"] == "number"
    assert flat["greeting_cooldown_s"]["kind"] == "number"
    assert flat["llm_base_url"]["kind"] == "text"
    assert flat["audio_device"]["value"] == cfg["audio_device"]


def test_coerce_value():
    assert gui.coerce_value("true", False) is True
    assert gui.coerce_value("0", True) is False
    assert gui.coerce_value(" 8765 ", 8765) == 8765
    assert gui.coerce_value("3.5", 3.0) == 3.5
    assert gui.coerce_value(" ws://x ", "y") == "ws://x"
    try:
        gui.coerce_value("abc", 1)
    except ValueError:
        pass
    else:
        raise AssertionError("so sai dinh dang phai raise ValueError")


def test_device_spec_roundtrip():
    dev = {"index": 12, "name": "Headset Earphone (2- G435)"}
    label = gui.device_label(dev)
    assert label == "12: Headset Earphone (2- G435)"
    assert gui.device_spec(label) == "12"
    assert gui.device_spec("Headset Earphone") == "Headset Earphone"
    assert gui.device_spec("") == ""


def test_safe_devices_never_raises():
    devs = gui.safe_devices()
    assert isinstance(devs, list)
    for d in devs:
        assert "index" in d and "name" in d
