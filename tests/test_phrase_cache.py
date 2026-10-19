"""Kiểm thử chống lặp câu chào/remind: cache 10 câu gần nhất + 9 biến thể remind."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture()
def cache_dir(monkeypatch):
    import tempfile

    tmp = tempfile.TemporaryDirectory()   # Tranh tmp_path: Temp cua pytest bi chan quyen tren may nay
    monkeypatch.setenv("PHRASE_CACHE_DIR", tmp.name)
    import phrase_cache

    try:
        yield phrase_cache
    finally:
        tmp.cleanup()


def test_remember_keeps_only_10_latest(cache_dir):
    for i in range(13):
        cache_dir.remember("greeting", f"Câu số {i}")
    items = cache_dir.recent("greeting")
    assert len(items) == 10
    assert items[0] == "Câu số 3"
    assert items[-1] == "Câu số 12"


def test_avoid_block_lists_recent_and_empty_when_cold(cache_dir):
    assert cache_dir.avoid_block("greeting") == ""
    cache_dir.remember("greeting", "Xin chào Minh Tuấn, sóp vui lắm!")
    block = cache_dir.avoid_block("greeting")
    assert "Xin chào Minh Tuấn, sóp vui lắm!" in block
    assert "KHÔNG" in block


def test_pick_unused_prefers_fresh_candidate(cache_dir):
    pool = ["Câu A", "Câu B", "Câu C"]
    cache_dir.remember("greeting", "câu a")
    for _ in range(5):
        picked = cache_dir.pick_unused("greeting", pool)
        assert picked != "Câu A"


def test_is_repeat_ignores_punctuation_and_case(cache_dir):
    cache_dir.remember("remind", "Mọi người ơi, nhớ thả tim cho SÓP nhé!")
    assert cache_dir.is_repeat("remind", "mọi người ơi nhớ thả tim cho sóp nhé")
    assert not cache_dir.is_repeat("remind", "Câu hoàn toàn khác")


def test_remind_pool_has_10_variants_and_no_immediate_repeat(cache_dir, monkeypatch):
    import remind_text

    def fake_llm_chat(system, user):
        return "\n".join(f"Câu nhắc biến thể số {i}, cả nhà thả tim cho sóp nha." for i in range(1, 10))

    import llm_client

    monkeypatch.setattr(llm_client, "chat", fake_llm_chat)
    base = "Mọi người xem lai nhớ cho sốp xin một tim và com men sản phẩm cần tư vấn nhé"
    items = remind_text.pool(base)
    assert len(items) == 10
    assert items[0] == base
    assert len(set(items)) == 10

    picked = [remind_text.pick(base) for _ in range(9)]
    assert len(set(picked)) == len(picked), picked


def test_greeting_batcher_avoids_repeating_template(cache_dir):
    import event_analyzer

    batcher = event_analyzer.GreetingBatcher(cooldown=0.0, max_batch=1, user_cooldown=0.0)
    seen = []
    for i in range(4):
        text = batcher.add(f"Khách {i}")   # max_batch=1 -> add() flush va tra ve cau chao
        if text:
            seen.append(text)
    assert len(seen) == 4
    assert len(set(seen)) == 4, seen


def test_cache_file_is_json_list_on_disk(cache_dir):
    cache_dir.remember("greeting", "Xin chào A")
    path = cache_dir._store_path("greeting")
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8")) == ["Xin chào A"]
