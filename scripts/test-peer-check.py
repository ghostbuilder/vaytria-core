"""Offline response-fixture checks; no external connection or coin daemon."""
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('peer_check', Path(__file__).resolve().parents[1] / 'client/peer_check.py')
peer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(peer)
MAGIC = bytes.fromhex('a1d7f2c9')
IDENTITY = {'networkMagic': MAGIC.hex(), 'peerPort': 31444}
NONCE = b'abcdefgh'


def response_version():
    payload = peer.version_payload('127.0.0.1', 31444, NONCE, 100)
    agent = b'/Vaytria:31.1.0/'
    return payload[:80] + bytes([len(agent)]) + agent + struct.pack('<i?', 0, False)


class FakeSocket:
    def __init__(self, responses):
        self.responses = responses
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def settimeout(self, timeout):
        assert timeout <= 7

    def recv(self, count):
        data, self.responses = self.responses[:count], self.responses[count:]
        return data

    def sendall(self, data):
        self.sent.append(data)


class PeerCheckTests(unittest.TestCase):
    def probe(self, responses):
        fake = FakeSocket(responses)
        with patch.object(peer.socket, 'create_connection', return_value=fake) as connect, patch.object(peer.secrets, 'token_bytes', return_value=NONCE):
            result = peer.check_peer('127.0.0.1', IDENTITY)
        connect.assert_called_once_with(('127.0.0.1', 31444), timeout=7)
        return result, fake

    def test_normal_handshake_requires_matching_pong(self):
        responses = (peer.frame(MAGIC, b'version', response_version()) +
                     peer.frame(MAGIC, b'verack') + peer.frame(MAGIC, b'pong', NONCE))
        result, fake = self.probe(responses)
        self.assertTrue(result['pingPongVerified'])
        self.assertEqual([packet[4:16].rstrip(b'\0') for packet in fake.sent], [b'version', b'verack', b'ping'])
        self.assertFalse(result['publicNetworkVerified'])

    def test_wrong_network_magic_rejected(self):
        result, _ = self.probe(peer.frame(bytes(4), b'version', response_version()))
        self.assertIn('network magic', result['error'])
        self.assertFalse(result['pingPongVerified'])

    def test_bad_checksum_rejected(self):
        response = bytearray(peer.frame(MAGIC, b'version', response_version()))
        response[20] ^= 1
        result, _ = self.probe(bytes(response))
        self.assertIn('checksum', result['error'])

    def test_oversized_payload_rejected_before_read(self):
        response = MAGIC + b'version'.ljust(12, b'\0') + struct.pack('<I', 65537) + bytes(4)
        result, _ = self.probe(response)
        self.assertIn('size limit', result['error'])

    def test_closed_connection_is_not_success(self):
        result, _ = self.probe(b'')
        self.assertTrue(result['tcpConnected'])
        self.assertFalse(result['versionReceived'])

    def test_wrong_pong_does_not_qualify(self):
        responses = (peer.frame(MAGIC, b'version', response_version()) +
                     peer.frame(MAGIC, b'verack') + peer.frame(MAGIC, b'pong', b'xxxxxxxx'))
        result, _ = self.probe(responses)
        self.assertFalse(result['pingPongVerified'])

    def workflow_snippet(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/public-peer-check.yml').read_text()
        self.assertNotIn('VAYTRIA_CHECK_HOST:', workflow)
        section = workflow.split('- name: One normal handshake', 1)[1].split('- name: Record limited scope', 1)[0]
        return textwrap.dedent(section.split("python - <<'PY'", 1)[1].split('\n          PY', 1)[0])

    def test_workflow_masks_target_before_starting_check(self):
        snippet = self.workflow_snippet()
        output = io.StringIO()

        def fake_run(arguments):
            self.assertEqual(output.getvalue(), '::add-mask::203.0.113.10\n')
            self.assertEqual(arguments[-2:], ['--host', '203.0.113.10'])
            return SimpleNamespace(returncode=0)

        with patch.dict(os.environ, {'GITHUB_EVENT_PATH': 'offline-fixture.json'}), patch.object(Path, 'read_text', return_value=json.dumps({'inputs': {'host': '203.0.113.10'}})), patch.object(subprocess, 'run', side_effect=fake_run) as run, patch('sys.stdout', output):
            with self.assertRaises(SystemExit) as result:
                exec(compile(snippet, '<workflow-fixture>', 'exec'), {})
        self.assertEqual(result.exception.code, 0)
        run.assert_called_once()

    def test_workflow_masks_and_rejects_invalid_input_without_connection(self):
        snippet = self.workflow_snippet()
        supplied = 'not-an-ip\n::notice::example%value'
        output = io.StringIO()
        with patch.dict(os.environ, {'GITHUB_EVENT_PATH': 'offline-fixture.json'}), patch.object(Path, 'read_text', return_value=json.dumps({'inputs': {'host': supplied}})), patch.object(subprocess, 'run') as run, patch('sys.stdout', output):
            with self.assertRaises(SystemExit) as result:
                exec(compile(snippet, '<workflow-fixture>', 'exec'), {})
        self.assertEqual(result.exception.code, 'A public IPv4 address is required')
        self.assertEqual(output.getvalue(), '::add-mask::not-an-ip%0A::notice::example%25value\n')
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
