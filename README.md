# Vaytria Core — experimental community software

An independent SHA-256d network derived from Bitcoin Core v31.1. MIT licensed.
Zero premine and no founder allocation. There is no founder fee, privileged
mining address, customer custody, sale, established price or promised return.

This is a public **software release**, not a claim that an independently hosted
public network, market or exchange listing already exists. No verified public
bootstrap peer is supplied. The original publisher does not undertake to host
nodes, provide support, maintain the software, or operate an exchange. Independent
volunteers may fork, audit, build and run it under the license.

## Downloads and participation

- [Releases](https://github.com/ghostbuilder/vaytria-core/releases): publishable
  binaries are attached only after their automated build and checks pass.
- [Build from source](BUILD.md): pinned upstream source plus the included patch.
- [Run a node or mine](RUNNING.md): local wallet, public relay and CPU mining.
- [Community handoff](HANDOFF.md): public peer coordination and maintenance.
- [Website](https://vaytria.com/participate.html).

Windows packages use native executables; WSL is not required. The packaged menu
client includes its Python runtime. Linux users need Python 3. A build in progress
or a missing release asset is not a qualified downloadable release.

## Network identity

- Genesis: `00000000c59f648b04817dd53eb907d6ab78dfef3cf35a6c4e4bbca3cac3af22`
- P2P TCP 31444; wallet RPC TCP 31443 stays local.
- Addresses: `vtr1`; this is neither Bitcoin nor the older `vay1` preview.
- Initial subsidy: 50 coins; 210,000-block halvings; eight decimal places;
  approximately 21-million maximum issuance; 100-block coinbase maturity.
- Target: 600 seconds; difficulty retarget every 2016 blocks. The target is not
  a guarantee of actual launch timing or miner profitability.
- Modern transaction rules activate from block 1. Bitcoin historical activation
  dates and Bitcoin's network/security history are not inherited.

Old private chains and test rewards are excluded. The genesis reward is
unspendable. The publisher has not mined reward blocks on this fresh identity.
The published software is permissionless: its operational mining checks are not
consensus restrictions and cannot prevent isolated forks or modified clients.

## Important limits

The client does not require permission or a founder launch file. It verifies
the chain identity and refuses mining without a connected public IP peer.
An IP peer is not a security audit or proof of an honest, decentralized network.
Participants must independently verify the chain they join. Community operators
must coordinate bootstrap addresses openly; none are invented or bundled here.

Mining spends CPU and electricity and may earn nothing. Node operation earns
no automatic reward. Small/new proof-of-work networks can be reorganized and
are not protected by Bitcoin's hash power. No money should be sent to this
project to obtain coins, listing access, hosting or mining allocations.

Bitcoin Core developer and contributor copyright/license notices are retained.
Vaytria-specific tooling is provided under the same MIT terms. Use the project
discussions for Vaytria coordination; do not report its modifications to Bitcoin
Core as though they were upstream Bitcoin software.
