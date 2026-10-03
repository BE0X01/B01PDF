import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings
from settings_store import open_settings


class SettingsStoreTests(unittest.TestCase):
    def test_migration_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = QSettings(str(root / "legacy.ini"), QSettings.Format.IniFormat)
            values = {"remember": True, "view/zoom": 150.0,
                      "view/fit": "width", "shortcuts/Open": "Ctrl+8",
                      "geometry": QByteArray(b"window geometry"),
                      "positions/book": '{"page": 5, "scroll": 120}'}
            for key, value in values.items():
                legacy.setValue(key, value)
            legacy.sync()
            settings = open_settings(root / "data", legacy)
            self.assertTrue((root / "data/settings.ini").is_file())
            for key, value in values.items():
                self.assertEqual(settings.value(key), value)
            self.assertEqual(legacy.allKeys(), [])
            settings.setValue("view/zoom", 200)
            settings.sync()
            legacy.setValue("view/zoom", 50)
            reopened = open_settings(root / "data", legacy)
            self.assertEqual(reopened.value("view/zoom", type=int), 200)
            reopened.remove("positions")
            reopened.sync()
            self.assertFalse(open_settings(root / "data", legacy).contains("positions/book"))

    def test_failed_migration_preserves_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = QSettings(str(root / "legacy.ini"), QSettings.Format.IniFormat)
            legacy.setValue("view/zoom", 150)
            legacy.sync()
            target = root / "data"
            target.mkdir()
            (target / "settings.ini").mkdir()
            with self.assertRaises(OSError):
                open_settings(target, legacy)
            self.assertEqual(legacy.value("view/zoom", type=int), 150)
