"""Build .exe onedir bang PyInstaller + copy data/config mau vao dist.

Chay: python scripts/build_exe.py [--clean]

Sau khi build:
  dist/AutoVoiceTikTokShop/AutoVoiceTikTokShop.exe      <- GUI khi chay khong tham so
  dist/AutoVoiceTikTokShop/context-data/                <- copy tu repo (sua duoc)
  dist/AutoVoiceTikTokShop/ui/, requirements.txt, docs/, .env.example
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "build.spec"
ENV_NAME = "AUTO_VOICE_CONFIG"


def _run(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, cwd=str(ROOT))


def _tree_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _rmtree(path: Path) -> None:
    """Xoa thu muc build/work cua PyInstaller. Chi ap dung cho build/dist (sinh ra khi build)."""
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def backup_user_data(dist: Path) -> Path | None:
    """Backup du lieu nguoi dung trong dist truoc khi PyInstaller xoa san dist.

    PyInstaller COLLECT voi --noconfirm goi _make_clean_directory -> rmtree
    ca thu muc dist/AutoVoiceTikTokShop. Comment "khong rmtree lam mat du lieu"
    o copy_runtime_files chi dung cho viec copy them, khong cua duoc viec xoa.
    -> Phai backup truoc, restore sau.
    """
    # context-live + config.json + .env + prompts + context-data: du lieu nguoi
    # dung (GUI ghi prompt thang vao thu muc canh .exe, context-data user sua
    # tay). COLLECT se xoa san dist -> phai backup de restore.
    items: list[str] = []
    for name in ("context-live", "config.json", ".env", "prompts", "context-data"):
        if (dist / name).exists():
            items.append(name)
    if not items:
        return None
    bak = dist.parent / f"_build_backup_{int(time.time())}"
    bak.mkdir(parents=True, exist_ok=True)
    for name in items:
        src = dist / name
        dst = bak / name
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    print(f"[build] backup {', '.join(items)} -> {bak.name}", flush=True)
    return bak


def restore_user_data(dist: Path, bak: Path | None) -> list[str]:
    """Restore du lieu nguoi dung sau khi PyInstaller xoa san dist."""
    if bak is None or not bak.is_dir():
        return []
    restored: list[str] = []
    for child in bak.iterdir():
        dst = dist / child.name
        if child.is_dir():
            shutil.copytree(child, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(child, dst)
        restored.append(child.name)
    return restored


def copy_runtime_files(dist: Path) -> list[str]:
    """Copy data nguoi dung co the sua + config mau ra canh .exe."""
    copied: list[str] = []
    for name in ("context-data", "prompts", "ui"):
        src = ROOT / name
        if not src.is_dir():
            continue
        dst = dist / name
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)
        copied.append(name)

    # context-live: copy them tu repo (khong rmtree - file da crawl cua nguoi dung
    # da duoc backup o backup_user_data truoc khi PyInstaller xoa san dist).
    src_live = ROOT / "context-live"
    dst_live = dist / "context-live"
    if src_live.is_dir():
        shutil.copytree(src_live, dst_live, dirs_exist_ok=True)
    dst_live.mkdir(parents=True, exist_ok=True)
    copied.append("context-live/")
    for name in ("requirements.txt", ".env.example"):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, dist / name)
            copied.append(name)
    docs_src = ROOT / "docs"
    if docs_src.is_dir():
        shutil.copytree(docs_src, dist / "docs", dirs_exist_ok=True)
        copied.append("docs/")
    return copied


def config_example(dist: Path) -> Path:
    """Ghi config.json mau canh .exe - KHONG ghi de config da sua tay."""
    path = dist / "config.json"
    if path.is_file():
        # Da co config (restore tu backup hoac user tu tao) -> giu nguyen.
        return path
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import settings  # type: ignore
    except Exception as e:  # pragma: no cover - chan doan
        print(f"[build] khong import duoc settings: {e}")
        return path
    path.write_text(
        __import__("json").dumps(settings.DEFAULTS, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build AutoVoiceTikTokShop.exe (onedir)")
    ap.add_argument("--clean", action="store_true", help="xoa build/ + dist/ truoc khi build")
    ap.add_argument("--skip-build", action="store_true", help="chi copy data (debug)")
    args = ap.parse_args()

    dist = ROOT / "dist" / "AutoVoiceTikTokShop"

    if args.clean:
        _rmtree(ROOT / "build")
        _rmtree(ROOT / "dist")

    t0 = time.monotonic()
    # Backup TRUOC: PyInstaller COLLECT se xoa san dist/ (ke context-live da crawl).
    bak = None if args.skip_build else backup_user_data(dist)

    if not args.skip_build:
        code = _run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--log-level", "WARN", str(SPEC)])
        if code != 0:
            print(f"[build] PyInstaller FAIL (exit={code}) sau {time.monotonic() - t0:.0f}s")
            return code

    exe = dist / "AutoVoiceTikTokShop.exe"
    if not exe.is_file():
        print(f"[build] FAIL: khong thay {exe}")
        return 1

    copied = copy_runtime_files(dist)
    restored = restore_user_data(dist, bak)
    cfg = config_example(dist)
    if bak is not None:
        shutil.rmtree(bak, ignore_errors=True)

    print("\n=== BUILD XONG ===")
    print(f"exe          : {exe}")
    print(f"exe size     : {_human(exe.stat().st_size)}")
    print(f"dist size    : {_human(_tree_size(dist))}")
    print(f"copy them    : {', '.join(copied) if copied else '-'}")
    print(f"restore data : {', '.join(restored) if restored else '-'}")
    print(f"config       : {cfg.name}")
    print(f"thoi gian    : {time.monotonic() - t0:.0f}s")
    print("\nThu chay:")
    print(f'  "{exe}" --help')
    print(f'  "{exe}" doctor')
    print(f'  set {ENV_NAME}=%CD%\\dist\\AutoVoiceTikTokShop\\config.json  (tuy chon)')
    return 0


if __name__ == "__main__":
    sys.exit(main())
