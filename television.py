import http.client
import json
import os
import select
import socket
import subprocess
import tempfile
import threading
import time
from http import HTTPStatus

import websocket
from samsungtvws import SamsungTVWS

CONFIG_FILENAME = "tv.json"
TOKEN_FILENAME = "tv_token.txt"
STATUS_PORT = 8001
REMOTE_PORT = 8002
STATUS_PATH = "/api/v2/"
APPLICATIONS_PATH = "/api/v2/applications/"
STATUS_TIMEOUT_SECONDS = 2
REMOTE_TIMEOUT_SECONDS = 30
REMOTE_KEY_PRESS_DELAY_SECONDS = 0
REMOTE_IDLE_SECONDS = 60
REMOTE_DRAIN_TIMEOUT_SECONDS = 1
NETWORK_TIMEOUT_SECONDS = 5
WOL_PORTS = (9, 7)
WOL_BURST_COUNT = 10
WOL_BURST_INTERVAL_SECONDS = 0.25
POWER_ON_TIMEOUT_SECONDS = 45
POWER_ON_RETRY_INTERVAL_SECONDS = 3
CLIENT_NAME = "SmartLife"
POWER_KEY = "KEY_POWER"
POWER_STATES = {"on": True, "off": False, "standby": False}
REMOTE_ERRORS = (OSError, websocket.WebSocketException)


class Television:
    def __init__(self, config_dir):
        self.config_dir = config_dir
        self.token_file = os.path.join(config_dir, TOKEN_FILENAME)
        self.host = None
        self.mac = None
        self.is_on = None
        self.remote = None
        self.remote_used_at = None
        self.remote_lock = threading.Lock()
        try:
            with open(os.path.join(config_dir, CONFIG_FILENAME), encoding="utf-8") as handle:
                config = json.load(handle)
            if not isinstance(config, dict):
                return
            host = config.get("host")
            mac = config.get("mac")
            if not isinstance(host, str) or not host.strip() or not isinstance(mac, str):
                return
            mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", ""))
            if len(mac_bytes) != 6:
                return
            self.host = host.strip()
            self.mac = mac_bytes
        except (OSError, ValueError):
            return

    @property
    def configured(self):
        return self.host is not None and self.mac is not None

    @property
    def remote_open(self):
        return self.remote is not None

    def require_configuration(self):
        if not self.configured:
            raise ValueError("Configure the TV host and MAC address in tv.json first")

    def require_known_power_state(self):
        if self.is_on is None:
            raise OSError("TV power state unavailable; cannot safely send the power key")

    def refresh(self):
        self.is_on = None
        if not self.configured:
            return
        try:
            status, body = self.fetch_status(STATUS_PATH)
            if status == HTTPStatus.OK:
                data = json.loads(body)
                device = data.get("device", {}) if isinstance(data, dict) else {}
                state = device.get("PowerState") if isinstance(device, dict) else None
                if isinstance(state, str):
                    self.is_on = POWER_STATES.get(state.lower())
        except (OSError, ValueError, http.client.HTTPException):
            pass

    def fetch_status(self, path):
        connection = http.client.HTTPConnection(self.host, STATUS_PORT, timeout=STATUS_TIMEOUT_SECONDS)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def lan_addresses(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect((self.host, WOL_PORTS[0]))
            source_ip = connection.getsockname()[0]
        interfaces = json.loads(subprocess.check_output(
            ["ip", "-j", "-4", "address", "show"],
            text=True,
            timeout=NETWORK_TIMEOUT_SECONDS,
        ))
        for interface in interfaces:
            if "BROADCAST" not in interface.get("flags", []):
                continue
            for address in interface.get("addr_info", []):
                if address.get("local") == source_ip and address.get("broadcast"):
                    return source_ip, address["broadcast"]
        raise OSError("No LAN broadcast interface found for the TV")

    def set_power(self, power):
        self.require_configuration()
        if power:
            self.turn_on()
        else:
            self.turn_off()

    def toggle_power(self):
        self.require_configuration()
        self.refresh()
        self.set_power(self.is_on is not True)

    def turn_on(self):
        deadline = time.monotonic() + POWER_ON_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            self.wake()
            self.refresh()
            if self.is_on is True:
                return
            remaining = max(0, deadline - time.monotonic())
            time.sleep(min(POWER_ON_RETRY_INTERVAL_SECONDS, remaining))
        raise TimeoutError("TV power-on was not confirmed after Wake-on-LAN")

    def wake(self):
        source_ip, broadcast = self.lan_addresses()
        packet = b"\xff" * 6 + self.mac * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            connection.bind((source_ip, 0))
            for index in range(WOL_BURST_COUNT):
                for port in WOL_PORTS:
                    connection.sendto(packet, (broadcast, port))
                if index < WOL_BURST_COUNT - 1:
                    time.sleep(WOL_BURST_INTERVAL_SECONDS)

    def turn_off(self):
        self.refresh()
        if self.is_on is False:
            return
        self.require_known_power_state()
        with self.connect_remote() as remote:
            self.refresh()
            self.require_known_power_state()
            if self.is_on:
                remote.send_key(POWER_KEY)

    def send_key(self, key):
        self.use_remote(lambda remote: remote.send_key(key, key_press_delay=REMOTE_KEY_PRESS_DELAY_SECONDS))

    def launch_app(self, app_id, name):
        self.require_configuration()
        status, _ = self.fetch_status(APPLICATIONS_PATH + app_id)
        if status == HTTPStatus.NOT_FOUND:
            raise LookupError(f"{name} is not installed on the TV")
        self.use_remote(lambda remote: remote.run_app(app_id))

    def use_remote(self, command):
        self.require_configuration()
        with self.remote_lock:
            if self.remote is not None and self.remote_reusable():
                try:
                    self.run(self.remote, command)
                    return
                except REMOTE_ERRORS:
                    pass
            self.discard_remote()
            remote = self.connect_remote()
            try:
                self.run(remote, command)
            except BaseException:
                remote.close()
                raise
            self.remote = remote

    def run(self, remote, command):
        command(remote)
        self.remote_used_at = time.monotonic()

    def remote_reusable(self):
        if time.monotonic() - self.remote_used_at > REMOTE_IDLE_SECONDS:
            return False
        connection = self.remote.connection
        if connection is None or not connection.connected:
            return False
        timeout = connection.gettimeout()
        connection.settimeout(REMOTE_DRAIN_TIMEOUT_SECONDS)
        try:
            while select.select([connection.sock], [], [], 0)[0] or connection.sock.pending():
                opcode, _ = connection.recv_data_frame(control_frame=True)
                if opcode == websocket.ABNF.OPCODE_CLOSE:
                    return False
        except REMOTE_ERRORS:
            return False
        finally:
            connection.settimeout(timeout)
        return True

    def close_remote(self):
        with self.remote_lock:
            self.discard_remote()

    def discard_remote(self):
        remote, self.remote = self.remote, None
        if remote is None:
            return
        try:
            remote.close()
        except REMOTE_ERRORS:
            pass

    def connect_remote(self):
        os.makedirs(self.config_dir, exist_ok=True)
        remote = SamsungTVWS(
            host=self.host,
            port=REMOTE_PORT,
            token=self.load_token(),
            name=CLIENT_NAME,
            timeout=REMOTE_TIMEOUT_SECONDS,
        )
        try:
            remote.open()
            if remote.token:
                self.save_token(remote.token)
        except BaseException:
            remote.close()
            raise
        return remote

    def load_token(self):
        try:
            with open(self.token_file, encoding="utf-8") as handle:
                return handle.read().strip() or None
        except FileNotFoundError:
            return None

    def save_token(self, token):
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.config_dir,
                prefix=TOKEN_FILENAME + ".", delete=False,
            ) as handle:
                temporary_path = handle.name
                handle.write(token)
            os.replace(temporary_path, self.token_file)
        finally:
            if temporary_path is not None and os.path.exists(temporary_path):
                os.unlink(temporary_path)
