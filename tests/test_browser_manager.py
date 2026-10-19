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
    """API trong trang (khong reload) an truc -> khong bat Network/DOM."""
    raw_api = [{"product_id": "1735159097906791637", "title": "SP A",
                "format_available_price": "35.000\u20ab", "format_origin_price": "40.000\u20ab",
                "stock_num": 100, "seller_info": {"shop_name": "jojo.vn.official"}}]
    calls = []

    monkeypatch.setattr(bm, "_fetch_products_via_page_api",
                        lambda cdp_port=30899, timeout_s=25.0: calls.append("api") or raw_api)
    monkeypatch.setattr(bm, "_harvest_live_products_network",
                        lambda cdp_port=30899, timeout_s=35.0: calls.append("network") or [])
    monkeypatch.setattr(bm, "_scan_live_products_dom", lambda cdp_port=30899: calls.append("dom") or [])

    prods = bm.fetch_live_products_cdp()
    assert len(prods) == 1
    # DOM quet truoc de lay co ghim, roi den API in-page; khong bao gio goi Network
    assert calls == ["dom", "api"]


def test_fetch_live_products_network_when_page_api_empty(monkeypatch):
    """API in-page rong (chu ky het han) -> bat response qua Network."""
    raw_api = [{"product_id": "999", "title": "SP B", "format_available_price": "1.000\u20ab"}]
    monkeypatch.setattr(bm, "_fetch_products_via_page_api", lambda cdp_port=30899, timeout_s=25.0: [])
    monkeypatch.setattr(bm, "_harvest_live_products_network",
                        lambda cdp_port=30899, timeout_s=35.0: raw_api)
    monkeypatch.setattr(bm, "_scan_live_products_dom", lambda cdp_port=30899: [])
    prods = bm.fetch_live_products_cdp()
    assert len(prods) == 1 and prods[0]["id"] == "999"


def test_fetch_live_products_dom_ping_pin(monkeypatch):
    """API bat duoc nhung khong chua sp DOM: pin tu DOM gan theo ten."""
    dom = [{"index": 1, "id": "", "name": "SP A"[:60], "price": "35.000\u20ab",
            "is_pinned": True, "url": "", "raw": {}}]
    raw_api = [{"product_id": "999", "title": "SP A"[:60], "format_available_price": "35.000\u20ab"}]
    monkeypatch.setattr(bm, "_fetch_products_via_page_api", lambda cdp_port=30899, timeout_s=25.0: raw_api)
    monkeypatch.setattr(bm, "_harvest_live_products_network", lambda cdp_port=30899, timeout_s=35.0: [])
    monkeypatch.setattr(bm, "_scan_live_products_dom", lambda cdp_port=30899: dom)
    prods = bm.fetch_live_products_cdp()
    assert len(prods) == 1
    assert prods[0]["id"] == "999"
    assert prods[0]["is_pinned"] is True


def test_fetch_live_products_dom_fallback(monkeypatch):
    """Cai API in-page + Network het han -> dung DOM (khong co id / url)."""
    dom = [{"index": 1, "id": "", "name": "SP B", "price": "10.000\u20ab",
            "is_pinned": False, "url": "", "raw": {"stock": "Con: 3"}}]
    monkeypatch.setattr(bm, "_fetch_products_via_page_api", lambda cdp_port=30899, timeout_s=25.0: [])
    monkeypatch.setattr(bm, "_harvest_live_products_network", lambda cdp_port=30899, timeout_s=35.0: [])
    monkeypatch.setattr(bm, "_scan_live_products_dom", lambda cdp_port=30899: dom)
    prods = bm.fetch_live_products_cdp()
    assert len(prods) == 1
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
    # fetch: API in-page rong -> se thu Net + DOM cung that bai
    monkeypatch.setattr(bm, "_harvest_live_products_network", lambda cdp_port=30899, timeout_s=35.0: [])
    monkeypatch.setattr(bm, "_scan_live_products_dom", lambda cdp_port=30899: [])
    assert bm.fetch_live_products_cdp() == []


