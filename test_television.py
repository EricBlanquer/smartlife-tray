import io
import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import television


class TelevisionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config_dir = Path(self.directory.name)
        self.config_path = self.config_dir / television.CONFIG_FILENAME
        self.config_path.write_text(json.dumps({
            "host": "192.0.2.10", "mac": "02:11:22:33:44:55",
        }))
        self.tv = television.Television(self.directory.name)

    def test_loads_configuration_without_network_or_token_file_creation(self):
        self.assertTrue(self.tv.configured)
        self.assertEqual(self.tv.host, "192.0.2.10")
        self.assertEqual(self.tv.mac, bytes.fromhex("021122334455"))
        self.assertIsNone(self.tv.is_on)
        self.assertFalse(Path(self.tv.token_file).exists())

    def test_invalid_configuration_is_safe(self):
        for config in (None, [], {}, {"host": 12, "mac": "ab"},
                       {"host": " ", "mac": "02:11:22:33:44:55"},
                       {"host": "tv", "mac": "invalid"}, {"host": "tv", "mac": "ab"}):
            with self.subTest(config=config):
                self.config_path.write_text(json.dumps(config))
                tv = television.Television(self.directory.name)
                self.assertFalse(tv.configured)
                tv.refresh()
                self.assertIsNone(tv.is_on)
                with self.assertRaisesRegex(ValueError, "tv.json"):
                    tv.set_power(True)
        self.config_path.write_text("{")
        self.assertFalse(television.Television(self.directory.name).configured)
        self.config_path.unlink()
        self.assertFalse(television.Television(self.directory.name).configured)

    def test_status_parses_real_power_and_keeps_bad_responses_unknown(self):
        cases = (
            ({"device": {"PowerState": "on"}}, True),
            ({"device": {"PowerState": "standby"}}, False),
            ({"device": {"PowerState": "off"}}, False),
            ({"device": {"PowerState": "unknown"}}, None),
            ({"device": {"PowerState": []}}, None),
            ({"device": []}, None), ([], None), ({}, None),
        )
        for payload, expected in cases:
            with self.subTest(payload=payload):
                response = io.BytesIO(json.dumps(payload).encode())
                response.status = 200
                with patch.object(television.http.client, "HTTPConnection") as connection:
                    connection.return_value.getresponse.return_value = response
                    self.tv.is_on = True
                    self.tv.refresh()
                    connection.return_value.request.assert_called_once_with("GET", "/api/v2/")
                    connection.return_value.close.assert_called_once_with()
                self.assertIs(self.tv.is_on, expected)

    def test_unreachable_tv_is_unknown_rather_than_falsely_off(self):
        self.tv.is_on = True
        with patch.object(television.http.client, "HTTPConnection") as connection:
            connection.return_value.request.side_effect = TimeoutError()
            self.tv.refresh()
            connection.return_value.close.assert_called_once_with()
        self.assertIsNone(self.tv.is_on)

    def test_malformed_host_does_not_break_other_device_refreshes(self):
        self.tv.is_on = True
        with patch.object(television.http.client, "HTTPConnection", side_effect=ValueError("invalid host")):
            self.tv.refresh()
        self.assertIsNone(self.tv.is_on)

    def test_http_failure_and_invalid_json_clear_stale_state(self):
        for status, body in ((503, b"unavailable"), (200, b"invalid json")):
            with self.subTest(status=status):
                response = io.BytesIO(body)
                response.status = status
                self.tv.is_on = True
                with patch.object(television.http.client, "HTTPConnection") as connection:
                    connection.return_value.getresponse.return_value = response
                    self.tv.refresh()
                self.assertIsNone(self.tv.is_on)

    def test_wol_packet_reaches_both_ports_with_correct_mac_and_burst_count(self):
        receivers = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(2)]
        for receiver in receivers:
            self.addCleanup(receiver.close)
            receiver.bind(("127.0.0.1", 0))
            receiver.settimeout(1)
        ports = tuple(receiver.getsockname()[1] for receiver in receivers)
        with (
            patch.object(self.tv, "lan_addresses", return_value=("127.0.0.1", "127.0.0.1")),
            patch.object(self.tv, "refresh", side_effect=lambda: setattr(self.tv, "is_on", True)),
            patch.object(television, "WOL_PORTS", ports),
            patch.object(television, "WOL_BURST_COUNT", 3),
            patch.object(television, "WOL_BURST_INTERVAL_SECONDS", 0),
        ):
            self.tv.set_power(True)
        expected = b"\xff" * 6 + bytes.fromhex("021122334455") * 16
        for receiver in receivers:
            for _ in range(3):
                packet, source = receiver.recvfrom(1024)
                self.assertEqual(packet, expected)
                self.assertEqual(source[0], "127.0.0.1")

    def test_wake_is_retried_until_the_tv_confirms_it_is_on(self):
        states = iter((None, True))
        with (
            patch.object(self.tv, "wake") as wake,
            patch.object(self.tv, "refresh", side_effect=lambda: setattr(self.tv, "is_on", next(states))),
            patch.object(television.time, "sleep"),
        ):
            self.tv.set_power(True)
        self.assertEqual(wake.call_count, 2)
        self.assertIs(self.tv.is_on, True)

    def test_unconfirmed_wake_stops_at_the_deadline(self):
        with (
            patch.object(self.tv, "wake") as wake,
            patch.object(self.tv, "refresh"),
            patch.object(television.time, "monotonic", side_effect=(0, 0, 46, 46)),
            patch.object(television.time, "sleep"),
        ):
            with self.assertRaisesRegex(TimeoutError, "not confirmed"):
                self.tv.set_power(True)
        wake.assert_called_once_with()

    def test_wol_uses_the_routed_interface_and_its_actual_broadcast(self):
        interfaces = [
            {"flags": ["BROADCAST"], "addr_info": [
                {"local": "10.0.0.1", "broadcast": "10.0.0.255"},
            ]},
            {"flags": ["BROADCAST"], "addr_info": [
                {"local": "172.16.2.7", "broadcast": "172.16.3.255"},
            ]},
        ]
        with (
            patch.object(television.socket, "socket") as connection,
            patch.object(television.subprocess, "check_output", return_value=json.dumps(interfaces)),
        ):
            connection.return_value.__enter__.return_value.getsockname.return_value = ("172.16.2.7", 123)
            self.assertEqual(self.tv.lan_addresses(), ("172.16.2.7", "172.16.3.255"))

    def test_wol_refuses_a_route_without_a_broadcast_interface(self):
        with (
            patch.object(television.socket, "socket") as connection,
            patch.object(television.subprocess, "check_output", return_value='[]'),
        ):
            connection.return_value.__enter__.return_value.getsockname.return_value = ("10.0.0.1", 123)
            with self.assertRaisesRegex(OSError, "LAN broadcast"):
                self.tv.set_power(True)
            connection.return_value.__enter__.return_value.sendto.assert_not_called()

    def test_power_off_checks_actual_state_and_pairing_token_stays_private(self):
        token_path = Path(self.tv.token_file)
        token_path.write_text("12345678")
        token_path.chmod(0o644)
        self.tv.is_on = True
        with patch.object(self.tv, "refresh"), patch.object(television, "SamsungTVWS") as remote:
            remote.return_value.__enter__.return_value.token = "12345678"
            self.tv.set_power(False)
            remote.return_value.__enter__.return_value.send_key.assert_called_once_with("KEY_POWER")
            remote.return_value.__exit__.assert_called_once()
        self.assertEqual(token_path.read_text(), "12345678")
        self.assertEqual(token_path.stat().st_mode & 0o777, 0o600)

    def test_first_pairing_creates_private_token_file(self):
        self.tv.is_on = True
        with patch.object(self.tv, "refresh"), patch.object(television, "SamsungTVWS") as remote:
            remote.return_value.__enter__.return_value.token = "12345678"
            self.tv.set_power(False)
            self.assertIsNone(remote.call_args.kwargs["token"])
        self.assertEqual(os.stat(self.tv.token_file).st_mode & 0o777, 0o600)

    def test_failed_pairing_preserves_the_existing_token(self):
        Path(self.tv.token_file).write_text("existing-token")
        self.tv.is_on = True
        with patch.object(self.tv, "refresh"), patch.object(television, "SamsungTVWS") as remote:
            remote.return_value.__enter__.return_value.open.side_effect = TimeoutError()
            with self.assertRaises(TimeoutError):
                self.tv.set_power(False)
            remote.return_value.__enter__.return_value.send_key.assert_not_called()
        self.assertEqual(Path(self.tv.token_file).read_text(), "existing-token")

    def test_off_and_unknown_state_never_send_a_power_toggle(self):
        for state in (False, None):
            with self.subTest(state=state):
                self.tv.is_on = state
                with patch.object(self.tv, "refresh"), patch.object(television, "SamsungTVWS") as remote:
                    if state is None:
                        with self.assertRaisesRegex(OSError, "power state unavailable"):
                            self.tv.set_power(False)
                    else:
                        self.tv.set_power(False)
                    remote.assert_not_called()

    def test_state_is_checked_again_after_pairing_before_any_toggle(self):
        for final_state in (False, None):
            with self.subTest(state=final_state):
                states = iter((True, final_state))
                with (
                    patch.object(self.tv, "refresh", side_effect=lambda: setattr(self.tv, "is_on", next(states))),
                    patch.object(television, "SamsungTVWS") as remote,
                ):
                    remote.return_value.__enter__.return_value.token = "12345678"
                    if final_state is None:
                        with self.assertRaisesRegex(OSError, "power state unavailable"):
                            self.tv.set_power(False)
                    else:
                        self.tv.set_power(False)
                    remote.return_value.__enter__.return_value.send_key.assert_not_called()

    def test_failed_token_write_removes_temporary_file(self):
        with patch.object(television.os, "replace", side_effect=OSError("disk error")):
            with self.assertRaisesRegex(OSError, "disk error"):
                self.tv.save_token("new-token")
        self.assertEqual(list(self.config_dir.iterdir()), [self.config_path])


if __name__ == "__main__":
    unittest.main()
