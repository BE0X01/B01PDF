"""Public GitHub release updater. No login or token is required."""
import hashlib
import json
import re
import shutil
import tempfile
import time
import threading
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from PySide6.QtCore import QObject, Signal

VERSION = "1.51"
API_ROOT = "https://api.github.com/repos/BE0X01/b01-pdf"
MAX_DOWNLOAD = 200 * 1024 * 1024


def cleanup_old_updates(temp_root=None, now=None):
    """Remove abandoned downloads; never remove an in-use Windows installer."""
    root = Path(temp_root or tempfile.gettempdir())
    now = time.time() if now is None else now
    for folder in root.glob('B01PDF-update-*'):
        try:
            if folder.is_symlink() or not folder.is_dir():
                continue
            if now - folder.stat().st_mtime < 24 * 60 * 60:
                continue
            exe = folder / 'B01PDF-Setup.exe'
            # Windows refuses deletion while the installer is running.
            if exe.exists():
                exe.unlink()
            shutil.rmtree(folder)
        except OSError:
            pass  # Locked files are retried on a subsequent launch.


def version_parts(value):
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", value)
    if not match:
        raise ValueError("Unsupported release version")
    parts = tuple(int(x) for x in match[1].split('.'))
    return parts + (0,) * max(0, 3 - len(parts))


def newer_release(release):
    return not release.get('draft') and not release.get('prerelease') and version_parts(release['tag_name']) > version_parts(VERSION)


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != 'https' or not (parsed.hostname in ('api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com') or (parsed.hostname or '').endswith('.blob.core.windows.net')):
            raise ValueError("Unexpected download redirect")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and parsed.hostname != urlparse(req.full_url).hostname:
            redirected.remove_header('Authorization')
        return redirected


def request(url, binary=False):
    if not url.startswith(API_ROOT + '/'):
        raise ValueError('Unexpected GitHub API URL')
    headers = {'User-Agent': 'B01PDF/' + VERSION,
               'Accept': 'application/octet-stream' if binary else 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28'}
    return build_opener(SafeRedirect()).open(Request(url, headers=headers), timeout=20)


def installer_asset(release):
    for asset in release.get('assets', []):
        if re.fullmatch(r'B01PDF-[0-9.]+-Windows-Setup\.zip', asset.get('name', '')):
            if not asset.get('url', '').startswith(API_ROOT + '/releases/assets/'):
                raise ValueError('Unexpected installer source')
            digest = asset.get('digest', '')
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
                raise ValueError('The release does not provide an installer checksum')
            if not 0 < asset.get('size', 0) <= MAX_DOWNLOAD:
                raise ValueError('Invalid installer size')
            return asset
    raise ValueError('No Windows installer ZIP was found in this release')


def extract_installer(archive, digest, folder):
    with open(archive, 'rb') as source:
        actual = hashlib.file_digest(source, 'sha256').hexdigest()
    if actual != digest.removeprefix('sha256:'):
        raise ValueError('Installer checksum verification failed')
    with zipfile.ZipFile(archive) as zipped:
        # Extract a single, fixed filename; never trust paths inside a ZIP.
        item = zipped.getinfo('B01PDF-Setup.exe')
        if item.file_size <= 0 or item.file_size > MAX_DOWNLOAD:
            raise ValueError('Invalid installer executable size')
        target = Path(folder) / 'B01PDF-Setup.exe'
        with zipped.open(item) as source, target.open('wb') as dest:
            shutil.copyfileobj(source, dest)
        with target.open('rb') as source:
            if source.read(2) != b'MZ':
                target.unlink()
                raise ValueError('The downloaded file is not a Windows executable')
    return str(target)


class UpdateJob(QObject):
    result = Signal(object)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, asset=None, parent=None):
        super().__init__(parent)
        self.asset = asset
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        folder = None
        try:
            if self.asset is None:
                with request(API_ROOT + '/releases/latest') as response:
                    release = json.loads(response.read(1024 * 1024))
                self.result.emit(release)
            else:
                folder = tempfile.mkdtemp(prefix='B01PDF-update-')
                archive = Path(folder) / 'installer.zip'
                received = 0
                with request(self.asset['url'], True) as source, archive.open('wb') as dest:
                    while chunk := source.read(128 * 1024):
                        received += len(chunk)
                        if received > MAX_DOWNLOAD:
                            raise ValueError('Installer download exceeds the size limit')
                        dest.write(chunk)
                        self.progress.emit(min(100, int(received / self.asset['size'] * 100)))
                if received != self.asset['size']:
                    raise ValueError('Incomplete installer download')
                exe = extract_installer(archive, self.asset['digest'], folder)
                archive.unlink()
                self.result.emit(exe)
        except Exception as error:
            if folder:
                shutil.rmtree(folder, ignore_errors=True)
            if isinstance(error, HTTPError) and error.code in (401, 403, 404):
                message = 'GitHub could not provide a release. Check the network, API rate limit, or repository availability.'
            else:
                message = 'Update failed: ' + str(error)
            try:
                self.failed.emit(message)
            except RuntimeError:
                pass  # The app may have closed while a daemon request was finishing.
        finally:
            self.running = False
