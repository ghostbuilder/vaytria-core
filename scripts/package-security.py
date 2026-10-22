"""Package the security toolkit separately; never relabel old coin binaries."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', choices=['win64', 'linux-x86_64'], required=True)
    args = parser.parse_args()
    report = json.loads((ROOT / 'reports/integration.json').read_text())
    tool = (ROOT / 'client/security.py').read_bytes()
    if not report['passed'] or report['securityToolSHA256'] != hashlib.sha256(tool).hexdigest():
        raise ValueError('Matching successful signing checks are required.')
    files = {'security.py': tool, 'vaytria.py': (ROOT / 'client/vaytria.py').read_bytes(),
             'verify-release.py': (ROOT / 'scripts/verify-release.py').read_bytes(),
             'SECURITY.md': (ROOT / 'SECURITY.md').read_bytes(), 'COPYING': (ROOT / 'COPYING').read_bytes(),
             'alerts.yml': (ROOT / 'monitoring/alerts.yml').read_bytes(),
             'checks/security-integration.json': (ROOT / 'reports/integration.json').read_bytes()}
    if args.platform == 'win64':
        import importlib.metadata
        import sys
        executable = ROOT / 'frozen/vaytria-security.exe'
        subprocess.run([str(executable), '--help'], check=True, stdout=subprocess.DEVNULL)
        files['vaytria-security.exe'] = executable.read_bytes()
        license_path = next(path for path in [Path(sys.base_prefix) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE'] if path.is_file())
        files['licenses/Python.txt'] = license_path.read_bytes()
        distribution = importlib.metadata.distribution('pyinstaller')
        entry = next(item for item in distribution.files if str(item).endswith(('COPYING.txt', 'COPYING')))
        files['licenses/PyInstaller.txt'] = Path(distribution.locate_file(entry)).read_bytes()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    files['build-info.json'] = (json.dumps({'version': 'security-v0.1.0-alpha', 'repositoryCommit': commit,
        'platform': args.platform, 'coinDaemonIncluded': False, 'independentAudit': False,
        'publicNetworkVerified': False}, indent=2) + '\n').encode()
    files['SHA256SUMS'] = ''.join(hashlib.sha256(value).hexdigest() + '  ' + name + '\n'
                                  for name, value in sorted(files.items())).encode()
    out = ROOT / 'dist'
    out.mkdir(exist_ok=True)
    path = out / ('vaytria-security-v0.1.0-alpha-' + args.platform + '.zip')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for name, value in files.items(): bundle.writestr('vaytria/' + name, value)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (out / ('SHA256SUMS-security-' + args.platform)).write_text(digest + '  ' + path.name + '\n')
    print(json.dumps({'package': path.name, 'sha256': digest, 'sourceCommit': commit}))


if __name__ == '__main__': main()
