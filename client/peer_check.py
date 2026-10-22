"""Bounded version/verack/ping check for a public Vaytria node you operate.

One IPv4 connection to the fixed Vaytria P2P port. No RPC, wallets, mining,
transaction relay, address discovery, persistent peer, or other-port probes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import struct
import time

IDENTITY = Path(__file__).resolve().parents[1] / 'network' / 'identity.json'
MAX_PAYLOAD = 65536
MAX_TOTAL = 262144


def sha256d(value):
    return hashlib.sha256(hashlib.sha256(value).digest()).digest()


def frame(magic, command, payload=b''):
    return magic + command.ljust(12, b'\0') + struct.pack('<I', len(payload)) + sha256d(payload)[:4] + payload


def version_payload(host, port, nonce, timestamp):
    remote = struct.pack('<Q', 0) + bytes(10) + b'\xff\xff' + socket.inet_aton(host) + struct.pack('>H', port)
    local = struct.pack('<Q', 0) + bytes(16) + struct.pack('>H', 0)
    agent = b'/VaytriaReachability:0.1/'
    return (struct.pack('<iQq', 70016, 0, timestamp) + remote + local + nonce +
            bytes([len(agent)]) + agent + struct.pack('<i?', 0, False))


def parse_version(payload):
    if len(payload) < 85:
        raise ValueError('Truncated version response')
    size = payload[80]
    if size >= 253 or len(payload) < 85 + size:
        raise ValueError('Invalid user-agent encoding')
    agent = payload[81:81 + size].decode('ascii')
    if not agent.startswith('/Vaytria:'):
        raise ValueError('Unexpected peer software identity')
    return {'peerProtocolVersion': struct.unpack('<i', payload[:4])[0],
            'peerSubversion': agent,
            'peerReportedHeight': struct.unpack('<i', payload[81 + size:85 + size])[0]}


def check_peer(host, identity):
    magic = bytes.fromhex(identity['networkMagic'])
    port = identity['peerPort']
    if magic != bytes.fromhex('a1d7f2c9') or port != 31444:
        raise ValueError('Unexpected Vaytria network identity')
    report = {'checkedAtUTC': datetime.now(timezone.utc).isoformat(),
              'endpointSHA256': hashlib.sha256((host + ':' + str(port)).encode()).hexdigest(),
              'port': port, 'tcpConnected': False, 'versionReceived': False,
              'verackReceived': False, 'pingPongVerified': False,
              'genesisQueried': False, 'persistentPeerEstablished': False,
              'publicNetworkVerified': False, 'walletAccessed': False,
              'nodeStarted': False, 'miningStarted': False}
    deadline = time.monotonic() + 18
    try:
        with socket.create_connection((host, port), timeout=7) as connection:
            report['tcpConnected'] = True

            def send(command, payload=b''):
                connection.sendall(frame(magic, command, payload))

            def read_exact(length):
                result = b''
                while len(result) < length:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('Handshake deadline reached')
                    connection.settimeout(min(remaining, 7))
                    chunk = connection.recv(length - len(result))
                    if not chunk:
                        raise ConnectionError('Connection closed before expected response')
                    result += chunk
                return result

            send(b'version', version_payload(host, port, secrets.token_bytes(8), int(time.time())))
            ping = secrets.token_bytes(8)
            ping_sent = False
            total = 0
            for _ in range(20):
                header = read_exact(24)
                if header[:4] != magic:
                    raise ValueError('Unexpected network magic')
                command = header[4:16].rstrip(b'\0')
                length = struct.unpack('<I', header[16:20])[0]
                total += length
                if length > MAX_PAYLOAD or total > MAX_TOTAL:
                    raise ValueError('Response exceeds handshake size limit')
                payload = read_exact(length)
                if sha256d(payload)[:4] != header[20:24]:
                    raise ValueError('Message checksum mismatch')
                if command == b'version':
                    if report['versionReceived']:
                        raise ValueError('Repeated version response')
                    report.update(parse_version(payload))
                    report.update(versionReceived=True, networkMagicMatched=True)
                    send(b'verack')
                elif command == b'verack':
                    if not report['versionReceived'] or payload:
                        raise ValueError('Invalid verack response')
                    report['verackReceived'] = True
                elif command == b'ping' and len(payload) == 8:
                    send(b'pong', payload)
                elif command == b'pong' and ping_sent and payload == ping:
                    report['pingPongVerified'] = True
                    break
                if report['versionReceived'] and report['verackReceived'] and not ping_sent:
                    send(b'ping', ping)
                    ping_sent = True
            if not report['pingPongVerified']:
                raise TimeoutError('Matching pong response not received')
    except (OSError, ValueError, ConnectionError, TimeoutError) as error:
        report.update(errorType=type(error).__name__, error=str(error).replace(host, '[owner endpoint]'))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='Public IPv4 of a Vaytria node you operate or have permission to test')
    parser.add_argument('--output', default='reports/public-peer.json')
    args = parser.parse_args()
    address = ipaddress.IPv4Address(args.host)
    if not address.is_global:
        parser.error('A public IPv4 address is required')
    report = check_peer(str(address), json.loads(IDENTITY.read_text()))
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['pingPongVerified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
