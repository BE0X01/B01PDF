"""Windows CI: verify old-file migration and normal-user Program Files writes."""
import ctypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QSettings
from settings_store import local_settings_directory, open_settings


def main():
    mode = sys.argv[1]
    if mode == "seed":
        old = local_settings_directory()
        old.mkdir(parents=True, exist_ok=True)
        settings = QSettings(str(old / "settings.ini"), QSettings.Format.IniFormat)
        settings.setValue("storage/migrated", True)
        settings.setValue("view/zoom", 150)
        settings.setValue("view/fit", "manual")
        settings.setValue("shortcuts/200%", "Ctrl+8")
        settings.setValue("positions/ci-book", '{"page":5,"scroll":120}')
        settings.sync()
        assert settings.status() == QSettings.Status.NoError
        return
    folder = Path(sys.argv[2])
    settings = open_settings(folder)
    assert Path(settings.fileName()) == folder / "settings.ini"
    if mode == "verify":
        assert settings.value("view/zoom", type=int) == 150
        assert settings.value("shortcuts/200%") == "Ctrl+8"
        assert settings.value("positions/ci-book") == '{"page":5,"scroll":120}'
        assert not (local_settings_directory() / "settings.ini").exists()
    elif mode == "standard":
        assert not ctypes.windll.shell32.IsUserAnAdmin()
        settings.setValue("ci/standardUserWrite", "passed")
        settings.sync()
        assert settings.status() == QSettings.Status.NoError
        assert QSettings(str(folder / "settings.ini"), QSettings.Format.IniFormat).value(
            "ci/standardUserWrite") == "passed"
        try:
            with (folder / "B01PDF.exe").open("r+b"):
                raise AssertionError("Executable unexpectedly writable by a standard user")
        except PermissionError:
            pass
    else:
        raise ValueError(mode)


if __name__ == "__main__":
    main()
