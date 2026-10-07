"""Windows paths: Downloads via Known Folder API, unique filenames, app data dir."""

from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path

log = logging.getLogger("gitoder.paths")


class _GUID(ctypes.Structure):
    """Windows GUID layout (ctypes.wintypes.GUID is absent on some Pythons)."""

    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid_from(text: str) -> _GUID:
    hexstr = text.strip("{}").replace("-", "")
    raw = bytes.fromhex(hexstr)
    g = _GUID()
    g.Data1 = int.from_bytes(raw[0:4], "little")
    g.Data2 = int.from_bytes(raw[4:6], "little")
    g.Data3 = int.from_bytes(raw[6:8], "little")
    g.Data4 = (ctypes.c_ubyte * 8)(*raw[8:16])
    return g


# FOLDERID_Downloads
_FOLDERID_DOWNLOADS = _guid_from("{374DE290-123F-4565-9164-39C4925E467B}")
_KF_FLAG_DEFAULT = 0
_DOWNLOADS_REGISTRY_VALUE = "{374DE290-123F-4565-9164-39C4925E467B}"

_app_data_dir: Path | None = None


def downloads_dir() -> Path:
    """Resolve the real Downloads folder (SHGetKnownFolderPath), with fallbacks."""
    try:
        buf = ctypes.c_wchar_p()
        result = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(_FOLDERID_DOWNLOADS), _KF_FLAG_DEFAULT, None, ctypes.byref(buf)
        )
        if result == 0 and buf.value:
            return Path(buf.value)
    except Exception as exc:  # noqa: BLE001 - never crash on path resolution
        log.warning("SHGetKnownFolderPath failed: %s", exc.__class__.__name__)
    # Fallback 1: registry user shell folders
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        )
        raw, _ = winreg.QueryValueEx(key, _DOWNLOADS_REGISTRY_VALUE)
        path = Path(os.path.expandvars(raw))
        if path.is_dir():
            return path
    except Exception:  # noqa: BLE001
        pass
    # Fallback 2: ~/Downloads
    home = Path.home() / "Downloads"
    home.mkdir(exist_ok=True)
    return home


def unique_destination(folder: Path, filename: str) -> Path:
    """repo-name.zip -> repo-name (1).zip -> (2) ... Never overwrites."""
    folder = Path(folder)
    target = folder / filename
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    for i in range(1, 10000):
        candidate = folder / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
    return folder / f"{stem} ({os.getpid()}){suffix}"


def app_data_dir() -> Path:
    """%LOCALAPPDATA%\\Gitoder, created on first use."""
    global _app_data_dir
    if _app_data_dir is None:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        _app_data_dir = Path(base) / "Gitoder"
    _app_data_dir.mkdir(parents=True, exist_ok=True)
    return _app_data_dir


def logs_dir() -> Path:
    d = app_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d
