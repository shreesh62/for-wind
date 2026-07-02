# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for bundling the Jarvis backend."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from PyInstaller.building.datastruct import Tree

project_root_reference = globals().get("__file__")
project_root = Path(project_root_reference).resolve().parent if project_root_reference else Path.cwd()

entry_script = project_root / "main.py"

data_trees = [
    Tree(str(project_root / "automation"), prefix="automation"),
    Tree(str(project_root / "awareness"), prefix="awareness"),
    Tree(str(project_root / "config"), prefix="config"),
    Tree(str(project_root / "core"), prefix="core"),
    Tree(str(project_root / "memory"), prefix="memory"),
    Tree(str(project_root / "plugins"), prefix="plugins"),
    Tree(str(project_root / "server" / "static"), prefix="server/static"),
    Tree(str(project_root / "ui"), prefix="ui"),
    Tree(str(project_root / "wake_words"), prefix="wake_words"),
]


a = Analysis(
    [str(entry_script)],
    pathex=[str(project_root)],
    binaries=[],
    datas=data_trees,
    hiddenimports=collect_submodules("plugins"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="jarvis-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="jarvis-backend",
)
