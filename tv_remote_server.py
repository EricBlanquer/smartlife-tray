#!/usr/bin/env python3

import argparse
import http.server
import ipaddress
import json
import os
import socket
import threading
from http import HTTPStatus
from urllib.parse import urlsplit

from app_paths import CONFIG_DIR
from remote_keypad import KEYPAD, keypad_svg
from remote_layout import PANEL_ACTION, POWER_ACTION, REMOTE_KEYS, REMOTE_LAYOUT
from remote_skin import REMOTE_SKIN, skin_file
from television import CONFIG_FILENAME, Television

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
DEFAULT_BIND = "127.0.0.1"
DEFAULT_PORT = 8095
MAX_BODY_BYTES = 1024
JSON_MEDIA_TYPE = "application/json"
LAYOUT_PATH = "/api/layout"
STATE_PATH = "/api/state"
KEY_PATH = "/api/key"
POWER_PATH = "/api/power"
SKIN_PATH = "/remote-skin.png"
SKIN_CONTENT_TYPE = "image/png"
KEYPAD_PATH = "/remote-keypad.svg"
KEYPAD_CONTENT_TYPE = "image/svg+xml"
KEYPAD_CONTENT = keypad_svg().encode("utf-8")
STATIC_FILES = {
    "/": (os.path.join(WEB_DIR, "remote.html"), "text/html; charset=utf-8"),
    "/remote.css": (os.path.join(WEB_DIR, "remote.css"), "text/css; charset=utf-8"),
    "/remote.js": (os.path.join(WEB_DIR, "remote.js"), "text/javascript; charset=utf-8"),
    "/icon.svg": (os.path.join(BASE_DIR, "icons", "smartlife-tray.svg"), "image/svg+xml"),
}
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class RemoteServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, tv, allowed_hosts):
        self.address_family = (
            socket.AF_INET6 if ipaddress.ip_address(address[0]).version == 6 else socket.AF_INET
        )
        self.tv = tv
        self.allowed_hosts = frozenset(allowed_hosts)
        self.power_lock = threading.Lock()
        super().__init__(address, RemoteRequestHandler)


class RemoteRequestHandler(http.server.BaseHTTPRequestHandler):
    server_version = "TVRemote"
    sys_version = ""

    def do_GET(self):
        if not self.host_allowed():
            self.send_json_error(HTTPStatus.FORBIDDEN, "Host not allowed")
            return
        path = urlsplit(self.path).path
        if path == LAYOUT_PATH:
            self.send_json(HTTPStatus.OK, self.layout())
        elif path == STATE_PATH:
            self.server.tv.refresh()
            self.send_json(HTTPStatus.OK, {"on": self.server.tv.is_on})
        elif path in STATIC_FILES:
            self.send_file(*STATIC_FILES[path])
        elif path == SKIN_PATH:
            self.send_skin()
        elif path == KEYPAD_PATH:
            self.send_body(HTTPStatus.OK, KEYPAD_CONTENT, KEYPAD_CONTENT_TYPE)
        else:
            self.send_json_error(HTTPStatus.NOT_FOUND, "Not found")

    def send_skin(self):
        path = self.skin_path()
        if path is None:
            self.send_json_error(HTTPStatus.NOT_FOUND, "Not found")
        else:
            self.send_file(path, SKIN_CONTENT_TYPE)

    def skin_path(self):
        return skin_file(self.server.tv.config_dir)

    def layout(self):
        photo = self.skin_path() is not None
        return {
            "layout": REMOTE_LAYOUT,
            "power": POWER_ACTION,
            "panel": PANEL_ACTION,
            "skin": REMOTE_SKIN.web(SKIN_PATH) if photo else None,
            "keypad": KEYPAD.web(KEYPAD_PATH) if photo else None,
        }

    def do_POST(self):
        if not self.host_allowed() or not self.origin_allowed():
            self.send_json_error(HTTPStatus.FORBIDDEN, "Cross-site request refused")
            return
        if self.headers.get_content_type() != JSON_MEDIA_TYPE:
            self.send_json_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "JSON body required")
            return
        body = self.read_json()
        if body is None:
            self.send_json_error(HTTPStatus.BAD_REQUEST, "Invalid JSON body")
            return
        path = urlsplit(self.path).path
        if path == KEY_PATH:
            self.send_remote_key(body.get("key"))
        elif path == POWER_PATH:
            self.toggle_power()
        else:
            self.send_json_error(HTTPStatus.NOT_FOUND, "Not found")

    def send_remote_key(self, key):
        if key not in REMOTE_KEYS:
            self.send_json_error(HTTPStatus.BAD_REQUEST, "Unknown key")
            return
        try:
            self.server.tv.send_key(key)
        except Exception as ex:
            self.send_json_error(HTTPStatus.BAD_GATEWAY, str(ex) or type(ex).__name__)
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_common_headers()
        self.end_headers()

    def toggle_power(self):
        if not self.server.power_lock.acquire(blocking=False):
            self.send_json_error(HTTPStatus.CONFLICT, "A power command is already running")
            return
        try:
            self.server.tv.toggle_power()
            self.server.tv.refresh()
        except Exception as ex:
            self.send_json_error(HTTPStatus.BAD_GATEWAY, str(ex) or type(ex).__name__)
            return
        finally:
            self.server.power_lock.release()
        self.send_json(HTTPStatus.OK, {"on": self.server.tv.is_on})

    def host_allowed(self):
        host = self.headers.get("Host")
        if not host:
            return False
        try:
            hostname = urlsplit("//" + host).hostname
        except ValueError:
            return False
        if hostname is None:
            return False
        if hostname in self.server.allowed_hosts:
            return True
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            return False
        return True

    def origin_allowed(self):
        origin = self.headers.get("Origin")
        return origin is None or origin == "http://" + self.headers.get("Host", "")

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return None
        if length <= 0 or length > MAX_BODY_BYTES:
            return None
        try:
            data = json.loads(self.rfile.read(length))
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def send_file(self, path, content_type):
        with open(path, "rb") as handle:
            content = handle.read()
        self.send_body(HTTPStatus.OK, content, content_type)

    def send_json(self, status, payload):
        self.send_body(status, json.dumps(payload).encode("utf-8"), JSON_MEDIA_TYPE)

    def send_json_error(self, status, message):
        self.send_json(status, {"error": message})

    def send_body(self, status, content, content_type):
        self.send_response(status)
        self.send_common_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_common_headers(self):
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)

    def log_request(self, code="-", size="-"):
        if isinstance(code, int) and code >= HTTPStatus.BAD_REQUEST:
            super().log_request(code, size)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Serve a Samsung TV remote control page on the local network."
    )
    parser.add_argument("--bind", default=DEFAULT_BIND, help="IP address to listen on")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port to listen on")
    parser.add_argument(
        "--allowed-host", action="append", default=[],
        help="host name accepted in addition to IP addresses (repeatable)",
    )
    arguments = parser.parse_args()
    try:
        ipaddress.ip_address(arguments.bind)
    except ValueError:
        parser.error("--bind must be an IP address")
    return parser, arguments


def main():
    parser, arguments = parse_arguments()
    tv = Television(CONFIG_DIR)
    if not tv.configured:
        parser.error(f"configure the TV in {os.path.join(CONFIG_DIR, CONFIG_FILENAME)}")
    server = RemoteServer((arguments.bind, arguments.port), tv, arguments.allowed_host)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        tv.close_remote()


if __name__ == "__main__":
    main()
