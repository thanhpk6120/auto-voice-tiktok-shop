"""Unit tests cho module browser_manager và tính năng quản lý Chrome/GoLogin."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import browser_manager as bm
import gui


def test_resolve_gologin_dir_fallback():
    # Khi truyen duong dan ton tai
    cwd = Path.cwd().resolve()
    assert bm.resolve_gologin_dir(cwd) == cwd

    # Khi truyen None, tu dong tim hoac fallback
    resolved = bm.resolve_gologin_dir(None)
    assert resolved is not None
    assert isinstance(resolved, Path)


def test_resolve_profiles_dir_from_config():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        cfg_file = tmp_dir / "config.json"
        custom_save = tmp_dir / "my_profiles"
        custom_save.mkdir()

        cfg_file.write_text(json.dumps({"save_path": str(custom_save)}), encoding="utf-8")

        resolved = bm.resolve_profiles_dir(configured_dir=None, gologin_dir=tmp_dir)
        assert resolved == custom_save


def test_get_installed_and_active_chrome_versions():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        orbita_base = tmp_dir / "gologin" / "browser" / "orbita-browser"
        orbita_base.mkdir(parents=True)

        # Tao mock 2 version: 120 va 141
        (orbita_base / "120").mkdir()
        (orbita_base / "120" / "chrome.exe").write_text("dummy", encoding="utf-8")
        (orbita_base / "141").mkdir()
        (orbita_base / "141" / "chrome.exe").write_text("dummy", encoding="utf-8")

        # Thu muc khong phai so -> bi bo qua
        (orbita_base / "cache").mkdir()

        installed = bm.get_installed_chrome_versions(tmp_dir)
        assert installed == ["141", "120"]

        # Chua co file version -> fallback version cao nhat
        assert bm.get_active_chrome_version(tmp_dir) == "141"

        # Ghi file version la 120 -> tra ve 120
        (orbita_base / "version").write_text("120", encoding="utf-8")
        assert bm.get_active_chrome_version(tmp_dir) == "120"


def test_set_active_chrome_version():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        orbita_base = tmp_dir / "gologin" / "browser" / "orbita-browser"
        orbita_base.mkdir(parents=True)
        (orbita_base / "141").mkdir()
        (orbita_base / "141" / "chrome.exe").write_text("dummy", encoding="utf-8")

        # Set version chua cai -> that bai
        ok, msg = bm.set_active_chrome_version(tmp_dir, "999")
        assert ok is False
        assert "chưa được cài đặt" in msg

        # Set version da cai -> thanh cong
        ok, msg = bm.set_active_chrome_version(tmp_dir, "141")
        assert ok is True
        assert (orbita_base / "version").read_text(encoding="utf-8").strip() == "141"


def test_delete_chrome_version():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        orbita_base = tmp_dir / "gologin" / "browser" / "orbita-browser"
        driver_base = tmp_dir / "gologin" / "browser" / "chrome-driver"
        orbita_base.mkdir(parents=True)
        driver_base.mkdir(parents=True)

        # Cai version 141 (active) va 120
        (orbita_base / "141").mkdir()
        (orbita_base / "141" / "chrome.exe").write_text("dummy", encoding="utf-8")
        (orbita_base / "version").write_text("141", encoding="utf-8")

        (orbita_base / "120").mkdir()
        (orbita_base / "120" / "chrome.exe").write_text("dummy", encoding="utf-8")
        (driver_base / "120").mkdir()
        (driver_base / "120" / "chromedriver.exe").write_text("dummy", encoding="utf-8")

        # 1. Thu xoa version dang active (141) -> phai that bai
        ok, msg = bm.delete_chrome_version(tmp_dir, "141")
        assert ok is False
        assert "đang là phiên bản đang kích hoạt" in msg
        assert (orbita_base / "141").exists()

        # 2. Thu xoa voi ky tu nguy hiem / path traversal -> phai that bai
        ok, msg = bm.delete_chrome_version(tmp_dir, "../etc")
        assert ok is False

        # 3. Xoa version 120 khong active -> thanh cong, xoa ca orbita va driver
        ok, msg = bm.delete_chrome_version(tmp_dir, "120")
        assert ok is True
        assert not (orbita_base / "120").exists()
        assert not (driver_base / "120").exists()


def test_list_gologin_profiles():
    with tempfile.TemporaryDirectory() as tmp_str:
        p_dir = Path(tmp_str)

        # Profile 1 co profile.json
        p1 = p_dir / "profile_abc1"
        p1.mkdir()
        (p1 / "profile.json").write_text(
            json.dumps({
                "name": "TikTok Shop Official",
                "notes": "Main seller account",
                "proxy": {"mode": "http", "host": "127.0.0.1", "port": 8080},
            }),
            encoding="utf-8",
        )

        # Profile 2 chi co thu muc Default
        p2 = p_dir / "profile_raw2"
        p2.mkdir()
        (p2 / "Default").mkdir()

        # Thu muc khong phai profile
        (p_dir / "not_a_profile").mkdir()

        profiles = bm.list_gologin_profiles(p_dir)
        assert len(profiles) == 2

        by_id = {p["id"]: p for p in profiles}
        assert "profile_abc1" in by_id
        assert by_id["profile_abc1"]["name"] == "TikTok Shop Official"
        assert by_id["profile_abc1"]["proxy"] == "http://127.0.0.1:8080"
        assert by_id["profile_raw2"]["name"] == "profile_raw2"


def test_gui_extract_profile_id():
    assert gui.extract_profile_id("TikTok Shop (profile_123)") == "profile_123"
    assert gui.extract_profile_id("profile_simple") == "profile_simple"
    assert gui.extract_profile_id("  Shop (acc_456)  ") == "acc_456"


def test_fetch_remote_chrome_releases_fallback():
    releases = bm.fetch_remote_chrome_releases(timeout_s=0.1)
    assert isinstance(releases, list)
    assert len(releases) >= 2
    for r in releases:
        assert "version" in r
        assert "chrome_url" in r
        assert "driver_url" in r


def test_create_gologin_profile_persists_config():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        prof, msg = bm.create_gologin_profile(
            profiles_dir=tmp_dir,
            name="My Live Test",
            resolution="1366x768",
            language="vi-VN",
            proxy_mode="http",
            proxy_host="10.0.0.1",
            proxy_port=8080,
        )
        assert prof is not None
        assert prof["name"] == "My Live Test"
        cfg_file = Path(prof["path"]) / "profile.json"
        assert cfg_file.exists()
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert data["resolution"] == "1366x768"
        assert data["language"] == "vi-VN"
        assert data["proxy"]["mode"] == "http"
        assert data["proxy"]["host"] == "10.0.0.1"
        assert data["proxy"]["port"] == 8080
        assert (Path(prof["path"]) / "Default").is_dir()


def test_launch_gologin_profile_applies_profile_json():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        g_dir = tmp_dir / "gologin"
        p_dir = tmp_dir / "profiles"
        orbita_base = g_dir / "gologin" / "browser" / "orbita-browser"
        (orbita_base / "141").mkdir(parents=True)
        (orbita_base / "141" / "chrome.exe").write_text("dummy", encoding="utf-8")

        prof, _ = bm.create_gologin_profile(
            profiles_dir=p_dir,
            gologin_dir=g_dir,
            name="Profile With Args",
            resolution="1920x1080",
            language="vi-VN",
            proxy_mode="http",
            proxy_host="127.0.0.1",
            proxy_port=8888,
        )

        from unittest.mock import patch, MagicMock
        mock_proc = MagicMock()
        mock_proc.pid = 9999

        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            proc, port, url = bm.launch_gologin_profile(
                profile_id=prof["id"],
                gologin_dir=g_dir,
                profiles_dir=p_dir,
                remote_debugging_port=30899,
            )
            assert proc == mock_proc
            assert port == 30899
            assert "30899" in url
            call_cmd = mock_popen.call_args[0][0]
            assert any("--window-size=1920,1080" in arg for arg in call_cmd)
            assert any("--lang=vi-VN" in arg for arg in call_cmd)
            assert any("--proxy-server=http://127.0.0.1:8888" in arg for arg in call_cmd)
            assert any("tiktok.com" in arg for arg in call_cmd)


def test_fetch_live_products_page_api(monkeypatch):
    """API trong trang tra products va introduce_id -> chi goi API, khong goi Network/DOM."""
    raw_api = {
        "products": [{
            "product_id": "1735159097906791637", "title": "SP A",
            "format_available_price": "35.000\u20ab", "format_origin_price": "40.000\u20ab",
            "stock_num": 100, "seller_info": {"shop_name": "jojo.vn.official"}
        }],
        "introduce_id": "1735159097906791637"
    }
    calls = []

    monkeypatch.setattr(bm, "_fetch_products_via_page_api",
                        lambda cdp_port=30899, timeout_s=25.0: calls.append("api") or raw_api)
    monkeypatch.setattr(bm, "_harvest_live_products_network",
                        lambda cdp_port=30899, timeout_s=35.0: calls.append("network") or [])
    monkeypatch.setattr(bm, "_scan_live_products_dom", lambda cdp_port=30899: calls.append("dom") or [])

    prods = bm.fetch_live_products_cdp()
    assert len(prods) == 1
    assert calls == ["api"]
    assert prods[0]["id"] == "1735159097906791637"
    assert prods[0]["is_pinned"] is True


def test_fetch_live_products_pin_only_exact_match(monkeypatch):
    """Chi co dung 1 san pham trung introduce_id la is_pinned=True, con lai False."""
    raw_api = {
        "products": [
            {"product_id": "111", "title": "SP 1", "format_available_price": "10.000\u20ab"},
            {"product_id": "222", "title": "SP 2", "format_available_price": "20.000\u20ab"},
            {"product_id": "333", "title": "SP 3", "format_available_price": "30.000\u20ab"},
        ],
        "introduce_id": "222"
    }
    monkeypatch.setattr(bm, "_fetch_products_via_page_api", lambda cdp_port=30899, timeout_s=25.0: raw_api)
    monkeypatch.setattr(bm, "_harvest_live_products_network", lambda cdp_port=30899, timeout_s=35.0: [])
    monkeypatch.setattr(bm, "_scan_live_products_dom", lambda cdp_port=30899: [])

    prods = bm.fetch_live_products_cdp()
    assert len(prods) == 3
    assert prods[0]["is_pinned"] is False
    assert prods[1]["is_pinned"] is True
    assert prods[2]["is_pinned"] is False


def test_fetch_live_products_no_pin_when_empty_introduce_id(monkeypatch):
    """Khi introduce_id rong (khong co san pham nao dang ghim tren live) -> tat ca is_pinned=False."""
    raw_api = {
        "products": [
            {"product_id": "111", "title": "SP 1", "format_available_price": "10.000\u20ab"},
            {"product_id": "222", "title": "SP 2", "format_available_price": "20.000\u20ab"},
        ],
        "introduce_id": ""
    }
    monkeypatch.setattr(bm, "_fetch_products_via_page_api", lambda cdp_port=30899, timeout_s=25.0: raw_api)
    monkeypatch.setattr(bm, "_harvest_live_products_network", lambda cdp_port=30899, timeout_s=35.0: [])
    monkeypatch.setattr(bm, "_scan_live_products_dom", lambda cdp_port=30899: [])

    prods = bm.fetch_live_products_cdp()
    assert len(prods) == 2
    assert prods[0]["is_pinned"] is False
    assert prods[1]["is_pinned"] is False


def test_fetch_live_products_network_when_page_api_empty(monkeypatch):
    """API in-page rong -> bat response qua Network."""
    raw_api = {
        "products": [{"product_id": "999", "title": "SP B", "format_available_price": "1.000\u20ab"}],
        "introduce_id": "999"
    }
    monkeypatch.setattr(bm, "_fetch_products_via_page_api", lambda cdp_port=30899, timeout_s=25.0: [])
    monkeypatch.setattr(bm, "_harvest_live_products_network",
                        lambda cdp_port=30899, timeout_s=35.0: raw_api)
    monkeypatch.setattr(bm, "_scan_live_products_dom", lambda cdp_port=30899: [])
    prods = bm.fetch_live_products_cdp()
    assert len(prods) == 1 and prods[0]["id"] == "999"
    assert prods[0]["is_pinned"] is True


def test_fetch_live_products_dom_fallback(monkeypatch):
    """API in-page + Network deu rong -> fallback sang DOM, toi da 1 sp duoc ghim."""
    dom = [
        {"index": 1, "id": "", "name": "SP B", "price": "10.000\u20ab",
         "is_pinned": True, "url": "", "raw": {"stock": "Con: 3"}},
        {"index": 2, "id": "", "name": "SP C", "price": "20.000\u20ab",
         "is_pinned": True, "url": "", "raw": {}}
    ]
    monkeypatch.setattr(bm, "_fetch_products_via_page_api", lambda cdp_port=30899, timeout_s=25.0: [])
    monkeypatch.setattr(bm, "_harvest_live_products_network", lambda cdp_port=30899, timeout_s=35.0: [])
    monkeypatch.setattr(bm, "_scan_live_products_dom", lambda cdp_port=30899: dom)
    prods = bm.fetch_live_products_cdp()
    assert len(prods) == 2
    assert prods[0]["name"] == "SP B"
    assert prods[0]["id"] == ""


def test_fetch_live_products_empty(monkeypatch):
    monkeypatch.setattr(bm, "_fetch_products_via_page_api", lambda cdp_port=30899, timeout_s=25.0: [])
    monkeypatch.setattr(bm, "_harvest_live_products_network", lambda cdp_port=30899, timeout_s=35.0: [])
    monkeypatch.setattr(bm, "_scan_live_products_dom", lambda cdp_port=30899: [])
    assert bm.fetch_live_products_cdp() == []


def test_fetch_live_products_no_browser(monkeypatch):
    """Khong co browser -> ca 3 helper tra []."""
    monkeypatch.setattr(bm, "_connect_cdp", lambda cdp_port=30899: (None, "khong co browser"))
    assert bm._fetch_products_via_page_api() == []
    assert bm._scan_live_products_dom() == []
    assert bm._harvest_live_products_network() == []
    monkeypatch.setattr(bm, "_harvest_live_products_network", lambda cdp_port=30899, timeout_s=35.0: [])
    monkeypatch.setattr(bm, "_scan_live_products_dom", lambda cdp_port=30899: [])
    assert bm.fetch_live_products_cdp() == []


def test_save_product_context_notes_real_promotional_price():
    """save_product_context phai ghi ro gia khuyen mai thuc te va gia goc/giam trong file .md."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        prod = {
            "id": "1733809814429206033",
            "name": "Bim Bim Ga Nuong",
            "index": 1,
            "price": "35.000\u20ab",
            "real_price": "5.396\u20ab",
            "origin_price": "43.166\u20ab",
            "discount": "-87%",
            "url": "https://shop.tiktok.com/view/product/1733809814429206033",
            "description": "Mo ta bim bim",
            "reviews": ["Khach 1: Ngon lam"]
        }
        saved_file = bm.save_product_context(prod, live_dir=tmp_dir)
        assert saved_file is not None
        content = saved_file.read_text(encoding="utf-8")
        assert "5.396\u20ab" in content
        assert "Giá khuyến mại thực tế trên live: 5.396\u20ab" in content
        assert "giá gốc 43.166\u20ab" in content
        assert "giảm -87%" in content
        assert "Báo đúng giá khuyến mại thực tế chỉ 5.396\u20ab" in content


def test_live_products_cache_save_and_load():
    """Luu cache san pham vao _products_cache.json va tai lai du lieu dung nguyen ven."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        prods = [
            {"index": 1, "id": "111", "name": "Banh Gau", "price": "38.000\u20ab", "is_pinned": True},
            {"index": 2, "id": "222", "name": "Bim Bim", "price": "5.396\u20ab", "is_pinned": False},
        ]
        assert bm.load_live_products_cache(live_dir=tmp_dir) == []

        saved_path = bm.save_live_products_cache(prods, live_dir=tmp_dir)
        assert saved_path is not None and saved_path.is_file()

        loaded = bm.load_live_products_cache(live_dir=tmp_dir)
        assert len(loaded) == 2
        assert loaded[0]["name"] == "Banh Gau"
        assert loaded[0]["is_pinned"] is True
        assert loaded[1]["price"] == "5.396\u20ab"


def test_has_and_read_product_context():
    """Kiem tra san pham da co context-live va doc lai thong tin gia khuyen mai."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        prod = {
            "id": "1733809814429206033",
            "name": "Bim Bim Ga Nuong",
            "index": 1,
            "price": "35.000\u20ab",
            "real_price": "5.396\u20ab",
            "origin_price": "43.166\u20ab",
            "discount": "-87%",
        }
        assert bm.has_product_context(prod, live_dir=tmp_dir) is False
        assert bm.read_product_context(prod, live_dir=tmp_dir) is None

        bm.save_product_context(prod, live_dir=tmp_dir)
        assert bm.has_product_context(prod, live_dir=tmp_dir) is True

        ctx = bm.read_product_context(prod, live_dir=tmp_dir)
        assert ctx is not None
        assert "5.396\u20ab" in ctx["price"]
        assert "5.396\u20ab" in ctx["real_price"]


def test_gui_loads_cached_products_on_init(monkeypatch):
    """Khi mo GUI, san pham live tu cache phien truoc phai duoc hien thi san len bang."""
    import tkinter as tk
    import gui

    cached = [
        {"index": 1, "id": "111", "name": "SP Cache 1", "price": "20.000\u20ab", "is_pinned": True},
        {"index": 2, "id": "222", "name": "SP Cache 2", "price": "50.000\u20ab", "is_pinned": False},
    ]
    monkeypatch.setattr(bm, "load_live_products_cache", lambda live_dir=None: cached)

    root = tk.Tk()
    root.withdraw()
    try:
        app = gui.App(root, cfg={})
        assert len(app._current_live_products) == 2
        rows = app.prod_tree.get_children()
        assert len(rows) == 2
        val1 = app.prod_tree.item(rows[0])["values"]
        assert val1[1] == "SP Cache 1"
        assert val1[2] == "20.000\u20ab"
        assert "Đang ghim" in str(val1[3])
    finally:
        root.destroy()


def test_load_context_live_skips_existing_when_chosen(monkeypatch):
    """Khi san pham da co context-live va chon skip, khong crawl lai va van cap nhat gia."""
    import time
    import tkinter as tk
    import gui

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        # Tao san 1 san pham trong context-live
        existing_prod = {
            "id": "1733809814429206033",
            "name": "Bim Bim",
            "index": 1,
            "price": "35.000\u20ab",
            "real_price": "5.000\u20ab",
        }
        bm.save_product_context(existing_prod, live_dir=tmp_dir)

        root = tk.Tk()
        root.withdraw()
        try:
            from tkinter import messagebox
            monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: None)
            monkeypatch.setattr(messagebox, "showwarning", lambda *a, **k: None)
            app = gui.App(root, cfg={"context_live_dir": str(tmp_dir)})
            u1 = "https://shop.tiktok.com/view/product/1733809814429206033"
            u2 = "https://shop.tiktok.com/view/product/1735159097906791637"
            app._current_live_products = [
                {"index": 1, "id": "1733809814429206033", "name": "Bim Bim", "price": "35.000\u20ab", "url": u1},
                {"index": 2, "id": "1735159097906791637", "name": "San Pham Moi", "price": "10.000\u20ab", "url": u2},
            ]

            crawled_urls = []
            monkeypatch.setattr(bm, "crawl_product_detail_cdp", lambda u, max_reviews=10: crawled_urls.append(u) or {
                "id": "1735159097906791637", "name": "San Pham Moi", "real_price": "8.000\u20ab", "url": u
            })
            # Gia lap nguoi dung bam "Bỏ qua tất cả"
            monkeypatch.setattr(app, "_show_overwrite_dialog", lambda name: "skip_all")

            # Chay worker
            app._load_context_live()
            # Doi worker chay xong
            time_start = time.time()
            while app._crawling and time.time() - time_start < 5:
                app._poll_log()
                root.update()
                time.sleep(0.02)
            root.update()

            # San pham 1 da bi bo qua nen khong crawl
            assert u1 not in crawled_urls
            # San pham 2 la moi nen van duoc crawl
            assert u2 in crawled_urls
            # San pham 1 doc lai gia cu da luu la 5.000d
            assert app._current_live_products[0]["price"] == "5.000\u20ab"
            # San pham 2 cap nhat gia moi la 8.000d
            assert app._current_live_products[1]["price"] == "8.000\u20ab"
        finally:
            root.destroy()
