"""Validate legacy package without executing it, then run only regtest checks."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_release', ROOT / 'scripts/verify-release.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)
PINS = {
    'win64': ('vaytria-0.1.2-alpha-win64.zip', 'd380ab7a4420badf1282ed596b2bd2c0fe48ab9e16a3bd076d516a74c848af21'),
    'linux-x86_64': ('vaytria-0.1.2-alpha-linux-x86_64.tar.gz', 'c23d7630afccd0d82a55ca30ad54c53845e7fe4376f5109ea662c67e67e88d23')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=PINS, required=True)
    args = parser.parse_args()
    filename, digest = PINS[args.platform]
    archive = ROOT / 'downloads' / filename
    verify.verify_archive(archive, digest)
    with tempfile.TemporaryDirectory(prefix='vaytria-security-fixture-') as temporary:
        if archive.suffix == '.zip':
            with zipfile.ZipFile(archive) as bundle: bundle.extractall(temporary)
        else:
            with tarfile.open(archive) as bundle: bundle.extractall(temporary, filter='data')
        suffix = '.exe' if args.platform == 'win64' else ''
        daemon = Path(temporary) / 'vaytria/bin' / ('vaytriad' + suffix)
        # Only this test runner may execute the daemon. It explicitly creates
        # disposable -regtest nodes; no production startup or wallet is used.
        subprocess.run([sys.executable, str(ROOT / 'scripts/test-client.py'),
                        '--daemon', str(daemon), '--security'], check=True)


if __name__ == '__main__': main()
