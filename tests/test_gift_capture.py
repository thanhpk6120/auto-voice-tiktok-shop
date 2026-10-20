"""Regression: su kien tang qua tren khung [Hoat dong] phai lot qua isJunk + dedupe cua CDP.

Loi goc: isJunk() coi moi node >= 4 dong la rac. Dong su kien gift that (ten khach /
'da tang' / ten qua / 'x1') thuong >= 4 dong -> bi continue() truoc pushEvent, nen
khong bao gio sinh text/voice cam on. Dong thoi dedupe 120 giay nuot lan tang thu hai
cua cung khach + cung mon qua.

Test chay truc tiep doan JS that trong CDP_SETUP_JS bang node (bo qua neu khong co node).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import browser_manager as bm  # noqa: E402


def _cut(js: str, start: str, end: str) -> str:
    i = js.index(start)
    j = js.index(end, i)
    return js[i:j]


def _harness() -> str:
    js = bm.CDP_SETUP_JS
    return "\n".join([
        "const window = { __tiktok_cdp_queue_v2: [] };",
        "let __now = 0;",
        "const Date = { now: () => __now };",
        re.search(r"const JUNK_EXACT = \[.*?\];", js, re.S).group(0),
        re.search(r"const JUNK_PREFIX_MAX = .*?;", js).group(0),
        re.search(r"const DATE_TIME_RE = .*?;", js).group(0),
        re.search(r"const GIFT_ORDER_HINT = .*?/i;", js).group(0),
        _cut(js, "    function isJunk(text) {", "    const seenRecent"),
        _cut(js, "    const seenRecent = new Map();", "    function findChatList"),
        r"""
const GIFT_RAW = "Hoàng Nam\nđã tặng\nHoa hồng\nx1";
const out = {
  giftNode: isJunk(GIFT_RAW),
  giftLabel: isJunk("Quà tặng"),
  realComment: isJunk("Sản phẩm này còn hàng không shop?"),
  wholeList: isJunk(Array.from({length: 20}, (_, i) => "a" + i).join("\n")),
  dateLine: isJunk("20/10/2026"),
};
__now = 1000; pushEvent("gift", "A", "Hoa hồng", "Hoạt động", GIFT_RAW);
__now = 1500; pushEvent("gift", "A", "Hoa hồng", "Hoạt động", GIFT_RAW);
out.giftRepeatFast = window.__tiktok_cdp_queue_v2.length;
__now = 5000; pushEvent("gift", "A", "Hoa hồng", "Hoạt động", GIFT_RAW);
out.giftRepeatAfter = window.__tiktok_cdp_queue_v2.length;
__now = 6000; pushEvent("chat", "A", "abc", "chat", "abc");
__now = 7000; pushEvent("chat", "A", "abc", "chat", "abc");
out.chatDedupe = window.__tiktok_cdp_queue_v2.length;
out.queuedTypes = window.__tiktok_cdp_queue_v2.map(e => e.type);
console.log(JSON.stringify({ out }));
""",
    ])


@pytest.mark.skipif(shutil.which("node") is None, reason="can node de chay JS that")
def test_gift_event_survives_isjunk_and_dedupe():
    # ponytail: nap script qua stdin thay vi ghi file - temp cua may nay bi chan quyen ghi.
    proc = subprocess.run(
        ["node", "-"], input=_harness(), capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)["out"]

    # Node su kien gift that KHONG duoc coi la rac nua.
    assert out["giftNode"] is False
    # Nhan UI van bi chan, comment that van duoc giu, blob ca danh sach van bi chan.
    assert out["giftLabel"] is True
    assert out["realComment"] is False
    assert out["wholeList"] is True
    assert out["dateLine"] is True

    # gift: lan thu 2 trong 1,5 giay bi dedupe, lan thu 3 sau 5 giay phai duoc giu.
    assert out["giftRepeatFast"] == 1
    assert out["giftRepeatAfter"] == 2
    assert out["queuedTypes"] == ["gift", "gift", "chat"]
    # chat giu cua so chong lap dai (120 giay) nhu cu.
    assert out["chatDedupe"] == 3
