# Security tooling and limits

Vaytria remains experimental. This tooling reduces specific wallet and release
risks; it is not an independent audit, insurance, or protection against a weak
proof-of-work network. No consensus, issuance or founder-allocation rules change.
No existing wallet is migrated automatically. Never send private keys, wallet
files, passphrases or recovery material to the website, repository or maintainers.

## Verify before executing a download

The security toolkit has GitHub/Sigstore build provenance. It authenticates the
workflow and source commit that produced the file, not the safety of the code.
The repository and workflow remain trust dependencies. Review the source and
obtain the expected hash and commit through an independently trusted channel.
With Python 3 and GitHub CLI installed, run the verifier from reviewed source:

```
python verify-release.py ARCHIVE.zip --sha256 EXPECTED_SHA256 --source-commit FULL_COMMIT --workflow security.yml
```

It checks the archive digest, every internal file, unsafe paths and duplicates,
then requires authenticated provenance from this repository and workflow on a
GitHub-hosted runner. It neither extracts nor executes archive contents. A hash
inside the same compromised download is not publisher authentication.

The old v0.1.2 coin packages have checksums but no new provenance attestation.
Their explicit `--integrity-only` verification must not be described as signed
release verification. Adding this workflow does not retroactively attest them.
Reproducible compilation and independent matching builds remain future work.

## Offline signing

Use the toolkit on a physically disconnected, trusted signing computer. The
tool's networking check verifies the local node setting, not the computer's
actual network isolation. Start that node with `-networkactive=0`, no public RPC,
and its own encrypted signing wallet. Keep encrypted recovery backups separate.
The connected computer should have a watch-only wallet without private keys.

Copy an unsigned base64 PSBT from the watch-only computer using removable media.
PSBT files can disclose financial and key-derivation metadata; keep them private.
The signer does not start nodes, create keys, export private keys or broadcast.

```
python security.py --datadir SIGNER_DATA --wallet SIGNER_WALLET inspect-psbt unsigned.psbt
python security.py --datadir SIGNER_DATA --wallet SIGNER_WALLET sign-psbt unsigned.psbt --out signed.psbt
```

On Windows, `vaytria-security.exe` replaces `python security.py`.
Check the destination address with the recipient through a trusted channel.
Verify EVERY output, including change, and the absolute fee. Type the displayed
review fingerprint to approve. The passphrase is prompted locally, never passed
on the command line. Missing prevout information, unsupported outputs, other
signature-hash modes, an unencrypted/unlocked wallet, active peer networking or
an existing output file cause refusal. A 30-second unlock is always followed by
a relock attempt. Signing never submits a payment to the network.

The PSBT format itself does not prove which blockchain a transaction belongs to.
The tool verifies the connected local node's Vaytria genesis; that is not proof
of the origin of every input. Use only PSBTs derived from your independently
verified Vaytria wallet and never reuse Bitcoin keys or backups for this coin.

For 2-of-3 storage, generate the three keys independently on separate trusted
signing devices. Put only their public keys in a `wsh(sortedmulti(2,...))`
descriptor on the watch-only node, retaining descriptor/checksum backups. Each
of two signers must independently review and sign the same transaction. Finalize
and broadcast only on the connected computer, after checking the final outputs.
The test fixture uses disposable wallets on one machine for verification; that
is NOT the production arrangement. No claim is made that third-party Bitcoin
wallets or hardware devices support Vaytria without integration and testing.

## Monitoring without wallet access

```
python security.py --datadir NODE_DATA monitor --state status.json --metrics vaytria.prom
```

This is a single observation, not an installed service or recurring task. It
starts no server. Re-running updates the files atomically. A node failure writes
`vaytria_up 0` and retains the last successful state, rather than inventing supply
or block-height values. It compares the last observed tip's chain membership to
detect reorganizations; these can be normal and do not by themselves prove an
attack. Brief events between observations can be missed. An unavailable former
tip alerts as uncertain. Stale timestamps must alert when the observer stops.

Use the included Prometheus rules with a textfile exporter on the SAME trusted
host (Windows exporter or Linux node_exporter), configured separately. No wallet
balances, addresses, cookies, peer IPs or supply claims appear in these files.
The observer's RPC method allowlist restricts its own calls, not the privileges
of a stolen RPC cookie. Prefer a separate wallet-disabled monitoring node; keep
RPC on localhost and protect its cookie/data directory. Do not expose RPC or
mount wallet secrets in a website. Someone must operate the monitoring and
respond to alerts; no external notification or background task is installed.

## Review and ongoing maintenance

Inspect the Vaytria-specific source patch, client, release workflow and dependency
changes. Automated tests are supporting evidence, never an independent review.
Track upstream Bitcoin Core security releases and review applicable fixes.
Maintain independent miners and nodes: no wallet or monitoring tool supplies
Bitcoin's hash power or guarantees resistance to chain reorganizations.
