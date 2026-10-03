"""File-backed preferences with a one-time migration from legacy QSettings."""
import os
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths


def open_settings(directory=None, legacy=None):
    if directory is None:
        base = os.environ.get("LOCALAPPDATA") or QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.GenericDataLocation)
        directory = Path(base) / "B01PDF"
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    settings = QSettings(str(directory / "settings.ini"), QSettings.Format.IniFormat)
    settings.setFallbacksEnabled(False)
    if not settings.value("storage/migrated", False, type=bool):
        legacy = legacy if legacy is not None else QSettings("B01", "B01PDF")
        legacy.setFallbacksEnabled(False)
        keys = legacy.allKeys()
        for key in keys:
            if not settings.contains(key):
                settings.setValue(key, legacy.value(key))
        settings.setValue("storage/migrated", True)
        settings.sync()
        if settings.status() != QSettings.Status.NoError:
            raise OSError("Cannot save B01PDF settings. Legacy settings were preserved.")
        # Delete legacy data only after the file has been saved successfully.
        legacy.clear()
        legacy.sync()
    return settings
