"""Normal offline/multisig payment checks using disposable regtest wallets only."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client'))
import security
from vaytria import Client, RPCError


def run(miner, buyer, secret):
    checks = []
    signers, pubkeys = [], []
    for number in range(3):
        name = 'offline-fixture-' + str(number)
        miner.rpc('createwallet', {'wallet_name': name, 'passphrase': secret, 'descriptors': True})
        signer = Client(miner.datadir, miner.port, miner.chain, miner.expected_genesis, name)
        signers.append(signer)
        address = signer.rpc('getnewaddress', wallet=True)
        pubkeys.append(signer.rpc('getaddressinfo', [address], wallet=True)['pubkey'])
    descriptor = miner.rpc('getdescriptorinfo', ['wsh(sortedmulti(2,' + ','.join(pubkeys) + '))'])['descriptor']
    address = miner.rpc('deriveaddresses', [descriptor])[0]
    miner.rpc('createwallet', {'wallet_name': 'watch-fixture', 'disable_private_keys': True, 'descriptors': True})
    watch = Client(miner.datadir, miner.port, miner.chain, miner.expected_genesis, 'watch-fixture')
    assert watch.rpc('importdescriptors', [[{'desc': descriptor, 'timestamp': 'now'}]], wallet=True)[0]['success']
    assert not watch.rpc('getwalletinfo', wallet=True)['private_keys_enabled']
    miner.rpc('walletpassphrase', [secret, 30], wallet=True)
    try:
        miner.rpc('sendtoaddress', [address, '2'], wallet=True)
    finally:
        miner.rpc('walletlock', wallet=True)
    miner.rpc('generatetoaddress', [1, miner.rpc('getnewaddress', wallet=True)])
    destination = buyer.rpc('getnewaddress', wallet=True)
    funded = watch.rpc('walletcreatefundedpsbt', [[], [{destination: 1}], 0,
                       {'includeWatching': True, 'changeAddress': address, 'fee_rate': 2}], wallet=True)
    psbt = watch.rpc('walletprocesspsbt', [funded['psbt'], False, 'ALL', True, False], wallet=True)['psbt']
    assert not watch.rpc('walletprocesspsbt', [psbt, True, 'ALL', True, False], wallet=True)['complete']
    checks.append('watch-only wallet constructs 2-of-3 payment but cannot sign it')
    miner.rpc('setnetworkactive', [False])
    deadline = time.monotonic() + 15
    while miner.rpc('getnetworkinfo')['connections'] and time.monotonic() < deadline:
        time.sleep(0.1)
    assert miner.rpc('getnetworkinfo')['connections'] == 0
    original = security.getpass.getpass
    try:
        security.getpass.getpass = lambda *args: secret
        with tempfile.TemporaryDirectory(prefix='vaytria-signing-check-') as temporary:
            first = Path(temporary) / 'first.psbt'
            reviewed = security.review_psbt(signers[0], psbt)
            security.sign_psbt(signers[0], psbt, first, reviewed['reviewSHA256'])
            assert signers[0].rpc('getwalletinfo', wallet=True)['unlocked_until'] == 0
            one = security.read_psbt(first)
            assert not miner.rpc('finalizepsbt', [one])['complete']
            checks.append('one offline key cannot complete a 2-of-3 spend; signing wallet relocked')
            second = Path(temporary) / 'second.psbt'
            reviewed = security.review_psbt(signers[1], one)
            security.sign_psbt(signers[1], one, second, reviewed['reviewSHA256'])
            assert signers[1].rpc('getwalletinfo', wallet=True)['unlocked_until'] == 0
            finalized = miner.rpc('finalizepsbt', [security.read_psbt(second)])
            assert finalized['complete']
            assert miner.rpc('getrawmempool') == [], 'Offline signing must not broadcast.'
            checks.append('two offline keys complete the payment without broadcasting or unlocking permanently')
    finally:
        security.getpass.getpass = original
        miner.rpc('setnetworkactive', [True])
    # Broadcast the voluntarily signed fixture on regtest only.
    if miner.chain != 'regtest':
        raise RuntimeError('Integration checks must never broadcast on a live network.')
    assert miner.rpc('testmempoolaccept', [[finalized['hex']]])[0]['allowed']
    miner.rpc('sendrawtransaction', [finalized['hex']])
    miner.rpc('generatetoaddress', [1, miner.rpc('getnewaddress', wallet=True)])
    observed = security.snapshot(miner)
    assert observed['up'] and not observed['publicNetworkVerified']
    assert 'wallet' not in str(observed).lower().replace(observed['scope'].lower(), '')
    checks.append('valid multisig fixture accepted and confirmed; monitoring exports no wallet data')
    return checks
