#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")

from gi.repository import Gtk, GLib
from gi.repository import AyatanaAppIndicator3 as AppIndicator

import hashlib
import json
import os
import socket
import threading
import time

import tinytuya
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

APP_ID = "smartlife-tray"
APP_TITLE = "SmartLife"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEVICES_FILE = os.path.join(BASE_DIR, "devices.json")
ICON_FILE = os.path.join(BASE_DIR, "icons", "smartlife-tray.svg")

UDP_PORT = 6667
UDP_KEY = hashlib.md5(b"yGAdlopoPVldABfn").digest()
UDP_HEADER_LEN = 20
UDP_FOOTER_LEN = 8
DISCOVERY_TIMEOUT = 6.0
DISCOVERY_RECV_TIMEOUT = 1.0
POLL_INTERVAL_SECONDS = 30
SOCKET_TIMEOUT = 5
COMMAND_SETTLE_SECONDS = 0.8

CATEGORY_AC = "kt"
CATEGORY_LIGHT = "dj"

DP_AC_SWITCH = "1"
DP_AC_TEMP_SET = "2"
DP_AC_TEMP_CURRENT = "3"
DP_AC_MODE = "4"
DP_AC_FAN_SPEED = "5"
DP_AC_ECO = "8"
DP_AC_SLEEP = "109"
DP_AC_LOUVRE = "107"

DP_LIGHT_SWITCH = "20"
DP_LIGHT_WORK_MODE = "21"
DP_LIGHT_BRIGHTNESS = "22"
DP_LIGHT_COLOUR_TEMP = "23"

TEMP_SCALE = 10
TEMP_MIN_CELSIUS = 16
TEMP_MAX_CELSIUS = 30

BRIGHTNESS_MIN = 10
BRIGHTNESS_MAX = 1000
BRIGHTNESS_STEP_PERCENT = 10

COLOUR_TEMP_MIN = 0
COLOUR_TEMP_MAX = 1000

WORK_MODE_WHITE = "white"

NBSP = " "
MARK_ON = "●"
MARK_OFF = "○"

AC_MODES = [
    ("cold", "Froid"),
    ("heat", "Chaud"),
    ("auto", "Auto"),
    ("wet", "Déshumidification"),
    ("fan", "Ventilation"),
]

AC_FAN_SPEEDS = [
    ("auto", "Auto"),
    ("mute", "Silencieux"),
    ("low", "Faible"),
    ("low_mid", "Faible +"),
    ("mid", "Moyen"),
    ("mid_high", "Moyen +"),
    ("high", "Fort"),
    ("turbo", "Turbo"),
]

AC_LOUVRE_SWING = "15"
AC_LOUVRE_OFF = "off"

AC_LOUVRE_POSITIONS = [
    ("1", "Position 1"),
    ("2", "Position 2"),
    ("3", "Position 3"),
    ("4", "Position 4"),
    ("5", "Position 5"),
    (AC_LOUVRE_SWING, "Oscillation"),
    (AC_LOUVRE_OFF, "Éteindre"),
]

COLOUR_TEMP_PRESETS = [
    (0, "Blanc chaud"),
    (250, "Chaud"),
    (500, "Neutre"),
    (750, "Froid"),
    (1000, "Lumière du jour"),
]


def decrypt_broadcast(payload):
    decryptor = Cipher(algorithms.AES(UDP_KEY), modes.ECB()).decryptor()
    raw = decryptor.update(payload) + decryptor.finalize()
    return json.loads(raw[: -raw[-1]])


def discover_devices(timeout=DISCOVERY_TIMEOUT):
    found = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", UDP_PORT))
    except OSError:
        sock.close()
        return found
    sock.settimeout(DISCOVERY_RECV_TIMEOUT)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data, _ = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            break
        try:
            info = decrypt_broadcast(data[UDP_HEADER_LEN:-UDP_FOOTER_LEN])
            found[info["gwId"]] = info
        except Exception:
            continue
    sock.close()
    return found


def clamp(value, low, high):
    return max(low, min(high, value))


def format_celsius(celsius):
    return f"{celsius:.0f}{NBSP}°C"


class Device:
    def __init__(self, entry):
        self.id = entry["id"]
        self.name = entry["name"]
        self.key = entry["key"]
        self.category = entry.get("category", "")
        self.product = entry.get("product_name", "")
        self.ip = None
        self.version = None
        self.dps = {}
        self.online = False

    @property
    def is_air_conditioner(self):
        return self.category == CATEGORY_AC

    @property
    def is_light(self):
        return self.category == CATEGORY_LIGHT

    @property
    def switch_dp(self):
        return DP_AC_SWITCH if self.is_air_conditioner else DP_LIGHT_SWITCH

    @property
    def is_on(self):
        return bool(self.dps.get(self.switch_dp))

    def open_connection(self):
        if not self.ip or not self.version:
            return None
        connection = tinytuya.Device(self.id, self.ip, self.key, version=self.version)
        connection.set_socketTimeout(SOCKET_TIMEOUT)
        return connection

    def refresh(self):
        connection = self.open_connection()
        if connection is None:
            self.online = False
            return
        result = connection.status()
        if not isinstance(result, dict) or "dps" not in result:
            self.online = False
            return
        self.dps = result["dps"]
        self.online = True

    def apply(self, dp, value):
        connection = self.open_connection()
        if connection is None:
            return False
        result = connection.set_value(dp, value)
        if isinstance(result, dict) and "dps" in result:
            self.dps.update(result["dps"])
        return not (isinstance(result, dict) and result.get("Error"))

    def temperature_set(self):
        raw = self.dps.get(DP_AC_TEMP_SET)
        return None if raw is None else raw / TEMP_SCALE

    def temperature_current(self):
        raw = self.dps.get(DP_AC_TEMP_CURRENT)
        return None if raw is None else raw / TEMP_SCALE

    def brightness_percent(self):
        raw = self.dps.get(DP_LIGHT_BRIGHTNESS)
        return None if raw is None else round(raw / BRIGHTNESS_MAX * 100)


class TrayApplication:
    def __init__(self):
        self.devices = [Device(entry) for entry in self.load_devices()]
        self.updating_widgets = False
        self.busy = False
        self.indicator = AppIndicator.Indicator.new(
            APP_ID, ICON_FILE, AppIndicator.IndicatorCategory.HARDWARE
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title(APP_TITLE)
        if os.path.exists(ICON_FILE):
            self.indicator.set_icon_full(ICON_FILE, APP_TITLE)
        self.menu = Gtk.Menu()
        self.device_widgets = {}
        self.status_item = None
        self.build_menu()
        self.indicator.set_menu(self.menu)
        self.run_background(self.locate_and_refresh_all)
        GLib.timeout_add_seconds(POLL_INTERVAL_SECONDS, self.on_poll_tick)

    def load_devices(self):
        with open(DEVICES_FILE) as handle:
            return json.load(handle)

    def run_background(self, work):
        thread = threading.Thread(target=work, daemon=True)
        thread.start()

    def locate_devices(self):
        broadcasts = discover_devices()
        for device in self.devices:
            info = broadcasts.get(device.id)
            if info:
                device.ip = info["ip"]
                device.version = float(info["version"])

    def locate_and_refresh_all(self):
        self.set_busy(True)
        self.locate_devices()
        for device in self.devices:
            try:
                device.refresh()
            except Exception:
                device.online = False
        self.set_busy(False)
        GLib.idle_add(self.sync_widgets)

    def refresh_all(self):
        self.set_busy(True)
        missing = [d for d in self.devices if not d.ip]
        if missing:
            self.locate_devices()
        for device in self.devices:
            try:
                device.refresh()
            except Exception:
                device.online = False
        self.set_busy(False)
        GLib.idle_add(self.sync_widgets)

    def set_busy(self, busy):
        self.busy = busy
        GLib.idle_add(self.sync_status_label)

    def on_poll_tick(self):
        if not self.busy:
            self.run_background(self.refresh_all)
        return True

    def build_menu(self):
        for device in self.devices:
            item = Gtk.MenuItem(label=device.name)
            submenu = Gtk.Menu()
            widgets = {"root": item}

            power = Gtk.CheckMenuItem(label="Allumé")
            power.connect("toggled", self.on_power_toggled, device)
            submenu.append(power)
            widgets["power"] = power

            submenu.append(Gtk.SeparatorMenuItem())

            if device.is_air_conditioner:
                self.build_air_conditioner_menu(submenu, widgets, device)
            elif device.is_light:
                self.build_light_menu(submenu, widgets, device)

            item.set_submenu(submenu)
            self.menu.append(item)
            self.device_widgets[device.id] = widgets

        self.menu.append(Gtk.SeparatorMenuItem())

        self.status_item = Gtk.MenuItem(label="")
        self.status_item.set_sensitive(False)
        self.menu.append(self.status_item)

        refresh = Gtk.MenuItem(label="Rafraîchir")
        refresh.connect("activate", self.on_refresh_clicked)
        self.menu.append(refresh)

        quit_item = Gtk.MenuItem(label="Quitter")
        quit_item.connect("activate", self.on_quit_clicked)
        self.menu.append(quit_item)

        self.menu.show_all()

    def build_air_conditioner_menu(self, submenu, widgets, device):
        ambient = Gtk.MenuItem(label="")
        ambient.set_sensitive(False)
        submenu.append(ambient)
        widgets["ambient"] = ambient

        temp_item = Gtk.MenuItem(label="Température")
        temp_menu = Gtk.Menu()
        widgets["temperature"] = {}
        group = []
        for celsius in range(TEMP_MIN_CELSIUS, TEMP_MAX_CELSIUS + 1):
            entry = Gtk.RadioMenuItem.new_with_label(group, format_celsius(celsius))
            group = entry.get_group()
            entry.connect("toggled", self.on_temperature_selected, device, celsius)
            temp_menu.append(entry)
            widgets["temperature"][celsius] = entry
        temp_item.set_submenu(temp_menu)
        submenu.append(temp_item)
        widgets["temperature_root"] = temp_item

        widgets["mode"] = self.build_enum_submenu(
            submenu, "Mode", AC_MODES, self.on_mode_selected, device
        )
        widgets["fan"] = self.build_enum_submenu(
            submenu, "Vitesse", AC_FAN_SPEEDS, self.on_fan_selected, device
        )
        widgets["louvre"] = self.build_enum_submenu(
            submenu, "Panneau", AC_LOUVRE_POSITIONS, self.on_louvre_selected, device
        )

        submenu.append(Gtk.SeparatorMenuItem())

        eco = Gtk.CheckMenuItem(label="Éco")
        eco.connect("toggled", self.on_flag_toggled, device, DP_AC_ECO)
        submenu.append(eco)
        widgets["eco"] = eco

        sleep = Gtk.CheckMenuItem(label="Sommeil")
        sleep.connect("toggled", self.on_flag_toggled, device, DP_AC_SLEEP)
        submenu.append(sleep)
        widgets["sleep"] = sleep

    def build_light_menu(self, submenu, widgets, device):
        bright_item = Gtk.MenuItem(label="Luminosité")
        bright_menu = Gtk.Menu()
        widgets["brightness"] = {}
        group = []
        for percent in range(BRIGHTNESS_STEP_PERCENT, 101, BRIGHTNESS_STEP_PERCENT):
            entry = Gtk.RadioMenuItem.new_with_label(group, f"{percent}{NBSP}%")
            group = entry.get_group()
            entry.connect("toggled", self.on_brightness_selected, device, percent)
            bright_menu.append(entry)
            widgets["brightness"][percent] = entry
        bright_item.set_submenu(bright_menu)
        submenu.append(bright_item)
        widgets["brightness_root"] = bright_item

        widgets["colour_temp"] = self.build_enum_submenu(
            submenu,
            "Température de couleur",
            COLOUR_TEMP_PRESETS,
            self.on_colour_temp_selected,
            device,
        )

    def build_enum_submenu(self, submenu, title, entries, handler, device):
        root = Gtk.MenuItem(label=title)
        menu = Gtk.Menu()
        widgets = {}
        group = []
        for value, label in entries:
            entry = Gtk.RadioMenuItem.new_with_label(group, label)
            group = entry.get_group()
            entry.connect("toggled", handler, device, value)
            menu.append(entry)
            widgets[value] = entry
        root.set_submenu(menu)
        submenu.append(root)
        widgets["__root__"] = root
        return widgets

    def sync_status_label(self):
        if self.status_item is None:
            return False
        offline = [d for d in self.devices if not d.online]
        if self.busy:
            text = "Mise à jour…"
        elif offline:
            text = f"{len(offline)} appareil(s) hors ligne"
        else:
            text = "Tous les appareils sont en ligne"
        self.status_item.set_label(text)
        return False

    def sync_widgets(self):
        self.updating_widgets = True
        for device in self.devices:
            widgets = self.device_widgets[device.id]
            widgets["root"].set_label(self.device_label(device))

            power = widgets["power"]
            power.set_active(device.is_on)
            power.set_sensitive(device.online)

            if device.is_air_conditioner:
                self.sync_air_conditioner(widgets, device)
            elif device.is_light:
                self.sync_light(widgets, device)
        self.updating_widgets = False
        self.sync_status_label()
        self.menu.show_all()
        return False

    def device_label(self, device):
        if not device.online:
            return f"{MARK_OFF} {device.name}{NBSP}: hors ligne"
        mark = MARK_ON if device.is_on else MARK_OFF
        if not device.is_on:
            return f"{mark} {device.name}"
        if device.is_air_conditioner:
            target = device.temperature_set()
            mode = dict(AC_MODES).get(device.dps.get(DP_AC_MODE), "")
            if target is not None:
                return f"{mark} {device.name}{NBSP}: {format_celsius(target)}, {mode}"
            return f"{mark} {device.name}{NBSP}: {mode}"
        if device.is_light:
            percent = device.brightness_percent()
            if percent is not None:
                return f"{mark} {device.name}{NBSP}: {percent}{NBSP}%"
        return f"{mark} {device.name}"

    def sync_air_conditioner(self, widgets, device):
        ambient = device.temperature_current()
        widgets["ambient"].set_label(
            f"Ambiant{NBSP}: {format_celsius(ambient)}"
            if ambient is not None
            else f"Ambiant{NBSP}: inconnu"
        )

        target = device.temperature_set()
        if target is not None:
            rounded = clamp(round(target), TEMP_MIN_CELSIUS, TEMP_MAX_CELSIUS)
            entry = widgets["temperature"].get(rounded)
            if entry:
                entry.set_active(True)

        self.sync_enum(widgets["mode"], device.dps.get(DP_AC_MODE))
        self.sync_enum(widgets["fan"], device.dps.get(DP_AC_FAN_SPEED))
        self.sync_enum(widgets["louvre"], device.dps.get(DP_AC_LOUVRE))

        widgets["eco"].set_active(bool(device.dps.get(DP_AC_ECO)))
        widgets["sleep"].set_active(bool(device.dps.get(DP_AC_SLEEP)))

        for key in ("temperature_root", "eco", "sleep"):
            widgets[key].set_sensitive(device.online and device.is_on)
        widgets["mode"]["__root__"].set_sensitive(device.online and device.is_on)
        widgets["fan"]["__root__"].set_sensitive(device.online and device.is_on)
        widgets["louvre"]["__root__"].set_sensitive(device.online and device.is_on)

    def sync_light(self, widgets, device):
        percent = device.brightness_percent()
        if percent is not None:
            rounded = clamp(
                round(percent / BRIGHTNESS_STEP_PERCENT) * BRIGHTNESS_STEP_PERCENT,
                BRIGHTNESS_STEP_PERCENT,
                100,
            )
            entry = widgets["brightness"].get(rounded)
            if entry:
                entry.set_active(True)

        raw_temp = device.dps.get(DP_LIGHT_COLOUR_TEMP)
        if raw_temp is not None:
            closest = min(COLOUR_TEMP_PRESETS, key=lambda p: abs(p[0] - raw_temp))[0]
            entry = widgets["colour_temp"].get(closest)
            if entry:
                entry.set_active(True)

        widgets["brightness_root"].set_sensitive(device.online and device.is_on)
        widgets["colour_temp"]["__root__"].set_sensitive(device.online and device.is_on)

    def sync_enum(self, widgets, value):
        entry = widgets.get(value)
        if entry:
            entry.set_active(True)

    def send(self, device, dp, value):
        def work():
            self.set_busy(True)
            try:
                device.apply(dp, value)
                time.sleep(COMMAND_SETTLE_SECONDS)
                device.refresh()
            except Exception:
                device.online = False
            self.set_busy(False)
            GLib.idle_add(self.sync_widgets)

        self.run_background(work)

    def on_power_toggled(self, item, device):
        if self.updating_widgets:
            return
        self.send(device, device.switch_dp, item.get_active())

    def on_flag_toggled(self, item, device, dp):
        if self.updating_widgets:
            return
        self.send(device, dp, item.get_active())

    def on_temperature_selected(self, item, device, celsius):
        if self.updating_widgets or not item.get_active():
            return
        self.send(device, DP_AC_TEMP_SET, int(celsius * TEMP_SCALE))

    def on_mode_selected(self, item, device, value):
        if self.updating_widgets or not item.get_active():
            return
        self.send(device, DP_AC_MODE, value)

    def on_fan_selected(self, item, device, value):
        if self.updating_widgets or not item.get_active():
            return
        self.send(device, DP_AC_FAN_SPEED, value)

    def on_louvre_selected(self, item, device, value):
        if self.updating_widgets or not item.get_active():
            return
        self.send(device, DP_AC_LOUVRE, value)

    def on_brightness_selected(self, item, device, percent):
        if self.updating_widgets or not item.get_active():
            return
        raw = clamp(round(percent / 100 * BRIGHTNESS_MAX), BRIGHTNESS_MIN, BRIGHTNESS_MAX)
        self.send(device, DP_LIGHT_BRIGHTNESS, raw)

    def on_colour_temp_selected(self, item, device, value):
        if self.updating_widgets or not item.get_active():
            return

        def work():
            self.set_busy(True)
            try:
                if device.dps.get(DP_LIGHT_WORK_MODE) != WORK_MODE_WHITE:
                    device.apply(DP_LIGHT_WORK_MODE, WORK_MODE_WHITE)
                device.apply(DP_LIGHT_COLOUR_TEMP, clamp(value, COLOUR_TEMP_MIN, COLOUR_TEMP_MAX))
                time.sleep(COMMAND_SETTLE_SECONDS)
                device.refresh()
            except Exception:
                device.online = False
            self.set_busy(False)
            GLib.idle_add(self.sync_widgets)

        self.run_background(work)

    def on_refresh_clicked(self, item):
        self.run_background(self.locate_and_refresh_all)

    def on_quit_clicked(self, item):
        Gtk.main_quit()


def main():
    TrayApplication()
    Gtk.main()


if __name__ == "__main__":
    main()
