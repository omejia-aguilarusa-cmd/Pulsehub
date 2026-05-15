# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Takeoff Pro Windows executable."""

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)


project_root = Path.cwd()
datas = []
binaries = []
hiddenimports = [
    "PyQt6.sip",
    "numpy",
    "numpy._core",
    "numpy._core._multiarray_umath",
    "numpy._core.multiarray",
    "numpy._core.umath",
    "shapely",
    "shapely.lib",
    "takeoff_pro.ui.ai_worker",
    "PIL",
    "PIL.Image",
    "PIL.TiffImagePlugin",
]


def include_runtime_module(name):
    """Return True for runtime modules and False for package test modules."""
    return ".tests" not in name and ".testing" not in name and not name.endswith(".conftest")


for package_name in ("pymupdf",):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

datas += collect_data_files("numpy", excludes=["**/tests/**", "**/testing/**"])
datas += collect_data_files("shapely", excludes=["**/tests/**"])
binaries += collect_dynamic_libs("numpy")
binaries += collect_dynamic_libs("shapely")
hiddenimports += collect_submodules("numpy._core", filter=include_runtime_module)
hiddenimports += collect_submodules("numpy.core", filter=include_runtime_module)
hiddenimports += collect_submodules("numpy.linalg", filter=include_runtime_module)
hiddenimports += collect_submodules("numpy.random", filter=include_runtime_module)
hiddenimports += collect_submodules("shapely", filter=include_runtime_module)
datas += collect_data_files("reportlab")

a = Analysis(
    [str(project_root / "src" / "takeoff_pro" / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="TakeoffPro",
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
