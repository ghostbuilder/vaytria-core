#!/usr/bin/env python3
"""Experimental Vaytria local wallet/node and bounded CPU miner. MIT licensed."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from decimal import Decimal, InvalidOperation
import getpass
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import quote

GENESIS = '00000000c59f648b04817dd53eb907d6ab78dfef3cf35a6c4e4bbca3cac3af22'
PACKAGE = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
DEFAULT_DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Vaytria' if os.name == 'nt' else Path.home() / '.vaytria-community'


class RPCError(RuntimeError):
    pass


class Client:
    def __init__(self, datadir, port=31443, chain='vaytria', expected_genesis=GENESIS, wallet='miner'):
        self.datadir, self.port, self.chain = Path(datadir), port, chain
        self.expected_genesis, self.wallet = expected_genesis, wallet

    def rpc(self, method, params=None, wallet=False):
        cookie = (self.datadir / self.chain / '.cookie').read_text().strip()
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=30)
        try:
            connection.request('POST', '/wallet/' + quote(self.wallet, safe='') if wallet else '/',
                json.dumps({'jsonrpc': '2.0', 'id': 'vaytria', 'method': method, 'params': params or []}),
                {'Authorization': 'Basic ' + base64.b64encode(cookie.encode()).decode(), 'Content-Type': 'application/json'})
            result = json.loads(connection.getresponse().read())
            if result.get('error'):
                raise RPCError(method + ': ' + str(result['error']['code']) + ' ' + result['error']['message'])
            return result['result']
        finally:
            connection.close()

    def verify(self):
        if self.rpc('getblockchaininfo')['chain'] != self.chain or self.rpc('getblockhash', [0]) != self.expected_genesis:
            raise RPCError('Wrong network or genesis. No wallet operation was attempted.')

    def start(self, peers=()):
        try:
            self.verify()
        except (OSError, ValueError):
            pass
        else:
            for peer in peers:
                self.rpc('addnode', [peer, 'add'])
            return {'running': True, 'alreadyRunning': True}
        binary = PACKAGE / 'bin' / ('vaytriad.exe' if os.name == 'nt' else 'vaytriad')
        expected = {}
        for line in (PACKAGE / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            expected[name] = digest
        name = binary.relative_to(PACKAGE).as_posix()
        if hashlib.sha256(binary.read_bytes()).hexdigest() != expected.get(name):
            raise RPCError('Daemon checksum differs from the package manifest. Refusing to execute it.')
        self.datadir.mkdir(parents=True, exist_ok=True, mode=0o700)
        arguments = [str(binary), '-chain=vaytria', '-datadir=' + str(self.datadir),
            '-server=1', '-listen=0', '-dnsseed=0', '-fixedseeds=0', '-discover=0', '-listenonion=0',
            '-dbcache=128', '-par=1', '-rpcthreads=4', '-fallbackfee=0.0002',
            '-rpcbind=127.0.0.1', '-rpcallowip=127.0.0.1', '-rpcport=' + str(self.port)]
        arguments += ['-addnode=' + peer for peer in peers]
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
        with (self.datadir / 'node.log').open('ab') as log:
            process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=log, stderr=log, **options)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RPCError('The local node exited. Inspect node.log in your local data directory.')
            try:
                self.verify()
                return {'running': True, 'peersConfigured': len(peers), 'nodePid': process.pid}
            except (OSError, ValueError, RPCError):
                time.sleep(0.25)
        process.terminate()
        process.wait(timeout=15)
        raise RPCError('Node startup timed out; the newly started process was stopped.')


def amount_string(value):
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount <= 0 or amount > 21000000 or amount != amount.quantize(Decimal('0.00000001')):
            raise ValueError()
    except (InvalidOperation, ValueError):
        raise RPCError('Use a positive amount, at most 21 million, with at most eight decimal places.')
    return format(amount, 'f')


def has_public_peer(peers):
    for peer in peers:
        address = peer.get('addr', '')
        host = address[1:].split(']', 1)[0] if address.startswith('[') else address.rsplit(':', 1)[0]
        try:
            if ipaddress.ip_address(host).is_global:
                return True
        except ValueError:
            continue
    return False


def mine(client, address, seconds=1800, workers=1, tries=100000):
    if not 1 <= seconds <= 1800 or not 1 <= workers <= 4 or not 1 <= tries <= 100000:
        raise RPCError('Use 1-1800 seconds, 1-4 workers and at most 100000 nonce attempts per RPC.')
    client.verify()
    if not client.rpc('validateaddress', [address])['isvalid']:
        raise RPCError('Invalid receiving address for this network.')
    if client.rpc('getconnectioncount') < 1:
        raise RPCError('No peers connected. Refusing isolated reward mining.')
    if client.chain != 'regtest' and not has_public_peer(client.rpc('getpeerinfo')):
        raise RPCError('No public IP peer connected. Local-only mining is not enabled by this client.')
    deadline, accepted = time.monotonic() + seconds, []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(client.rpc, 'generatetoaddress', [1, address, tries]) for _ in range(workers)}
        try:
            while pending:
                completed, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in completed:
                    for block_hash in future.result():
                        accepted.append(block_hash)
                        print(json.dumps({'acceptedBlock': block_hash}), flush=True)
                    if time.monotonic() < deadline:
                        pending.add(pool.submit(client.rpc, 'generatetoaddress', [1, address, tries]))
        except KeyboardInterrupt:
            for future in pending:
                future.cancel()
    return accepted


def create(client):
    secret = getpass.getpass('New wallet passphrase (keep offline): ')
    if len(secret) < 16 or secret != getpass.getpass('Repeat passphrase: '):
        raise RPCError('Passphrases must match and have at least 16 characters.')
    result = client.rpc('createwallet', {'wallet_name': client.wallet, 'passphrase': secret,
        'descriptors': True, 'load_on_startup': True})
    secret = None
    return result


def send(client, address, value, confirmed):
    amount = amount_string(value)
    if not confirmed:
        raise RPCError('Review recipient and amount, then pass --confirm. No transaction was sent.')
    if not client.rpc('validateaddress', [address])['isvalid']:
        raise RPCError('Invalid receiving address. No transaction was sent.')
    secret = getpass.getpass('Wallet passphrase: ')
    client.rpc('walletpassphrase', [secret, 30], wallet=True)
    secret = None
    try:
        return {'transactionId': client.rpc('sendtoaddress', [address, amount], wallet=True)}
    finally:
        try:
            client.rpc('walletlock', wallet=True)
        except Exception:
            print('Wallet relock failed; its unlock timeout is 30 seconds.', file=sys.stderr)


def menu(client):
    print('Vaytria experimental community client. No guaranteed reward or cash value.')
    print('No bootstrap peer is supplied by the founder. Find volunteer peers in the public project discussions.')
    while True:
        print('\n1 Start node / add a public peer\n2 Create encrypted wallet\n3 Receiving address\n4 Balance\n5 Mine for up to 30 minutes\n6 Back up encrypted wallet\n7 Stop node\n0 Exit menu (node continues running)')
        choice = input('Choose: ').strip()
        if choice == '0':
            return
        try:
            if choice == '1':
                peer = input('Public peer IP:port, or blank to start without a peer: ').strip()
                result = client.start([peer] if peer else [])
            else:
                client.verify()
                if choice == '2':
                    result = create(client)
                elif choice == '3':
                    result = {'address': client.rpc('getnewaddress', ['receive', 'bech32'], wallet=True)}
                elif choice == '4':
                    result = client.rpc('getbalances', wallet=True)
                elif choice == '5':
                    address = client.rpc('getnewaddress', ['mining', 'bech32'], wallet=True)
                    if not client.rpc('getaddressinfo', [address], wallet=True)['ismine']:
                        raise RPCError('The local wallet does not control this mining address.')
                    result = {'blocks': mine(client, address, seconds=1800, workers=1)}
                elif choice == '6':
                    target = Path(input('New absolute backup file path: ').strip()).expanduser()
                    if not target.is_absolute() or target.exists():
                        raise RPCError('Choose a new absolute file path. Existing files will not be overwritten.')
                    result = client.rpc('backupwallet', [str(target)], wallet=True)
                    print('Keep the encrypted backup on a separate device and its passphrase separately offline.')
                elif choice == '7':
                    result = client.rpc('stop')
                else:
                    print('Choose one of the listed numbers.')
                    continue
            print(json.dumps(result, indent=2))
        except (RPCError, OSError, ValueError) as error:
            print(str(error), file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datadir', default=str(DEFAULT_DATA))
    parser.add_argument('--wallet', default='miner')
    parser.add_argument('--rpc-port', type=int, default=31443)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ['create', 'address', 'balance', 'transactions', 'peers', 'stop', 'menu']:
        commands.add_parser(name)
    start = commands.add_parser('start')
    start.add_argument('--peer', action='append', default=[])
    payment = commands.add_parser('send')
    payment.add_argument('address')
    payment.add_argument('amount')
    payment.add_argument('--confirm', action='store_true')
    mining = commands.add_parser('mine')
    mining.add_argument('address')
    mining.add_argument('--seconds', type=int, default=1800)
    mining.add_argument('--workers', type=int, choices=range(1, 5), default=1)
    args = parser.parse_args()
    client = Client(args.datadir, args.rpc_port, wallet=args.wallet)
    if args.command == 'start':
        result = client.start(args.peer)
    elif args.command == 'menu':
        return menu(client)
    else:
        client.verify()
        if args.command == 'create':
            result = create(client)
        elif args.command == 'address':
            result = {'address': client.rpc('getnewaddress', ['receive', 'bech32'], wallet=True)}
        elif args.command == 'balance':
            result = client.rpc('getbalances', wallet=True)
        elif args.command == 'transactions':
            result = client.rpc('listtransactions', ['*', 20], wallet=True)
        elif args.command == 'peers':
            result = [{'address': peer['addr'], 'inbound': peer['inbound']} for peer in client.rpc('getpeerinfo')]
        elif args.command == 'stop':
            result = client.rpc('stop')
        elif args.command == 'mine':
            result = {'blocks': mine(client, args.address, args.seconds, args.workers)}
        else:
            result = send(client, args.address, args.amount, args.confirm)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (RPCError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        print('For a failed or timed-out payment, inspect transactions before retrying. Never automatically repeat it.', file=sys.stderr)
        sys.exit(1)
