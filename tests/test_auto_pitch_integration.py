"""Kiểm thử tích hợp thực tế: AutoPitchManager + tts_client.synthesize + PriorityAudioQueue."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "src"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import audio_player  # noqa: E402
import tts_client  # noqa: E402
from audio_queue import PriorityAudioQueue  # noqa: E402
from auto_pitch import AutoPitchManager  # noqa: E402


def test_synthesize_supports_out_path():
    with tempfile.TemporaryDirectory() as tmp_dir:
        target = Path(tmp_dir) / "custom_sub" / "custom_test.wav"
        out = tts_client.synthesize("Xin chào TikTok Shop", out_path=str(target))
        assert Path(out).is_file()
        assert Path(out).resolve() == target.resolve()
        assert Path(out).stat().st_size > 44  # WAV header + audio frames


def test_auto_pitch_e2e_with_real_synthesize_and_audio_queue():
    with tempfile.TemporaryDirectory() as tmp_prods, tempfile.TemporaryDirectory() as tmp_cache:
        p_dir = Path(tmp_prods)
        c_dir = Path(tmp_cache)

        # Tạo sản phẩm giả lập
        for i in range(3):
            (p_dir / f"sp-0{i}.md").write_text(
                f"# Bánh quy socola {i}\nGiá ưu đãi: 25.000đ\nNgon giòn", encoding="utf-8"
            )

        mgr = AutoPitchManager(
            context_live_dir=p_dir,
            context_dir=p_dir,
            cache_dir=c_dir,
            buffer_size=2,
            min_s=5.0,
            max_s=10.0,
        )

        # 1. Refill dùng tts_client.synthesize thật (tạo wav sine-fallback hợp lệ)
        mgr.trigger_refill(tts_client.synthesize)
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and mgr.buffer_count < 2:
            time.sleep(0.05)
        assert mgr.buffer_count == 2
        cached_wavs = list(c_dir.glob("pitch_*.wav"))
        assert len(cached_wavs) == 2
        for w in cached_wavs:
            assert w.is_file() and w.stat().st_size > 44

        # 2. Setup PriorityAudioQueue thật giống hệt app.py
        played_items = []

        def on_audio_finish(item):
            played_items.append(item)
            if item and item.get("kind") == "auto_pitch":
                mgr.on_pitch_finished(item, tts_client.synthesize)

        queue = PriorityAudioQueue(
            on_play=audio_player.noop_play,
            on_finish=on_audio_finish,
            dry_run=True,
            interrupt_mode="finish",
            post_speech_padding_s=0.08,
        ).start()

        # 3. Lấy 1 voice từ buffer đẩy vào queue
        p_item = mgr.pop_pitch()
        assert p_item is not None
        assert mgr.buffer_count == 1
        wav_to_play = Path(p_item.get("wav_path") or p_item.get("wav"))
        assert wav_to_play.is_file()

        # Đẩy vào queue với payload chuẩn của app.py (key 'wav')
        queue.put("auto_pitch", 3, p_item["speak_text"], wav_to_play)

        # Đợi queue phát xong
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and len(played_items) < 1:
            time.sleep(0.05)
        queue.stop()
        assert len(played_items) == 1
        assert played_items[0]["kind"] == "auto_pitch"

        # 4. Kiểm tra file wav vừa phát đã được dọn sạch
        assert not wav_to_play.is_file()

        # 5. Kiểm tra buffer được refill bù lại đủ 2
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and mgr.buffer_count < 2:
            time.sleep(0.05)
        assert mgr.buffer_count == 2
