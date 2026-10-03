"""Include upstream license texts and PDFium attribution in desktop builds."""
from pathlib import Path
from urllib.request import urlopen
import importlib.metadata
import shutil

root = Path(__file__).resolve().parents[1] / "notices"
root.mkdir(exist_ok=True)
urls = {
    "LGPL-3.0.txt": "https://raw.githubusercontent.com/qt/qtbase/v6.10.2/LICENSES/LGPL-3.0-only.txt",
    "GPL-3.0.txt": "https://raw.githubusercontent.com/qt/qtbase/v6.10.2/LICENSES/GPL-3.0-only.txt",
    "Qt-PDF-third-party.html": "https://doc.qt.io/qt-6.10/qtpdf-licensing.html",
    "PDFium-LICENSE.txt": "https://raw.githubusercontent.com/qt/qtwebengine-chromium/c971c6841dd6beab9f54aeaf9a53be413273039e/chromium/third_party/pdfium/LICENSE",
}
for name, url in urls.items():
    with urlopen(url, timeout=60) as response:
        data = response.read()
    if not data:
        raise RuntimeError(f"Empty license: {url}")
    (root / name).write_bytes(data)
for name in ("Pillow",):
    distribution = importlib.metadata.distribution(name)
    for file in distribution.files or []:
        if "licenses/" in str(file):
            source = Path(distribution.locate_file(file))
            if source.is_file():
                target = root / name / source.name
                target.parent.mkdir(exist_ok=True)
                shutil.copy2(source, target)
