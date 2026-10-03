import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from updates import cleanup_old_updates


class CleanupTests(unittest.TestCase):
    def test_removes_only_stale_update_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / 'B01PDF-update-old'
            recent = root / 'B01PDF-update-recent'
            unrelated = root / 'other-app'
            for folder in (old, recent, unrelated):
                folder.mkdir()
                (folder / 'B01PDF-Setup.exe').write_bytes(b'MZ')
            now = time.time()
            os.utime(old, (now - 90000, now - 90000))
            cleanup_old_updates(root, now)
            self.assertFalse(old.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(unrelated.exists())

    def test_locked_installer_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'B01PDF-update-locked'
            folder.mkdir()
            (folder / 'B01PDF-Setup.exe').write_bytes(b'MZ')
            now = time.time()
            os.utime(folder, (now - 90000, now - 90000))
            with patch.object(Path, 'unlink', side_effect=PermissionError):
                cleanup_old_updates(directory, now)
            self.assertTrue((folder / 'B01PDF-Setup.exe').exists())
