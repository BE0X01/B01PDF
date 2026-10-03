# B01PDF

A minimal Windows desktop PDF viewer. Current version: 0.4.

## Install

Download [Version 0.4](https://github.com/BE0X01/B01PDF/releases/tag/v0.4), extract `B01PDF-0.4-Windows-Setup.zip`, and run `B01PDF-Setup.exe`. Python is not required. New installations default to Program Files\B01PDF and request administrator permission. Existing user settings are preserved. Older per-user installations can be removed after verifying the new installation.

## Features

- 100% default zoom, 10-400% manual zoom, Fit Width / Fit Page.
- 1 Page, 2 Pages (1-2, 3-4 spreads), or continuous Scroll view. Fit Width and Fit Page have active button indicators and respond to window resizing; manual zoom clears the active indicators.
- Width-responsive thumbnail sidebar and toolbar toggles for the sidebar and Dark / Light.
- Original / Sharp filters in Settings. Filters affect display only.
- Global zoom, fit, view mode, theme, sidebar and filter preferences restored across files and app restarts.
- Optional per-file last page and scroll position. Disabling this clears saved positions; it does not reset global view preferences.
- Drag and drop, password-protected PDFs, command-line file opening.

In 1 Page and 2 Pages modes, wheel scrolls an oversized page vertically. At the bottom, another downward wheel step advances; at the top, an upward step returns to the previous page bottom. A spread advances by two pages. Shift+wheel scrolls horizontally without changing pages. Drag with the left mouse button to pan. Continuous Scroll mode retains normal scrolling. Down/Right/Page Down advances; Up/Left/Page Up goes back; Home/End jumps to the first/last page. Navigation keys apply to the PDF view; editable controls retain their usual editing behavior. Ctrl+wheel changes zoom. Ctrl+O opens, Ctrl+0 resets to 100%, Ctrl+plus/minus changes zoom, and F9 toggles the sidebar.

## Updates

Settings > Check for Updates queries the latest stable GitHub release without a login or token. When a newer version is available, confirm to download its installer ZIP, verify the SHA-256 checksum, and start the installer. The viewer closes to allow replacement of its files. Canceling the prompt keeps the installed version. Updating requires network access; reading PDFs does not.

Version 0.1 does not contain the updater and must be upgraded manually once. Future updates can be installed through 0.2's update function. Updates use the same Windows application ID and preserve user settings.

## Development

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
python -m unittest discover -s tests -v
```

The Windows workflow runs behavior and updater tests, packages the app, checks the packaged executable startup, creates the installer, and publishes the tested 0.4 installer ZIP. An existing release is never overwritten.

100% maps one PDF point to 96/72 logical pixels, with OS display scaling applied. It does not imply physical paper dimensions. Original uses the PDF engine's standard antialiasing; Sharp applies an Unsharp Mask. There is no extra AA mode.

Windows settings are stored under `HKEY_CURRENT_USER\Software\B01\B01PDF`. File position identity is based on the full file path. Moving or renaming a file creates a new position record. Legacy 0.1 per-file view modes are ignored in favor of global preferences.

The app renders only visible pages; render cache is bounded to 96 MiB and each render to 12 megapixels. Complex page rendering takes place on the UI thread and can briefly pause the UI. Text selection/search, annotations, printing and PDF editing are outside the current scope. Network work runs in the background and sends no PDF contents or file paths.

## Dependencies

PySide6 / Qt PDF and Pillow. See [THIRD_PARTY.md](THIRD_PARTY.md) for license notices.

The supplied logo is bundled as a multi-resolution Windows icon. The Add/Remove Programs name is B01PDF; its version is stored in the separate DisplayVersion field.
