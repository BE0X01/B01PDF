"""Preferences beside the executable, with one-time legacy migration."""
import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths


class InstalledSettings(QSettings):
    """Keep edits in memory; serialize only when explicitly flushed on exit."""
    def __init__(self, filename, format):
        self._target = Path(filename)
        self._write_status = QSettings.Status.NoError
        self._changed = set()
        self._removed = []
        # This native instance only reads the installed file. No setValue/remove
        # calls reach it, so Qt's automatic sync cannot write pending edits.
        super().__init__(str(self._target), format)
        self.setFallbacksEnabled(False)
        self._values = {key: super(InstalledSettings, self).value(key)
                        for key in super().allKeys()}

    def setValue(self, key, value):
        self._changed.add(key)
        self._values[key] = value

    def value(self, key, defaultValue=None, type=None):
        value = self._values.get(key, defaultValue)
        if type is None or value is None:
            return value
        if type is bool and isinstance(value, str):
            return value.lower() not in ("", "0", "false")
        return type(value)

    def contains(self, key):
        return key in self._values

    def allKeys(self):
        return sorted(self._values)

    def remove(self, key):
        self._removed.append(key)
        for existing in list(self._values):
            if not key or existing == key or existing.startswith(key + "/"):
                del self._values[existing]

    def clear(self):
        self.remove("")

    def status(self):
        return self._write_status if self._write_status != QSettings.Status.NoError else super().status()

    def isWritable(self):
        try:
            with self._target.open("r+b"):
                return True
        except OSError:
            return False

    def sync(self):
        import tempfile
        # Import other instances' saved changes without replacing pending edits.
        reader = QSettings(str(self._target), QSettings.Format.IniFormat)
        reader.setFallbacksEnabled(False)
        reader.sync()
        if reader.status() != QSettings.Status.NoError:
            self._write_status = reader.status()
            return
        def removed(key):
            return any(not group or key == group or key.startswith(group + "/")
                       for group in self._removed)
        for key in list(self._values):
            if key not in self._changed and not reader.contains(key):
                del self._values[key]
        for key in reader.allKeys():
            if key not in self._changed and not removed(key):
                self._values[key] = reader.value(key)
        try:
            # Qt encoding preserves geometry bytes and shortcut punctuation.
            # This temporary serialization file exists only during the flush.
            with tempfile.TemporaryDirectory(prefix="B01PDF-settings-") as directory:
                staging = Path(directory) / "settings.ini"
                writer = QSettings(str(staging), QSettings.Format.IniFormat)
                writer.setFallbacksEnabled(False)
                for key, value in self._values.items():
                    writer.setValue(key, value)
                writer.sync()
                if writer.status() != QSettings.Status.NoError:
                    self._write_status = writer.status()
                    del writer
                    return
                data = staging.read_bytes()
                del writer
                # Keep the existing NTFS file and its normal-user permissions.
                with self._target.open("r+b") as stream:
                    stream.write(data)
                    stream.truncate()
                    stream.flush()
                    os.fsync(stream.fileno())
            self._write_status = QSettings.Status.NoError
            self._changed.clear()
            self._removed.clear()
        except OSError:
            self._write_status = QSettings.Status.AccessError



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
    # Serialization happens outside that folder; the target is written in place.
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
