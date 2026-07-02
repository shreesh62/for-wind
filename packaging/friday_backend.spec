# PyInstaller spec for FRIDAY backend.
#
# Builds a standalone executable that runs the FRIDAY API server
# without requiring Python to be installed on the target machine.
#
# Build:
#   pip install pyinstaller
#   pyinstaller packaging/friday_backend.spec
#
# Output: dist/friday-backend/friday-backend.exe
#
# This bundles the backend platform only (per ADR-017, no UI).
# Friends run friday-backend.exe; the API serves at localhost:8801.

# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None

# Project root (spec runs from repo root)
ROOT = Path.cwd()

a = Analysis(
    ['../friday/api/server.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Bundle .env.example as a template (NOT the real .env)
        ('../.env.example', '.'),
    ],
    hiddenimports=[
        # Ensure dynamically-imported modules are included
        'friday',
        'friday.api',
        'friday.api.app',
        'friday.api.server',
        'friday.api.routes.commands',
        'friday.api.routes.status',
        'friday.api.routes.memory',
        'friday.api.routes.models',
        'friday.api.routes.tasks',
        'friday.api.routes.perception',
        'friday.api.routes.websocket',
        'friday.bridge',
        'friday.core',
        'friday.memory',
        'friday.memory.controller',
        'friday.memory.semantic',
        'friday.models.router',
        'friday.models.providers.nvidia_provider',
        'friday.models.providers.groq_provider',
        'friday.perception.world_state',
        'friday.perception.priority',
        'friday.planner',
        'friday.verification',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'fastapi',
        'pydantic',
        'httpx',
        'dotenv',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy/unneeded packages to shrink the binary
        'matplotlib',
        'tkinter',
        'PIL.ImageQt',
        'torch',
        'tensorflow',
        'sentence_transformers',
    ],
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
    name='friday-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Console window shows server logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='friday-backend',
)
