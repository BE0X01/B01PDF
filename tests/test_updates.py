import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from updates import VERSION, API_ROOT, UpdateJob, version_parts, newer_release, installer_asset, extract_installer, SafeRedirect
from urllib.request import Request


class UpdateTests(unittest.TestCase):
    def test_version_comparison(self):
        self.assertEqual(version_parts('v0.2'), version_parts('0.2.0'))
        self.assertTrue(newer_release({'tag_name': 'v0.10'}))
        self.assertFalse(newer_release({'tag_name': 'v0.1'}))
        self.assertFalse(newer_release({'tag_name': 'v0.3', 'prerelease': True}))

    def test_asset_validation(self):
        asset = {'name': 'B01PDF-0.3-Windows-Setup.zip', 'url': API_ROOT + '/releases/assets/123',
                 'size': 123, 'digest': 'sha256:' + 'a' * 64}
        self.assertEqual(installer_asset({'assets': [asset]}), asset)
        with self.assertRaises(ValueError):
            installer_asset({'assets': [{**asset, 'url': 'https://example.com/installer'}]})
        with self.assertRaises(ValueError):
            installer_asset({'assets': [{**asset, 'digest': ''}]})

    def test_checksum_and_safe_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'installer.zip'
            with zipfile.ZipFile(archive, 'w') as zipped:
                zipped.writestr('B01PDF-Setup.exe', b'MZtest executable')
                zipped.writestr('../unwanted.txt', b'no')
            digest = 'sha256:' + hashlib.sha256(archive.read_bytes()).hexdigest()
            executable = extract_installer(archive, digest, directory)
            self.assertEqual(Path(executable).read_bytes(), b'MZtest executable')
            self.assertFalse((Path(directory).parent / 'unwanted.txt').exists())
            with self.assertRaises(ValueError):
                extract_installer(archive, 'sha256:' + '0' * 64, directory)

    def test_release_check_and_download_jobs(self):
        payload = {'tag_name': 'v0.3', 'assets': []}
        job = UpdateJob()
        results = []
        job.result.connect(results.append)
        with patch('updates.request', return_value=io.BytesIO(json.dumps(payload).encode())):
            job.run()
        self.assertEqual(results, [payload])
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, 'w') as zipped:
            zipped.writestr('B01PDF-Setup.exe', b'MZtest')
        data = archive_buffer.getvalue()
        asset = {'url': API_ROOT + '/releases/assets/1', 'size': len(data),
                 'digest': 'sha256:' + hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory() as directory:
            job = UpdateJob(asset)
            results = []
            job.result.connect(results.append)
            with patch('updates.request', return_value=io.BytesIO(data)), patch('updates.tempfile.mkdtemp', return_value=directory):
                job.run()
            self.assertEqual(Path(results[0]).read_bytes(), b'MZtest')

    def test_reject_untrusted_redirect(self):
        request = Request(API_ROOT + '/releases/assets/1')
        with self.assertRaises(ValueError):
            SafeRedirect().redirect_request(request, None, 302, '', {}, 'http://github.com/file')
        with self.assertRaises(ValueError):
            SafeRedirect().redirect_request(request, None, 302, '', {}, 'https://example.com/file')


if __name__ == '__main__':
    unittest.main()
