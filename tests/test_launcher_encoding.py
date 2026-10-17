"""Test: launcher phai ghi duoc tieng Viet ra stdout khi stdout la pipe.

Bug: tren Windows, khi stdout la pipe/file, Python dung cp1252 -> ghi ky tu tieng Viet
nem UnicodeEncodeError. `_Tee.write` nuot moi exception, nen CA DONG do bi mat (khong
chi hong ky tu). Trieu chung da quan sat: dong `[doctor] ... LLM ... reply='Duoc.'`
khong xuat hien trong stdout khi GUI spawn tien trinh con.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
for p in (str(SRC), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import launcher  # noqa: E402


class _Cp1252LikePipe(io.TextIOBase):
    """Gia lap stdout pipe tren Windows: encoding cp1252, ghi chu vuot bang -> UnicodeEncodeError."""

    encoding = "cp1252"

    def __init__(self):
        self.buf: list[str] = []

    def write(self, data: str) -> int:  # type: ignore[override]
        data.encode(self.encoding)  # nem UnicodeEncodeError voi tieng Viet
        self.buf.append(data)
        return len(data)

    def flush(self) -> None:
        pass


def test_force_utf8_uses_reconfigure_when_available():
    """Stream co reconfigure() -> launcher ep sang utf-8."""
    calls: list[dict] = []

    class _Stream:
        def reconfigure(self, **kw):
            calls.append(kw)

    launcher._force_utf8(_Stream())
    assert calls, "reconfigure phai duoc goi"
    assert calls[0].get("encoding") == "utf-8"
    assert calls[0].get("errors") == "replace"


def test_force_utf8_ignores_stream_without_reconfigure():
    """Stream khong co reconfigure (vd _Tee) -> bo qua, khong nem loi."""

    class _NoReconfigure:
        pass

    launcher._force_utf8(_NoReconfigure())  # khong duoc nem


def test_tee_swallows_vietnamese_loss_but_other_stream_keeps_it():
    """Chung minh co che mat dong: _Tee nuot loi tu stream cp1252 nhung van ghi stream utf-8.

    Day la ly do goc: log file (utf-8) CO dong LLM, con stdout pipe (cp1252) MAT dong do.
    """
    bad = _Cp1252LikePipe()
    good = io.StringIO()
    tee = launcher._Tee(bad, good)

    text = "LLM : OK reply='Được.'\n"
    tee.write(text)  # khong duoc nem
    tee.flush()

    assert good.getvalue() == text, "stream utf-8 phai nhan duoc nguyen van"
    assert bad.buf == [], "stream cp1252 khong ghi duoc -> day chinh la dong bi mat"


def test_tee_returns_length_even_when_all_streams_fail():
    class _Broken:
        def write(self, data):
            raise OSError("boom")

        def flush(self):
            raise OSError("boom")

    tee = launcher._Tee(_Broken())
    assert tee.write("abc") == 3
