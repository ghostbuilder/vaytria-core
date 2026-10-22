#!/usr/bin/env python3
"""Vaytria offline PSBT signing and one-shot, read-only node monitoring. MIT."""
import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys

from vaytria import Client, DEFAULT_DATA, GENESIS, RPCError

MAX_PSBT_BYTES = 1_000_000
READ_METHODS = frozenset({'getblockchaininfo', 'getblockhash', 'getblockheader',
                         'getnetworkinfo', 'getmempoolinfo'})


def read_psbt(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_PSBT_BYTES + 1)
    if len(raw) > MAX_PSBT_BYTES:
        raise ValueError('PSBT exceeds the supported size.')
    value = raw.decode('ascii').strip()
    if not base64.b64decode(value, validate=True).startswith(b'psbt\xff'):
        raise ValueError('Not a PSBT file.')
    return value


def write_new(path, content):
    # Never replace an existing transaction, wallet or backup.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(content + '\n')


def review_psbt(client, psbt):
    client.verify()
    decoded = client.rpc('decodepsbt', [psbt])
    if 'fee' not in decoded or not decoded.get('inputs'):
        raise RPCError('Every input needs prevout information and a calculable fee.')
    if any(item.get('sighash', 'ALL') != 'ALL' for item in decoded['inputs']):
        raise RPCError('Only SIGHASH_ALL is supported by this signing tool.')
    fee = Decimal(str(decoded['fee']))
    if not fee.is_finite() or fee < 0:
        raise RPCError('Invalid fee.')
    outputs = []
    for output in decoded['tx']['vout']:
        script = output['scriptPubKey']
        amount = Decimal(str(output['value']))
        if not script.get('address') or not amount.is_finite() or amount < 0:
            raise RPCError('Every output must have a reviewable address and amount.')
        outputs.append({'address': script['address'], 'amount': format(amount, 'f')})
    if not outputs:
        raise RPCError('No outputs to review.')
    review = {'genesisHash': client.expected_genesis, 'unsignedTransactionId': decoded['tx']['txid'],
              'inputs': len(decoded['inputs']), 'outputs': outputs, 'fee': format(fee, 'f')}
    review['reviewSHA256'] = hashlib.sha256(json.dumps(review, sort_keys=True).encode()).hexdigest()
    return review


def sign_psbt(client, psbt, output, approved_review):
    review = review_psbt(client, psbt)
    if approved_review != review['reviewSHA256']:
        raise RPCError('Transaction review does not match. Nothing signed.')
    if Path(output).exists():
        raise FileExistsError('Output exists. Choose a new file.')
    network = client.rpc('getnetworkinfo')
    if network['networkactive'] or network['connections']:
        raise RPCError('Signing requires networking disabled and zero peer connections.')
    wallet = client.rpc('getwalletinfo', wallet=True)
    if not wallet['private_keys_enabled'] or wallet.get('unlocked_until') != 0:
        raise RPCError('Use a locked, encrypted signing wallet with private keys enabled.')
    secret = getpass.getpass('Offline signing wallet passphrase: ')
    try:
        client.rpc('walletpassphrase', [secret, 30], wallet=True)
        secret = None
        result = client.rpc('walletprocesspsbt', [psbt, True, 'ALL', True, False], wallet=True)
    finally:
        secret = None
        client.rpc('walletlock', wallet=True)
    # The tool never broadcasts or exports private keys. A second signer can
    # consume this file; keep it private because PSBTs contain wallet metadata.
    write_new(output, result['psbt'])
    return {'saved': True, 'broadcast': False, 'reviewSHA256': review['reviewSHA256']}


class ReadOnlyClient:
    def __init__(self, client):
        self.client = client

    def rpc(self, method, params=None):
        if method not in READ_METHODS:
            raise RPCError('Monitoring method is not allowed.')
        return self.client.rpc(method, params)

    def verify(self):
        if (self.rpc('getblockchaininfo')['chain'] != self.client.chain or
                self.rpc('getblockhash', [0]) != self.client.expected_genesis):
            raise RPCError('Wrong monitoring network.')


def snapshot(client, previous=None):
    reader = ReadOnlyClient(client)
    reader.verify()
    chain = reader.rpc('getblockchaininfo')
    network = reader.rpc('getnetworkinfo')
    pool = reader.rpc('getmempoolinfo')
    previous = previous or {}
    reorg = False
    if previous.get('genesisHash') == client.expected_genesis and previous.get('bestBlockHash'):
        if chain['blocks'] < previous['blockHeight']:
            reorg = True
        elif chain['bestblockhash'] != previous['bestBlockHash']:
            try:
                reorg = reader.rpc('getblockheader', [previous['bestBlockHash']])['confirmations'] < 0
            except RPCError:
                # An unknown former tip may mean a restart with different data.
                # Alert on uncertainty rather than silently treating it as safe.
                reorg = True
    return {'recordedAtUTC': datetime.now(timezone.utc).isoformat(), 'genesisHash': client.expected_genesis,
            'up': True, 'blockHeight': chain['blocks'], 'bestBlockHash': chain['bestblockhash'],
            'chainWork': chain['chainwork'], 'initialBlockDownload': chain['initialblockdownload'],
            'peerCount': network['connections'], 'mempoolTransactions': pool['size'],
            'reorganizationObserved': reorg, 'publicNetworkVerified': False,
            'scope': 'Local node observation only; no wallet balance or global issuance claim.'}


def metrics(value):
    lines = ['# No addresses, keys, cookies or wallet amounts are exported.']
    fields = {'up': 'up', 'blockHeight': 'block_height', 'peerCount': 'peers',
              'mempoolTransactions': 'mempool_transactions',
              'initialBlockDownload': 'initial_block_download', 'reorganizationObserved': 'reorg_observed'}
    for key, name in fields.items():
        if key in value:
            lines += ['# TYPE vaytria_' + name + ' gauge', 'vaytria_' + name + ' ' + str(int(value[key]))]
    lines += ['# TYPE vaytria_observed_at_seconds gauge',
              'vaytria_observed_at_seconds ' + str(int(datetime.now(timezone.utc).timestamp()))]
    return '\n'.join(lines) + '\n'


def replace_observation(path, value):
    target = Path(path)
    temporary = target.with_name(target.name + '.tmp')
    write_new(temporary, value.rstrip('\n'))
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datadir', default=str(DEFAULT_DATA))
    parser.add_argument('--rpc-port', type=int, default=31443)
    parser.add_argument('--wallet', default='miner')
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect-psbt')
    inspect.add_argument('input')
    sign = commands.add_parser('sign-psbt')
    sign.add_argument('input')
    sign.add_argument('--out', required=True)
    monitor = commands.add_parser('monitor')
    monitor.add_argument('--state', required=True)
    monitor.add_argument('--metrics', required=True)
    args = parser.parse_args()
    client = Client(args.datadir, args.rpc_port, wallet=args.wallet)
    if args.command == 'monitor':
        if Path(args.state).resolve() == Path(args.metrics).resolve():
            raise ValueError('State and metrics need separate files.')
        previous = json.loads(Path(args.state).read_text()) if Path(args.state).exists() else None
        try:
            result = snapshot(client, previous)
        except (OSError, ValueError, RPCError):
            replace_observation(args.metrics, metrics({'up': False}))
            raise RPCError('Node unavailable or wrong network. Metrics report down; last state retained.')
        replace_observation(args.state, json.dumps(result, indent=2))
        replace_observation(args.metrics, metrics(result))
    else:
        psbt = read_psbt(args.input)
        result = review_psbt(client, psbt)
        print(json.dumps(result, indent=2))
        if args.command == 'sign-psbt':
            approved = input('Verify EVERY output, change address and fee on this offline device.\n'
                             'Type the full reviewSHA256 above to sign (no broadcast): ').strip()
            result = sign_psbt(client, psbt, args.out, approved)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RPCError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
