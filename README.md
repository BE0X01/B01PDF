# B01PDF

A minimal Windows desktop PDF viewer focused on comfortable reading, simple navigation, and flexible view controls.

[Download the latest version](https://github.com/BE0X01/B01PDF/releases/latest) · [All releases](https://github.com/BE0X01/B01PDF/releases) · [Report an issue](https://github.com/BE0X01/B01PDF/issues)

## Installation

1. Download `B01PDF-<version>-Windows-Setup.zip` from the latest release.
2. Extract the ZIP and run `B01PDF-Setup.exe`.
3. Launch B01PDF and select `Open`, or drag a PDF into the window.

Python is not required. The default installation directory is `Program Files\B01PDF`. Installation requires administrator permission. All application text is in English.

## Features

| Feature | Description |
| --- | --- |
| Fit modes | `Fit Width` and `Fit Page` have active button indicators and automatically adjust when the window resizes. |
| Zoom | Restore 100%, use preset zoom steps, or adjust with Ctrl+mouse wheel. Manual zoom exits the active fit mode. |
| View modes | Choose `1 Page`, `2 Pages`, or continuous `Scroll`. Two-page view displays pairs such as 1-2 and 3-4. |
| Thumbnail sidebar | Navigate using page previews. Thumbnails scale with the sidebar width; the toolbar toggles its visibility. |
| Themes | Switch between `Dark` and `Light` from the toolbar. |
| Image filters | Select `Original` or `Sharp` in Settings. Filters affect the display without modifying the PDF. |
| Saved preferences | Zoom, fit mode, view mode, theme, sidebar visibility, filter, and shortcuts are saved globally. |
| Reading position | Optionally remember the last page and scroll position for each file. |
| File opening | Supports password-protected PDFs, drag and drop, and command-line file opening. |

The sidebar width is limited to a minimum of 160px and a maximum of 25% of the window width.

## Navigation and Panning

- In single-page and two-page views, the mouse wheel scrolls an oversized page vertically. At the bottom, another downward wheel step advances. At the top, an upward step returns to the bottom of the previous page.
- Two-page view advances or returns by one pair of pages.
- `Shift+mouse wheel` scrolls horizontally without changing pages.
- Drag with the left mouse button to pan an enlarged page.
- Continuous Scroll view scrolls through the entire document.

## Default Keyboard Shortcuts

Change shortcuts in `Settings`, save your changes, or restore the defaults. Conflicting shortcuts are reported before saving.

| Action | Default shortcut |
| --- | --- |
| Open PDF | `Ctrl+O` |
| Open Settings | `Ctrl+,` |
| Fit Page | `Ctrl+0` |
| Fit Width | `Ctrl+9` |
| Zoom to 100% | `Ctrl+1` |
| Zoom to 200% | `Ctrl+2` |
| Zoom to 300% | `Ctrl+3` |
| Zoom to 50% | `` Ctrl+` `` |
| Zoom in by one preset | `Ctrl++` (`Ctrl+=` is also supported) |
| Zoom out by one preset | `Ctrl+-` |
| Single-page view | `Alt+1` |
| Two-page view | `Alt+2` |
| Continuous Scroll view | `Alt+3` |
| Toggle sidebar | `F9` |
| Open quit confirmation | `Ctrl+Q` |

Use `Down`, `Right`, or `Page Down` for the next page; `Up`, `Left`, or `Page Up` for the previous page. `Home` jumps to the first page and `End` to the last page. These navigation keys are fixed and cannot be assigned to other actions. Editable controls retain their standard editing behavior.

### Zoom Behavior

The toolbar −/+ buttons and `Ctrl+-` / `Ctrl++` use these preset levels:

`10% → 25% → 33% → 50% → 75% → 100% → 150% → 200% → 300%`

Zooming out at 10% or in at 300% does nothing. If the current zoom falls between presets, the next action selects the nearest preset in that direction.

`Ctrl+mouse wheel` changes zoom in 10-percentage-point steps, within a range of 10-400%.

`Ctrl+Q` displays a quit confirmation with `OK` and `Cancel`. Closing with the window's X button exits directly.

## Updates

Select `Settings` → `Check for Updates` to check the latest stable GitHub release. When a newer version is available, confirm the download. B01PDF downloads the installer ZIP, verifies its SHA-256 checksum, and starts the installer. The viewer closes so its files can be replaced. Existing settings are preserved.

Checking for and downloading updates requires internet access. Reading PDFs does not. The updater does not send PDF contents or file paths.

Version 0.1 has no built-in updater. If automatic installation does not work in an older version, download and run the latest installer manually. If an older per-user installation remains, verify that the new installation works before removing it.

## Development

Built with Python 3.12, PySide6 / Qt PDF, and Pillow.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Run the tests:

```powershell
python -m unittest discover -s tests -v
```

The Windows build workflow runs viewer and updater tests, packages the application, checks the packaged executable, builds the Inno Setup installer, and verifies installation and startup under Program Files. Releases contain the tested installer ZIP. Existing releases are never overwritten.

### Implementation Notes

- At 100%, one PDF point maps to 96/72 logical pixels, with operating-system display scaling applied. This does not imply physical paper dimensions.
- `Original` uses the PDF engine's standard rendering. `Sharp` applies an Unsharp Mask.
- Windows settings are stored under `HKEY_CURRENT_USER\Software\B01\B01PDF`.
- Reading positions are identified by the full file path. Moving or renaming a file creates a new position record. Disabling position memory clears saved positions without resetting global view preferences.
- Only visible pages are rendered. The render cache is limited to 96MiB, and each render to 12 megapixels. Complex pages may briefly pause the interface during rendering.
- Text selection, search, annotations, printing, and PDF editing are not currently supported.

## License

See [LICENSE](LICENSE) for the project license and [THIRD_PARTY.md](THIRD_PARTY.md) for dependency notices.
