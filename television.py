import http.client
import json
import os
import socket
import subprocess
import tempfile
import time

from samsungtvws import SamsungTVWS

CONFIG_FILENAME = "tv.json"
TOKEN_FILENAME = "tv_token.txt"
STATUS_PORT = 8001
REMOTE_PORT = 8002
STATUS_PATH = "/api/v2/"
STATUS_TIMEOUT_SECONDS = 2
REMOTE_TIMEOUT_SECONDS = 30
NETWORK_TIMEOUT_SECONDS = 5
WOL_PORTS = (9, 7)
WOL_BURST_COUNT = 10
WOL_BURST_INTERVAL_SECONDS = 0.25
POWER_ON_TIMEOUT_SECONDS = 45
POWER_ON_RETRY_INTERVAL_SECONDS = 3
CLIENT_NAME = "SmartLife"
POWER_KEY = "KEY_POWER"
POWER_STATES = {"on": True, "off": False, "standby": False}


class Television:
    def __init__(self, config_dir):
        self.config_dir = config_dir
        self.token_file = os.path.join(config_dir, TOKEN_FILENAME)
        self.host = None
        self.mac = None
        self.is_on = None
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

    def refresh(self):
        self.is_on = None
        if not self.configured:
            return
        connection = None
        try:
            connection = http.client.HTTPConnection(
                self.host, STATUS_PORT, timeout=STATUS_TIMEOUT_SECONDS
            )
            connection.request("GET", STATUS_PATH)
            response = connection.getresponse()
            if response.status == 200:
                data = json.load(response)
                device = data.get("device", {}) if isinstance(data, dict) else {}
                state = device.get("PowerState") if isinstance(device, dict) else None
                if isinstance(state, str):
                    self.is_on = POWER_STATES.get(state.lower())
        except (OSError, ValueError, http.client.HTTPException):
            pass
        finally:
            if connection is not None:
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
        if not self.configured:
            raise ValueError("Configure the TV host and MAC address in tv.json first")
        if power:
            self.turn_on()
        else:
            self.turn_off()

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
        if self.is_on is None:
            raise OSError("TV power state unavailable; cannot safely send the power key")
        os.makedirs(self.config_dir, exist_ok=True)
        try:
            with open(self.token_file, encoding="utf-8") as handle:
                token = handle.read().strip() or None
        except FileNotFoundError:
            token = None
        with SamsungTVWS(
            host=self.host,
            port=REMOTE_PORT,
            token=token,
            name=CLIENT_NAME,
            timeout=REMOTE_TIMEOUT_SECONDS,
        ) as remote:
            remote.open()
            if remote.token:
                self.save_token(remote.token)
            self.refresh()
            if self.is_on is None:
                raise OSError("TV power state unavailable; cannot safely send the power key")
            if self.is_on:
                remote.send_key(POWER_KEY)

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
