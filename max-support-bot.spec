# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

runtime_datas = [('maxbot/certs/russian_trusted_root_ca.pem', 'maxbot/certs')]
# Bundle the interpreter's certificate rejection policy when it ships one.
# Its public certificates are needed for TLS in the frozen application.
runtime_ssl_policy = Path(sys.base_prefix) / 'Lib' / 'codex-rejected-cas.pem'
if runtime_ssl_policy.is_file():
    policy = runtime_ssl_policy.read_text(encoding='ascii')
    if 'PRIVATE KEY' in policy or 'BEGIN TRUSTED CERTIFICATE' not in policy:
        raise ValueError('Unexpected interpreter TLS policy data')
    runtime_datas.append((str(runtime_ssl_policy), '.'))

a = Analysis(
    ['bootstrap.py'],
    pathex=[],
    binaries=[],
    datas=runtime_datas,
    hiddenimports=[
        'uvicorn.loops.asyncio',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets.auto',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='max-support-bot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
