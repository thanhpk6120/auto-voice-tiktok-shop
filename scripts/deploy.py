"""Deploy app sang thu muc chay (copy nhanh khong build lai .exe).

Dung khi chay app tu SOURCE (python src/gui.py) va ban muon "day" ban cap nhat
vao mot thu muc khac de chay - khong can build lai PyInstaller.

KHONG dung khi chay .exe: code .py da duoc PyInstaller dong goi vao
base_library.zip nen sua code deu phai build lai (scripts/build_exe.py).

Usage:
  python scripts/deploy.py <thu-muc-dich> [--dry-run]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Thu muc can copy sang thu muc dich.
# - src/        : code app (bat buoc)
# - prompts/    : prompt sinh cau thoai (bat buoc)
# - context-data/: context mau (fallback khi context-live rong)
# - ui/         : index.html test tay
# - extension/  : Chrome Extension (che do nhan su kien qua extension)
# - data/       : sample-events.jsonl (test)
# KHONG copy: gologin-basic-offline (2.4GB), vendor (1.9GB), local_cache, out, logs
ITEMS = ("src", "prompts", "context-data", "ui", "extension", "data")

# File don le can copy.
FILES = (".env", "requirements.txt", ".env.example")

# context-live: du lieu da crawl cua nguoi dung -> KHONG BAO GIO ghi de.
# Chi copy khi thu muc dich chua co (lan deploy dau tien).
CONTEXT_LIVE = "context-live"

# File .py o dich bi thua (da xoa o source) -> chuyen vao _obsolete/ de khong
# import nham. KHONG xoa cung (rule: xoa phai vao Recycle Bin).
OBSOLETE_DIR = "_obsolete"


def _copy_dir(src: Path, dst: Path, dry: bool) -> str:
    """Copy de thu muc dich. KHONG xoa gi o dich (chi ghi de file cung ten)."""
    if not src.is_dir():
        return ""
    n = len(list(src.glob("*")))
    if dry:
        return f"  {src.name}/ ({n} muc)"
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return f"  {src.name}/ ({n} muc)"


def _quarantine_stale_py(src: Path, dst: Path, dry: bool) -> int:
    """Chuyen file .py o dst khong con o src vao _obsolete/ (khong xoa cung)."""
    if not src.is_dir() or not dst.is_dir():
        return 0
    src_names = {p.name for p in src.glob("*.py")}
    stale = [p for p in dst.glob("*.py") if p.name not in src_names]
    if not stale:
        return 0
    if dry:
        return len(stale)
    obs = dst.parent / OBSOLETE_DIR
    obs.mkdir(parents=True, exist_ok=True)
    for p in stale:
        shutil.move(str(p), str(obs / p.name))
    return len(stale)


def main() -> int:
    ap = argparse.ArgumentParser(description="Copy app sang thu muc chay khac")
    ap.add_argument("target", help="thu muc dich")
    ap.add_argument("--dry-run", action="store_true", help="chi hien thi ke hoach")
    args = ap.parse_args()

    dst_root = Path(args.target).expanduser().resolve()
    dst_root.mkdir(parents=True, exist_ok=True)

    print(f"[deploy] nguon   : {ROOT}")
    print(f"[deploy] dich   : {dst_root}")
    print("[deploy] se copy:")
    for name in ITEMS:
        line = _copy_dir(ROOT / name, dst_root / name, args.dry_run)
        if line:
            print(line)

    # context-live: du lieu crawl cua nguoi dung -> giu nguyen, chi copy lan dau.
    live_src = ROOT / CONTEXT_LIVE
    live_dst = dst_root / CONTEXT_LIVE
    if live_dst.exists() and any(live_dst.iterdir()):
        print(f"  {CONTEXT_LIVE}/  (GIU NGUYEN - da co du lieu crawl o dich)")
    else:
        line = _copy_dir(live_src, live_dst, args.dry_run)
        if line:
            print(line + "  (lan dau - thu muc dich chua co)")

    for name in FILES:
        src = ROOT / name
        if not src.is_file():
            continue
        if args.dry_run:
            print(f"  {name}")
            continue
        shutil.copy2(src, dst_root / name)
        print(f"  {name}")

    stale = _quarantine_stale_py(ROOT / "src", dst_root / "src", args.dry_run)
    if stale:
        print(f"\n[deploy] {stale} file .py cu da xoa o source -> chuyen vao {OBSOLETE_DIR}/")

    if args.dry_run:
        print("[deploy] dry-run, khong thay doi gi.")
        return 0

    print("\n[deploy] xong. Chay:")
    print(f'  cd "{dst_root}"')
    print("  python src/gui.py")
    print("\n[deploy] luu y: config.json nam o %APPDATA%\\AutoVoiceTikTokShop\\config.json")
    print("[deploy] (dung chung may) - muon config rieng dat AUTO_VOICE_CONFIG.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
