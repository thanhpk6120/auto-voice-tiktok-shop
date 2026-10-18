"""Quản lý phiên bản Chrome/Orbita và Profile GoLogin tích hợp cho ứng dụng Auto Voice.

Hỗ trợ:
- Quét và nhận diện tự động thư mục GoLogin và thư mục lưu profiles.
- Liệt kê các phiên bản Chrome/Orbita và ChromeDriver đã cài đặt.
- Kích hoạt (switch) phiên bản Chrome sử dụng.
- Tải về và cài đặt các phiên bản Chrome / ChromeDriver từ remote repository.
- Xoá phiên bản Chrome / ChromeDriver an toàn (ngăn xoá phiên bản đang kích hoạt).
- Quét danh sách profile GoLogin offline và khởi chạy với cổng CDP debug.
- Kết nối trực tiếp Chrome DevTools Protocol (CDP) để đọc sự kiện chat TikTok Shop.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable, Iterator

# Mẫu hợp lệ cho tên phiên bản Chrome (chỉ cho phép số và dấu chấm)
_VERSION_RE = re.compile(r"^[0-9]+(\.[0-9]+)*$")
CDP_SETUP_JS = """
(() => {
    if (window.__tiktok_cdp_observers && Array.isArray(window.__tiktok_cdp_observers)) {
        for (const o of window.__tiktok_cdp_observers) {
            try { o.disconnect(); } catch(e) {}
        }
    }
    window.__tiktok_cdp_observers = [];
    window.__tiktok_cdp_queue_v2 = window.__tiktok_cdp_queue_v2 || [];

    const JUNK_PHRASES = [
        'bình luận của người xem sẽ xuất hiện ở đây',
        'các đơn hàng đặt trong live của bạn sẽ hiển thị tại đây',
        'hoạt động của người xem sẽ xuất hiện ở đây',
        'kéo để thay đổi kích thước',
        'tin nhắn mới bên trên',
        'tin nhắn mới bên dưới',
        'liên quan đến sản phẩm',
        'trò chuyện',
        'hoạt động',
        'tất cả',
        'xem thêm',
        'thêm kịch bản',
        'không có bảng tin video',
        'bảng điều khiển live',
        'chuyển chế độ',
        'flash sale',
        'quà tặng',
        'biển quảng cáo',
        'voucher',
        'sản phẩm',
        '0/100', '1/100', '2/100',
        'yêu cầu minh họa',
        'thêm vào giỏ',
        'xem sản phẩm',
        'quà tặng quảng bá',
        'tin nhắn từ hệ thống',
        'người đăng ký',
        'người theo dõi'
    ];

    const DATE_TIME_RE = /^(\\d{1,2}[\\/\\-.]\\d{1,2}([\\/\\-.]\\d{2,4})?(\\s+\\d{1,2}(:\\d{2})*)?|\\d{1,2}:\\d{2}(:\\d{2})?)$/;

    function isJunk(text) {
        if (!text) return true;
        const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
        if (lines.length >= 3) return true;
        const s = text.trim().toLowerCase();
        if (s.length < 2) return true;
        if (DATE_TIME_RE.test(s)) return true;
        for (const phrase of JUNK_PHRASES) {
            if (s === phrase || s.startsWith(phrase)) return true;
        }
        return false;
    }

    const seenRecent = new Set();
    function pushEvent(type, user, content, source, raw) {
        const key = type + '|' + (user || '') + '|' + (content || '');
        if (seenRecent.has(key)) return;
        seenRecent.add(key);
        setTimeout(() => seenRecent.delete(key), 3000);

        window.__tiktok_cdp_queue_v2.push({
            type: type,
            user: user || 'Khách',
            content: content || '',
            text: content || '',
            source: source || 'chat',
            raw: raw || '',
            ts: Date.now() / 1000
        });
    }

    function findChatList() {
        const pTags = document.querySelectorAll('p, span, div');
        for (const p of pTags) {
            if (p.children.length === 0 && p.innerText.trim() === 'Trò chuyện') {
                let el = p;
                while (el && el !== document.body) {
                    const list = el.querySelector('.arco-list-content, [role="list"], .arco-list-items');
                    if (list) return list;
                    el = el.parentElement;
                }
            }
        }
        return document.querySelector('.arco-list-content, [role="list"]');
    }

    function findActivityList() {
        const actDiv = document.querySelector('div.bg-neutral-white.flex-grow.min-h-0');
        if (actDiv) return actDiv;

        const allSpans = document.querySelectorAll('span, div');
        for (const s of allSpans) {
            if (s.children.length === 0 && s.innerText.trim() === 'Hoạt động') {
                let el = s;
                while (el && el !== document.body) {
                    if (el.className && el.className.includes('flex-grow')) {
                        return el;
                    }
                    el = el.parentElement;
                }
            }
        }
        return null;
    }

    let chatObs = null;
    let actObs = null;
    let lastChatTarget = null;
    let lastActTarget = null;

    function attachObservers() {
        const chatList = findChatList();
        if (chatList && (!chatObs || !lastChatTarget || !lastChatTarget.isConnected)) {
            if (chatObs) { try { chatObs.disconnect(); } catch(e) {} }
            chatObs = new MutationObserver((mutations) => {
                for (const m of mutations) {
                    for (const node of m.addedNodes) {
                        if (node.nodeType === 1) {
                            const raw = (node.innerText || node.textContent || '').trim();
                            if (isJunk(raw)) continue;

                            let user = 'Khách';
                            let text = raw;

                            const nickEl = node.querySelector('[class*="nick"], [class*="user"], [class*="name"]');
                            if (nickEl) {
                                user = nickEl.innerText.trim() || user;
                                text = raw.replace(user, '').trim().replace(/^[:：]\\s*/, '') || raw;
                            } else {
                                const parts = raw.split(/[:：]/, 2);
                                if (parts.length === 2 && parts[0].length < 30) {
                                    user = parts[0].trim();
                                    text = parts[1].trim();
                                }
                            }
                            if (isJunk(text)) continue;
                            pushEvent('chat', user, text, 'Trò chuyện', raw);
                        }
                    }
                }
            });
            chatObs.observe(chatList, { childList: true, subtree: true });
            lastChatTarget = chatList;
            window.__tiktok_cdp_observers.push(chatObs);
        }

        const actList = findActivityList();
        if (actList && (!actObs || !lastActTarget || !lastActTarget.isConnected)) {
            if (actObs) { try { actObs.disconnect(); } catch(e) {} }
            actObs = new MutationObserver((mutations) => {
                for (const m of mutations) {
                    for (const node of m.addedNodes) {
                        if (node.nodeType === 1) {
                            const raw = (node.innerText || node.textContent || '').trim();
                            if (isJunk(raw)) continue;

                            let evType = 'chat';
                            let user = 'Khách';
                            let text = raw;

                            const s = raw.toLowerCase();
                            if (s.includes('đặt hàng') || s.includes('mua') || s.includes('chốt đơn') || s.includes('ordered')) {
                                evType = 'order';
                            } else if (s.includes('tặng') || s.includes('đã gửi') || s.includes('gift') || s.includes('hoa hồng')) {
                                evType = 'gift';
                            } else if (s.includes('vào phòng') || s.includes('joined') || s.includes('follow') || s.includes('chia sẻ')) {
                                evType = 'join';
                            }

                            const parts = raw.split(/[:：]/, 2);
                            if (parts.length === 2 && parts[0].length < 30) {
                                user = parts[0].trim();
                                text = parts[1].trim();
                            }
                            if (isJunk(text)) continue;
                            pushEvent(evType, user, text, 'Hoạt động', raw);
                        }
                    }
                }
            });
            actObs.observe(actList, { childList: true, subtree: true });
            lastActTarget = actList;
            window.__tiktok_cdp_observers.push(actObs);
        }
    }

    attachObservers();
    setInterval(attachObservers, 2000);

    const cTarget = findChatList();
    const aTarget = findActivityList();
    return JSON.stringify({
        chatFound: !!cTarget,
        chatSnippet: cTarget ? (cTarget.innerText || '').slice(0, 100).replace(/\\s+/g, ' ').trim() : 'Chưa tìm thấy',
        actFound: !!aTarget,
        actSnippet: aTarget ? (aTarget.innerText || '').slice(0, 100).replace(/\\s+/g, ' ').trim() : 'Chưa tìm thấy'
    });
})();
"""

CDP_POLL_JS = """
(() => {
    if (!window.__tiktok_cdp_queue_v2) return "[]";
    const items = window.__tiktok_cdp_queue_v2.splice(0, window.__tiktok_cdp_queue_v2.length);
    return JSON.stringify(items);
})()
"""

# Danh sách phiên bản remote nổi bật để fallback khi không truy cập được GitHub API
DEFAULT_REMOTE_CHROME_RELEASES = [
    {
        "version": "141.0.7390.65",
        "tag": "v141",
        "chrome_url": "https://github.com/thanhpkt36/chrome/releases/download/v141/chrome.7z",
        "driver_url": "https://github.com/thanhpkt36/chromedriver-win64/releases/download/v141/chromedriver.zip",
    },
    {
        "version": "120.0.6099.109",
        "tag": "v120",
        "chrome_url": "https://github.com/thanhpkt36/chrome/releases/download/v120/chrome.7z",
        "driver_url": "https://github.com/thanhpkt36/chromedriver-win64/releases/download/v120/chromedriver.zip",
    },
    {
        "version": "119.0.6045.105",
        "tag": "v119",
        "chrome_url": "https://github.com/thanhpkt36/chrome/releases/download/v119/chrome.7z",
        "driver_url": "https://github.com/thanhpkt36/chromedriver-win64/releases/download/v119/chromedriver.zip",
    },
    {
        "version": "118.0.5993.70",
        "tag": "v118",
        "chrome_url": "https://github.com/thanhpkt36/chrome/releases/download/v118/chrome.7z",
        "driver_url": "https://github.com/thanhpkt36/chromedriver-win64/releases/download/v118/chromedriver.zip",
    },
]


def resolve_gologin_dir(configured_dir: str | Path | None = None) -> Path:
    """Xác định đường dẫn thư mục gologin-basic-offline."""
    if configured_dir:
        p = Path(configured_dir).resolve()
        if p.exists():
            return p

    cwd = Path.cwd().resolve()
    candidates = [
        cwd / "gologin-basic-offline",
        cwd.parent / "gologin-basic-offline",
        Path(__file__).resolve().parent.parent / "gologin-basic-offline",
    ]
    for c in candidates:
        if c.exists() and (c / "gologin").exists():
            return c

    return cwd / "gologin-basic-offline"


def resolve_profiles_dir(
    configured_dir: str | Path | None = None,
    gologin_dir: str | Path | None = None,
) -> Path:
    """Xác định đường dẫn thư mục chứa các profile GoLogin."""
    if configured_dir:
        p = Path(configured_dir).resolve()
        if p.exists():
            return p

    base_gologin = resolve_gologin_dir(gologin_dir)
    cfg_file = base_gologin / "config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                saved_path = data.get("save_path")
                if saved_path:
                    sp = Path(saved_path).resolve()
                    if sp.exists():
                        return sp
        except Exception:
            pass

    return base_gologin / "profiles"


def _orbita_base(gologin_dir: str | Path | None) -> Path:
    return resolve_gologin_dir(gologin_dir) / "gologin" / "browser" / "orbita-browser"


def _driver_base(gologin_dir: str | Path | None) -> Path:
    return resolve_gologin_dir(gologin_dir) / "gologin" / "browser" / "chrome-driver"


# -----------------------------------------------------------------------------
# Quản lý phiên bản Chrome & ChromeDriver
# -----------------------------------------------------------------------------

def get_installed_chrome_versions(gologin_dir: str | Path | None = None) -> list[str]:
    """Liệt kê các phiên bản Chrome/Orbita đã cài đặt trong orbita-browser."""
    base = _orbita_base(gologin_dir)
    if not base.exists():
        return []

    versions = []
    try:
        for item in base.iterdir():
            if item.is_dir() and item.name and item.name[0].isdigit():
                if (item / "chrome.exe").exists() or list(item.glob("**/chrome.exe")):
                    versions.append(item.name)
    except Exception:
        pass

    def _key(v: str):
        try:
            return [int(x) for x in v.split(".")]
        except Exception:
            return [0]

    return sorted(versions, key=_key, reverse=True)


def get_installed_chromedriver_versions(gologin_dir: str | Path | None = None) -> list[str]:
    """Liệt kê các phiên bản ChromeDriver đã cài đặt."""
    base = _driver_base(gologin_dir)
    if not base.exists():
        return []

    versions = []
    try:
        for item in base.iterdir():
            if item.is_dir() and item.name and item.name[0].isdigit():
                if (item / "chromedriver.exe").exists() or list(item.glob("**/chromedriver.exe")):
                    versions.append(item.name)
    except Exception:
        pass

    def _key(v: str):
        try:
            return [int(x) for x in v.split(".")]
        except Exception:
            return [0]

    return sorted(versions, key=_key, reverse=True)


def get_active_chrome_version(gologin_dir: str | Path | None = None) -> str | None:
    """Lấy phiên bản Chrome đang kích hoạt từ file version."""
    base = _orbita_base(gologin_dir)
    ver_file = base / "version"
    if ver_file.exists():
        try:
            val = ver_file.read_text(encoding="utf-8").strip()
            if val:
                return val
        except Exception:
            pass

    installed = get_installed_chrome_versions(gologin_dir)
    return installed[0] if installed else None


def set_active_chrome_version(gologin_dir: str | Path | None, version: str) -> tuple[bool, str]:
    """Kích hoạt phiên bản Chrome được chọn bằng cách ghi vào file version."""
    version = str(version).strip()
    if not version:
        return False, "Phiên bản không hợp lệ."

    installed = get_installed_chrome_versions(gologin_dir)
    if version not in installed:
        return False, f"Phiên bản {version} chưa được cài đặt trong máy."

    base = _orbita_base(gologin_dir)
    base.mkdir(parents=True, exist_ok=True)
    ver_file = base / "version"

    try:
        ver_file.write_text(version, encoding="utf-8")
        return True, f"Đã kích hoạt phiên bản Chrome {version} thành công."
    except Exception as e:
        return False, f"Lỗi khi ghi file version: {e}"


def delete_chrome_version(gologin_dir: str | Path | None, version: str) -> tuple[bool, str]:
    """Xoá một phiên bản Chrome và ChromeDriver tương ứng."""
    version = str(version).strip()
    if not version or not _VERSION_RE.match(version):
        return False, f"Tên phiên bản '{version}' không hợp lệ hoặc chứa ký tự nguy hiểm."

    active = get_active_chrome_version(gologin_dir)
    if active == version:
        return (
            False,
            f"Không thể xoá phiên bản {version} vì đây đang là phiên bản đang kích hoạt. "
            "Vui lòng kích hoạt một phiên bản khác trước khi xoá.",
        )

    orbita_ver = _orbita_base(gologin_dir) / version
    driver_ver = _driver_base(gologin_dir) / version

    deleted_any = False
    errors = []

    if orbita_ver.exists():
        try:
            shutil.rmtree(orbita_ver)
            deleted_any = True
        except Exception as e:
            errors.append(f"Không thể xoá orbita-browser/{version}: {e}")

    if driver_ver.exists():
        try:
            shutil.rmtree(driver_ver)
            deleted_any = True
        except Exception as e:
            errors.append(f"Không thể xoá chrome-driver/{version}: {e}")

    if errors:
        return False, "; ".join(errors)
    if not deleted_any:
        return False, f"Không tìm thấy dữ liệu đã cài đặt của phiên bản {version} để xoá."

    return True, f"Đã xoá hoàn tất phiên bản Chrome {version}."


# -----------------------------------------------------------------------------
# Tải và cài đặt phiên bản từ Remote Repository
# -----------------------------------------------------------------------------

def fetch_remote_chrome_releases(timeout_s: float = 4.0) -> list[dict]:
    """Lấy danh sách các bản phát hành Chrome từ Google Chrome for Testing và GitHub Releases."""
    releases: list[dict] = []
    seen_versions = set()

    # 1. Nguồn chính thức: Google Chrome for Testing (Cập nhật hàng ngày, đầy đủ mọi channel)
    cft_url = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"
    try:
        req = urllib.request.Request(cft_url, headers={"User-Agent": "AutoVoiceTikTokShop/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            cft_data = json.loads(resp.read().decode("utf-8"))
        for channel, info in cft_data.get("channels", {}).items():
            ver = info.get("version", "").strip()
            if not ver or ver in seen_versions:
                continue
            chrome_dl = None
            driver_dl = None
            for d in info.get("downloads", {}).get("chrome", []):
                if d.get("platform") == "win64":
                    chrome_dl = d.get("url")
                    break
            for d in info.get("downloads", {}).get("chromedriver", []):
                if d.get("platform") == "win64":
                    driver_dl = d.get("url")
                    break
            if chrome_dl:
                seen_versions.add(ver)
                releases.append({
                    "version": ver,
                    "tag": f"google-{channel.lower()}",
                    "name": f"Google {channel} ({ver}) [Chính thức]",
                    "chrome_url": chrome_dl,
                    "driver_url": driver_dl,
                })
    except Exception:
        pass

    # 1.1 Nguồn mở rộng: Google Chrome for Testing - Tất cả các Milestone (M115 -> M158+)
    cft_milestones_url = "https://googlechromelabs.github.io/chrome-for-testing/latest-versions-per-milestone-with-downloads.json"
    try:
        req = urllib.request.Request(cft_milestones_url, headers={"User-Agent": "AutoVoiceTikTokShop/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            m_data = json.loads(resp.read().decode("utf-8"))
        milestones = m_data.get("milestones", {})
        sorted_m_keys = sorted(
            milestones.keys(),
            key=lambda x: int(x) if str(x).isdigit() else 0,
            reverse=True,
        )
        for m_key in sorted_m_keys:
            m_info = milestones[m_key]
            ver = m_info.get("version", "").strip()
            if not ver or ver in seen_versions:
                continue
            chrome_dl = None
            driver_dl = None
            for d in m_info.get("downloads", {}).get("chrome", []):
                if d.get("platform") == "win64":
                    chrome_dl = d.get("url")
                    break
            for d in m_info.get("downloads", {}).get("chromedriver", []):
                if d.get("platform") == "win64":
                    driver_dl = d.get("url")
                    break
            if chrome_dl:
                seen_versions.add(ver)
                releases.append({
                    "version": ver,
                    "tag": f"m{m_key}",
                    "name": f"Google Chrome M{m_key} ({ver})",
                    "chrome_url": chrome_dl,
                    "driver_url": driver_dl,
                })
    except Exception:
        pass
    # 2. Nguồn bổ sung: GitHub Releases (Orbita & Chrome Portable)
    gh_url = "https://api.github.com/repos/thanhpkt36/chrome/releases"
    try:
        req = urllib.request.Request(
            gh_url,
            headers={"User-Agent": "AutoVoiceTikTokShop/1.0", "Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            gh_data = json.loads(resp.read().decode("utf-8"))
        for item in gh_data:
            if item.get("draft") or item.get("prerelease"):
                continue
            tag = item.get("tag_name", "").strip()
            ver = tag.lstrip("v")
            if not ver or ver in seen_versions or not _VERSION_RE.match(ver):
                continue
            chrome_url = None
            for asset in item.get("assets", []):
                name = asset.get("name", "").lower()
                if "chrome" in name and (name.endswith(".7z") or name.endswith(".zip")):
                    chrome_url = asset.get("browser_download_url")
                    break
            if chrome_url:
                seen_versions.add(ver)
                releases.append({
                    "version": ver,
                    "tag": tag,
                    "name": f"Orbita / Chrome {tag} ({ver})",
                    "chrome_url": chrome_url,
                    "driver_url": f"https://github.com/thanhpkt36/chromedriver-win64/releases/download/{tag}/chromedriver.zip",
                })
    except Exception:
        pass

    # 3. Fallback mặc định nếu offline hoặc lỗi mạng
    for fb in DEFAULT_REMOTE_CHROME_RELEASES:
        ver = fb["version"]
        if ver not in seen_versions:
            seen_versions.add(ver)
            item = dict(fb)
            item.setdefault("name", f"Chrome {fb.get('tag', ver)} ({ver})")
            releases.append(item)

    return releases

def _extract_archive(archive_path: Path, dest_dir: Path) -> bool:
    """Giải nén file .zip hoặc .7z sử dụng tar.exe của hệ thống hoặc zipfile."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = archive_path.suffix.lower()

    try:
        proc = subprocess.run(
            ["tar", "-xf", str(archive_path), "-C", str(dest_dir)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode == 0:
            return True
    except Exception:
        pass

    if suffix == ".zip":
        try:
            import zipfile
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(dest_dir)
            return True
        except Exception:
            pass

    return False


def install_chrome_from_url(
    gologin_dir: str | Path | None,
    version: str,
    chrome_url: str,
    driver_url: str | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """Tải và cài đặt phiên bản Chrome/Orbita và ChromeDriver tương ứng."""
    version = str(version).strip()
    if not version or not _VERSION_RE.match(version):
        return False, f"Phiên bản '{version}' không hợp lệ."

    def _log(msg: str):
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass

    base_orbita = _orbita_base(gologin_dir)
    target_chrome_dir = base_orbita / version
    base_driver = _driver_base(gologin_dir)
    target_driver_dir = base_driver / version

    target_chrome_dir.mkdir(parents=True, exist_ok=True)
    target_driver_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)

        _log(f"Đang tải Chrome v{version} từ {chrome_url}...")
        archive_name = "chrome.7z" if chrome_url.endswith(".7z") else "chrome.zip"
        chrome_archive = tmp_dir / archive_name

        try:
            urllib.request.urlretrieve(chrome_url, chrome_archive)
        except Exception as e:
            return False, f"Lỗi tải Chrome: {e}"

        _log(f"Đang giải nén Chrome v{version}...")
        extract_tmp = tmp_dir / "chrome_extracted"
        if not _extract_archive(chrome_archive, extract_tmp):
            return False, "Không thể giải nén file Chrome (cần công cụ hỗ trợ tar/7z)."

        found_chrome = None
        for p in extract_tmp.rglob("chrome.exe"):
            found_chrome = p
            break

        if not found_chrome:
            return False, "Không tìm thấy file chrome.exe trong file nén."

        source_dir = found_chrome.parent
        _log(f"Đang sao chép file Chrome vào {target_chrome_dir}...")
        for item in source_dir.iterdir():
            dest = target_chrome_dir / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        if driver_url:
            _log(f"Đang tải ChromeDriver v{version}...")
            driver_archive = tmp_dir / "driver.zip"
            try:
                urllib.request.urlretrieve(driver_url, driver_archive)
                driver_tmp = tmp_dir / "driver_extracted"
                if _extract_archive(driver_archive, driver_tmp):
                    for dp in driver_tmp.rglob("chromedriver.exe"):
                        shutil.copy2(dp, target_driver_dir / "chromedriver.exe")
                        _log(f"Đã sao chép chromedriver.exe vào {target_driver_dir}")
                        break
            except Exception as e:
                _log(f"Cảnh báo: không tải được ChromeDriver ({e}), vẫn hoàn tất cài Chrome.")

    set_active_chrome_version(gologin_dir, version)
    _log(f"Hoàn thành cài đặt Chrome v{version}!")
    return True, f"Cài đặt và kích hoạt thành công Chrome v{version}."


# -----------------------------------------------------------------------------
# Quản lý Profile GoLogin & Khởi chạy trình duyệt
# -----------------------------------------------------------------------------

def list_gologin_profiles(profiles_dir: str | Path | None = None) -> list[dict]:
    """Quét và trả về danh sách các profile GoLogin có sẵn."""
    p_dir = resolve_profiles_dir(profiles_dir)
    if not p_dir.exists():
        return []

    profiles = []
    try:
        for item in p_dir.iterdir():
            if not item.is_dir():
                continue
            cfg_file = item / "profile.json"
            name = item.name
            notes = ""
            proxy_info = "none"

            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        name = meta.get("name") or item.name
                        notes = meta.get("notes") or ""
                        proxy = meta.get("proxy", {})
                        if isinstance(proxy, dict):
                            mode = proxy.get("mode", "none")
                            host = proxy.get("host") or ""
                            port = proxy.get("port") or ""
                            proxy_info = f"{mode}://{host}:{port}" if host else mode
                except Exception:
                    pass
            elif not (item / "Default").exists():
                continue

            profiles.append({
                "id": item.name,
                "name": name,
                "path": str(item.resolve()),
                "notes": notes,
                "proxy": proxy_info,
            })
    except Exception:
        pass

    return sorted(profiles, key=lambda x: x["name"].lower())

def create_gologin_profile(
    profiles_dir: str | Path | None = None,
    gologin_dir: str | Path | None = None,
    name: str = "TikTok Shop Live",
    version: str | None = None,
    resolution: str = "1920x1080",
    language: str = "vi-VN",
    timezone: str = "Asia/Ho_Chi_Minh",
    proxy_mode: str = "none",
    proxy_host: str = "",
    proxy_port: int = 0,
    proxy_user: str = "",
    proxy_pass: str = "",
    start_url: str = "https://shop.tiktok.com/streamer/live/product/dashboard",
) -> tuple[dict | None, str]:
    """Tạo profile GoLogin mới và lưu cấu hình vào profile.json."""
    import datetime
    import uuid

    base_gologin = resolve_gologin_dir(gologin_dir)
    target_p_dir = resolve_profiles_dir(profiles_dir, base_gologin)

    if not target_p_dir.exists():
        try:
            target_p_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return None, f"Không thể tạo thư mục lưu profiles: {e}"

    profile_id = f"profile_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    profile_path = target_p_dir / profile_id
    try:
        profile_path.mkdir(parents=True, exist_ok=True)
        (profile_path / "Default").mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return None, f"Lỗi tạo thư mục profile {profile_id}: {e}"

    act_ver = version or get_active_chrome_version(base_gologin) or "141"
    ua = (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{act_ver}.0.0.0 Safari/537.36"
    )

    profile_data = {
        "profile_id": profile_id,
        "name": name.strip() or f"Profile {profile_id}",
        "os": "win",
        "version": act_ver,
        "userAgent": ua,
        "language": language,
        "timezone": timezone,
        "resolution": resolution,
        "cpu": "4",
        "hardwareConcurrency": 4,
        "deviceMemory": 8,
        "startUrl": start_url or "https://shop.tiktok.com/streamer/live/product/dashboard",
        "canvasMode": "noise",
        "webglMode": "noise",
        "audioContextMode": "noise",
        "clientRectsMode": "off",
        "fontsMode": "noise",
        "webglVendor": "Google Inc. (Intel)",
        "webglRenderer": "ANGLE (Intel, Intel UHD Graphics 630 (0x0000130F) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "fillTzFromIp": False,
        "fillLocationFromIp": False,
        "geolocation": "Allow",
        "doNotTrack": False,
        "clearCache": True,
        "proxy": {
            "mode": proxy_mode if proxy_mode in ("http", "socks5") else "none",
            "host": proxy_host.strip(),
            "port": int(proxy_port) if str(proxy_port).isdigit() else 0,
            "username": proxy_user.strip(),
            "password": proxy_pass.strip(),
        },
        "created_at": datetime.datetime.utcnow().isoformat(),
    }

    try:
        cfg_path = profile_path / "profile.json"
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(profile_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        return None, f"Lỗi ghi profile.json: {e}"

    res = {
        "id": profile_id,
        "name": profile_data["name"],
        "path": str(profile_path.resolve()),
        "proxy": f"{proxy_mode}://{proxy_host}:{proxy_port}" if proxy_mode != "none" and proxy_host else "none",
        "version": act_ver,
    }
    return res, f"Tạo profile '{profile_data['name']}' ({profile_id}) thành công."


def find_chrome_executable(gologin_dir: str | Path | None = None, version: str | None = None) -> Path | None:
    """Tìm file chrome.exe cho phiên bản được chỉ định hoặc phiên bản đang kích hoạt."""
    base = _orbita_base(gologin_dir)
    # 1. Thử version chỉ định
    if version:
        vdir = base / version
        if vdir.exists():
            target = vdir / "chrome.exe"
            if target.exists():
                return target
            for p in vdir.rglob("chrome.exe"):
                return p

    # 2. Thử version đang active
    act = get_active_chrome_version(gologin_dir)
    if act:
        vdir = base / act
        if vdir.exists():
            target = vdir / "chrome.exe"
            if target.exists():
                return target
            for p in vdir.rglob("chrome.exe"):
                return p

    # 3. Fallback bất kỳ version nào đã cài đặt
    installed = get_installed_chrome_versions(gologin_dir)
    for v in installed:
        vdir = base / v
        if vdir.exists():
            target = vdir / "chrome.exe"
            if target.exists():
                return target
            for p in vdir.rglob("chrome.exe"):
                return p

    return None


def launch_gologin_profile(
    profile_id: str,
    gologin_dir: str | Path | None = None,
    profiles_dir: str | Path | None = None,
    remote_debugging_port: int = 30899,
    extra_args: list[str] | None = None,
) -> tuple[subprocess.Popen | None, int, str]:
    """Khởi chạy trình duyệt Orbita cho một profile với cổng Remote Debugging CDP."""
    base_gologin = resolve_gologin_dir(gologin_dir)
    base_profiles = resolve_profiles_dir(profiles_dir, base_gologin)

    profile_path = base_profiles / profile_id
    if not profile_path.exists():
        return None, 0, f"Thư mục profile {profile_id} không tồn tại: {profile_path}"

    # Đọc cấu hình từ profile.json nếu có
    cfg_file = profile_path / "profile.json"
    meta: dict = {}
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                meta = json.load(f) or {}
        except Exception:
            meta = {}

    pref_ver = meta.get("version")
    chrome_exe = find_chrome_executable(base_gologin, version=pref_ver)
    if not chrome_exe or not chrome_exe.exists():
        # Fallback phiên bản active
        chrome_exe = find_chrome_executable(base_gologin)

    if not chrome_exe or not chrome_exe.exists():
        return None, 0, f"Không tìm thấy chrome.exe trong {base_gologin}"

    cmd = [
        str(chrome_exe),
        f"--remote-debugging-port={remote_debugging_port}",
        f"--user-data-dir={profile_path}",
        "--disable-encryption",
        "--password-store=basic",
        "--donut-pie={test:test}",
        "--disable-automation",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-translate",
        "--disable-default-apps",
        "--disable-component-extensions-with-background-pages",
        "--font-masking-mode=2",
    ]
    res = meta.get("resolution")
    if res and "x" in str(res).lower():
        parts = str(res).lower().split("x", 1)
        if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
            cmd.append(f"--window-size={parts[0].strip()},{parts[1].strip()}")

    lang = meta.get("language")
    if lang:
        cmd.append(f"--lang={lang}")

    tz = meta.get("timezone")
    if tz:
        cmd.append(f"--tz={tz}")

    proxy = meta.get("proxy")
    if isinstance(proxy, dict) and proxy.get("mode") in ("http", "socks5") and proxy.get("host"):
        p_host = proxy.get("host")
        p_port = proxy.get("port")
        spec = f"{p_host}:{p_port}" if p_port else p_host
        cmd.append(f"--proxy-server={proxy.get('mode')}://{spec}")

    if extra_args:
        cmd.extend(extra_args)

    start_url = meta.get("startUrl") or "https://shop.tiktok.com/streamer/live/product/dashboard"
    cmd.append(start_url)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        return proc, remote_debugging_port, f"http://127.0.0.1:{remote_debugging_port}"
    except Exception as e:
        return None, 0, f"Lỗi khởi chạy trình duyệt: {e}"


# -----------------------------------------------------------------------------
# Trực tiếp kết nối Chrome DevTools Protocol (CDP) không dùng Extension
# -----------------------------------------------------------------------------

def get_cdp_target(cdp_port: int = 30899, timeout_s: float = 2.0) -> dict | None:
    """Lấy target trang web TikTok Shop từ endpoint JSON của CDP."""
    url = f"http://127.0.0.1:{cdp_port}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "AutoVoiceTikTokShop/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            targets = json.loads(resp.read().decode("utf-8"))
        if not isinstance(targets, list):
            return None

        # Ưu tiên tab TikTok Shop
        for t in targets:
            t_url = t.get("url", "").lower()
            if "tiktok.com" in t_url or "dashboard" in t_url:
                if t.get("webSocketDebuggerUrl"):
                    return t

        # Fallback tab type page
        for t in targets:
            if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                return t
        return None
    except Exception:
        return None


def stream_cdp_events(
    stop_event: threading.Event,
    cdp_port: int = 30899,
    poll_interval_s: float = 0.3,
) -> Iterator[dict]:
    """Generator lắng nghe sự kiện chat trực tiếp qua Chrome DevTools Protocol."""
    import event_bridge
    try:
        from websockets.sync.client import connect
    except ImportError:
        return

    req_id = 0
    while not stop_event.is_set():
        target = get_cdp_target(cdp_port=cdp_port)
        if not target:
            time.sleep(1.0)
            continue

        ws_url = target.get("webSocketDebuggerUrl")
        if not ws_url:
            time.sleep(1.0)
            continue

        try:
            with connect(ws_url, open_timeout=5, close_timeout=2) as ws:
                req_id += 1
                setup_cmd = {
                    "id": req_id,
                    "method": "Runtime.evaluate",
                    "params": {"expression": CDP_SETUP_JS, "returnByValue": True},
                }
                ws.send(json.dumps(setup_cmd))
                setup_resp = json.loads(ws.recv())
                diag_str = setup_resp.get("result", {}).get("result", {}).get("value", "{}")
                try:
                    diag = json.loads(diag_str) if isinstance(diag_str, str) else diag_str
                except Exception:
                    diag = {}
                c_ok = diag.get("chatFound", False)
                c_snip = diag.get("chatSnippet", "")
                a_ok = diag.get("actFound", False)
                a_snip = diag.get("actSnippet", "")

                print(f"[cdp/scan] Đã kết nối tab '{target.get('title', 'TikTok')}'", flush=True)
                print(f"[cdp/scan] Khung [Trò chuyện] (sẵn sàng={c_ok}): '{c_snip}'", flush=True)
                print(f"[cdp/scan] Khung [Hoạt động] (sẵn sàng={a_ok}): '{a_snip}'", flush=True)

                while not stop_event.is_set():
                    req_id += 1
                    poll_cmd = {
                        "id": req_id,
                        "method": "Runtime.evaluate",
                        "params": {"expression": CDP_POLL_JS, "returnByValue": True},
                    }
                    ws.send(json.dumps(poll_cmd))
                    resp = json.loads(ws.recv())
                    raw_val = (
                        resp.get("result", {})
                        .get("result", {})
                        .get("value", "[]")
                    )

                    events = []
                    if isinstance(raw_val, str):
                        try:
                            events = json.loads(raw_val)
                        except Exception:
                            events = []
                    elif isinstance(raw_val, list):
                        events = raw_val

                    for raw_ev in events:
                        if isinstance(raw_ev, dict):
                            raw_ev.setdefault("text", raw_ev.get("content", ""))
                            src_lbl = raw_ev.get("source", "Trình duyệt")
                            usr = raw_ev.get("user", "Khách")
                            txt = raw_ev.get("text", "")
                            typ = raw_ev.get("type", "chat")
                            print(f"[cdp/fetch] Khung [{src_lbl}] ({typ}): {usr}: '{txt}'", flush=True)
                        norm = event_bridge.normalize(raw_ev)
                        if norm:
                            yield norm
                    time.sleep(poll_interval_s)

        except Exception:
            if not stop_event.is_set():
                time.sleep(1.0)
