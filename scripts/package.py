#!/usr/bin/env python3
"""Allowlisted public package with checksums and matching test evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.1.0-alpha'


def digest(data): return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', required=True, choices=['linux-x86_64', 'win64'])
    parser.add_argument('--bin-dir', required=True)
    parser.add_argument('--frozen-client')
    args = parser.parse_args()
    windows = args.platform == 'win64'
    suffix = '.exe' if windows else ''
    binary = Path(args.bin_dir)
    test = json.loads((ROOT / 'reports/integration.json').read_text())
    assert test['passed'] and test['clientSHA256'] == digest((ROOT / 'client/vaytria.py').read_bytes())
    assert test['daemonSHA256'] == digest((binary / ('bitcoind' + suffix)).read_bytes())
    files = {}
    for original, name in [('bitcoind', 'vaytriad'), ('bitcoin-cli', 'vaytria-cli')]:
        files['bin/' + name + suffix] = (binary / (original + suffix)).read_bytes()
    for name in ['identity.json', 'genesis.json', 'relay.conf', 'source.patch']:
        files[name] = (ROOT / 'network' / name).read_bytes()
    for name in ['COPYING', 'README.md', 'BUILD.md', 'RUNNING.md', 'HANDOFF.md']:
        files[name] = (ROOT / name).read_bytes()
    files['vaytria.py'] = (ROOT / 'client/vaytria.py').read_bytes()
    files['checks/integration.json'] = (ROOT / 'reports/integration.json').read_bytes()
    if windows:
        frozen = Path(args.frozen_client)
        subprocess.run([str(frozen.resolve()), '--help'], stdout=subprocess.DEVNULL, check=True)
        files['vaytria.exe'] = frozen.read_bytes()
        files['Vaytria.cmd'] = b'@echo off\r\n"%~dp0vaytria.exe" menu\r\npause\r\n'
        license_path = next(path for path in [Path(sys.base_prefix) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE'] if path.is_file())
        files['licenses/Python.txt'] = license_path.read_bytes()
        distribution = importlib.metadata.distribution('pyinstaller')
        license_entry = next(item for item in distribution.files if str(item).endswith(('COPYING.txt', 'COPYING')))
        files['licenses/PyInstaller.txt'] = Path(distribution.locate_file(license_entry)).read_bytes()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    files['build-info.json'] = (json.dumps({'version': VERSION, 'platform': args.platform,
        'repositoryCommit': commit, 'upstreamCommit': '9be056a8a72b624dae9623b2f7bded92c2a21c91',
        'sourcePatchSHA256': digest(files['source.patch']), 'clientSHA256': digest(files['vaytria.py']),
        'recordedAtUTC': datetime.now(timezone.utc).isoformat(), 'publicNetworkVerified': False,
        'founderAllocationCoins': 0, 'premineCoins': 0, 'noVerifiedBootstrapPeerSupplied': True}, indent=2) + '\n').encode()
    for name, content in files.items():
        if name.startswith('bin/') or name == 'vaytria.exe': continue
        for marker in [b'/mnt/c/', b'BEGIN PRIVATE KEY', b'recovery-passphrase']:
            assert marker.lower() not in content.lower(), (name, 'private marker')
    files['SHA256SUMS'] = ''.join(digest(data) + '  ' + name + '\n' for name, data in sorted(files.items())).encode()
    out = ROOT / 'dist'
    out.mkdir(exist_ok=True)
    filename = 'vaytria-' + VERSION + '-' + args.platform + ('.zip' if windows else '.tar.gz')
    path = out / filename
    if windows:
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items(): archive.writestr('vaytria/' + name, data)
        with zipfile.ZipFile(path) as archive:
            assert set(archive.namelist()) == {'vaytria/' + name for name in files}
            assert all(archive.read('vaytria/' + name) == data for name, data in files.items())
    else:
        with tarfile.open(path, 'w:gz') as archive:
            for name, data in files.items():
                info = tarfile.TarInfo('vaytria/' + name)
                info.size, info.mtime, info.uid, info.gid = len(data), 0, 0, 0
                info.mode = 0o755 if name.startswith('bin/') or name.endswith('.py') else 0o644
                archive.addfile(info, io.BytesIO(data))
        with tarfile.open(path) as archive:
            assert set(archive.getnames()) == {'vaytria/' + name for name in files}
            assert all(archive.extractfile('vaytria/' + name).read() == data for name, data in files.items())
    (out / ('SHA256SUMS-' + args.platform)).write_text(digest(path.read_bytes()) + '  ' + filename + '\n')
    print(json.dumps({'package': filename, 'sha256': digest(path.read_bytes()), 'bytes': path.stat().st_size}))


if __name__ == '__main__': main()
