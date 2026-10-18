"""Entry point duy nhat cho ca GUI va CLI (dung cho ban dong goi .exe).

Quy tac:
  - Khong co tham so  -> mo GUI (import gui, gui.main()).
  - Co tham so        -> day thang cho app.main() (giu nguyen CLI: --help, doctor,
    run, simulate, live, stop).

Ly do console=False (xem README - Build .exe):
  .exe onedir mo GUI khong nen hien cua so console den. Nhung khi nguoi dung chay
  `AutoVoiceTikTokShop.exe doctor` tu terminal thi van phai thay output, nen launcher
  tu gan stdout/stderr vao console cua tien trinh cha (AttachConsole), neu khong co
  thi tu cap console moi (AllocConsole). Moi lan chay deu duoc tee ra logs/cli.log de
  con doc lai duoc khi chay kieu double-click.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent
for _p in (str(_SRC), str(_SRC.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import settings  # noqa: E402  (can sys.path o tren)


def app_dir() -> Path:
    """Thu muc chua .exe (frozen) hoac goc repo (chay source)."""
    return settings._project_root()


def _log_dir() -> Path:
    """Thu muc log: canh .exe, fallback %LOCALAPPDATA% khi thu muc app chi doc."""
    for cand in (app_dir() / "logs", Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "AutoVoiceTikTokShop" / "logs"):
        try:
            cand.mkdir(parents=True, exist_ok=True)
            return cand
        except Exception:
            continue
    return Path(os.getenv("TEMP", "."))


class _Tee:
    """Ghi dong thoi ra nhieu stream (console + file log). Loi ghi tung stream bi bo qua."""

    def __init__(self, *streams):
        self._streams = [s for s in streams if s is not None]

    def write(self, data: str) -> int:
        for st in self._streams:
            try:
                st.write(data)
                st.flush()
            except Exception:
                pass
        return len(data) if isinstance(data, str) else 0

    def flush(self) -> None:
        for st in self._streams:
            try:
                st.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return False


def ensure_console() -> str:
    """Gan stdout/stderr vao console that khi build console=False. Tra chuoi trang thai.

    Thu tu: stdout co san (build console=True / bi redirect vao pipe) -> AttachConsole
    (console cua tien trinh cha) -> AllocConsole (cua so console moi).
    """
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return "source"
    if getattr(sys, "stdout", None) is not None and getattr(sys.stdout, "fileno", None):
        return "stdout-ready"  # build console=True, hoac stdout da la pipe/file
    try:
        import ctypes

        k32 = ctypes.windll.kernel32
        if k32.AttachConsole(-1):  # -1 = ATTACH_PARENT_PROCESS
            status = "attached-parent"
        elif k32.AllocConsole():
            status = "allocated-new"
        else:
            return "none"
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
        return status
    except Exception as e:
        return f"error:{type(e).__name__}"


def _force_utf8(stream) -> None:
    """Ep stream sang UTF-8 truoc khi tee.

    Mac dinh tren Windows, stdout dang pipe/file dung cp1252 -> ghi tieng Viet nem
    UnicodeEncodeError, va `_Tee` nuot loi nen DONG DO BI MAT hoan toan (khong phai
    chi hong ky tu). Trai qua that: dong `[doctor] ... LLM ... reply='Duoc.'` bien mat
    khoi stdout khi GUI spawn tien trinh con.
    """
    reconf = getattr(stream, "reconfigure", None)
    if reconf is None:
        return
    try:
        reconf(encoding="utf-8", errors="replace")
    except Exception:
        pass


def install_tee() -> Path:
    """Tee stdout/stderr ra logs/cli.log. Goi som nhat co the trong main()."""
    _force_utf8(sys.stdout)
    _force_utf8(sys.stderr)
    log_path = _log_dir() / "cli.log"
    try:
        f = open(log_path, "a", encoding="utf-8", errors="replace", buffering=1)
    except Exception:
        return log_path
    sys.stdout = _Tee(sys.stdout, f)
    sys.stderr = _Tee(sys.stderr, f)
    return log_path


# Subcommand noi bo: GUI spawn tien trinh con de chay pipeline / doctor.
# KHONG dung `sys.executable -c <code>`: ban frozen la .exe nen PyInstaller bo qua `-c`,
# va con cua se mo lai GUI thay vi chay pipeline.
INTERNAL_FLAG = "--internal"


def run_internal(argv: list[str]) -> int:
    """Chay app trong tien trinh con: apply config da luu roi day vao app.main().

    app.main() khong nhan tham so - no doc `sys.argv` qua argparse, nen phai
    ghi lai sys.argv truoc khi goi.
    """
    settings.apply()
    saved = sys.argv
    sys.argv = [saved[0], *argv]
    try:
        import app

        return app.main()
    except SystemExit as e:
        code = e.code
        return int(code) if isinstance(code, int) else (0 if code is None else 1)
    finally:
        sys.argv = saved


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] == INTERNAL_FLAG:
        install_tee()
        return run_internal(argv[1:])

    if not argv:
        install_tee()  # GUI: khong co console, log ra file la duong doc lai duy nhat
        import gui

        return gui.main()

    status = ensure_console()  # phai chay truoc install_tee: sau khi tee, stdout khong con fileno()
    install_tee()
    print(f"[launcher] console={status} exe={sys.executable}")
    try:
        import app

        return app.main()
    except SystemExit as e:  # argparse --help / loi tham so
        code = e.code
        return int(code) if isinstance(code, int) else (0 if code is None else 1)
    except KeyboardInterrupt:
        print("\n[launcher] Ctrl+C để dừng")
        return 130
    except Exception:
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
