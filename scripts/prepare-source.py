#!/usr/bin/env python3
"""Reconstruct exactly the publicly documented source; no wallet data is used."""
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = '9be056a8a72b624dae9623b2f7bded92c2a21c91'
PATCH = 'dc7505ec8631b47d56069638249802f40faf36df1640d9e0204f46c6b7c4e833'


def main():
    patch = ROOT / 'network/source.patch'
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == PATCH, 'Patch differs from the qualified source.'
    target = ROOT / 'core'
    if target.exists():
        raise RuntimeError('core already exists. Use a fresh checkout/build directory; no reset is performed.')
    subprocess.run(['git', 'clone', '--no-checkout', '--filter=blob:none',
        'https://github.com/bitcoin/bitcoin.git', str(target)], check=True)
    subprocess.run(['git', '-C', str(target), 'checkout', '--detach', UPSTREAM], check=True)
    actual = subprocess.check_output(['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True).strip()
    assert actual == UPSTREAM
    subprocess.run(['git', '-C', str(target), 'apply', '--check', str(patch)], check=True)
    subprocess.run(['git', '-C', str(target), 'apply', str(patch)], check=True)
    print('Source reconstructed from the pinned upstream commit and exact qualified patch.')


if __name__ == '__main__':
    main()
