import http.client
import json
import socket
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ElementTree
from unittest.mock import Mock, patch

import tv_remote_server as server_module
from PIL import Image

from remote_keypad import KEYPAD
from remote_layout import PANEL_ACTION, POWER_ACTION, REMOTE_LAYOUT
import remote_skin
from remote_skin import REMOTE_SKIN, SKIN_HEIGHT, SKIN_WIDTH

LOCALHOST = "127.0.0.1"
JSON_HEADERS = {"Content-Type": "application/json"}


class RemoteServerTests(unittest.TestCase):
    def setUp(self):
        self.config = tempfile.TemporaryDirectory()
        self.addCleanup(self.config.cleanup)
        self.tv = Mock()
        self.tv.is_on = True
        self.tv.config_dir = self.config.name
        self.skin_path = f"{self.config.name}/remote-skin.png"
        skin = patch.object(remote_skin, "SKIN_FILE", self.skin_path)
        skin.start()
        self.addCleanup(skin.stop)
        self.server = server_module.RemoteServer((LOCALHOST, 0), self.tv, ["remote.lan"])
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, args=(0.01,), daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        logger = patch.object(server_module.RemoteRequestHandler, "log_message")
        self.log_message = logger.start()
        self.addCleanup(logger.stop)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, method, path, body=None, headers=None, host=None):
        connection = http.client.HTTPConnection(LOCALHOST, self.port, timeout=5)
        self.addCleanup(connection.close)
        connection.putrequest(method, path, skip_host=True)
        connection.putheader("Host", host or f"{LOCALHOST}:{self.port}")
        for name, value in (headers or {}).items():
            connection.putheader(name, value)
        payload = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else b"")
        if method == "POST":
            connection.putheader("Content-Length", str(len(payload)))
        connection.endheaders(payload if method == "POST" else None)
        response = connection.getresponse()
        return response, response.read()

    def post(self, path, body, headers=JSON_HEADERS, host=None):
        return self.request("POST", path, body, headers, host)

    def test_page_and_assets_are_served_with_a_strict_policy(self):
        for path, content_type, marker in (
            ("/", "text/html; charset=utf-8", b'src="/remote.js"'),
            ("/remote.css", "text/css; charset=utf-8", b".pad"),
            ("/remote.js", "text/javascript; charset=utf-8", b"/api/key"),
            ("/icon.svg", "image/svg+xml", b"<svg"),
        ):
            with self.subTest(path=path):
                response, body = self.request("GET", path)
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Content-Type"), content_type)
                self.assertIn("default-src 'self'", response.getheader("Content-Security-Policy"))
                self.assertIn("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))
                self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
                self.assertIn(marker, body)

    def test_unknown_and_traversal_paths_are_not_found(self):
        for path in ("/missing", "/../television.py", "/web/remote.html", "/tv_token.txt"):
            with self.subTest(path=path):
                response, _ = self.request("GET", path)
                self.assertEqual(response.status, 404)

    def test_layout_and_live_state(self):
        response, body = self.request("GET", "/api/layout")
        self.assertEqual(json.loads(body), json.loads(json.dumps({
            "layout": REMOTE_LAYOUT,
            "power": POWER_ACTION,
            "panel": PANEL_ACTION,
            "skin": None,
            "keypad": None,
        })))
        self.tv.refresh.side_effect = lambda: setattr(self.tv, "is_on", None)
        response, body = self.request("GET", "/api/state?ignored=1")
        self.assertEqual(json.loads(body), {"on": None})
        self.tv.refresh.assert_called_once_with()

    def test_known_key_is_sent(self):
        response, body = self.post("/api/key", {"key": "KEY_VOLUP"})
        self.assertEqual((response.status, body), (204, b""))
        self.tv.send_key.assert_called_once_with("KEY_VOLUP")
        self.log_message.assert_not_called()

    def test_power_and_unknown_keys_are_refused(self):
        for key in ("KEY_POWER", POWER_ACTION, "KEY_FACTORY", None, 12):
            with self.subTest(key=key):
                response, body = self.post("/api/key", {"key": key})
                self.assertEqual(response.status, 400)
                self.assertEqual(json.loads(body), {"error": "Unknown key"})
        self.tv.send_key.assert_not_called()
        self.log_message.assert_called()

    def test_malformed_bodies_are_refused(self):
        cases = (
            (b"not json", JSON_HEADERS, 400),
            (b"[]", JSON_HEADERS, 400),
            (b"", JSON_HEADERS, 400),
            (b"{" + b" " * server_module.MAX_BODY_BYTES + b"}", JSON_HEADERS, 400),
            (b'{"key": "KEY_UP"}', {"Content-Type": "text/plain"}, 415),
            (b'{"key": "KEY_UP"}', {}, 415),
        )
        for body, headers, status in cases:
            with self.subTest(body=body[:20], headers=headers):
                response, _ = self.post("/api/key", body, headers)
                self.assertEqual(response.status, status)
        self.tv.send_key.assert_not_called()

    def test_cross_site_requests_are_refused(self):
        response, _ = self.post("/api/key", {"key": "KEY_UP"}, {**JSON_HEADERS, "Origin": "http://evil.example"})
        self.assertEqual(response.status, 403)
        response, _ = self.post("/api/key", {"key": "KEY_UP"}, host="evil.example:8095")
        self.assertEqual(response.status, 403)
        response, _ = self.request("GET", "/api/state", host="evil.example")
        self.assertEqual(response.status, 403)
        response, _ = self.request("GET", "/", host="[bad")
        self.assertEqual(response.status, 403)
        self.tv.send_key.assert_not_called()
        self.tv.refresh.assert_not_called()

    def test_same_origin_ip_and_allowed_names_are_accepted(self):
        origin = f"http://{LOCALHOST}:{self.port}"
        response, _ = self.post("/api/key", {"key": "KEY_UP"}, {**JSON_HEADERS, "Origin": origin})
        self.assertEqual(response.status, 204)
        response, _ = self.post(
            "/api/key", {"key": "KEY_DOWN"},
            {**JSON_HEADERS, "Origin": "http://remote.lan:8095"}, host="remote.lan:8095",
        )
        self.assertEqual(response.status, 204)
        response, _ = self.request("GET", "/", host="[::1]:8095")
        self.assertEqual(response.status, 200)
        self.assertEqual(self.tv.send_key.call_count, 2)

    def test_tv_failure_is_reported_to_the_page(self):
        self.tv.send_key.side_effect = OSError("No route to host")
        response, body = self.post("/api/key", {"key": "KEY_UP"})
        self.assertEqual(response.status, 502)
        self.assertEqual(json.loads(body), {"error": "No route to host"})
        self.tv.send_key.side_effect = TimeoutError()
        response, body = self.post("/api/key", {"key": "KEY_UP"})
        self.assertEqual(json.loads(body), {"error": "TimeoutError"})

    def test_power_toggles_and_returns_the_new_state(self):
        self.tv.refresh.side_effect = lambda: setattr(self.tv, "is_on", False)
        response, body = self.post("/api/power", {})
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(body), {"on": False})
        self.tv.toggle_power.assert_called_once_with()

    def test_concurrent_power_commands_are_refused(self):
        started = threading.Event()
        release = threading.Event()

        def slow_toggle():
            started.set()
            release.wait(5)

        self.tv.toggle_power.side_effect = slow_toggle
        results = []
        worker = threading.Thread(target=lambda: results.append(self.post("/api/power", {})))
        worker.start()
        try:
            self.assertTrue(started.wait(2))
            response, body = self.post("/api/power", {})
            self.assertEqual(response.status, 409)
        finally:
            release.set()
            worker.join(5)
        self.assertEqual(results[0][0].status, 200)
        self.tv.toggle_power.side_effect = OSError("TV power state unavailable")
        response, body = self.post("/api/power", {})
        self.assertEqual((response.status, json.loads(body)), (502, {"error": "TV power state unavailable"}))
        self.tv.toggle_power.side_effect = None
        response, _ = self.post("/api/power", {})
        self.assertEqual(response.status, 200)

    def test_photo_is_offered_only_when_usable(self):
        skin_path = self.skin_path
        response, _ = self.request("GET", "/remote-skin.png")
        self.assertEqual(response.status, 404)
        Image.new("RGBA", (SKIN_WIDTH, SKIN_HEIGHT)).save(skin_path, "PNG")
        response, body = self.request("GET", "/remote-skin.png")
        self.assertEqual((response.status, response.getheader("Content-Type")), (200, "image/png"))
        self.assertTrue(body.startswith(b"\x89PNG"))
        response, body = self.request("GET", "/api/layout")
        layout = json.loads(body)
        self.assertEqual(layout["skin"], json.loads(json.dumps(REMOTE_SKIN.web("/remote-skin.png"))))
        self.assertEqual(layout["keypad"], json.loads(json.dumps(KEYPAD.web("/remote-keypad.svg"))))
        Image.new("RGBA", (SKIN_WIDTH, SKIN_HEIGHT + 1)).save(skin_path, "PNG")
        response, body = self.request("GET", "/api/layout")
        self.assertIsNone(json.loads(body)["skin"])
        self.assertIsNone(json.loads(body)["keypad"])
        response, _ = self.request("GET", "/remote-skin.png")
        self.assertEqual(response.status, 404)

    def test_keypad_drawing_is_served_as_svg(self):
        response, body = self.request("GET", "/remote-keypad.svg")
        self.assertEqual((response.status, response.getheader("Content-Type")), (200, "image/svg+xml"))
        self.assertEqual(ElementTree.fromstring(body).tag, "{http://www.w3.org/2000/svg}svg")

    def test_unknown_post_path_is_not_found(self):
        response, _ = self.post("/api/other", {})
        self.assertEqual(response.status, 404)


class RemoteServerStartupTests(unittest.TestCase):
    def test_ipv6_bind_is_supported(self):
        if not socket.has_ipv6:
            self.skipTest("IPv6 unavailable")
        try:
            server = server_module.RemoteServer(("::1", 0), Mock(), [])
        except OSError as ex:
            self.skipTest(f"IPv6 loopback unavailable: {ex}")
        self.addCleanup(server.server_close)
        self.assertEqual(server.address_family, socket.AF_INET6)

    def test_unconfigured_tv_and_host_names_are_refused_at_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            for argv in (["tv_remote_server.py"], ["tv_remote_server.py", "--bind", "tv.lan"]):
                with self.subTest(argv=argv):
                    with (
                        patch.object(server_module, "CONFIG_DIR", directory),
                        patch("sys.argv", argv),
                        patch("sys.stderr"),
                    ):
                        with self.assertRaises(SystemExit) as raised:
                            server_module.main()
                    self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
