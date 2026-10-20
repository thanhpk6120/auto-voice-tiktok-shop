"""Deploy app sang thu muc chay (copy nhanh khong build lai .exe).

Dung khi chay app tu SOURCE (python src/gui.py) va ban muon "day" ban cap nhat
vao mot thu muc khac de chay - khong can build lai PyInstaller.

KHONG dung khi chay .exe: code app duoc PyInstaller dong goi vao PYZ (archive
nhung trong file .exe) nen sua code deu phai build lai (scripts/build_exe.py).

Usage:
  python scripts/deploy.py <thu-muc-dich> [--dry-run]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Thu muc copy - code va du lieu MAU, ghi de moi lan deploy:
# - src/        : code app (bat buoc)
# - prompts/    : prompt sinh cau thoai (bat buoc)
# - extension/  : Chrome Extension (che do nhan su kien qua extension)
ITEMS = ("src", "prompts", "extension")

# File don le can copy.
FILES = (".env", "requirements.txt", ".env.example")

# Thu muc du lieu nguoi dung -> KHONG BAO GIO ghi de. Chi copy lan dau khi
# thu muc dich con trong.
# - context-live/ : context san pham da crawl (theo tung may)
# - context-data/ : context mau, user co the sua tay
USER_DATA_DIRS = ("context-live", "context-data")

# File .py o dich bi thua (da xoa o source) -> chuyen vao _obsolete/ de khong
# import nham. KHONG xoa cung (rule: xoa phai vao Recycle Bin).
OBSOLETE_DIR = "_obsolete"

# GoLogin: 2.4GB, KHONG copy. App can no o che do browser_mode=gologin_cdp
# (gia tri DEFAULT). Neu thu muc dich thieu, app bao loi kho hieu.
GOLOGIN_DIR = "gologin-basic-offline"


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


def _check_gologin(dst_root: Path) -> list[str]:
    """Canh bao neu thu muc dich thieu GoLogin (bat buoc cho browser_mode=gologin_cdp)."""
    if (dst_root / GOLOGIN_DIR).is_dir():
        return []
    return [
        f"[deploy] CANH BAO: '{GOLOGIN_DIR}' khong co trong thu muc dich.",
        f"[deploy]   App mac dinh browser_mode=gologin_cdp -> can GoLogin de mo profile.",
        f"[deploy]   Chon 1 trong 2:",
        f"[deploy]     1) GUI tab 'Trinh duyet / GoLogin' -> dat gologin_dir tro toi ban san co",
        f"[deploy]     2) Copy {GOLOGIN_DIR} (2.4 GB) mot lan sang thu muc dich",
        f"[deploy]   Hoac doi browser_mode sang 'extension' (can extension/ + bridge).",
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Copy app sang thu muc chay khac")
    ap.add_argument("target", help="thu muc dich")
    ap.add_argument("--dry-run", action="store_true", help="chi hien thi ke hoach")
    args = ap.parse_args()

    dst_root = Path(args.target).expanduser().resolve()
    dst_root.mkdir(parents=True, exist_ok=True)

    print(f"[deploy] nguon   : {ROOT}")
    print(f"[deploy] dich   : {dst_root}")
    if not str(dst_root).startswith(str(ROOT)):
        print("[deploy] luu y: thu muc dich NAM NGOAI workspace ban goc.")
    print("[deploy] se copy:")
    for name in ITEMS:
        line = _copy_dir(ROOT / name, dst_root / name, args.dry_run)
        if line:
            print(line)

    # Du lieu nguoi dung -> giu nguyen, chi copy lan dau khi dich con trong.
    for name in USER_DATA_DIRS:
        src = ROOT / name
        dst = dst_root / name
        if dst.exists() and any(dst.iterdir()):
            print(f"  {name}/  (GIU NGUYEN - da co du lieu o dich)")
        else:
            line = _copy_dir(src, dst, args.dry_run)
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

    for line in _check_gologin(dst_root):
        print(line)

    print("\n[deploy] xong. Chay:")
    print(f'  cd "{dst_root}"')
    print("  python src/gui.py")
    print("\n[deploy] luu y: config.json nam o %APPDATA%\\AutoVoiceTikTokShop\\config.json")
    print("[deploy] (dung chung cho moi thu muc chay). Muon config rieng:")
    print(f'[deploy]   set AUTO_VOICE_CONFIG="{dst_root}\\config.json"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
