# Third-party software

B01PDF source is MIT licensed (LICENSE). Dependencies retain their own licenses.

- PySide6 / Shiboken6 / Qt: LGPL-3.0 or applicable alternative license; Qt PDF includes PDFium and its third-party notices. The dynamically linked libraries are shipped as separate files in the PyInstaller onedir folder and can be replaced by compatible builds. Do not turn this distribution into a static Qt build without reviewing the license obligations.
  - https://doc.qt.io/qtforpython-6/licenses.html
  - https://doc.qt.io/qt-6/qtpdf-index.html#licenses
  - https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.10.2
  - https://code.qt.io/cgit/qt/qtwebengine.git/tag/?h=v6.10.2
- Pillow: MIT-CMU and included component licenses.
  - https://github.com/python-pillow/Pillow/blob/12.1.0/LICENSE
- Python: PSF license. https://docs.python.org/3/license.html
- PyInstaller: GPL with bootloader exception allowing packaged applications under their own license. https://pyinstaller.org/en/stable/license.html

The build downloads matching upstream LGPL/GPL license texts, the PDFium LICENSE and Qt PDF attribution page, and copies Pillow license files into the notices directory. Qt/PySide source for the matching version is available from the links above. Users may modify or reverse engineer the application for debugging modifications to LGPL components under the applicable license.
