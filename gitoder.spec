# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: single windowed Gitoder.exe with bundled fonts and icon.
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('keyring.backends') + ['pathspec']

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('gitoder/assets/fonts', 'assets/fonts'),
        ('gitoder/assets/icons', 'assets/icons'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Gitoder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='gitoder/assets/icons/gitoder.ico',
)
