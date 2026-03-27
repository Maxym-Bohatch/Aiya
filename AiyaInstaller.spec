# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None
bundle_dir = Path('bundle')

datas = [
    ('dist/AiyaClientLauncher.exe', 'bundle'),
    ('dist/AiyaUninstaller.exe', 'bundle'),
    ('.env.client.example', 'bundle'),
    ('docs/CLIENT_SETUP.md', 'bundle'),
    ('docs/DOCKER_MIGRATION.md', 'bundle'),
]

a = Analysis(
    ['installer/bootstrap_installer.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['installer.common'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AiyaInstaller',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
