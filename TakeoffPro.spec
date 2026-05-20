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

# Bundle the single-workspace web UI alongside the executable.
_assets_src = project_root / "src" / "takeoff_pro" / "ui" / "assets"
datas = [
    (str(_assets_src / "estimator_ui.html"), "takeoff_pro/ui/assets"),
    (str(_assets_src / "workspace_styles.css"), "takeoff_pro/ui/assets"),
    (str(_assets_src / "workspace_logic.js"), "takeoff_pro/ui/assets"),
    (str(_assets_src / "workspace_app.js"), "takeoff_pro/ui/assets"),
    (str(_assets_src / "drawing_workspace_services.js"), "takeoff_pro/ui/assets"),
    (str(_assets_src / "favicon.ico"), "takeoff_pro/ui/assets"),
    (str(_assets_src / "favicon-16x16.png"), "takeoff_pro/ui/assets"),
    (str(_assets_src / "favicon-32x32.png"), "takeoff_pro/ui/assets"),
    (str(_assets_src / "apple-touch-icon.png"), "takeoff_pro/ui/assets"),
    (str(_assets_src / "manifest.json"), "takeoff_pro/ui/assets"),
    (str(_assets_src / "manifest-icons-snippet.json"), "takeoff_pro/ui/assets"),
    (str(_assets_src / "icons"), "takeoff_pro/ui/assets/icons"),
]
binaries = []
hiddenimports = [
    "PyQt6.sip",
    "PyQt6.QtOpenGLWidgets",
    "PyQt6.QtOpenGL",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebChannel",
    "numpy",
    "numpy._core",
    "numpy._core._multiarray_umath",
    "numpy._core.multiarray",
    "numpy._core.umath",
    "shapely",
    "shapely.lib",
    "takeoff_pro.ui.ai_worker",
    "takeoff_pro.ui.estimator_web_panel",
    "takeoff_pro.render.profiler",
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

# PyQt6-WebEngine: manually collect DLLs, process binary, and resources.
# collect_all("PyQt6.QtWebEngineWidgets") returns nothing because it's a module,
# not a package — the real binaries live inside PyQt6/Qt6/bin/.
try:
    import PyQt6 as _pyqt6
    _pyqt6_dir = Path(_pyqt6.__file__).parent
    _qt6_bin   = _pyqt6_dir / "Qt6" / "bin"
    _qt6_res   = _pyqt6_dir / "Qt6" / "resources"
    _qt6_loc   = _pyqt6_dir / "Qt6" / "translations"

    # Core WebEngine DLLs + renderer process
    for _dll_name in [
        "Qt6WebEngineCore.dll",
        "Qt6WebEngineWidgets.dll",
        "Qt6WebEngineQuick.dll",
        "QtWebEngineProcess.exe",
    ]:
        _dll_path = _qt6_bin / _dll_name
        if _dll_path.exists():
            binaries.append((str(_dll_path), "PyQt6/Qt6/bin"))

    # Resource paks (icudtl.dat comes from Qt6Core, already collected)
    if _qt6_res.exists():
        for _f in _qt6_res.glob("qtwebengine*"):
            datas.append((str(_f), "PyQt6/Qt6/resources"))

    # WebEngine locales
    _we_loc = _qt6_loc / "qtwebengine_locales"
    if _we_loc.exists():
        datas.append((str(_we_loc), "PyQt6/Qt6/translations/qtwebengine_locales"))

    # PyQt6 .pyd bindings for WebEngine
    for _pyd_name in [
        "QtWebEngineCore.pyd",
        "QtWebEngineWidgets.pyd",
        "QtWebEngineQuick.pyd",
    ]:
        _pyd = _pyqt6_dir / _pyd_name
        if _pyd.exists():
            binaries.append((str(_pyd), "PyQt6"))

    hiddenimports += [
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineQuick",
        "PyQt6.QtWebChannel",
    ]
except Exception as _e:
    print(f"WARNING: WebEngine collection failed: {_e}")  # noqa: T201

a = Analysis(
    [str(project_root / "src" / "takeoff_pro" / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(project_root / "webengine_runtime_hook.py")],
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
    icon=str(_assets_src / "favicon.ico"),
)
