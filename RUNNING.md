# Run independently

No registration, founder approval or payment to the project is needed. Release
availability does not establish an active public network. The bootstrap peer
list is empty until independent operators publish endpoints.

Want to host the first community relay? Start with
[Host an independent node](FIRST-NODE.md). A relay can start at height zero
without existing peers; mining through the client still needs a connected peer.

## Verify the package

Check the downloaded archive's SHA-256 against the release checksums. Extract
it into a new directory. `SHA256SUMS` inside the archive covers package contents.
Never merge an old preview/private chain into this fresh identity.

## Windows

Extract the native win64 release, then open `Vaytria.cmd` for the local menu.
It includes its Python runtime; WSL and a separate Python installation are not
required. Use the menu to start the node, enter a volunteer public peer, create
an encrypted wallet, obtain an address, back up the wallet and mine.

Command-line alternatives from the extracted directory:

```powershell
.\vaytria.exe start --peer YOUR_VERIFIED_PUBLIC_PEER:31444
.\vaytria.exe create
.\vaytria.exe address
.\vaytria.exe balance
.\vaytria.exe mine YOUR_OWN_RECEIVING_ADDRESS --seconds 1800 --workers 1
.\vaytria.exe stop
```

`YOUR_VERIFIED_PUBLIC_PEER` is a placeholder, not a real peer. Find opt-in
endpoints in the public project discussions and verify them independently.

## Linux wallet/miner

Linux requires Python 3. From the extracted package:

```sh
python3 vaytria.py start --peer YOUR_VERIFIED_PUBLIC_PEER:31444
python3 vaytria.py create
python3 vaytria.py address
python3 vaytria.py balance
python3 vaytria.py mine YOUR_OWN_RECEIVING_ADDRESS --seconds 1800 --workers 1
python3 vaytria.py stop
```

The wallet node binds both RPC and its P2P listener to loopback only. It does
not expose a public inbound P2P port. An ordinary miner need not operate a
publicly listening server.
Its direct outbound connections still reveal the miner's source IP to peers.
If hiding your home IP is required, keep the ordinary profile stopped until a
compatible privacy connection is configured and verified. A loopback listener
alone does not provide IP anonymity.
The mining client requires a connected public IP peer, uses the native block
assembler for transactions/fees and schedules at most four bounded hashing RPCs.
Time limits stop new work and drain in-flight requests. Ctrl+C does the same.

## Public relay

Run the matching daemon with `relay.conf` on a machine that you operate, with
persistent storage and TCP 31444 deliberately reachable. The relay configuration
disables wallets and keeps RPC on 127.0.0.1. Add opt-in peer endpoints through
`addnode=HOST:31444` in its `[vaytria]` section. Publish only your public P2P
endpoint, never RPC credentials. A relay alone receives no automatic reward.

Linux example (review configuration first):

```sh
mkdir -p "$HOME/.vaytria-relay"
cp relay.conf "$HOME/.vaytria-relay/bitcoin.conf"
./bin/vaytriad -datadir="$HOME/.vaytria-relay"
```

Windows uses `bin\vaytriad.exe` with the same `-datadir` and reviewed configuration.
Do not expose wallet RPC, disable OS security tools or assume a firewall is
configured merely because the process starts.

## Wallets, transfers and rewards

Passphrases are prompted locally, not put in arguments or uploaded to a website.
Back up the encrypted wallet to a separate device and keep its passphrase
separately offline. Losing either can make coins inaccessible. The site and
publisher cannot recover or reset private keys. Default data is under the
current user's LocalAppData/Vaytria on Windows or ~/.vaytria-community on Linux.

Mining rewards follow the 100-block maturity rule. Use `transactions` to check
confirmation status. Sending requires an explicit `--confirm` and a local wallet
passphrase; it relocks the wallet after the attempt. If a send fails or times out,
inspect transactions before retrying to avoid paying twice.

No public peer, buyer, market price, reward, stable block interval, security audit
or continuing support is guaranteed. If nobody supplies nodes and mining power,
the network does not sustain itself.
