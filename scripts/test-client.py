#!/usr/bin/env python3
"""Two isolated regtest nodes: transaction-aware mining, payment and key handling."""
import argparse
import contextlib
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('community', ROOT / 'client/vaytria.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
REGTEST = '0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206'


def wait_for(condition, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if condition():
                return
        except (OSError, ValueError, module.RPCError):
            pass
        time.sleep(0.1)
    raise RuntimeError('Isolated integration check timed out.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--daemon', required=True)
    parser.add_argument('--security', action='store_true')
    args = parser.parse_args()
    daemon = Path(args.daemon).resolve()
    checks = []
    for value in ['-1', '0', 'NaN', 'Infinity', '0.000000001', '21000001']:
        try:
            module.amount_string(value)
        except module.RPCError:
            continue
        raise AssertionError('Invalid payment amount accepted.')
    assert module.amount_string('0.00000001') == '0.00000001'
    checks.append('invalid payment amounts rejected and eight-decimal precision retained')
    assert not module.has_public_peer([{'addr': '127.0.0.1:31444'}, {'addr': '192.0.2.1:31444'}, {'addr': '[::1]:31444'}])
    assert module.has_public_peer([{'addr': '8.8.8.8:31444'}])
    # These address fixtures are parsed only; no external network request occurs.
    checks.append('public-peer classification rejects loopback, private and documentation addresses')
    class Isolated:
        chain = 'vaytria'
        def verify(self): pass
        def rpc(self, method, params=None):
            return {'validateaddress': {'isvalid': True}, 'getconnectioncount': 1,
                    'getpeerinfo': [{'addr': '127.0.0.1:31444'}]}[method]
    try:
        module.mine(Isolated(), 'fixture', seconds=1)
    except module.RPCError:
        checks.append('main-chain client refuses local-only reward mining before hashing')
    else:
        raise AssertionError('Isolated main-chain mining was accepted.')
    for port in [18443, 18444, 18543, 18544]:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', port))
    with tempfile.TemporaryDirectory(prefix='vaytria-regtest-') as temporary:
        processes, clients = [], []
        try:
            for i, name in enumerate(['miner', 'buyer']):
                data = Path(temporary) / name
                data.mkdir()
                rpc, peer = 18443 + i * 100, 18444 + i * 100
                with (data / 'node.log').open('wb') as log:
                    processes.append(subprocess.Popen([str(daemon), '-regtest', '-server=1', '-datadir=' + str(data),
                        '-bind=127.0.0.1:' + str(peer), '-port=' + str(peer), '-rpcbind=127.0.0.1',
                        '-rpcallowip=127.0.0.1', '-rpcport=' + str(rpc), '-connect=0', '-dnsseed=0',
                        '-fixedseeds=0', '-discover=0', '-listenonion=0', '-dbcache=64', '-par=1',
                        '-fallbackfee=0.0002'], stdout=log, stderr=log))
                client = module.Client(data, rpc, 'regtest', REGTEST, name)
                clients.append(client)
                wait_for(lambda: client.rpc('getblockcount') == 0)
                client.verify()
            miner, buyer = clients
            buyer.rpc('addnode', ['127.0.0.1:18444', 'onetry'])
            wait_for(lambda: miner.rpc('getconnectioncount') == buyer.rpc('getconnectioncount') == 1)
            secret = secrets.token_hex(32)
            original_prompt = module.getpass.getpass
            try:
                module.getpass.getpass = lambda *args: secret
                for client in clients:
                    module.create(client)
                    assert client.rpc('getwalletinfo', wallet=True)['unlocked_until'] == 0
            finally:
                module.getpass.getpass = original_prompt
            checks.append('two cookie-authenticated local nodes and encrypted wallet creation verified')
            miner_address = miner.rpc('getnewaddress', wallet=True)
            buyer_address = buyer.rpc('getnewaddress', wallet=True)
            # Match the real miner's one-block RPCs. Slow durable Windows writes
            # must not turn a bulk fixture into an unrelated 30-second timeout.
            for _ in range(101):
                assert len(miner.rpc('generatetoaddress', [1, miner_address])) == 1
            work_salts = []
            for height in [100, 101]:
                coinbase = miner.rpc('getblock', [miner.rpc('getblockhash', [height]), 2])['tx'][0]
                script = bytes.fromhex(coinbase['vin'][0]['coinbase'])
                assert len(script) >= 35 and script[-33] == 32, 'Fresh 32-byte mining work salt is absent.'
                work_salts.append(script[-32:])
            assert work_salts[0] != work_salts[1], 'Mining RPCs repeated their coinbase work salt.'
            checks.append('separate native mining RPCs append distinct 32-byte coinbase work salts')
            wait_for(lambda: buyer.rpc('getblockcount') == 101)
            miner.rpc('walletpassphrase', [secret, 30], wallet=True)
            txid = miner.rpc('sendtoaddress', [buyer_address, '1.25'], wallet=True)
            miner.rpc('walletlock', wallet=True)
            fee = Decimal(str(miner.rpc('getmempoolentry', [txid])['fees']['base']))
            with contextlib.redirect_stdout(io.StringIO()):
                assert module.mine(miner, miner_address, seconds=1, workers=1)
            wait_for(lambda: buyer.rpc('gettransaction', [txid], wallet=True)['confirmations'] > 0)
            tx = buyer.rpc('gettransaction', [txid], wallet=True)
            assert Decimal(str(tx['amount'])) == Decimal('1.25')
            block = miner.rpc('getblock', [tx['blockhash'], 2])
            assert any(item['txid'] == txid for item in block['tx'])
            assert sum(Decimal(str(vout['value'])) for vout in block['tx'][0]['vout']) == Decimal('50') + fee
            checks.append('real regtest payment included by native miner with correct subsidy and fee')
            original_factory, original_argv = module.Client, sys.argv
            try:
                module.Client = lambda *args, **kwargs: buyer
                module.getpass.getpass = lambda *args: secret
                sys.argv = ['vaytria.py', 'send', miner_address, '0.25', '--confirm']
                output = io.StringIO()
                with contextlib.redirect_stdout(output): module.main()
                returned = json.loads(output.getvalue())['transactionId']
                assert buyer.rpc('getwalletinfo', wallet=True)['unlocked_until'] == 0
            finally:
                module.Client, sys.argv = original_factory, original_argv
                module.getpass.getpass = original_prompt
            wait_for(lambda: returned in miner.rpc('getrawmempool'))
            miner.rpc('generatetoaddress', [1, miner_address])
            wait_for(lambda: buyer.rpc('gettransaction', [returned], wallet=True)['confirmations'] > 0)
            checks.append('actual CLI returns payment, confirms and relocks the encrypted wallet')
            if args.security:
                security_spec = importlib.util.spec_from_file_location('security_integration', ROOT / 'scripts/security-integration.py')
                security_module = importlib.util.module_from_spec(security_spec)
                security_spec.loader.exec_module(security_module)
                checks.extend(security_module.run(miner, buyer, secret))
            wrong = module.Client(buyer.datadir, buyer.port, chain='regtest')
            try: wrong.verify()
            except module.RPCError: checks.append('wrong genesis rejected before wallet operations')
            else: raise AssertionError('Wrong network accepted.')
        finally:
            for client in clients:
                try: client.rpc('stop')
                except Exception: pass
            for process in processes:
                try: process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=15)
    reports = ROOT / 'reports'
    reports.mkdir(exist_ok=True)
    report = {'recordedAtUTC': datetime.now(timezone.utc).isoformat(), 'passed': True,
        'clientSHA256': hashlib.sha256((ROOT / 'client/vaytria.py').read_bytes()).hexdigest(),
        'daemonSHA256': hashlib.sha256(daemon.read_bytes()).hexdigest(), 'checks': checks,
        'scope': 'Two isolated loopback regtest nodes only. No live-coin mining, public peers, buyers or market.'}
    if args.security:
        report['securityToolSHA256'] = hashlib.sha256((ROOT / 'client/security.py').read_bytes()).hexdigest()
    (reports / 'integration.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
