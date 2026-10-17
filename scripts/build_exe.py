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


def copy_runtime_files(dist: Path) -> list[str]:
    """Copy data nguoi dung co the sua + config mau ra canh .exe."""
    copied: list[str] = []
    for name in ("context-data", "ui"):
        src = ROOT / name
        if not src.is_dir():
            continue
        dst = dist / name
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)
        copied.append(name)
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
    """Ghi config.json mau (moi tab GUI deu co gia tri) canh .exe."""
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import settings  # type: ignore
    except Exception as e:  # pragma: no cover - chan doan
        print(f"[build] khong import duoc settings: {e}")
        return dist / "config.json"
    path = dist / "config.json"
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

    if args.clean:
        _rmtree(ROOT / "build")
        _rmtree(ROOT / "dist")

    t0 = time.monotonic()
    if not args.skip_build:
        code = _run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--log-level", "WARN", str(SPEC)])
        if code != 0:
            print(f"[build] PyInstaller FAIL (exit={code}) sau {time.monotonic() - t0:.0f}s")
            return code

    dist = ROOT / "dist" / "AutoVoiceTikTokShop"
    exe = dist / "AutoVoiceTikTokShop.exe"
    if not exe.is_file():
        print(f"[build] FAIL: khong thay {exe}")
        return 1

    copied = copy_runtime_files(dist)
    cfg = config_example(dist)

    print("\n=== BUILD XONG ===")
    print(f"exe          : {exe}")
    print(f"exe size     : {_human(exe.stat().st_size)}")
    print(f"dist size    : {_human(_tree_size(dist))}")
    print(f"copy them    : {', '.join(copied) if copied else '-'}")
    print(f"config mau   : {cfg.name} (DEFAULTS)")
    print(f"thoi gian    : {time.monotonic() - t0:.0f}s")
    print("\nThu chay:")
    print(f'  "{exe}" --help')
    print(f'  "{exe}" doctor')
    print(f'  set {ENV_NAME}=%CD%\\dist\\AutoVoiceTikTokShop\\config.json  (tuy chon)')
    return 0


if __name__ == "__main__":
    sys.exit(main())
