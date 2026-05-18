# PyInstaller runtime hook — sets Qt WebEngine process path before any Qt init.
# This must run before any PyQt6 import in the frozen bundle.
import os
import sys

if getattr(sys, "frozen", False):
    _mei = getattr(sys, "_MEIPASS", "")
    # Candidate locations for QtWebEngineProcess.exe inside the extracted archive
    _candidates = [
        os.path.join(_mei, "PyQt6", "Qt6", "bin", "QtWebEngineProcess.exe"),
        os.path.join(_mei, "QtWebEngineProcess.exe"),
        os.path.join(_mei, "PyQt6", "Qt6", "libexec", "QtWebEngineProcess.exe"),
    ]
    for _p in _candidates:
        if os.path.isfile(_p):
            os.environ.setdefault("QTWEBENGINEPROCESS_PATH", _p)
            break

    # Resources (icudtl.dat, v8_context_snapshot.bin, etc.)
    for _res_dir in [
        os.path.join(_mei, "PyQt6", "Qt6", "resources"),
        os.path.join(_mei, "resources"),
    ]:
        if os.path.isdir(_res_dir):
            os.environ.setdefault("QTWEBENGINE_RESOURCES_PATH", _res_dir)
            break

    # Locales
    for _loc_dir in [
        os.path.join(_mei, "PyQt6", "Qt6", "translations", "qtwebengine_locales"),
        os.path.join(_mei, "qtwebengine_locales"),
    ]:
        if os.path.isdir(_loc_dir):
            os.environ.setdefault("QTWEBENGINE_LOCALES_PATH", _loc_dir)
            break
