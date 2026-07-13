# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for CodeMonkeys Windows desktop.
# Build:  powershell -ExecutionPolicy Bypass -File scripts/build-windows.ps1

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
DESKTOP = ROOT / "desktop"

block_cipher = None

datas = [
    (str(ROOT / "static"), "static"),
    (str(ROOT / "corps"), "corps"),
    (str(ROOT / "server.py"), "."),
    (str(ROOT / "feedback_triage.py"), "."),
]

# fido2 ships public_suffix_list.dat (and related) as package data — without
# these, frozen imports crash: FileNotFoundError ... fido2/public_suffix_list.dat
datas += collect_data_files("fido2")
datas += collect_data_files("certifi")
datas += collect_data_files("google.auth")

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "anthropic",
    "fido2",
    "fido2.server",
    "fido2.webauthn",
    "fido2.rpid",
    "pyotp",
    "segno",
    "cryptography",
    "google.auth",
    "google.oauth2",
    "feedback_triage",
    "server",
    "desktop",
    "desktop.launcher",
]
hiddenimports += collect_submodules("fido2")

icon_path = DESKTOP / "codemonkeys.ico"
icon = str(icon_path) if icon_path.exists() else None

a = Analysis(
    [str(DESKTOP / "launcher.py")],
    pathex=[str(ROOT), str(DESKTOP)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(DESKTOP / "pyi_rth_codemonkeys.py")],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CodeMonkeys",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Temporary True while packaging settles — flip False once startup is solid.
    # Override: edit this line or rebuild after smoke is green.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CodeMonkeys",
)
