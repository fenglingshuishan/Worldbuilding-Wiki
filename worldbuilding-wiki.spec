# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

project_root = Path(SPECPATH).resolve()
source_root = project_root / "src"

analysis = Analysis(
    [str(source_root / "worldbuilding_wiki" / "__main__.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=[
        (
            str(source_root / "worldbuilding_wiki" / "static"),
            "worldbuilding_wiki/static",
        ),
        (
            str(source_root / "worldbuilding_wiki" / "sample_data"),
            "worldbuilding_wiki/sample_data",
        ),
    ],
    hiddenimports=collect_submodules("uvicorn"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "ruff", "httpx"],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="WorldbuildingWiki",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="WorldbuildingWiki",
)
