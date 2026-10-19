"""Kiem thu resolve giong VoiceStudio: ten profile -> voice_id, va canh bao ten sai.

Bug goc: VoiceStudio 0.5.6 chi nhan voice_id cua profile trong `/v1/audio/speech`.
Truyen ten (`SonTungMTP`) khong gay loi — no lang le doc bang giong MAC DINH.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import tts_client


@pytest.fixture()
def fake_voices(monkeypatch):
    """Gia lap /v1/audio/voices: 2 alias + 1 profile ten 'SonTungMTP'."""
    info = {
        "url": tts_client.VOICE_URL,
        "aliases": {"alloy", "onyx"},
        "by_name": {"sontungmtp": "ef920857"},
        "profiles": [{"voice_id": "ef920857", "name": "SonTungMTP", "type": "profile"}],
    }
    monkeypatch.setattr(tts_client, "list_voices", lambda force=False: info)
    return info


def test_profile_name_resolves_to_id(fake_voices):
    assert tts_client.resolve_voice("SonTungMTP") == ("ef920857", "")
    assert tts_client.resolve_voice("sontungmtp") == ("ef920857", "")


def test_profile_id_passes_through_without_warning(fake_voices):
    assert tts_client.resolve_voice("ef920857") == ("ef920857", "")


def test_openai_alias_passes_through(fake_voices):
    assert tts_client.resolve_voice("alloy") == ("alloy", "")
    assert tts_client.resolve_voice("") == ("default", "")


def test_unknown_name_warns_about_default_voice(fake_voices):
    vid, warn = tts_client.resolve_voice("KhongTonTai")
    assert vid == "KhongTonTai"
    assert "MAC DINH" in warn
    assert "ef920857" in warn


def test_gui_label_form_is_accepted(fake_voices):
    """Dropdown GUI hien 'SonTungMTP  <ef920857>' -> phai lay dung voice_id."""
    assert tts_client.resolve_voice("SonTungMTP  <ef920857>") == ("ef920857", "")


def test_no_voices_endpoint_keeps_raw_value(monkeypatch):
    """VoiceStudio tat / khong doc duoc danh sach -> khong doan, giu nguyen gia tri."""
    empty = {"url": tts_client.VOICE_URL, "aliases": set(), "by_name": {}, "profiles": []}
    monkeypatch.setattr(tts_client, "list_voices", lambda force=False: empty)
    assert tts_client.resolve_voice("SonTungMTP") == ("SonTungMTP", "")
