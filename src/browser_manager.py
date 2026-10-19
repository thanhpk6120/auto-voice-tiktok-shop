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
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Iterator

# Mẫu hợp lệ cho tên phiên bản Chrome (chỉ cho phép số và dấu chấm)
_VERSION_RE = re.compile(r"^[0-9]+(\.[0-9]+)*$")
CDP_SETUP_JS = r"""
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
        'người theo dõi',
        'chào mừng bạn đến với tiktok live'
    ];

    const DATE_TIME_RE = /^(\d{1,2}[/.\-]\d{1,2}([/.\-]\d{2,4})?(\s+\d{1,2}(:\d{2})*)?|\d{1,2}:\d{2}(:\d{2})?)$/;

    function isJunk(text) {
        if (!text) return true;
        const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
        if (lines.length >= 4) return true;
        const s = text.trim().toLowerCase();
        if (s.length < 2) return true;
        if (DATE_TIME_RE.test(s)) return true;
        for (const phrase of JUNK_PHRASES) {
            if (s === phrase || s.startsWith(phrase)) return true;
        }
        return false;
    }

    const seenRecent = new Map();
    function pushEvent(type, user, content, source, raw) {
        const now = Date.now();
        const key = type + '|' + (user || '') + '|' + (content || '');
        // Dọn bớt các mục cũ quá 120 giây khi bộ nhớ lớn
        if (seenRecent.size > 500) {
            for (const [k, t] of seenRecent.entries()) {
                if (now - t > 120000) seenRecent.delete(k);
            }
        }
        const lastTime = seenRecent.get(key);
        // Chống lặp sự kiện cùng loại/user/nội dung trong vòng 120 giây (tránh virtual DOM re-render)
        if (lastTime && (now - lastTime < 120000)) return;
        seenRecent.set(key, now);
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
                    if (el.className && typeof el.className === 'string' && el.className.includes('flex-col') && el.className.includes('h-full')) {
                        return el;
                    }
                    el = el.parentElement;
                }
            }
        }
        return document.querySelector('.arco-list-content, [role="list"]');
    }

    function findActivityList() {
        const pTags = document.querySelectorAll('p, span, div');
        for (const p of pTags) {
            if (p.children.length === 0 && p.innerText.trim() === 'Hoạt động') {
                let el = p;
                while (el && el !== document.body) {
                    if (el.className && typeof el.className === 'string' && el.className.includes('flex-col') && el.className.includes('h-full')) {
                        return el;
                    }
                    el = el.parentElement;
                }
            }
        }
        return document.querySelector('div.bg-neutral-white.flex-grow, [class*="activity"]');
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

                            let evType = 'chat';
                            let user = 'Khách';
                            let text = raw;

                            const nickEl = node.querySelector('[class*="nick"], [class*="user"], [class*="name"]');
                            if (nickEl && nickEl.innerText.trim()) {
                                user = nickEl.innerText.trim();
                                text = raw.replace(user, '').trim().replace(/^[:：\s]+/, '') || raw;
                            } else if (raw.includes(':') || raw.includes('：')) {
                                const parts = raw.split(/[:：]/, 2);
                                if (parts.length === 2 && parts[0].length < 30) {
                                    user = parts[0].trim();
                                    text = parts[1].trim();
                                }
                            } else {
                                const lines = raw.split('\n').map(l => l.trim()).filter(Boolean);
                                if (lines.length >= 2 && lines[0].length < 30) {
                                    user = lines[0];
                                    text = lines.slice(1).join(' ');
                                }
                            }

                            const mJoin = raw.match(/([^\s]+(?:\s+[^\s]+){0,3})\s+(?:vừa vào|đã vào|joined|đã tham gia|vừa tham gia|tham gia)/i);
                            if (mJoin) {
                                user = mJoin[1].trim();
                                text = raw;
                                evType = 'join';
                            }

                            if (isJunk(text)) continue;
                            pushEvent(evType, user, text, 'Trò chuyện', raw);
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
                            } else if (s.includes('đang xem') || s.includes('viewing') || s.includes('bấm xem') || s.includes('xem sản phẩm')) {
                                evType = 'viewing_product';
                            } else if (s.includes('vào phòng') || s.includes('joined') || s.includes('follow') || s.includes('chia sẻ')) {
                                evType = 'join';
                            }
                            const parts = raw.split(/[:：]/, 2);
                            if (parts.length === 2 && parts[0].length < 30) {
                                user = parts[0].trim();
                                text = parts[1].trim();
                            } else {
                                const mOrder = raw.match(/(?:khách hàng|người mua)?\s*([^\s]+(?:\s+[^\s]+){0,3})\s+(?:đã chốt đơn|đã đặt hàng|ordered|đã mua)\s*(.*)/i);
                                if (mOrder) {
                                    user = mOrder[1].trim();
                                    text = mOrder[2].trim() || raw;
                                }
                                const mGift = raw.match(/([^\s]+(?:\s+[^\s]+){0,3})\s+(?:đã tặng|gửi tặng)\s*(.*)/i);
                                if (mGift) {
                                    user = mGift[1].trim();
                                    text = mGift[2].trim() || raw;
                                }
                                const mView = raw.match(/([^\s]+(?:\s+[^\s]+){0,3})\s+(?:đang xem sản phẩm|đang xem|bấm xem|viewing product|viewing)\s*(.*)/i);
                                if (mView) {
                                    user = mView[1].trim();
                                    text = mView[2].trim() || raw;
                                    evType = 'viewing_product';
                                }
                                const mJoin = raw.match(/([^\s]+(?:\s+[^\s]+){0,3})\s+(?:vừa vào|đã vào|joined|đã tham gia|vừa tham gia|tham gia)/i);
                                if (mJoin) {
                                    user = mJoin[1].trim();
                                    text = raw;
                                    evType = 'join';
                                }
                                if (user === 'Khách') {
                                    const lines = raw.split('\n').map(l => l.trim()).filter(Boolean);
                                    if (lines.length >= 2 && lines[0].length < 30) {
                                        user = lines[0];
                                        text = lines.slice(1).join(' ');
                                    }
                                }
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
                            raw_str = raw_ev.get("raw", "")
                            if raw_str:
                                try:
                                    classified = event_bridge.classify_line(raw_str)
                                    if classified:
                                        if classified.get("user") and classified["user"] != "Khách":
                                            raw_ev["user"] = classified["user"]
                                        if classified.get("product"):
                                            raw_ev["product"] = classified["product"]
                                        if classified.get("amount"):
                                            raw_ev["amount"] = classified["amount"]
                                        if classified.get("gift"):
                                            raw_ev["gift"] = classified["gift"]
                                            raw_ev["count"] = classified.get("count", 1)
                                        if classified.get("type"):
                                            raw_ev["type"] = classified["type"]
                                except Exception:
                                    pass
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



# -----------------------------------------------------------------------------
# Lấy danh sách sản phẩm trong giỏ hàng live (logic DOM thuần, KHÔNG dùng AI)
# -----------------------------------------------------------------------------

def _slugify_product(name: str, fallback: str = "san-pham") -> str:
    """Đổi tên sản phẩm thành slug tên file (bỏ dấu, chỉ giữ chữ/số/gạch)."""
    import unicodedata

    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("đ", "d").replace("Đ", "D")
    s = re.sub(r"[^\w\s-]", "", s.lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")[:60]
    return s or fallback


def _cdp_new_tab(url: str, cdp_port: int = 30899, timeout_s: float = 5.0) -> str:
    """Mở tab mới trong trình duyệt qua HTTP endpoint CDP. Trả về targetId ("" nếu lỗi)."""
    endpoint = f"http://127.0.0.1:{cdp_port}/json/new?{urllib.parse.quote(url, safe='')}"
    try:
        req = urllib.request.Request(endpoint, method="PUT",
                                    headers={"User-Agent": "AutoVoiceTikTokShop/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return str(data.get("id") or "")
    except Exception:
        return ""


def _cdp_close_tab(target_id: str, cdp_port: int = 30899, timeout_s: float = 5.0) -> None:
    """Đóng tab theo targetId qua HTTP endpoint CDP."""
    if not target_id:
        return
    endpoint = f"http://127.0.0.1:{cdp_port}/json/close/{urllib.parse.quote(target_id)}"
    try:
        req = urllib.request.Request(endpoint, headers={"User-Agent": "AutoVoiceTikTokShop/1.0"})
        urllib.request.urlopen(req, timeout=timeout_s).close()
    except Exception:
        pass


def _cdp_ws_for_target(target_id: str, cdp_port: int = 30899, timeout_s: float = 5.0):
    """Mở websocket tới một target cụ thể (không đụng tab đang làm việc)."""
    url = f"http://127.0.0.1:{cdp_port}/json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AutoVoiceTikTokShop/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            targets = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    for t in targets or []:
        if str(t.get("id")) == str(target_id) and t.get("webSocketDebuggerUrl"):
            try:
                from websockets.sync.client import connect
                return connect(t["webSocketDebuggerUrl"], open_timeout=timeout_s, close_timeout=2)
            except Exception:
                return None
    return None


# Script chạy TRONG TAB DASHBOARD: nhúng PDP vào iframe ẩn cùng origin rồi đọc DOM.
# Không mở tab mới -> tránh trang "Security Check" (slider) của TikTok.
_CDP_PRODUCT_DETAIL_IFRAME_JS = r"""
(async () => {
    const pid = '__PID__';
    const url = 'https://shop.tiktok.com/view/product/' + pid;
    const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();

    const ifr = document.createElement('iframe');
    ifr.style.cssText = 'position:fixed;left:-9999px;top:0;width:1280px;height:1400px;';
    ifr.src = url;
    document.body.appendChild(ifr);

    const wait = (ms) => new Promise(r => setTimeout(r, ms));
    const loaded = await new Promise((res) => {
        let done = false;
        ifr.onload = () => { if (!done) { done = true; res(true); } };
        setTimeout(() => { if (!done) { done = true; res(false); } }, 15000);
    });

    const out = {
        id: pid, name: '', url: url, description: '', reviews: [],
        real_price: '', origin_price: '', discount: ''
    };
    try {
        await wait(4000);
        const d = ifr.contentDocument;
        const w = ifr.contentWindow;
        if (!d) return out;
        if (d.body && d.body.innerText.includes('Verify to continue')) return out;

        out.id = (d.location.href.match(/(?:view\/product|pdp)\/(\d{6,})/) || [])[1] || pid;
        const h1 = d.querySelector('h1') || d.querySelector('[class*="H4-Semibold"]');
        out.name = norm(h1 && h1.innerText).slice(0, 400);

        // Trích xuất giá khuyến mại thực tế trên trang chi tiết sản phẩm (PDP)
        const lt = d.querySelector('span[class*="line-through"], div[class*="line-through"]');
        if (lt && lt.parentElement) {
            const par = lt.parentElement;
            out.origin_price = norm(lt.innerText);
            for (const el of par.querySelectorAll('*')) {
                if (el.children.length === 0) {
                    const txt = norm(el.innerText);
                    if (txt.includes('%')) {
                        out.discount = txt;
                    } else if (el !== lt && !txt.includes('₫') && !txt.includes('đ') && /^[\d.,]+$/.test(txt)) {
                        out.real_price = txt + '₫';
                    }
                }
            }
        }
        if (!out.real_price) {
            for (const el of d.querySelectorAll('span, div')) {
                if (el.children.length === 0) {
                    const t = norm(el.innerText);
                    if (/^[\d.,]+\s*₫$/.test(t) || /^₫[\d.,]+$/.test(t)) {
                        out.real_price = t.replace(/^₫/, '') + '₫';
                        break;
                    }
                }
            }
        }

        // Mô tả: ưu tiên khối ngay sau tiêu đề "Mô tả sản phẩm"
        const hd = [...d.querySelectorAll('div,span,p,h2,h3')]
            .find(e => e.children.length === 0 && /^mô tả sản phẩm$/i.test(norm(e.innerText)));
        let blocks = [];
        if (hd) {
            let node = hd.parentElement;
            for (let i = 0; node && i < 4; i++) {
                const cands = [...node.querySelectorAll('div,p,span')]
                    .filter(e => e.children.length === 0 && norm(e.innerText).length >= 60)
                    .map(e => norm(e.innerText));
                if (cands.length) { blocks = cands; break; }
                node = node.parentElement;
            }
        }
        if (!blocks.length) {
            blocks = [...d.querySelectorAll('div,p,span')]
                .filter(e => e.children.length === 0 && norm(e.innerText).length >= 120)
                .map(e => norm(e.innerText))
                .filter(t => !/^\d+(\.\d+)?$/.test(t));
        }
        const seenB = new Set();
        out.description = blocks.filter(b => !seenB.has(b) && seenB.add(b)).join('\n').slice(0, 3000);

        // Đánh giá: cuộn xuống khu review để lazy-load, rồi đọc từng item
        const box = d.querySelector('[class*="reviews-"]');
        if (box) {
            box.scrollIntoView();
            for (let i = 0; i < 8; i++) { w.scrollBy(0, 900); await wait(450); }
            const list = [...box.children].pop();
            const cont = list && [...list.children].pop();
            if (cont) {
                for (const it of cont.children) {
                    const leaf = [...it.querySelectorAll('*')].filter(c => c.children.length === 0 && norm(c.innerText));
                    const txts = leaf.map(c => norm(c.innerText));
                    if (!txts.length) continue;
                    const user = txts[0] || '';
                    // Câu dài nhất, không phải nhãn hệ thống
                    const body = txts.filter(s => s.length >= 15 && !/đã xác minh|mặt hàng|^\d{4}-\d{2}-\d{2}$|^\+\d+$/i.test(s))
                                      .sort((a, b) => b.length - a.length)[0] || '';
                    if (!body) continue;
                    const date = txts.find(s => /^\d{4}-\d{2}-\d{2}$/.test(s)) || '';
                    out.reviews.push(user + ': ' + body + (date ? ' (' + date + ')' : ''));
                }
            }
        }
    } catch (e) {
        /* tra ve nhung gi da co */
    } finally {
        try { ifr.remove(); } catch (e) { /* ignore */ }
    }
    return out;
})()
"""


# Script JS quét bảng sản phẩm trong giỏ hàng live (DOM virtual list)
_CDP_PRODUCTS_JS = r"""
(() => {
    // Dashboard hiện dùng VIRTUAL LIST (không còn <tr>/arco-table-tr).
    // Mỗi sản phẩm là 1 div.rounded-4.mb-8 cao ~90-200px trong
    // [class*="virtualized-container"]. Đọc text con để lấy tên/giá/tồn.
    const out = [];
    const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
    const isPrice = (s) => /^[0-9.,]+\s*\u20ab$/.test(s);
    const seen = new Set();

    const roots = [
        ...document.querySelectorAll('div.rounded-4.mb-8'),
        ...document.querySelectorAll('[class*="virtualized-container"] div[class*="rounded-4"]'),
    ];

    let idx = 0;
    for (const el of roots) {
        const rect = el.getBoundingClientRect();
        if (rect.height < 80 || rect.height > 320 || rect.width < 200) continue;
        if (roots.some(o => o !== el && o.contains(el))) continue;

        const leaves = [...el.querySelectorAll('*')]
            .filter(c => c.children.length === 0 && norm(c.innerText))
            .map(c => norm(c.innerText));
        if (!leaves.length) continue;

        const name = leaves.find(s => s.length >= 12 && !isPrice(s) &&
            !/^(Lựa chọn yêu thích|Đã yêu cầu minh họa|Còn:)/i.test(s));
        if (!name) continue;

        const prices = leaves.filter(isPrice);
        const stock = leaves.find(s => /^Còn:/i.test(s)) || '';
        const pinned = leaves.some(s => /^(?:Đang ghim|Đang giới thiệu|Hủy ghim|Hủy giới thiệu)$/i.test(s) || /\b(?:đang ghim|đang giới thiệu)\b/i.test(s));
        const key = name.slice(0, 80);
        if (seen.has(key)) continue;
        seen.add(key);

        idx += 1;
        out.push({
            index: idx,
            id: '',
            name: name,
            price: prices[0] || '',
            is_pinned: pinned,
            url: '',
            raw: { stock: stock, origin_price: prices[1] || '', dom: true },
        });
        if (idx >= 200) break;
    }
    return out;
})()
"""


def _product_id_from_url(url: str) -> str:
    """Tách product_id (>=10 chữ số) từ URL sản phẩm TikTok Shop. Rỗng nếu không có."""
    m = re.search(r"(?:product_id|productId|id)=([0-9]{6,})", url or "")
    if not m:
        m = re.search(r"/(?:view/product|product|pdp|p)/([0-9]{6,})", url or "")
    return m.group(1) if m else ""


def _cdp_eval(ws, expr: str, req_id: int = 1, timeout_s: float = 20.0):
    """Gửi Runtime.evaluate và trả về giá trị đã parse JSON (nếu là chuỗi JSON)."""
    ws.send(json.dumps({
        "id": req_id,
        "method": "Runtime.evaluate",
        "params": {"expression": expr, "returnByValue": True, "awaitPromise": True},
    }))
    deadline = time.monotonic() + max(1.0, timeout_s)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            resp = json.loads(ws.recv(timeout=remaining))
        except Exception:
            return None
        if resp.get("id") != req_id:
            continue
        res = resp.get("result", {})
        if res.get("exceptionDetails"):
            return None
        val = res.get("result", {}).get("value")
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return val
        return val


def _connect_cdp(cdp_port: int = 30899, timeout_s: float = 5.0):
    """Mở kết nối websocket tới tab TikTok Shop. Trả (ws, None) hoặc (None, lý do)."""
    try:
        from websockets.sync.client import connect
    except ImportError:
        return None, "Thiếu thư viện websockets"
    target = get_cdp_target(cdp_port=cdp_port)
    if not target or not target.get("webSocketDebuggerUrl"):
        return None, f"Không tìm thấy tab TikTok Shop trên cổng CDP {cdp_port}"
    return connect(target["webSocketDebuggerUrl"], open_timeout=timeout_s, close_timeout=2), None


# Gọi lại endpoint giỏ hàng live NGAY TRONG TAB DASHBOARD: dùng URL có chữ ký mà
# chính trang đã phát ra (msToken/X-Bogus). Không reload -> không gián đoạn live.
# Lưu ý: khoá dữ liệu thật là data.products (KHÔNG phải list/items).
_CDP_LIVE_PRODUCT_API_JS = r"""
(async () => {
    const entries = performance.getEntriesByType('resource')
        .map(e => e.name)
        .filter(n => n.includes('/live_product/list'));
    if (!entries.length) return null;

    // Duyệt từ mới nhất về cũ: URL cũ có thể đã hết hạn chữ ký.
    for (let i = entries.length - 1; i >= 0; i--) {
        try {
            const r = await fetch(entries[i], { credentials: 'include' });
            if (!r.ok) continue;
            const j = await r.json();
            const d = j.data || {};
            const items = d.products || d.list || d.items || (Array.isArray(d) ? d : []);
            if (items && items.length) {
                const introId = String(d.introduce_id || d.just_pinned_introduce_id || '');
                return { products: items, introduce_id: introId };
            }
        } catch (e) { /* thu URL ke tiep */ }
    }
    return null;
})()
"""


def _fetch_products_via_page_api(cdp_port: int = 30899, timeout_s: float = 25.0) -> dict | list:
    """Gọi lại /live_product/list từ trong tab dashboard bằng URL đã ký sẵn.

    Không reload trang nên không gián đoạn phiên live. Trả dict chứa
    products và introduce_id (hoặc list thô), hoặc [] nếu lỗi/hết hạn.
    """
    ws, err = _connect_cdp(cdp_port=cdp_port)
    if ws is None:
        if err:
            print(f"[browser] {err}")
        return []
    try:
        with ws:
            data = _cdp_eval(ws, _CDP_LIVE_PRODUCT_API_JS, req_id=8990, timeout_s=timeout_s)
        return data if isinstance(data, (dict, list)) else []
    except Exception as e:
        print(f"[browser] Lỗi gọi API giỏ hàng trong trang: {e}")
        return []


def _harvest_live_products_network(cdp_port: int = 30899, timeout_s: float = 35.0) -> dict | list:
    """Bắt response /live_product/list của dashboard qua CDP Network.

    API này chỉ chạy được với chữ ký msToken dùng-một-lần do trang tự sinh nên
    không thể tự gọi lại; cách duy nhất lấy product_id là bắt response thật.
    Trả về list dict thô (product_id, title, giá...) hoặc [] nếu không bắt được.
    """
    ws, err = _connect_cdp(cdp_port=cdp_port)
    if ws is None:
        if err:
            print(f"[browser] {err}")
        return []

    pending: dict[str, str] = {}
    seen: set[str] = set()
    bodies: list[dict] = []
    got = 0

    try:
        with ws:
            ws.send(json.dumps({"id": 8900, "method": "Network.enable", "params": {}}))
            time.sleep(0.3)
            ws.send(json.dumps({"id": 8901, "method": "Page.reload", "params": {}}))

            deadline = time.monotonic() + max(5.0, float(timeout_s))
            while time.monotonic() < deadline:
                try:
                    msg = json.loads(ws.recv(timeout=3))
                except Exception:
                    continue
                method = msg.get("method")

                if method == "Network.responseReceived":
                    url = msg["params"]["response"].get("url", "")
                    if "/live_product/list" in url:
                        pending[msg["params"]["requestId"]] = url
                elif method == "Network.loadingFinished":
                    rid = msg["params"]["requestId"]
                    if rid in pending and rid not in seen:
                        seen.add(rid)
                        got += 1
                        ws.send(json.dumps({
                            "id": 8000 + got,
                            "method": "Network.getResponseBody",
                            "params": {"requestId": rid},
                        }))
                elif isinstance(msg.get("id"), int) and 8000 < msg["id"] <= 8100:
                    try:
                        payload = json.loads(msg.get("result", {}).get("body") or "{}")
                    except Exception:
                        continue
                    d = payload.get("data") or {}
                    items = d.get("products") or d.get("list") or []
                    intro_id = str(d.get("introduce_id") or d.get("just_pinned_introduce_id") or "")
                    if items:
                        bodies = {"products": items, "introduce_id": intro_id}
                        break
    except Exception as e:
        print(f"[browser] Lỗi harvest live products: {e}")
    return bodies


def fetch_live_products_cdp(cdp_port: int = 30899) -> list[dict]:
    """Đọc danh sách sản phẩm trong giỏ hàng live của dashboard TikTok Shop.

    Nguồn chính: gọi lại /live_product/list ngay trong tab dashboard (nhanh, không reload)
    hoặc bắt qua CDP Network. Trạng thái ghim chuẩn xác từ introduce_id của API
    (chỉ có tối đa 1 sản phẩm ghim trên live tại 1 thời điểm).
    Dự phòng: quét DOM virtual list khi không gọi được API.
    Trả về list dict: index, id, name, price, is_pinned, url, raw.
    """
    raws: list[dict] = []
    introduce_id = ""

    # 1) Goi lai API trong trang (nhanh, KHONG reload -> khong gian doan live)
    api_res = _fetch_products_via_page_api(cdp_port=cdp_port)
    if isinstance(api_res, dict):
        raws = api_res.get("products") or []
        introduce_id = str(api_res.get("introduce_id") or "")
    elif isinstance(api_res, list):
        raws = api_res

    # 2) Du phong: bat response khi trang tu tai lai
    if not raws:
        net_res = _harvest_live_products_network(cdp_port=cdp_port)
        if isinstance(net_res, dict):
            raws = net_res.get("products") or []
            introduce_id = str(net_res.get("introduce_id") or "")
        elif isinstance(net_res, list):
            raws = net_res

    if raws:
        products: list[dict] = []
        for i, p in enumerate(raws, 1):
            if not isinstance(p, dict):
                continue
            name = str(p.get("title") or "").strip()
            if not name:
                continue
            pid = str(p.get("product_id") or "")
            # Trạng thái ghim: chỉ có tối đa 1 sản phẩm ghim trên live (trùng introduce_id)
            is_pinned = bool(introduce_id and pid and pid == introduce_id)
            products.append({
                "index": i,
                "id": pid,
                "name": name,
                "price": str(p.get("format_available_price") or ""),
                "is_pinned": is_pinned,
                "url": f"https://shop.tiktok.com/view/product/{pid}" if pid else "",
                "raw": {
                    "api": True,
                    "stock_num": p.get("stock_num"),
                    "origin_price": str(p.get("format_origin_price") or ""),
                    "shop": ((p.get("seller_info") or {}).get("shop_name") or ""),
                    "introduce_id": introduce_id,
                },
            })
        return products

    # 3) Dự phòng: quét DOM (đảm bảo tối đa 1 sản phẩm ghim)
    return _scan_live_products_dom(cdp_port=cdp_port)


def _scan_live_products_dom(cdp_port: int = 30899) -> list[dict]:
    """Quét DOM virtual list của dashboard. Dự phòng khi không bắt được API."""
    ws, err = _connect_cdp(cdp_port=cdp_port)
    if ws is None:
        if err:
            print(f"[browser] {err}")
        return []
    try:
        with ws:
            data = _cdp_eval(ws, _CDP_PRODUCTS_JS, req_id=9001, timeout_s=20.0)
        if not isinstance(data, list):
            return []
        out: list[dict] = []
        pinned_found = False
        for i, p in enumerate(data, 1):
            if not isinstance(p, dict):
                continue
            name = str(p.get("name") or "").strip()
            if not name:
                continue
            is_pin = bool(p.get("is_pinned"))
            if is_pin and not pinned_found:
                pinned_found = True
            else:
                is_pin = False
            out.append({
                "index": int(p.get("index") or i),
                "id": str(p.get("id") or ""),
                "name": name,
                "price": str(p.get("price") or ""),
                "is_pinned": is_pin,
                "url": str(p.get("url") or ""),
                "raw": p.get("raw") if isinstance(p.get("raw"), dict) else {},
            })
        return out
    except Exception as e:
        print(f"[browser] Lỗi _scan_live_products_dom: {e}")
        return []


def crawl_product_detail_cdp(
    url: str,
    cdp_port: int = 30899,
    max_reviews: int = 10,
    timeout_s: float = 60.0,
) -> dict:
    """Lấy tên, mô tả, đánh giá của 1 sản phẩm qua iframe ẩn trong tab dashboard.

    Không mở tab mới (tab mới bị TikTok chặn bằng "Security Check"), cũng không
    điều hướng tab dashboard đang chạy live. Trả về dict: id, name, url,
    description, reviews (tối đa max_reviews phần tử). Lỗi/timeout -> dict rỗng.
    """
    empty = {"id": "", "name": "", "url": url or "", "description": "", "reviews": []}
    if not url:
        return empty

    pid = _product_id_from_url(url)
    if not pid:
        print(f"[browser] Không tách được product_id từ URL: {url}")
        return empty

    try:
        from websockets.sync.client import connect  # noqa: F401
    except ImportError:
        print("[browser] Thiếu thư viện websockets")
        return empty

    ws, err = _connect_cdp(cdp_port=cdp_port)
    if ws is None:
        print(f"[browser] {err}")
        return empty

    script = _CDP_PRODUCT_DETAIL_IFRAME_JS.replace("__PID__", pid)
    try:
        with ws:
            # Không đổi URL tab dashboard -> không cần khôi phục, không rủi ro SPA.
            data = _cdp_eval(ws, script, req_id=9300, timeout_s=timeout_s)
    except Exception as e:
        print(f"[browser] Lỗi crawl_product_detail_cdp ({url}): {e}")
        return empty

    if not isinstance(data, dict):
        return empty
    reviews = data.get("reviews")
    if not isinstance(reviews, list):
        reviews = []
    limit = max(0, int(max_reviews))
    real_price = str(data.get("real_price") or "").strip()
    origin_price = str(data.get("origin_price") or "").strip()
    discount = str(data.get("discount") or "").strip()
    return {
        "id": str(data.get("id") or pid),
        "name": str(data.get("name") or ""),
        "url": str(data.get("url") or url),
        "description": str(data.get("description") or ""),
        "reviews": [str(r) for r in reviews[:limit]],
        "price": real_price,
        "real_price": real_price,
        "origin_price": origin_price,
        "discount": discount,
    }


def _live_dir(live_dir: str | Path | None = None) -> Path:
    """Thư mục context-live đã resolve (theo config nếu không truyền)."""
    if live_dir:
        target = Path(live_dir)
        if target.is_absolute():
            return target
    else:
        try:
            import settings
            return settings.resolve_path(settings.get().get("context_live_dir") or "context-live")
        except Exception:
            target = Path(os.getenv("CONTEXT_LIVE_DIR", "context-live"))
    try:
        import settings
        return settings.resolve_path(target)
    except Exception:
        return Path(__file__).resolve().parent.parent / target

def get_product_context_path(product: dict, live_dir: str | Path | None = None) -> Path | None:
    """Trả về Path nếu file context-live của sản phẩm đã tồn tại, ngược lại None."""
    if not isinstance(product, dict):
        return None
    name = str(product.get("name") or "").strip()
    pid = str(product.get("id") or "").strip()
    if not name and not pid:
        return None

    target_dir = _live_dir(live_dir)
    if not target_dir.is_dir():
        return None

    slug = _slugify_product(name, fallback=f"san-pham-{pid or 'live'}")
    key = f"{pid}||{slug}" if pid else slug
    index_path = target_dir / "_index.json"
    if index_path.is_file():
        try:
            raw = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                fname = raw.get(key)
                if fname and (target_dir / fname).is_file():
                    return target_dir / fname
        except Exception:
            pass

    # Kiểm tra trực tiếp file .md
    cand = target_dir / f"{slug}.md"
    if cand.is_file():
        return cand
    if pid:
        cand_pid = target_dir / f"{slug}-{pid}.md"
        if cand_pid.is_file():
            return cand_pid
    return None


def has_product_context(product: dict, live_dir: str | Path | None = None) -> bool:
    """Kiểm tra sản phẩm đã có file context-live hay chưa."""
    return get_product_context_path(product, live_dir) is not None


def read_product_context(product: dict, live_dir: str | Path | None = None) -> dict | None:
    """Đọc thông tin giá và nội dung từ file context-live đã tồn tại của sản phẩm."""
    path = get_product_context_path(product, live_dir)
    if not path or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        out = {"path": str(path), "price": "", "real_price": "", "origin_price": "", "discount": ""}
        for line in text.splitlines():
            line = line.strip()
            m = re.match(
                r"^-?\s*giá\s*(?:khuyến mại(?:\s*thực tế(?:\s*trên live)?)?|ưu đãi|niêm yết(?:\s*giỏ hàng)?)?\s*:\s*(.+)$",
                line,
                re.I,
            )
            if m and not out["price"]:
                val = m.group(1).strip()
                out["price"] = val.split("(")[0].strip()
                m_real = re.search(r"([\d.,]+\s*₫)", val)
                if m_real:
                    out["real_price"] = m_real.group(1)
        return out
    except Exception:
        return None


def save_live_products_cache(products: list[dict], live_dir: str | Path | None = None) -> Path | None:
    """Lưu danh sách sản phẩm giỏ hàng live vào cache để lần sau mở app có sẵn."""
    if not isinstance(products, list):
        return None
    target_dir = _live_dir(live_dir)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        cache_path = target_dir / "_products_cache.json"
        cache_path.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
        return cache_path
    except Exception as e:
        print(f"[browser] Lỗi lưu cache sản phẩm live: {e}")
        return None


def load_live_products_cache(live_dir: str | Path | None = None) -> list[dict]:
    """Tải danh sách sản phẩm giỏ hàng live đã lưu từ phiên trước."""
    target_dir = _live_dir(live_dir)
    cache_path = target_dir / "_products_cache.json"
    if not cache_path.is_file():
        return []
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [p for p in raw if isinstance(p, dict) and (p.get("name") or p.get("id"))]
    except Exception as e:
        print(f"[browser] Lỗi đọc cache sản phẩm live: {e}")
    return []



def save_product_context(product: dict, live_dir: str | Path | None = None) -> Path | None:
    """Ghi context 1 sản phẩm vào context-live, đè file cũ nếu trùng cả tên và id.

    Dùng `_index.json` làm chỉ mục: khoá `<id>||<slug>`, giá trị tên file.
    Id rỗng -> khoá chỉ dùng slug tên.
    Trả về Path file đã ghi, hoặc None nếu lỗi.
    """
    if not isinstance(product, dict):
        return None

    name = str(product.get("name") or "").strip()
    pid = str(product.get("id") or "").strip()
    if not name and not pid:
        return None

    target_dir = _live_dir(live_dir)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[browser] Không tạo được thư mục {target_dir}: {e}")
        return None

    index_path = target_dir / "_index.json"
    index: dict = {}
    if index_path.is_file():
        try:
            raw = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                index = {str(k): str(v) for k, v in raw.items()}
        except Exception:
            index = {}

    slug = _slugify_product(name, fallback=f"san-pham-{pid or 'live'}")
    key = f"{pid}||{slug}" if pid else slug

    # Tên file dựa trên TÊN sản phẩm (không dùng tiền tố thứ tự giỏ hàng).
    used_names = {v for k, v in index.items() if k != key}

    existing = index.get(key)
    if existing and (target_dir / existing).is_file():
        file_path = target_dir / existing          # ĐÈ LÊN file cũ, không tạo mới
    else:
        candidate = f"{slug}.md"
        # Trùng tên nhưng KHÁC id -> thêm hậu tố id để không ghi đè file của sản phẩm kia
        if candidate in used_names or (target_dir / candidate).is_file():
            candidate = f"{slug}-{pid}.md" if pid else f"{slug}-{abs(hash(key)) % 100000}.md"
        file_path = target_dir / candidate
        index[key] = file_path.name

    real_price = str(product.get("real_price") or "").strip()
    origin_price = str(product.get("origin_price") or "").strip()
    discount = str(product.get("discount") or "").strip()
    list_price = str(product.get("list_price") or product.get("price") or "Ưu đãi trên live").strip()
    effective_price = real_price or list_price

    url = str(product.get("url") or "").strip()
    desc = str(product.get("description") or "").strip()
    reviews = product.get("reviews") or []
    if not isinstance(reviews, list):
        reviews = []

    lines = [
        f"# {name or pid}",
        "",
        f"- Mã sản phẩm (id): {pid or 'không xác định'}",
        f"- Thứ tự trong giỏ hàng live: {product.get('index', '-')}",
    ]
    if real_price:
        promo_info = f"- Giá khuyến mại thực tế trên live: {real_price}"
        details_str = []
        if origin_price:
            details_str.append(f"giá gốc {origin_price}")
        if discount:
            details_str.append(f"giảm {discount}")
        if details_str:
            promo_info += f" ({', '.join(details_str)})"
        lines.append(promo_info)
        if list_price and list_price != real_price:
            lines.append(f"- Giá niêm yết giỏ hàng: {list_price}")
    else:
        lines.append(f"- Giá ưu đãi: {list_price}")

    if url:
        lines.append(f"- Link sản phẩm: {url}")
    lines += ["", "## Mô tả sản phẩm", "", desc or "(Chưa lấy được mô tả.)", ""]
    lines += ["## Đánh giá / bình luận của khách", ""]
    if reviews:
        lines += [f"{i}. {r}" for i, r in enumerate(reviews, 1)]
    else:
        lines.append("(Sản phẩm chưa có đánh giá/bình luận nào.)")
    lines += [
        "",
        "## Hướng dẫn tư vấn bán hàng",
        "",
        f"- Khách hỏi '{name or pid}' (hoặc mã {product.get('index', '-')}) thì tư vấn theo đúng thông tin trên.",
        "- Dựa vào mô tả và đánh giá thật ở trên để trả lời, không bịa thông tin ngoài file này.",
    ]
    if real_price:
        cta_price = f"- Báo đúng giá khuyến mại thực tế chỉ {real_price}"
        if discount:
            cta_price += f" (đang giảm sốc {discount})"
        cta_price += " chỉ áp dụng khi mua trên phiên live."
        lines.append(cta_price)
    else:
        lines.append(f"- Nhấn mạnh giá ưu đãi {list_price} chỉ có trên phiên live.")
    lines += [
        "- Nhắc khách bấm giỏ hàng góc trái màn hình để chốt đơn.",
        "",
    ]
    content = "\n".join(lines)

    try:
        file_path.write_text(content, encoding="utf-8")
        index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        print(f"[browser] Lỗi ghi context sản phẩm {file_path}: {e}")
        return None

    try:
        import event_analyzer
        event_analyzer.reload_intent()
    except Exception:
        pass
    return file_path


def save_live_products_to_context_live(products: list[dict], live_dir: str | Path | None = None) -> list[Path]:
    """Lưu danh sách sản phẩm lấy từ giỏ hàng live vào các file markdown trong context-live/."""
    if not products:
        return []

    target_dir = Path(live_dir or os.getenv("CONTEXT_LIVE_DIR", "context-live"))
    if not target_dir.is_absolute():
        try:
            import settings
            target_dir = settings.resolve_path(target_dir)
        except Exception:
            target_dir = Path(__file__).resolve().parent.parent / target_dir

    target_dir.mkdir(parents=True, exist_ok=True)
    saved_files: list[Path] = []

    for prod in products:
        idx = prod.get("index", 1)
        name = prod.get("name", f"Sản phẩm {idx}").strip()
        price = prod.get("price", "Ưu đãi trên live").strip()
        is_pinned = prod.get("is_pinned", False)

        slug = re.sub(r"[^\w\s-]", "", name.lower())
        slug = re.sub(r"[\s_-]+", "-", slug).strip("-")[:40] or f"san-pham-{idx}"
        file_path = target_dir / f"sp-{idx:02d}-{slug}.md"

        status_str = "Đang ghim giới thiệu trên live" if is_pinned else "Trong giỏ hàng live"
        content = (
            f"# Sản phẩm #{idx}: {name}\n\n"
            f"- Thứ tự trên live: Số {idx}\n"
            f"- Trạng thái: {status_str}\n"
            f"- Giá ưu đãi: {price}\n"
            f"- Ghi chú: Khách hỏi mã {idx}, số {idx}, sp {idx} hoặc '{name}' thì trả lời theo thông tin này.\n\n"
            f"## Hướng dẫn tư vấn bán hàng:\n"
            f"- Chào thân mật khách hàng, xác nhận đúng sản phẩm số {idx}.\n"
            f"- Nêu bật giá bán ưu đãi {price} độc quyền trên phiên live.\n"
            f"- Nhắc khách bấm vào giỏ hàng góc trái màn hình để đặt hàng ngay kẻo hết mã giảm giá.\n"
        )
        try:
            file_path.write_text(content, encoding="utf-8")
            saved_files.append(file_path)
        except Exception as e:
            print(f"[browser] Lỗi ghi file {file_path}: {e}")

    try:
        import event_analyzer
        event_analyzer.reload_intent()
    except Exception:
        pass

    return saved_files
