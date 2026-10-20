"""Test cho json_utils, intent_router, prompt only-JSON và context-live dedupe."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import json_utils  # noqa: E402
import intent_router  # noqa: E402


# ----------------------------- json_utils -----------------------------

def test_parse_json_loose_handles_llm_mistakes():
    cases = [
        ('{"intent":"greeting"}', {"intent": "greeting"}),
        ('```json\n{"intent": "greeting"}\n```', {"intent": "greeting"}),
        ('Lời dẫn:\n```json\n{"a":1}\n```\nHết.', {"a": 1}),
        ("{ intent: 'greeting', confidence: 0.9 }", {"intent": "greeting", "confidence": 0.9}),
        ('{"a":1,}', {"a": 1}),
        ('[{"t":"g"},{"t":"c"},]', [{"t": "g"}, {"t": "c"}]),
        ('{"ok": True, "n": None}', {"ok": True, "n": None}),
        ('\ufeff{"intent":"greeting"}', {"intent": "greeting"}),
        ('{\u201cintent\u201d: \u201cgreeting\u201d}', {"intent": "greeting"}),
        ('{"text": "dòng một\ndòng hai"}', {"text": "dòng một\ndòng hai"}),
        ('{"n": "có { } trong chuỗi"}', {"n": "có { } trong chuỗi"}),
        ('{"intent":"greeting"} thừa chữ', {"intent": "greeting"}),
    ]
    for src, want in cases:
        assert json_utils.parse_json_loose(src) == want, src


def test_parse_json_loose_returns_default_on_garbage():
    assert json_utils.parse_json_loose("không có json", default={"fb": 1}) == {"fb": 1}
    assert json_utils.parse_json_loose("", default=None) is None


def test_json_helpers_tolerate_odd_keys_and_types():
    assert json_utils.as_list({"items": [{"a": 1}]}) == [{"a": 1}]
    assert json_utils.as_list({"type": "greeting"}) == [{"type": "greeting"}]
    assert json_utils.as_dict([{"k": "v"}]) == {"k": "v"}
    assert json_utils.get_str({"Tên": "Sóp"}, "name", "tên") == "Sóp"
    assert json_utils.get_int({"priority": "3"}, "priority") == 3
    assert json_utils.get_bool({"is_pinned": "không"}, "is_pinned") is False
    assert json_utils.get_bool({"is_pinned": "có"}, "is_pinned") is True


# ----------------------------- intent_router -----------------------------

def test_classify_intent_rules_matches_expected_intents():
    cases = [
        ("alo shop ơi", "greeting"),
        ("chào shop", "greeting"),
        ("shop ơi size XL còn không", "product_question"),
        ("áo thun này giá bao nhiêu shop", "product_question"),
        ("mã 1 còn hàng không", "product_question"),
        ("mình chốt đơn áo thun nhé", "order"),
        ("cảm ơn shop đã tặng quà", "gift"),
        ("hôm nay trời đẹp nhỉ", "other"),
    ]
    for text, want in cases:
        got = intent_router.classify_intent_rules(text)
        assert got["intent"] == want, f"{text} -> {got}"
        assert got["source"] == "rule"


def test_classify_intent_falls_back_to_rules_when_no_model():
    got = intent_router.classify_intent("shop ơi áo thun giá bao nhiêu", products=[], model="")
    assert got["source"] == "rule"
    assert got["intent"] == "product_question"


def test_prompt_mapping_and_labels():
    assert intent_router.prompt_for_intent("greeting") == "system_greeting"
    assert intent_router.prompt_for_intent("product_question") == "system_sales"
    assert intent_router.prompt_for_intent("order") == "system_order"
    assert intent_router.prompt_for_intent("gift") == "system_gift"
    assert intent_router.prompt_for_intent("chat") == "system_chat"
    assert intent_router.prompt_for_intent("lạ_lùng") == "system_chat"
    for k in intent_router.VALID_INTENTS:
        assert intent_router.intent_label(k)


def test_parse_speak_reply_reads_json_and_survives_plain_text():
    ok = intent_router.parse_speak_reply(
        '```json\n{"speak_text":"Xin chào cả nhà","kind":"greeting","priority":3}\n```'
    )
    assert ok == {"speak_text": "Xin chào cả nhà", "kind": "greeting", "priority": 3}

    loose = intent_router.parse_speak_reply(
        '{ speak_text: "Chào bạn", kind: greeting, priority: 3 }'
    )
    assert loose["speak_text"] == "Chào bạn"
    assert loose["kind"] == "greeting"

    plain = intent_router.parse_speak_reply("Chào bạn nhé, sóp đây ạ!")
    assert plain["speak_text"] == "Chào bạn nhé, sóp đây ạ!"
    assert plain["kind"] == "chat"


def test_build_speak_prompt_forces_only_json():
    sysp = intent_router.build_speak_prompt("NỘI DUNG GỐC", "sales", 2)
    assert "NỘI DUNG GỐC" in sysp
    low = sysp.lower()
    assert "json" in low
    assert "speak_text" in sysp
    assert '"kind": "sales"' in sysp
    assert '"priority": 2' in sysp


# ----------------------------- prompts -----------------------------

def test_every_prompt_demands_only_json_with_sample():
    from event_analyzer import get_prompt

    pdir = ROOT / "prompts"
    names = [f.stem for f in pdir.glob("*.md") if f.name.lower() != "readme.md"]
    assert names, "khong tim thay prompt nao"
    for name in names:
        content = get_prompt(name, prompts_dir=pdir)
        low = content.lower()
        assert "json" in low, f"{name} thiếu yêu cầu JSON"
        assert "{" in content and "}" in content, f"{name} thiếu JSON mẫu"
        assert ("chỉ trả về" in low) or ("chi tra ve" in low), f"{name} thiếu ràng buộc only-JSON"


def test_prompts_are_vietnamese_with_diacritics():
    pdir = ROOT / "prompts"
    for f in pdir.glob("*.md"):
        if f.name.lower() == "readme.md":
            continue
        content = f.read_text(encoding="utf-8")
        assert any(c in content for c in "ăâđêôơưáàảãạấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"), (
            f"{f.name} không có dấu tiếng Việt"
        )


# ----------------------------- context-live -----------------------------

def test_save_product_context_dedupes_by_id_and_name():
    import browser_manager

    with tempfile.TemporaryDirectory() as td:
        prod = {
            "index": 1,
            "id": "123456789",
            "name": "Áo thun nam Cotton Compact",
            "price": "150.000₫",
            "description": "Cotton 100%",
            "reviews": ["Đẹp lắm", "Giao nhanh"],
        }
        p1 = browser_manager.save_product_context(prod, live_dir=td)
        p2 = browser_manager.save_product_context(prod, live_dir=td)
        assert p1 is not None and p2 is not None
        assert p1 == p2, "trùng tên + id phải đè lên cùng một file"
        md_files = [f for f in Path(td).glob("*.md")]
        assert len(md_files) == 1, [f.name for f in md_files]

        # Khác tên -> coi là sản phẩm khác -> tạo file mới
        p3 = browser_manager.save_product_context({**prod, "name": "Áo thun nữ"}, live_dir=td)
        assert p3 is not None and p3 != p1
        assert len(list(Path(td).glob("*.md"))) == 2

        content = p1.read_text(encoding="utf-8")
        assert "123456789" in content
        assert "Cotton 100%" in content
        assert "Đẹp lắm" in content


def test_save_product_context_index_tracks_files():
    import browser_manager

    with tempfile.TemporaryDirectory() as td:
        browser_manager.save_product_context(
            {"index": 2, "id": "987654321", "name": "Tai nghe Bass Boost"}, live_dir=td
        )
        idx = json.loads((Path(td) / "_index.json").read_text(encoding="utf-8"))
        assert any("987654321" in k for k in idx), idx


def test_chat_intent_reads_saved_product_context():
    import browser_manager
    from event_analyzer import ChatIntent

    with tempfile.TemporaryDirectory() as td:
        browser_manager.save_product_context(
            {
                "index": 1,
                "id": "555666777",
                "name": "Kem dưỡng ẩm Water Gel",
                "price": "350.000₫",
                "description": "Cấp ẩm sâu",
                "reviews": ["Thơm mát"],
            },
            live_dir=td,
        )
        it = ChatIntent(context_dir=str(ROOT / "context-data"), live_dir=td)
        matched = it.match("shop ơi kem dưỡng ẩm giá bao nhiêu")
        assert matched is not None
        assert "Water Gel" in matched["name"]
        assert matched.get("live") is True


# ----------------------------- crawl fallbacks -----------------------------

def test_crawl_helpers_degrade_gracefully_without_browser():
    import browser_manager

    assert browser_manager.fetch_live_products_cdp(cdp_port=1) == []

    empty = browser_manager.crawl_product_detail_cdp("", cdp_port=1)
    assert sorted(empty.keys()) == ["description", "id", "name", "reviews", "url"]
    assert empty["reviews"] == []

    empty2 = browser_manager.crawl_product_detail_cdp("https://example.com", cdp_port=1)
    assert sorted(empty2.keys()) == ["description", "id", "name", "reviews", "url"]
    assert empty2["reviews"] == []


def test_slugify_handles_vietnamese_diacritics():
    import browser_manager

    assert browser_manager._slugify_product("Áo thun nam Cotton Compact") == "ao-thun-nam-cotton-compact"
    assert browser_manager._slugify_product("Kem dưỡng da cấp ẩm Water Gel") == "kem-duong-da-cap-am-water-gel"
    assert browser_manager._slugify_product("") == "san-pham"
    assert browser_manager._slugify_product("!!!") == "san-pham"


# ----------------------------- batch JSON -----------------------------

def test_batch_parse_uses_lenient_json():
    from batch_processor import parse_llm_json_response

    assert len(parse_llm_json_response(
        '```json\n[{"type":"greeting","user":"A","text":"Chào bạn","priority":3}]\n```'
    )) == 1
    assert len(parse_llm_json_response(
        "[{'type':'chat','user':'C','text':'Hê lô','priority':2}]"
    )) == 1
    assert len(parse_llm_json_response(
        '[{"type": sales, "user": "D", "text": "Tư vấn nhé", "priority": 2}]'
    )) == 1
    assert parse_llm_json_response("không có json") == []


def test_analyst_model_config_exists():
    import settings

    assert "analyst_llm_model" in settings.DEFAULTS
    assert "analyst_llm_model" in settings.SECTIONS["LLM"]
    assert "analyst_llm_model" in settings.FIELD_DOCS
    assert "analyst_llm_timeout_s" in settings.DEFAULTS


# ----------------------------- hành vi ghi đè / tên file -----------------------------

def test_same_name_different_id_does_not_overwrite():
    """Trùng TÊN nhưng KHÁC id -> 2 sản phẩm khác nhau, không được ghi đè lẫn nhau."""
    import browser_manager

    with tempfile.TemporaryDirectory() as td:
        a = browser_manager.save_product_context(
            {"index": 1, "id": "111111111", "name": "Áo thun nam", "price": "150k"}, live_dir=td
        )
        b = browser_manager.save_product_context(
            {"index": 2, "id": "222222222", "name": "Áo thun nam", "price": "200k"}, live_dir=td
        )
        assert a is not None and b is not None
        assert a != b, "hai id khác nhau phải ra hai file khác nhau"
        assert len(list(Path(td).glob("*.md"))) == 2

        # Lưu lại sản phẩm đầu -> phải đè lên chính file cũ, không tạo file thứ ba
        a2 = browser_manager.save_product_context(
            {"index": 1, "id": "111111111", "name": "Áo thun nam", "price": "155k"}, live_dir=td
        )
        assert a2 == a
        assert len(list(Path(td).glob("*.md"))) == 2


def test_filename_is_derived_from_product_name():
    import browser_manager

    with tempfile.TemporaryDirectory() as td:
        p = browser_manager.save_product_context(
            {"index": 7, "id": "333", "name": "Kem dưỡng da cấp ẩm Water Gel"}, live_dir=td
        )
        assert p is not None
        assert p.name == "kem-duong-da-cap-am-water-gel.md", p.name
        assert not p.name.startswith("sp-"), "tên file không dùng tiền tố thứ tự giỏ hàng"


def test_context_sections_are_extracted_for_llm():
    """ChatIntent phải tách được mô tả + đánh giá + id để gửi kèm cho LLM."""
    import browser_manager
    from event_analyzer import ChatIntent

    with tempfile.TemporaryDirectory() as td:
        browser_manager.save_product_context(
            {
                "index": 1,
                "id": "555777999",
                "name": "Kem dưỡng ẩm Water Gel",
                "price": "350.000₫",
                "description": "Dưỡng ẩm sâu 24 giờ, thành phần HA.",
                "reviews": ["Thấm nhanh không bết dính", "Mùi thơm nhẹ"],
            },
            live_dir=td,
        )
        it = ChatIntent(context_dir=str(ROOT / "context-data"), live_dir=td)
        prod = it.match("shop ơi kem dưỡng ẩm Water Gel giá bao nhiêu")
        assert prod is not None
        assert prod["price"] == "350.000₫", prod["price"]
        assert "Dưỡng ẩm sâu" in prod["description"]
        assert len(prod["reviews"]) == 2
        assert prod["id"] == "555777999"
        assert prod["live"] is True


def test_context_live_readme_is_not_treated_as_product():
    import browser_manager
    from event_analyzer import ChatIntent

    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "README.md").write_text("# Thư mục context-live\n\nHướng dẫn sử dụng.\n", encoding="utf-8")
        browser_manager.save_product_context(
            {"index": 1, "id": "444", "name": "Tai nghe Bass Boost"}, live_dir=td
        )
        it = ChatIntent(context_dir=str(ROOT / "context-data"), live_dir=td)
        names = [p["name"] for p in it.products]
        assert "Tai nghe Bass Boost" in names
        assert not any("context-live" in n.lower() or "Thư mục" in n for n in names)


def test_intent_router_reports_why_llm_failed():
    """Khi model phân tích lỗi, phải trả về luật dự phòng KÈM lý do để chẩn đoán."""
    got = intent_router.classify_intent("alo shop ơi", products=[], model="model-khong-ton-tai-xyz")
    assert got["source"] == "rule"
    assert got["intent"] == "greeting"
    assert got.get("error"), "phải có lý do thất bại"
    assert intent_router.last_analyze_error()


def test_gui_has_prompt_tab_and_load_context_button():
    """GUI phải có tab Quản lý Prompt, nút Load context-live và bỏ nút Lưu context-live cũ."""
    src = (ROOT / "src" / "gui.py").read_text(encoding="utf-8")
    assert "_build_prompts_tab" in src
    assert "_load_context_live" in src
    assert "_save_live_products" not in src, "nút Lưu context-live cũ phải bị bỏ"
    assert '"Quản lý Prompt"' in src
    assert "📥 Load context-live" in src


def test_analyst_model_syncs_to_llm_tab_field():
    """Lưu model ở tab Quản lý Prompt phải đồng bộ sang _Field để không bị ghi đè."""
    src = (ROOT / "src" / "gui.py").read_text(encoding="utf-8")
    i = src.index("def _save_analyst_model")
    block = src[i:i + 900]
    assert "f.key == \"analyst_llm_model\"" in block
    assert "f.set_value(model)" in block


def test_build_spec_includes_new_modules():
    spec = (ROOT / "build.spec").read_text(encoding="utf-8")
    assert '"json_utils"' in spec
    assert '"intent_router"' in spec


def test_builtin_prompt_fallback_is_only_json_and_diacritic():
    """Khi thư mục prompts không đọc được, prompt dựng sẵn phải vẫn only-JSON + có dấu + tự xưng 'sóp'."""
    from event_analyzer import get_prompt

    for name in (
        "system_greeting",
        "system_sales",
        "system_order",
        "system_gift",
        "system_chat",
        "system_batch",
        "system_analyzer",
    ):
        content = get_prompt(name, prompts_dir="thu-muc-prompt-khong-ton-tai")
        assert content, f"{name}: prompt dựng sẵn rỗng"
        low = content.lower()
        assert "json" in low, f"{name}: prompt dựng sẵn thiếu yêu cầu JSON"
        assert "{" in content, f"{name}: prompt dựng sẵn thiếu JSON mẫu"
    # Prompt sinh câu thoại phải ép tự xưng "sóp" để TTS đọc đúng vai streamer
    for name in ("system_greeting", "system_sales", "system_order", "system_gift", "system_chat"):
        assert "sóp" in get_prompt(name, prompts_dir="thu-muc-prompt-khong-ton-tai"), name


# ----------------------------- batch: nhóm theo intent -----------------------------

def test_group_events_by_intent_groups_by_type():
    from batch_processor import group_events_by_intent

    events = [
        {"type": "order", "user": "A", "product": "Áo"},
        {"type": "gift", "user": "B", "gift": "Hoa"},
        {"type": "viewing_product", "user": "C", "product": "Kem"},
        {"type": "join", "user": "D"},
    ]
    groups = group_events_by_intent(events)
    assert set(groups) == {"order", "gift", "product_question", "greeting"}, set(groups)
    assert len(groups["order"]) == 1
    assert len(groups["gift"]) == 1
    assert len(groups["product_question"]) == 1
    assert len(groups["greeting"]) == 1


def test_group_events_by_intent_classifies_chat_text():
    from batch_processor import group_events_by_intent

    settings_cache = None
    try:
        import settings
        settings_cache = dict(settings.get())
        settings._cache = dict(settings.DEFAULTS)
        settings._cache["analyst_llm_model"] = ""   # offline: dùng luật từ khoá
    except Exception:
        pass
    try:
        groups = group_events_by_intent([
            {"type": "chat", "user": "A", "text": "áo thun giá bao nhiêu shop"},
            {"type": "chat", "user": "B", "text": "alo shop ơi"},
            {"type": "chat", "user": "C", "text": "trời hôm nay đẹp ghê"},
        ])
        assert "product_question" in groups
        assert "greeting" in groups
        assert ("chat" in groups) or ("other" in groups)
    finally:
        if settings_cache is not None:
            import settings
            settings._cache = settings_cache


def test_process_event_batch_fallback_local_without_llm():
    """LLM lỗi toàn bộ lô -> xử lý cục bộ, vẫn ra câu thoại đúng vai (không raise)."""
    import batch_processor as bp
    from unittest import mock

    def boom(*a, **k):
        raise RuntimeError("LLM 429 simulated")

    with mock.patch("llm_client.chat", side_effect=boom), \
         mock.patch("src.llm_client.chat", side_effect=boom):
        items = bp.process_event_batch([
            {"type": "order", "user": "Đức Huy", "product": "Áo thun", "amount": 150000},
            {"type": "gift", "user": "Trang", "gift": "Hoa hồng", "count": 1},
            {"type": "join", "user": "Thanh"},
        ], max_events=10)
    assert items, "fallback phải trả ra câu thoại"
    types = {it["type"] for it in items}
    assert "order" in types and "gift" in types


def test_rate_limit_backoff_avoids_immediate_retry():
    """429 -> tạm hoãn gọi AI vài giây; trong cooldown thì dùng luật và ghi lý do."""
    import intent_router as ir
    import time as _time

    old_until = ir._rate_limited_until
    try:
        # Cache phân loại là state dùng chung -> xoá để test này không dùng kết quả cache.
        ir.clear_intent_cache()
        ir._rate_limited_until = _time.monotonic() + 60.0
        got = ir.classify_intent("alo shop ơi", products=[], model="openrouter/typesafe/jev-router")
        assert got["source"] == "rule"
        assert "hoãn" in got.get("error", "")
        assert ir.rate_limit_remaining_s() > 0
    finally:
        ir._rate_limited_until = old_until
        ir.clear_intent_cache()
