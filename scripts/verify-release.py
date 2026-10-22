#!/usr/bin/env python3
"""Verify a pinned archive without executing or extracting it. MIT licensed."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import zipfile

MAX_SIZE = 256 * 1024 * 1024
REPOSITORY = 'ghostbuilder/vaytria-core'


def verify_archive(path, expected_sha256):
    path = Path(path)
    if not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('Expected SHA256 must be 64 lowercase hexadecimal characters.')
    if path.stat().st_size > MAX_SIZE:
        raise ValueError('Archive too large.')
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError('Archive does not match the independently obtained SHA256.')
    files = {}
    canonical_names = set()
    total = 0

    def accept(name, size, regular):
        nonlocal total
        parts = PurePosixPath(name).parts
        if (not regular or not parts or name.startswith('/') or '\\' in name or ':' in name or
                any(part in ('', '.', '..') for part in name.split('/')) or len(parts) < 2 or
                parts[0] != 'vaytria' or name.casefold() in canonical_names or len(files) >= 256 or
                any(part.endswith(('.', ' ')) or part.split('.')[0].upper() in
                    {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
                     *(f'LPT{i}' for i in range(1, 10))} for part in parts)):
            raise ValueError('Unsafe, duplicate or excessive archive entry.')
        canonical_names.add(name.casefold())
        total += size
        if size < 0 or total > MAX_SIZE:
            raise ValueError('Expanded archive too large.')

    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                mode = entry.external_attr >> 16
                accept(entry.filename, entry.file_size, not entry.is_dir() and
                       (stat.S_IFMT(mode) in (0, stat.S_IFREG)))
                files[entry.filename] = archive.read(entry)
    else:
        with tarfile.open(path) as archive:
            for entry in archive:
                accept(entry.name, entry.size, entry.isfile())
                files[entry.name] = archive.extractfile(entry).read()
    manifest = files.get('vaytria/SHA256SUMS', b'').decode('ascii')
    expected = {}
    for line in manifest.splitlines():
        digest, name = line.split('  ', 1)
        if name in expected or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid or duplicate manifest entry.')
        expected[name] = digest
    content = {name[len('vaytria/'):]: data for name, data in files.items() if name != 'vaytria/SHA256SUMS'}
    if not expected or set(content) != set(expected):
        raise ValueError('Manifest must cover every file exactly once.')
    for name, data in content.items():
        if hashlib.sha256(data).hexdigest() != expected[name]:
            raise ValueError('Internal file checksum mismatch: ' + name)
    return {'sha256': expected_sha256, 'filesVerified': len(content), 'executesFiles': False}


def verify_provenance(path, commit, workflow):
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Pin the full source commit.')
    if workflow not in ('build.yml', 'security.yml'):
        raise ValueError('Unknown trusted workflow.')
    subprocess.run(['gh', 'attestation', 'verify', str(Path(path).resolve()), '--repo', REPOSITORY,
                    '--signer-workflow', REPOSITORY + '/.github/workflows/' + workflow,
                    '--source-digest', commit, '--deny-self-hosted-runners'], check=True, timeout=120)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('--sha256', required=True, help='Obtain through an independently trusted channel.')
    parser.add_argument('--source-commit')
    parser.add_argument('--workflow', default='build.yml', choices=['build.yml', 'security.yml'])
    parser.add_argument('--integrity-only', action='store_true', help='Explicitly skip publisher authentication for legacy releases.')
    args = parser.parse_args()
    if not args.integrity_only and not args.source_commit:
        parser.error('--source-commit is required unless --integrity-only is explicitly selected')
    result = verify_archive(args.archive, args.sha256)
    if not args.integrity_only:
        verify_provenance(args.archive, args.source_commit, args.workflow)
    result['provenanceVerified'] = not args.integrity_only
    result['scope'] = 'File integrity and optional build identity; not a code audit or network-security guarantee.'
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
