"""Update ban chay (.exe) tu thu muc khac bang ban build moi.

Sau `python scripts/build_exe.py`, ban moi nam trong `dist/AutoVoiceTikTokShop/`.
Script nay copy sang thu muc dang chay app.

Code app duoc PyInstaller dong goi vao PYZ (archive nhung trong file `.exe`) ->
doi code = thay file `.exe`. `_internal/` la thu vien runtime (numpy, tcl8,
websockets...) -> chi can copy lai khi DOI DEPENDENCY, khong can moi lan code
doi.

KHONG ghi de (du lieu nguoi dung):
  - prompts/      : GUI ghi prompt thang vao thu muc canh .exe (gui.py)
  - context-data/ : context mau, user sua tay
  - context-live/ : context san pham da crawl
  - config.json   : app doc o %APPDATA%; file canh .exe la file mau
  - .env          : secret

Usage:
  python scripts/update_dist.py "D:\\AutoVoice"              # chi doi code
  python scripts/update_dist.py "D:\\AutoVoice" --internal   # + doi thu vien
  python scripts/update_dist.py "D:\\AutoVoice" --dry-run
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "AutoVoiceTikTokShop"

EXE_NAME = "AutoVoiceTikTokShop.exe"
INTERNAL = "_internal"


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _tree_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())



def main() -> int:
    ap = argparse.ArgumentParser(description="Copy ban build moi sang thu muc app dang chay")
    ap.add_argument("target", help="thu muc dang chay app (.exe)")
    ap.add_argument("--internal", action="store_true",
                    help="copy lai _internal/ (dung khi doi dependency)")
    ap.add_argument("--dry-run", action="store_true", help="chi hien thi ke hoach")
    args = ap.parse_args()

    exe_src = DIST / EXE_NAME
    if not exe_src.is_file():
        print(f"[update] FAIL: khong thay {exe_src}")
        print("[update] Chay `python scripts/build_exe.py` truoc.")
        return 1

    dst = Path(args.target).expanduser().resolve()
    if not dst.is_dir():
        print(f"[update] FAIL: thu muc dich khong ton tai: {dst}")
        return 1

    exe_dst = dst / EXE_NAME
    print(f"[update] nguon : {DIST}")
    print(f"[update] dich  : {dst}")

    if args.dry_run:
        print(f"  + {EXE_NAME}  ({_human(exe_src.stat().st_size)})")
        if args.internal:
            print(f"  + {INTERNAL}/  ({_human(_tree_size(DIST / INTERNAL))})")
        print("  [giu nguyen] prompts/, context-data/, context-live/, config.json, .env")
        print("[update] dry-run.")
        return 0
    t0 = time.monotonic()

    # 1) Copy .exe moi vao file tam -> os.replace la thao tac ATOMIC.
    #    Windows tra PermissionError (WinError 5) neu app dang chay (file .exe
    #    dang duoc process mo). Lam BUOC nay TRUOC khi dung gi -> neu fail thi
    #    ban cai con nguyen ven, khong o trang thai nua vua.
    exe_tmp = dst / f"{EXE_NAME}.new"
    try:
        shutil.copy2(exe_src, exe_tmp)
        os.replace(exe_tmp, exe_dst)
    except PermissionError:
        if exe_tmp.exists():
            exe_tmp.unlink(missing_ok=True)
        print("[update] FAIL: khong ghi duoc file .exe (app dang chay? file bi khoa).")
        print("[update] Hay DONG app truoc roi chay lai lenh nay.")
        print("[update] Ban cai hien tai KHONG bi thay doi gi.")
        return 1
    print(f"  + {EXE_NAME}  ({_human(exe_src.stat().st_size)})")

    if args.internal:
        internal = dst / INTERNAL
        if internal.is_dir():
            old = dst / f"{INTERNAL}.old"
            if old.exists():
                shutil.rmtree(old, ignore_errors=True)
            internal.rename(old)
            print(f"  ~ {INTERNAL}/ -> {INTERNAL}.old (doi ten, xoa sau khi verify)")
        shutil.copytree(DIST / INTERNAL, internal, dirs_exist_ok=True)
        print(f"  + {INTERNAL}/  ({_human(_tree_size(DIST / INTERNAL))})")

    # 4) context-live: giu nguyen du lieu crawl, chi them file moi chua co.
    live_src = DIST / "context-live"
    live_dst = dst / "context-live"
    if live_src.is_dir():
        live_dst.mkdir(parents=True, exist_ok=True)
        added = 0
        for f in live_src.rglob("*"):
            if f.is_file():
                t = live_dst / f.relative_to(live_src)
                if not t.exists():
                    t.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, t)
                    added += 1
        print(f"  = context-live/ (giu file cu, them {added} file moi)")

    print(f"\n[update] xong sau {time.monotonic() - t0:.0f}s.")
    print("[update] Chay lai app de ap dung ban moi:")
    print(f'  "{dst}\\{EXE_NAME}" doctor')
    if args.internal:
        print(f'[update] Sau khi verify: xoa "{dst}\\{INTERNAL}.old" de gian dung dia.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
