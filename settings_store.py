"""Preferences beside the executable, with one-time legacy migration."""
import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths


def file_permissions(path, descriptor=None):
    """Read/restore only this file's Windows DACL after Qt's atomic replacement."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    get = api.GetFileSecurityW
    get.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p,
                    wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    get.restype = wintypes.BOOL
    set_security = api.SetFileSecurityW
    set_security.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    set_security.restype = wintypes.BOOL
    dacl = 4
    if descriptor is not None:
        buffer = ctypes.create_string_buffer(descriptor)
        if not set_security(str(path), dacl, buffer):
            raise ctypes.WinError(ctypes.get_last_error())
        return None
    size = wintypes.DWORD()
    get(str(path), dacl, None, 0, ctypes.byref(size))
    if not size.value:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_string_buffer(size.value)
    if not get(str(path), dacl, buffer, size.value, ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    return buffer.raw[:size.value]


class InstalledSettings(QSettings):
    def sync(self):
        path = Path(self.fileName())
        permissions = file_permissions(path) if path.is_file() else None
        super().sync()
        if permissions is not None and self.status() == QSettings.Status.NoError:
            if file_permissions(path) != permissions:
                file_permissions(path, permissions)


def application_directory():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def local_settings_directory():
    base = os.environ.get("LOCALAPPDATA") or QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericDataLocation)
    return Path(base) / "B01PDF"


def open_settings(directory=None, legacy=None, old_directory=None):
    use_default = directory is None
    directory = Path(directory) if directory is not None else application_directory()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "settings.ini"
    # Probe the actual file; QSettings.isWritable() can reject a protected folder
    # even when its pre-created settings file is writable.
    with target.open("a+b"):
        pass
    settings = InstalledSettings(str(target), QSettings.Format.IniFormat)
    settings.setFallbacksEnabled(False)
    # Setup makes only this file writable; Program Files remains protected.
    # QSettings must therefore allow direct writes without a sibling temp file.
    settings.setAtomicSyncRequired(False)
    if settings.status() != QSettings.Status.NoError:
        raise OSError(f"Cannot read or write {target}. Reinstall B01PDF to restore settings permissions.")
    if not settings.value("storage/executableFolder", False, type=bool):
        if old_directory is None and use_default:
            old_directory = local_settings_directory()
        old_path = Path(old_directory) / "settings.ini" if old_directory is not None else None
        old = None
        if old_path is not None and old_path.resolve() != target.resolve() and old_path.is_file():
            old = QSettings(str(old_path), QSettings.Format.IniFormat)
            old.setFallbacksEnabled(False)
            keys = old.allKeys()
            if old.status() != QSettings.Status.NoError:
                raise OSError(f"Cannot read existing settings: {old_path}. Existing data was preserved.")
            for key in keys:
                if not settings.contains(key):
                    settings.setValue(key, old.value(key))
        # An already migrated local INI needs no further registry access.
        migrate_registry = not settings.value("storage/migrated", False, type=bool)
        if migrate_registry:
            legacy = legacy if legacy is not None else QSettings("B01", "B01PDF")
            legacy.setFallbacksEnabled(False)
            for key in legacy.allKeys():
                if not settings.contains(key):
                    settings.setValue(key, legacy.value(key))
        settings.setValue("storage/migrated", True)
        settings.setValue("storage/executableFolder", True)
        settings.sync()
        if settings.status() != QSettings.Status.NoError:
            raise OSError(f"Cannot save {target}. Existing settings were preserved.")
        # Old storage is removed only after a successful save in the new location.
        if old is not None:
            del old
            try:
                old_path.unlink()
                old_path.parent.rmdir()  # Remove the old directory only if empty.
            except OSError:
                pass
        if migrate_registry:
            legacy.clear()
            legacy.sync()
    return settings
