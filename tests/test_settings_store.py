import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings
from settings_store import application_directory, open_settings


class SettingsStoreTests(unittest.TestCase):
    def test_saving_preserves_file_identity_and_other_instance_values(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy = QSettings(str(Path(directory) / "legacy.ini"), QSettings.Format.IniFormat)
            first = open_settings(Path(directory) / "install", legacy)
            second = open_settings(Path(directory) / "install", legacy)
            path = Path(first.fileName())
            identity = path.stat().st_ino
            first.setValue("view/zoom", 200)
            first.sync()
            second.setValue("view/dark", True)
            second.sync()
            self.assertEqual(second.value("view/zoom", type=int), 200)
            self.assertTrue(second.value("view/dark", type=bool))
            self.assertEqual(path.stat().st_ino, identity)
            self.assertEqual(second.status(), QSettings.Status.NoError)

    def test_frozen_path_uses_executable_not_working_directory(self):
        with patch("settings_store.sys.frozen", True, create=True), patch(
                "settings_store.sys.executable", str(Path(tempfile.gettempdir()) / "installed" / "B01PDF.exe")):
            self.assertEqual(application_directory(), (Path(tempfile.gettempdir()) / "installed").resolve())

    def test_migrates_local_file_and_prefers_existing_install_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "local"
            old.mkdir()
            source = QSettings(str(old / "settings.ini"), QSettings.Format.IniFormat)
            source.setValue("storage/migrated", True)
            source.setValue("view/zoom", 150)
            source.setValue("shortcuts/Open", "Ctrl+8")
            source.setValue("positions/book", '{"page":5,"scroll":120}')
            source.setValue("geometry", QByteArray(b"geometry bytes"))
            source.sync()
            destination = root / "install"
            destination.mkdir()
            existing = QSettings(str(destination / "settings.ini"), QSettings.Format.IniFormat)
            existing.setValue("view/zoom", 200)
            existing.sync()
            with patch("settings_store.application_directory", return_value=destination), patch(
                    "settings_store.local_settings_directory", return_value=old):
                settings = open_settings()
                self.assertEqual(Path(settings.fileName()), destination / "settings.ini")
                self.assertEqual(settings.value("view/zoom", type=int), 200)
                self.assertEqual(settings.value("geometry"), QByteArray(b"geometry bytes"))
                self.assertEqual(settings.value("shortcuts/Open"), "Ctrl+8")
                self.assertEqual(settings.value("positions/book"), '{"page":5,"scroll":120}')
                self.assertFalse((old / "settings.ini").exists())
                self.assertFalse(settings.isAtomicSyncRequired())
                settings.setValue("view/zoom", 300)
                settings.sync()
                self.assertEqual(open_settings().value("view/zoom", type=int), 300)

    def test_failed_destination_preserves_local_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "local"
            old.mkdir()
            old_file = old / "settings.ini"
            old_file.write_text("[view]\nzoom=150\n")
            target = root / "install"
            target.mkdir()
            (target / "settings.ini").mkdir()
            with self.assertRaises(OSError):
                open_settings(target, old_directory=old)
            self.assertEqual(old_file.read_text(), "[view]\nzoom=150\n")

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
