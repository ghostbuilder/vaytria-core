#!/usr/bin/env python3
"""Start the actual packaged client at genesis; never mine a live block."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive')
    args = parser.parse_args()
    archive = Path(args.archive).resolve()
    with tempfile.TemporaryDirectory(prefix='vaytria-package-check-') as temporary:
        base = Path(temporary)
        if archive.suffix == '.zip':
            with zipfile.ZipFile(archive) as bundle:
                assert all(not name.startswith('/') and '..' not in Path(name).parts for name in bundle.namelist())
                bundle.extractall(base)
        else:
            with tarfile.open(archive) as bundle:
                bundle.extractall(base, filter='data')
        package = base / 'vaytria'
        for line in (package / 'SHA256SUMS').read_text().splitlines():
            expected, name = line.split('  ', 1)
            assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected, name
        command = [str(package / 'vaytria.exe')] if os.name == 'nt' else [sys.executable, str(package / 'vaytria.py')]
        command += ['--datadir', str(base / 'data')]
        started = False
        try:
            result = subprocess.run(command + ['start'], capture_output=True, text=True, timeout=90)
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout)['running']
            started = True
            peers = subprocess.run(command + ['peers'], capture_output=True, text=True, check=True, timeout=45)
            assert json.loads(peers.stdout) == [], 'No public network belongs in this isolated startup test.'
            print('Package hashes, native startup at the pinned genesis and empty peer list passed. No live block mined.')
        finally:
            if started:
                subprocess.run(command + ['stop'], capture_output=True, check=True, timeout=45)
                # Wait for shutdown to release database files before temporary directory cleanup.
                import time
                deadline = time.monotonic() + 30
                while (base / 'data/vaytria/.cookie').exists() and time.monotonic() < deadline:
                    time.sleep(0.25)
                time.sleep(2)


if __name__ == '__main__':
    main()
