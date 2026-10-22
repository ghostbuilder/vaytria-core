# Host an independent Vaytria node

Vaytria is public experimental software. We are looking for independent
operators willing to host the first community bootstrap nodes. No currently
listed, persistent community peer is supplied by the project. There is no
registration, founder approval, hosting payment to the project or founder fee.

Use a computer or server you already operate. You cover its electricity,
storage and internet. Running a relay alone earns no automatic coins or money.
Do not buy hosting or hardware on the assumption that Vaytria will have value.

## Before starting

1. Download the matching native package from
   [v0.1.2-alpha](https://github.com/ghostbuilder/vaytria-core/releases/tag/v0.1.2-alpha).
   Check its archive SHA-256 against the matching release checksum before
   extracting, and retain the internal manifest and build information.
2. Use a fresh relay data directory, separate from wallets and old preview
   chains. The expected genesis is
   `00000000c59f648b04817dd53eb907d6ab78dfef3cf35a6c4e4bbca3cac3af22`.
3. Review the packaged `relay.conf`. It disables wallets, binds IPv4 P2P to
   `0.0.0.0:31444`, and keeps RPC on `127.0.0.1:31443`.
4. Decide whether you want to make this machine's public P2P address visible.
   A direct public node exposes its public IP to peers. Keep keys and wallets
   off the relay. A DNS name does not hide the underlying IP.

An empty peer list does not prevent the first relay daemon from starting. It
will initially wait at genesis, height zero. Starting that first process does
not establish a synchronized network or earn a mining reward. Miners using the
released client need another connected, verified public-IP peer.

## Native Windows x64

Extract the package and open PowerShell in the directory that contains `bin`
and `relay.conf`. These commands create a new relay directory and copy a
configuration into it; they do not delete or reset existing data.
If that relay directory already contains a configuration, review it and omit
the `Copy-Item` line rather than overwriting your existing settings.

```powershell
New-Item -ItemType Directory -Path "$env:LOCALAPPDATA\Vaytria-Relay-v2" -Force
Copy-Item -LiteralPath '.\relay.conf' -Destination "$env:LOCALAPPDATA\Vaytria-Relay-v2\relay.conf"
.\bin\vaytriad.exe -chain=vaytria -datadir="$env:LOCALAPPDATA\Vaytria-Relay-v2" -conf="$env:LOCALAPPDATA\Vaytria-Relay-v2\relay.conf" -disablewallet=1 -natpmp=0 -printtoconsole=1
```

Keep the daemon console open. If the destination configuration already exists,
review it before copying over it. In a second PowerShell window, from the same
extracted package directory, read the chain identity and peer status:

```powershell
.\bin\vaytria-cli.exe -chain=vaytria -datadir="$env:LOCALAPPDATA\Vaytria-Relay-v2" -conf="$env:LOCALAPPDATA\Vaytria-Relay-v2\relay.conf" -rpcconnect=127.0.0.1 -rpcport=31443 getblockchaininfo
.\bin\vaytria-cli.exe -chain=vaytria -datadir="$env:LOCALAPPDATA\Vaytria-Relay-v2" -conf="$env:LOCALAPPDATA\Vaytria-Relay-v2\relay.conf" -rpcconnect=127.0.0.1 -rpcport=31443 getnetworkinfo
```

For a clean shutdown, use the same CLI options with `stop` in place of
`getnetworkinfo`. Do not simply terminate an arbitrary process or delete data.

## Ubuntu 24.04 x86_64

Extract the Linux package and open a terminal in its directory. Python 3 is
needed for the menu/miner client, but the relay daemon below runs directly.
Minimal servers may also need libevent and SQLite runtime packages. The
published integration environment uses `libevent-dev` and `libsqlite3-0`.
Install any missing OS dependencies through your normal package manager.

```sh
mkdir -p "$HOME/.vaytria-relay-v2"
cp -n relay.conf "$HOME/.vaytria-relay-v2/relay.conf"
./bin/vaytriad -chain=vaytria -datadir="$HOME/.vaytria-relay-v2" -conf="$HOME/.vaytria-relay-v2/relay.conf" -disablewallet=1 -natpmp=0 -printtoconsole=1
```

If the configuration already exists, review it rather than overwriting it.
In another terminal, use `./bin/vaytria-cli` with the same chain, data and
configuration options plus `-rpcconnect=127.0.0.1 -rpcport=31443` and the commands
`getblockchaininfo`, `getnetworkinfo` or `stop`.

## Make only P2P reachable

- Deliberately allow inbound **TCP 31444** for this daemon in the host firewall.
  If a home router is involved, forward only that port to this machine and
  reserve its local address so DHCP changes do not break the rule.
- Keep **RPC 31443 private**, bound to loopback. Do not enable a router DMZ or
  disable firewalls, antivirus, content filters or other security controls.
- Test from outside the local network. A TCP port test proves a listener can
  be reached, not that it speaks the correct protocol or sustains a network.
- Verify a normal Vaytria peer connection and matching chain identity from a
  second node. Then observe accepted block propagation, persistence and restart
  behavior before making reliability claims.

## Let the community find your node

If you choose to publish your P2P endpoint, create a post in
[public Discussions](https://github.com/ghostbuilder/vaytria-core/discussions).
Include only the information you intend to make public:

```text
I volunteer to operate a Vaytria node.
P2P endpoint: MY_OPT_IN_PUBLIC_ADDRESS:31444
Software version: 0.1.2-alpha
Genesis: 00000000c59f648b04817dd53eb907d6ab78dfef3cf35a6c4e4bbca3cac3af22
Expected availability: [your actual availability]
Outside connection test: [what was tested and when]
```

Never post RPC cookies, authentication credentials, private keys, wallet backups,
recovery material, device serial numbers or personal information you want hidden.
An operator's address is not proof of honesty, security or decentralization.

## Miners and privacy

Once independently reachable peers exist, participants can follow
[RUNNING.md](RUNNING.md) to use the released client with their own receiving
addresses. No founder allocation is reserved. The client refuses isolated
main-chain reward mining; do not remove that guard to manufacture a launch claim.
Keep personal wallets on a separate secured machine. The default wallet/miner
and relay profiles use the same local ports and cannot simply be started
together on the same host without a deliberately separate port configuration.

A miner does not need an inbound public server, but a direct **outbound** peer
connection still reveals its source IP to that peer. If keeping your home IP
private is required, do not start the ordinary direct-connect profile. A
compatible privacy connection must be configured and verified first. Installing
Tor Browser by itself does not route the Vaytria application through Tor. The
released client currently rejects onion-only peers for mining; Tor support in
the underlying daemon is not proof of an end-to-end private mining setup.

There is no public sale, established price, exchange listing, guaranteed reward,
profitability claim, independent audit or promised continuing support. A public
software release does not guarantee that volunteers or a market will appear.
