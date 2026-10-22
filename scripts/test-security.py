"""Offline fixtures for security tooling; no nodes, secrets or external requests."""
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client'))
import security
spec = importlib.util.spec_from_file_location('verify_release', ROOT / 'scripts/verify-release.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class Fixture:
    chain, expected_genesis = 'vaytria', security.GENESIS
    def __init__(self):
        self.calls = []
        self.network = {'networkactive': False, 'connections': 0}
        self.decoded = {'fee': '0.00001', 'inputs': [{}],
                        'tx': {'txid': 'f' * 64, 'vout': [{'value': '1', 'scriptPubKey': {'address': 'fixture'}}]}}
        self.fail_sign = False
    def verify(self): pass
    def rpc(self, method, params=None, wallet=False):
        self.calls.append(method)
        if method == 'decodepsbt': return copy.deepcopy(self.decoded)
        if method == 'getnetworkinfo': return self.network
        if method == 'getwalletinfo': return {'private_keys_enabled': True, 'unlocked_until': 0}
        if method == 'walletprocesspsbt':
            if self.fail_sign: raise security.RPCError('Fixture signing failure')
            return {'psbt': base64.b64encode(b'psbt\xfffixture').decode(), 'complete': False}
        if method in ('walletpassphrase', 'walletlock'): return None
        if method == 'getblockchaininfo':
            return {'chain': self.chain, 'blocks': 12, 'bestblockhash': 'a' * 64,
                    'chainwork': '123', 'initialblockdownload': False}
        if method == 'getblockhash': return self.expected_genesis
        if method == 'getmempoolinfo': return {'size': 0}
        if method == 'getblockheader': return {'confirmations': -1}
        raise AssertionError('Unexpected RPC: ' + method)


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.client = Fixture()

    def test_psbt_parser_rejects_non_psbt(self):
        path = self.root / 'input'
        for data in (b'wrong', base64.b64encode(b'notpsbt'), b'x' * (security.MAX_PSBT_BYTES + 1)):
            path.write_bytes(data)
            with self.assertRaises(ValueError): security.read_psbt(path)

    def test_review_covers_fee_outputs_and_transaction(self):
        first = security.review_psbt(self.client, 'fixture')['reviewSHA256']
        for field in ('fee', 'amount', 'address', 'txid'):
            changed = Fixture()
            if field == 'fee': changed.decoded['fee'] = '0.001'
            elif field == 'txid': changed.decoded['tx']['txid'] = 'b' * 64
            elif field == 'address': changed.decoded['tx']['vout'][0]['scriptPubKey']['address'] = 'other'
            else: changed.decoded['tx']['vout'][0]['value'] = '2'
            self.assertNotEqual(first, security.review_psbt(changed, 'fixture')['reviewSHA256'])

    def test_missing_prevouts_unknown_output_and_unsafe_sighash_refused(self):
        changes = [lambda d: d.pop('fee'), lambda d: d['inputs'][0].update(sighash='NONE'),
                   lambda d: d['tx']['vout'][0]['scriptPubKey'].clear(), lambda d: d.update(fee='-1')]
        for change in changes:
            client = Fixture(); change(client.decoded)
            with self.assertRaises(security.RPCError): security.review_psbt(client, 'fixture')

    def test_wrong_review_never_unlocks(self):
        with self.assertRaises(security.RPCError): security.sign_psbt(self.client, 'fixture', self.root / 'out', 'wrong')
        self.assertNotIn('walletpassphrase', self.client.calls)

    def test_connected_signer_refused(self):
        for network in ({'networkactive': True, 'connections': 0}, {'networkactive': False, 'connections': 1}):
            self.client.network = network
            review = security.review_psbt(self.client, 'fixture')['reviewSHA256']
            with self.assertRaises(security.RPCError): security.sign_psbt(self.client, 'fixture', self.root / 'out', review)
        self.assertNotIn('walletpassphrase', self.client.calls)

    def test_sign_failure_relocks(self):
        self.client.fail_sign = True
        with patch.object(security.getpass, 'getpass', return_value='fake-regtest-only'):
            with self.assertRaises(security.RPCError):
                security.sign_psbt(self.client, 'fixture', self.root / 'out', security.review_psbt(self.client, 'fixture')['reviewSHA256'])
        self.assertEqual(self.client.calls[-1], 'walletlock')
        self.assertFalse((self.root / 'out').exists())

    def test_sign_never_broadcasts_or_overwrites(self):
        out = self.root / 'out'
        with patch.object(security.getpass, 'getpass', return_value='fake-regtest-only'):
            security.sign_psbt(self.client, 'fixture', out, security.review_psbt(self.client, 'fixture')['reviewSHA256'])
        self.assertNotIn('sendrawtransaction', self.client.calls)
        self.assertEqual(self.client.calls[-1], 'walletlock')
        with self.assertRaises(FileExistsError): security.write_new(out, 'replacement')

    def test_monitor_cannot_use_wallet_or_mutating_rpc(self):
        reader = security.ReadOnlyClient(self.client)
        for method in ('sendtoaddress', 'walletpassphrase', 'walletprocesspsbt', 'stop', 'getwalletinfo'):
            with self.assertRaises(security.RPCError): reader.rpc(method)
        self.assertEqual(self.client.calls, [])

    def test_monitor_detects_reorg_without_claiming_network_verified(self):
        value = security.snapshot(self.client, {'genesisHash': self.client.expected_genesis,
                                  'blockHeight': 11, 'bestBlockHash': 'b' * 64})
        self.assertTrue(value['reorganizationObserved'])
        self.assertFalse(value['publicNetworkVerified'])
        self.assertTrue(set(self.client.calls).issubset(security.READ_METHODS))
        self.assertNotIn('supply', json.dumps(value))

    def test_down_metrics_never_invent_height_or_supply(self):
        value = security.metrics({'up': False})
        self.assertIn('vaytria_up 0', value)
        self.assertNotIn('block_height', value)
        self.assertNotIn('supply', value)

    def archive(self, entries=None, duplicate=False):
        data = b'fixture executable bytes, never executed'
        sums = hashlib.sha256(data).hexdigest() + '  bin/fixture\n'
        archive = self.root / 'fixture.zip'
        with zipfile.ZipFile(archive, 'w') as bundle:
            for name, value in entries or [('vaytria/bin/fixture', data), ('vaytria/SHA256SUMS', sums.encode())]:
                bundle.writestr(name, value)
            if duplicate: bundle.writestr('vaytria/bin/fixture', data)
        return archive, hashlib.sha256(archive.read_bytes()).hexdigest()

    def test_archive_verifies_all_files_without_extraction(self):
        archive, digest = self.archive()
        self.assertEqual(verify.verify_archive(archive, digest)['filesVerified'], 1)
        self.assertEqual(list(self.root.iterdir()), [archive])

    def test_archive_requires_independent_matching_hash(self):
        archive, _ = self.archive()
        with self.assertRaises(ValueError): verify.verify_archive(archive, '0' * 64)

    def test_archive_rejects_unsafe_names_unlisted_files_and_duplicates(self):
        for name in ('vaytria/../bad', '/vaytria/bad', 'vaytria\\bad', 'vaytria/C:bad', 'other/file',
                     'vaytria/CON', 'vaytria/trailing.', 'vaytria/trailing '):
            archive, digest = self.archive([(name, b'bad')])
            with self.assertRaises(ValueError): verify.verify_archive(archive, digest)
        archive, digest = self.archive([('vaytria/unlisted', b'bad')])
        with self.assertRaises(ValueError): verify.verify_archive(archive, digest)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            archive, digest = self.archive(duplicate=True)
        with self.assertRaises(ValueError): verify.verify_archive(archive, digest)

    def test_provenance_pins_repo_workflow_commit_and_runner(self):
        with patch.object(subprocess, 'run') as run:
            verify.verify_provenance(self.root / 'fixture.zip', 'a' * 40, 'security.yml')
        command = run.call_args.args[0]
        self.assertIn('--deny-self-hosted-runners', command)
        self.assertIn('a' * 40, command)
        self.assertIn('ghostbuilder/vaytria-core/.github/workflows/security.yml', command)
        self.assertTrue(run.call_args.kwargs['check'])


if __name__ == '__main__': unittest.main()
