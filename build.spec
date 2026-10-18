# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec - onedir, GUI launcher (console=False).

Build: python scripts/build_exe.py   (hoac: pyinstaller --noconfirm build.spec)

Quyet dinh:
  - onedir (khong phai onefile): khoi dong nhanh, khong giai nen lai moi lan chay,
    va `context-data/`/`ui/` nam trong `_internal/` doc truc tiep duoc.
  - console=False: .exe mo GUI khong hien cua so console den. CLI van in ra terminal
    nho src/launcher.ensure_console() (AttachConsole) + tee ra logs/cli.log.
  - excludes: vendor/ (1.9GB model cache), local_cache/, out/ (du lieu sinh ra khi chay),
    va cac package nang khong dung (matplotlib, scipy, pandas, PIL...).
"""
from pathlib import Path

ROOT = Path(SPECPATH).resolve()

datas = [
    # Read-only data di kem: bo nao RAG + dashboard test tay.
    (str(ROOT / "context-data"), "context-data"),
    (str(ROOT / "prompts"), "prompts"),
    (str(ROOT / "ui"), "ui"),
    (str(ROOT / "requirements.txt"), "."),
    # sounddevice: data (_sounddevice_data) do hook cua pyinstaller-hooks-contrib lo,
    # khong can collect_data_files (sounddevice la module phang, khong phai package).
]

hiddenimports = [
    # Khai bao tuong minh: import dong / nam trong nhanh try-except nen PyInstaller
    # co the bo sot.
    "sounddevice",
    "_sounddevice",
    "numpy",
    "websockets",
    "websockets.legacy",
    "websockets.legacy.client",
    "websockets.legacy.server",
    "tkinter",
    "_tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.scrolledtext",
    "tkinter.ttk",
    # Module noi bo cua app (import phang trong src/, hoac qua `src.` tu llm_client)
    "app",
    "gui",
    "launcher",
    "settings",
    "config",
    "audio_player",
    "audio_queue",
    "event_analyzer",
    "event_bridge",
    "event_simulator",
    "llm_client",
    "tts_client",
    "browser_manager",
    "batch_processor",
]

excludes = [
    "gologin-basic-offline",
    "vendor",
    "local_cache",
    "out",
    "dist",
    "build",
    "matplotlib",
    "scipy",
    "pandas",
    "PIL",
    "IPython",
    "pytest",
    "setuptools",
    "pip",
]

a = Analysis(
    [str(ROOT / "src" / "launcher.py")],
    pathex=[str(ROOT), str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "scripts" / "pyi_rth_paths.py")],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoVoiceTikTokShop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI; CLI van co output nho AttachConsole trong launcher.py
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AutoVoiceTikTokShop",
)
