#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")

from gi.repository import Gtk, GLib, Gio
from gi.repository import AyatanaAppIndicator3 as AppIndicator

import hashlib
import json
import math
import os
import shutil
import socket
import subprocess
import threading
import time
import unicodedata

import tinytuya
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

APP_ID = "smartlife-tray"
APP_TITLE = "SmartLife"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEVICES_FILE = os.path.join(BASE_DIR, "devices.json")
ICON_FILE = os.path.join(BASE_DIR, "icons", "smartlife-tray.svg")
CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
    os.path.expanduser("~"), ".config"
)
CONFIG_DIR = os.path.join(CONFIG_HOME, APP_ID)
PRESETS_FILE = os.path.join(CONFIG_DIR, "presets.json")
PRESETS_TEMP_FILE = PRESETS_FILE + ".tmp"
PRESETS_INDENT = 2
ALEXA_EXECUTABLE = "alexa"
ALEXA_DEFAULT_PATH = os.path.join(os.path.expanduser("~"), "alexa-cmd", ALEXA_EXECUTABLE)
ALEXA_TV_COMMAND = ("send", "allume", "la", "télé")
ALEXA_COMMAND_TIMEOUT_SECONDS = 360

UDP_PORT = 6667
UDP_KEY = hashlib.md5(b"yGAdlopoPVldABfn").digest()
UDP_HEADER_LEN = 20
UDP_FOOTER_LEN = 8
DISCOVERY_TIMEOUT = 6.0
DISCOVERY_RECV_TIMEOUT = 1.0
POLL_INTERVAL_MENU_OPEN_SECONDS = 4
POLL_INTERVAL_NO_MENU_MONITOR_SECONDS = 180
MENU_ACTIVITY_WINDOW_SECONDS = 60
SHOW_POLL_COUNTDOWN = False
COUNTDOWN_TICK_MS = 1000
SOCKET_TIMEOUT = 5
COMMAND_SETTLE_SECONDS = 0.8

MONITOR_CALL_TIMEOUT_MS = 5000

STATUS_NOTIFIER_WATCHER = "org.kde.StatusNotifierWatcher"
INDICATOR_WAIT_TIMEOUT_SECONDS = 30

DBUSMENU_MATCH_RULE = "interface='com.canonical.dbusmenu'"
DBUSMENU_ACTIVITY_MEMBERS = ("AboutToShowGroup", "AboutToShow", "EventGroup")

CATEGORY_AC = "kt"
CATEGORY_LIGHT = "dj"

DP_AC_SWITCH = "1"
DP_AC_TEMP_SET = "2"
DP_AC_TEMP_CURRENT = "3"
DP_AC_MODE = "4"
DP_AC_FAN_SPEED = "5"
DP_AC_ECO = "8"
DP_AC_DRYING = "9"
DP_AC_DISPLAY = "13"
DP_AC_COUNTDOWN_LEFT = "22"
DP_AC_TEMP_UNIT = "105"
DP_AC_LOUVRE = "107"
DP_AC_SLEEP = "109"
DP_AC_HEALTH = "110"

DP_LIGHT_SWITCH = "20"
DP_LIGHT_WORK_MODE = "21"
DP_LIGHT_BRIGHTNESS = "22"
DP_LIGHT_COLOUR_TEMP = "23"
DP_LIGHT_COLOUR = "24"
DP_LIGHT_SCENE = "25"
DP_LIGHT_COUNTDOWN = "26"
DP_LIGHT_DO_NOT_DISTURB = "34"

AC_PRESET_DPS = (
    DP_AC_SWITCH,
    DP_AC_TEMP_UNIT,
    DP_AC_MODE,
    DP_AC_TEMP_SET,
    DP_AC_FAN_SPEED,
    DP_AC_LOUVRE,
    DP_AC_ECO,
    DP_AC_SLEEP,
    DP_AC_DISPLAY,
    DP_AC_DRYING,
    DP_AC_HEALTH,
)

LIGHT_PRESET_DPS = (
    DP_LIGHT_SWITCH,
    DP_LIGHT_WORK_MODE,
    DP_LIGHT_BRIGHTNESS,
    DP_LIGHT_COLOUR_TEMP,
    DP_LIGHT_COLOUR,
    DP_LIGHT_SCENE,
    DP_LIGHT_DO_NOT_DISTURB,
)

TEMP_SCALE = 10
TEMP_UNIT_CELSIUS = "c"
TEMP_UNIT_FAHRENHEIT = "f"

TEMP_RANGES = {
    TEMP_UNIT_CELSIUS: (16, 30, "°C"),
    TEMP_UNIT_FAHRENHEIT: (61, 86, "°F"),
}

TEMP_UNITS = [
    (TEMP_UNIT_CELSIUS, "Celsius"),
    (TEMP_UNIT_FAHRENHEIT, "Fahrenheit"),
]

BRIGHTNESS_MIN = 10
BRIGHTNESS_MAX = 1000
BRIGHTNESS_STEP_PERCENT = 10

COLOUR_TEMP_MIN = 0
COLOUR_TEMP_MAX = 1000

COLOUR_SATURATION = 1000
COLOUR_VALUE = 1000
COLOUR_HUE_DIGITS = 4

WORK_MODE_WHITE = "white"
WORK_MODE_COLOUR = "colour"
WORK_MODE_SCENE = "scene"

WORK_MODE_DPS = {
    WORK_MODE_WHITE: (DP_LIGHT_COLOUR_TEMP,),
    WORK_MODE_COLOUR: (DP_LIGHT_COLOUR,),
    WORK_MODE_SCENE: (DP_LIGHT_SCENE,),
}

NBSP = " "
MARK_ON = "●"
MARK_OFF = "○"

DIALOG_BORDER_WIDTH = 12
DIALOG_SPACING = 8

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

AC_FLAGS = [
    ("eco", DP_AC_ECO, "Éco"),
    ("sleep", DP_AC_SLEEP, "Sommeil"),
    ("display", DP_AC_DISPLAY, "Affichage"),
    ("drying", DP_AC_DRYING, "Séchage"),
    ("health", DP_AC_HEALTH, "Santé"),
]

COLOUR_TEMP_PRESETS = [
    (0, "Blanc chaud"),
    (250, "Chaud"),
    (500, "Neutre"),
    (750, "Froid"),
    (1000, "Lumière du jour"),
]

COLOUR_PRESETS = [
    (0, "Rouge"),
    (30, "Orange"),
    (60, "Jaune"),
    (120, "Vert"),
    (180, "Cyan"),
    (240, "Bleu"),
    (280, "Violet"),
    (320, "Magenta"),
]

LIGHT_SCENES = [
    ("000e0d0000000000000000c80000", "Nuit"),
    ("010e0d0000000000000003e801f4", "Lecture"),
    ("020e0d0000000000000003e803e8", "Travail"),
    ("030e0d0000000000000001f401f4", "Détente"),
    (
        "04464602007803e803e800000000464601000003e803e800000000",
        "Douceur",
    ),
    (
        "05464601000003e803e800000000464602007803e803e80000000046460300f003e803e800000000",
        "Arc-en-ciel",
    ),
    (
        "06464601000003e803e800000000464602007803e803e80000000046460300f003e803e800000000",
        "Scintillement",
    ),
    (
        "07464602000003e803e800000000464601007803e803e80000000046460100f003e803e800000000"
        "464601003d03e803e80000000046460100ae03e803e800000000464601011303e803e800000000",
        "Somptueux",
    ),
]

SECONDS_PER_MINUTE = 60

LIGHT_COUNTDOWNS = [
    (0, "Aucune"),
    (15 * SECONDS_PER_MINUTE, "15 min"),
    (30 * SECONDS_PER_MINUTE, "30 min"),
    (60 * SECONDS_PER_MINUTE, "1 h"),
    (120 * SECONDS_PER_MINUTE, "2 h"),
    (240 * SECONDS_PER_MINUTE, "4 h"),
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


def format_temperature(value, unit):
    return f"{value:.0f}{NBSP}{TEMP_RANGES[unit][2]}"


def format_celsius(celsius):
    return format_temperature(celsius, TEMP_UNIT_CELSIUS)


def format_countdown(minutes):
    if not minutes:
        return f"Minuterie{NBSP}: aucune"
    return f"Minuterie{NBSP}: {minutes}{NBSP}min"


def preset_sort_key(name):
    folded = unicodedata.normalize("NFKD", name)
    return ("".join(c for c in folded if not unicodedata.combining(c)).lower(), name)


def colour_payload(hue):
    return f"{hue:04x}{COLOUR_SATURATION:04x}{COLOUR_VALUE:04x}"


def turn_on_tv_with_alexa():
    executable = shutil.which(ALEXA_EXECUTABLE)
    if executable is None and os.access(ALEXA_DEFAULT_PATH, os.X_OK):
        executable = ALEXA_DEFAULT_PATH
    if executable is None:
        raise FileNotFoundError("Alexa command not found. Install alexa-cmd first.")
    subprocess.run(
        [executable, *ALEXA_TV_COMMAND],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=ALEXA_COMMAND_TIMEOUT_SECONDS,
    )


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

    @property
    def preset_dps(self):
        if self.is_air_conditioner:
            return AC_PRESET_DPS
        if self.is_light:
            return LIGHT_PRESET_DPS
        return ()

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

    def apply_many(self, values):
        connection = self.open_connection()
        if connection is None:
            return False
        result = connection.set_multiple_values(values)
        if isinstance(result, dict) and "dps" in result:
            self.dps.update(result["dps"])
        return not (isinstance(result, dict) and result.get("Error"))

    def capture_preset(self):
        return {dp: self.dps[dp] for dp in self.preset_dps if dp in self.dps}

    def preset_settings(self, values):
        settings = {
            dp: values[dp] for dp in self.preset_dps if dp in values and dp != self.switch_dp
        }
        work_mode = values.get(DP_LIGHT_WORK_MODE)
        if not self.is_light or work_mode not in WORK_MODE_DPS:
            return settings
        for mode, dps in WORK_MODE_DPS.items():
            if mode != work_mode:
                for dp in dps:
                    settings.pop(dp, None)
        return settings

    def apply_preset(self, values):
        switch = values.get(self.switch_dp)
        settings = self.preset_settings(values)
        if switch is not None and not switch:
            return self.apply(self.switch_dp, False)
        if switch and not self.is_on:
            if not self.apply(self.switch_dp, True):
                return False
            time.sleep(COMMAND_SETTLE_SECONDS)
        if not settings:
            return True
        return self.apply_many(settings)

    def temperature_set(self):
        raw = self.dps.get(DP_AC_TEMP_SET)
        return None if raw is None else raw / TEMP_SCALE

    def temperature_current(self):
        raw = self.dps.get(DP_AC_TEMP_CURRENT)
        return None if raw is None else raw / TEMP_SCALE

    def temperature_unit(self):
        unit = self.dps.get(DP_AC_TEMP_UNIT)
        return unit if unit in TEMP_RANGES else TEMP_UNIT_CELSIUS

    def brightness_percent(self):
        raw = self.dps.get(DP_LIGHT_BRIGHTNESS)
        return None if raw is None else round(raw / BRIGHTNESS_MAX * 100)

    def colour_hue(self):
        raw = self.dps.get(DP_LIGHT_COLOUR)
        if not isinstance(raw, str) or len(raw) < COLOUR_HUE_DIGITS:
            return None
        try:
            return int(raw[:COLOUR_HUE_DIGITS], 16)
        except ValueError:
            return None

    def countdown_minutes(self):
        raw = self.dps.get(DP_LIGHT_COUNTDOWN)
        return None if raw is None else round(raw / SECONDS_PER_MINUTE)


class MenuActivityMonitor:
    def __init__(self, on_activity):
        self.on_activity = on_activity
        self.own_name = None
        self.connection = None

    def start(self):
        try:
            self.own_name = Gio.bus_get_sync(Gio.BusType.SESSION, None).get_unique_name()
            address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
            connection = Gio.DBusConnection.new_for_address_sync(
                address,
                Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
                | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
                None,
                None,
            )
            connection.set_exit_on_close(False)
            connection.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus.Monitoring",
                "BecomeMonitor",
                GLib.Variant("(asu)", ([DBUSMENU_MATCH_RULE], 0)),
                None,
                Gio.DBusCallFlags.NONE,
                MONITOR_CALL_TIMEOUT_MS,
                None,
            )
            connection.add_filter(self.on_message, None)
        except GLib.Error:
            return
        self.connection = connection

    def on_message(self, connection, message, incoming, user_data):
        self.handle_message(message)
        return None

    def handle_message(self, message):
        if message.get_member() not in DBUSMENU_ACTIVITY_MEMBERS:
            return
        if message.get_destination() != self.own_name:
            return
        GLib.idle_add(self.on_activity)


class TrayApplication:
    def __init__(self):
        self.devices = [Device(entry) for entry in self.load_devices()]
        self.presets = self.load_presets()
        self.updating_widgets = False
        self.busy = False
        self.alexa_busy = False
        self.indicator = None
        self.watcher_id = None
        self.indicator_wait_source_id = None
        self.menu = Gtk.Menu()
        self.device_widgets = {}
        self.status_item = None
        self.status_label = None
        self.poll_source_id = None
        self.activity_source_id = None
        self.countdown_source_id = None
        self.poll_interval_seconds = None
        self.next_poll_time = None
        self.menu_active = False
        self.build_menu()
        self.wait_for_status_notifier_watcher()
        self.run_background(self.locate_and_refresh_all)
        self.start_menu_monitor()

    def wait_for_status_notifier_watcher(self):
        self.watcher_id = Gio.bus_watch_name(
            Gio.BusType.SESSION,
            STATUS_NOTIFIER_WATCHER,
            Gio.BusNameWatcherFlags.NONE,
            self.on_watcher_appeared,
            None,
        )
        self.indicator_wait_source_id = GLib.timeout_add_seconds(
            INDICATOR_WAIT_TIMEOUT_SECONDS, self.on_indicator_wait_expired
        )

    def on_watcher_appeared(self, connection, name, owner):
        self.stop_waiting_for_watcher()
        self.start_indicator()

    def on_indicator_wait_expired(self):
        self.indicator_wait_source_id = None
        self.stop_waiting_for_watcher()
        self.start_indicator()
        return False

    def stop_waiting_for_watcher(self):
        if self.watcher_id is not None:
            Gio.bus_unwatch_name(self.watcher_id)
            self.watcher_id = None
        if self.indicator_wait_source_id is not None:
            GLib.source_remove(self.indicator_wait_source_id)
            self.indicator_wait_source_id = None

    def start_indicator(self):
        if self.indicator is not None:
            return
        self.indicator = AppIndicator.Indicator.new(
            APP_ID, ICON_FILE, AppIndicator.IndicatorCategory.HARDWARE
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title(APP_TITLE)
        if os.path.exists(ICON_FILE):
            self.indicator.set_icon_full(ICON_FILE, APP_TITLE)
        self.indicator.set_menu(self.menu)

    def load_devices(self):
        with open(DEVICES_FILE) as handle:
            return json.load(handle)

    def load_presets(self):
        try:
            with open(PRESETS_FILE, encoding="utf-8") as handle:
                stored = json.load(handle)
        except (OSError, ValueError):
            return {}
        if not isinstance(stored, dict):
            return {}
        return {
            device_id: presets
            for device_id, presets in stored.items()
            if isinstance(presets, dict)
        }

    def save_presets(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(PRESETS_TEMP_FILE, "w", encoding="utf-8") as handle:
                json.dump(self.presets, handle, indent=PRESETS_INDENT, ensure_ascii=False)
            os.replace(PRESETS_TEMP_FILE, PRESETS_FILE)
            return True
        except OSError as ex:
            self.discard_temp_presets()
            self.report_error(f"Enregistrement impossible{NBSP}: {ex}")
            return False

    def discard_temp_presets(self):
        try:
            os.remove(PRESETS_TEMP_FILE)
        except OSError:
            pass

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

    def start_menu_monitor(self):
        self.menu_monitor = MenuActivityMonitor(self.on_menu_activity)
        self.menu_monitor.start()
        self.schedule_idle_poll()

    def schedule_idle_poll(self):
        if self.menu_monitor.connection is None:
            self.schedule_poll(POLL_INTERVAL_NO_MENU_MONITOR_SECONDS)
        else:
            self.cancel_poll()

    def cancel_poll(self):
        if self.poll_source_id is not None:
            GLib.source_remove(self.poll_source_id)
            self.poll_source_id = None
        self.poll_interval_seconds = None
        self.next_poll_time = None

    def schedule_poll(self, interval_seconds):
        self.cancel_poll()
        self.poll_interval_seconds = interval_seconds
        self.next_poll_time = time.monotonic() + interval_seconds
        self.poll_source_id = GLib.timeout_add_seconds(interval_seconds, self.on_poll_tick)

    def on_poll_tick(self):
        self.next_poll_time = time.monotonic() + self.poll_interval_seconds
        if self.menu_active:
            self.start_countdown()
        if not self.busy:
            self.run_background(self.refresh_all)
        return True

    def poll_countdown(self):
        if self.next_poll_time is None:
            return None
        return max(0, math.ceil(self.next_poll_time - time.monotonic()))

    def start_countdown(self):
        self.cancel_countdown()
        if not SHOW_POLL_COUNTDOWN:
            return
        self.countdown_source_id = GLib.timeout_add(COUNTDOWN_TICK_MS, self.on_countdown_tick)

    def cancel_countdown(self):
        if self.countdown_source_id is not None:
            GLib.source_remove(self.countdown_source_id)
            self.countdown_source_id = None

    def on_countdown_tick(self):
        self.sync_status_label()
        return True

    def on_menu_activity(self):
        self.restart_activity_window()
        if not self.menu_active:
            self.menu_active = True
            self.schedule_poll(POLL_INTERVAL_MENU_OPEN_SECONDS)
            self.start_countdown()
            self.sync_status_label()
            if not self.busy:
                self.run_background(self.refresh_all)
        return False

    def restart_activity_window(self):
        if self.activity_source_id is not None:
            GLib.source_remove(self.activity_source_id)
        self.activity_source_id = GLib.timeout_add_seconds(
            MENU_ACTIVITY_WINDOW_SECONDS, self.on_activity_window_expired
        )

    def on_activity_window_expired(self):
        self.activity_source_id = None
        self.menu_active = False
        self.cancel_countdown()
        self.schedule_idle_poll()
        return False

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

            self.build_presets_menu(submenu, widgets, device)

            submenu.append(Gtk.SeparatorMenuItem())

            if device.is_air_conditioner:
                self.build_air_conditioner_menu(submenu, widgets, device)
            elif device.is_light:
                self.build_light_menu(submenu, widgets, device)

            item.set_submenu(submenu)
            self.menu.append(item)
            self.device_widgets[device.id] = widgets

        self.menu.append(Gtk.SeparatorMenuItem())

        self.build_tv_menu()
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

    def build_tv_menu(self):
        root = Gtk.MenuItem(label="Télévision")
        submenu = Gtk.Menu()
        self.tv_power_item = Gtk.MenuItem(label="Allumer avec Alexa")
        self.tv_power_item.connect("activate", self.on_tv_power_clicked)
        submenu.append(self.tv_power_item)
        self.tv_status_item = Gtk.MenuItem(label="Commande via Alexa")
        self.tv_status_item.set_sensitive(False)
        submenu.append(self.tv_status_item)
        root.set_submenu(submenu)
        self.menu.append(root)

    def build_presets_menu(self, submenu, widgets, device):
        root = Gtk.MenuItem(label="Préréglages")
        menu = Gtk.Menu()
        root.set_submenu(menu)
        submenu.append(root)
        widgets["presets_root"] = root
        widgets["presets_menu"] = menu
        self.fill_presets_menu(widgets, device)

    def fill_presets_menu(self, widgets, device):
        menu = widgets["presets_menu"]
        for child in menu.get_children():
            menu.remove(child)
        names = self.preset_names(device)
        for name in names:
            entry = Gtk.MenuItem(label=name)
            entry.connect("activate", self.on_preset_activated, device, name)
            menu.append(entry)
        if names:
            menu.append(Gtk.SeparatorMenuItem())
        save = Gtk.MenuItem(label="Enregistrer l'état actuel…")
        save.connect("activate", self.on_preset_save_clicked, device)
        menu.append(save)
        if names:
            delete_root = Gtk.MenuItem(label="Supprimer")
            delete_menu = Gtk.Menu()
            for name in names:
                entry = Gtk.MenuItem(label=name)
                entry.connect("activate", self.on_preset_delete_clicked, device, name)
                delete_menu.append(entry)
            delete_root.set_submenu(delete_menu)
            menu.append(delete_root)
        menu.show_all()

    def store_presets(self, device, presets):
        previous = self.presets.get(device.id)
        if presets:
            self.presets[device.id] = presets
        else:
            self.presets.pop(device.id, None)
        if not self.save_presets():
            if previous is None:
                self.presets.pop(device.id, None)
            else:
                self.presets[device.id] = previous
            return
        self.fill_presets_menu(self.device_widgets[device.id], device)

    def preset_names(self, device):
        return sorted(self.presets.get(device.id, {}), key=preset_sort_key)

    def build_air_conditioner_menu(self, submenu, widgets, device):
        ambient = Gtk.MenuItem(label="")
        ambient.set_sensitive(False)
        submenu.append(ambient)
        widgets["ambient"] = ambient

        countdown = Gtk.MenuItem(label=format_countdown(None))
        countdown.set_sensitive(False)
        submenu.append(countdown)
        widgets["countdown"] = countdown

        temp_item = Gtk.MenuItem(label="Température")
        temp_menu = Gtk.Menu()
        temp_item.set_submenu(temp_menu)
        submenu.append(temp_item)
        widgets["temperature"] = {}
        widgets["temperature_menu"] = temp_menu
        widgets["temperature_root"] = temp_item
        widgets["temperature_unit"] = None
        self.build_temperature_entries(widgets, device)

        widgets["mode"] = self.build_enum_submenu(
            submenu, "Mode", AC_MODES, self.on_mode_selected, device
        )
        widgets["fan"] = self.build_enum_submenu(
            submenu, "Vitesse", AC_FAN_SPEEDS, self.on_fan_selected, device
        )
        widgets["louvre"] = self.build_enum_submenu(
            submenu, "Panneau", AC_LOUVRE_POSITIONS, self.on_louvre_selected, device
        )
        widgets["unit"] = self.build_enum_submenu(
            submenu, "Unité", TEMP_UNITS, self.on_temp_unit_selected, device
        )

        submenu.append(Gtk.SeparatorMenuItem())

        for key, dp, label in AC_FLAGS:
            self.build_flag(submenu, widgets, device, key, dp, label)

    def build_temperature_entries(self, widgets, device):
        unit = device.temperature_unit()
        if widgets["temperature_unit"] == unit:
            return
        menu = widgets["temperature_menu"]
        for child in menu.get_children():
            menu.remove(child)
        widgets["temperature"] = {}
        low, high, _ = TEMP_RANGES[unit]
        group = []
        for value in range(low, high + 1):
            entry = Gtk.RadioMenuItem.new_with_label(group, format_temperature(value, unit))
            group = entry.get_group()
            entry.connect("toggled", self.on_temperature_selected, device, value)
            menu.append(entry)
            widgets["temperature"][value] = entry
        widgets["temperature_unit"] = unit

    def build_flag(self, submenu, widgets, device, key, dp, label):
        item = Gtk.CheckMenuItem(label=label)
        item.connect("toggled", self.on_flag_toggled, device, dp)
        submenu.append(item)
        widgets[key] = item

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
        widgets["colour"] = self.build_enum_submenu(
            submenu, "Couleur", COLOUR_PRESETS, self.on_colour_selected, device
        )
        widgets["scene"] = self.build_enum_submenu(
            submenu, "Scène", LIGHT_SCENES, self.on_scene_selected, device
        )
        widgets["light_countdown"] = self.build_enum_submenu(
            submenu, format_countdown(None), LIGHT_COUNTDOWNS, self.on_countdown_selected, device
        )

        submenu.append(Gtk.SeparatorMenuItem())

        self.build_flag(
            submenu,
            widgets,
            device,
            "do_not_disturb",
            DP_LIGHT_DO_NOT_DISTURB,
            "Ne pas déranger",
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
        label = self.with_countdown(text)
        if label != self.status_label:
            self.status_label = label
            self.status_item.set_label(label)
        return False

    def with_countdown(self, text):
        if not SHOW_POLL_COUNTDOWN or self.busy or not self.menu_active:
            return text
        remaining = self.poll_countdown()
        if remaining is None:
            return text
        return f"{text} ({remaining}{NBSP}s)"

    def sync_widgets(self):
        self.updating_widgets = True
        for device in self.devices:
            widgets = self.device_widgets[device.id]
            widgets["root"].set_label(self.device_label(device))

            power = widgets["power"]
            power.set_active(device.is_on)
            power.set_sensitive(device.online)
            widgets["presets_root"].set_sensitive(device.online)

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
                unit = device.temperature_unit()
                return f"{mark} {device.name}{NBSP}: {format_temperature(target, unit)}, {mode}"
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

        widgets["countdown"].set_label(format_countdown(device.dps.get(DP_AC_COUNTDOWN_LEFT)))

        self.build_temperature_entries(widgets, device)
        target = device.temperature_set()
        if target is not None:
            low, high, _ = TEMP_RANGES[device.temperature_unit()]
            entry = widgets["temperature"].get(clamp(round(target), low, high))
            if entry:
                entry.set_active(True)

        self.sync_enum(widgets["mode"], device.dps.get(DP_AC_MODE))
        self.sync_enum(widgets["fan"], device.dps.get(DP_AC_FAN_SPEED))
        self.sync_enum(widgets["louvre"], device.dps.get(DP_AC_LOUVRE))
        self.sync_enum(widgets["unit"], device.temperature_unit())

        for key, dp, _ in AC_FLAGS:
            widgets[key].set_active(bool(device.dps.get(dp)))

        available = device.online and device.is_on
        for key, _, _ in AC_FLAGS:
            widgets[key].set_sensitive(available)
        widgets["temperature_root"].set_sensitive(available)
        for key in ("mode", "fan", "louvre", "unit"):
            widgets[key]["__root__"].set_sensitive(available)

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

        hue = device.colour_hue()
        if hue is not None:
            closest = min(COLOUR_PRESETS, key=lambda p: abs(p[0] - hue))[0]
            entry = widgets["colour"].get(closest)
            if entry:
                entry.set_active(True)

        self.sync_enum(widgets["scene"], device.dps.get(DP_LIGHT_SCENE))
        widgets["light_countdown"]["__root__"].set_label(
            format_countdown(device.countdown_minutes())
        )
        widgets["do_not_disturb"].set_active(bool(device.dps.get(DP_LIGHT_DO_NOT_DISTURB)))

        available = device.online and device.is_on
        widgets["brightness_root"].set_sensitive(available)
        for key in ("colour_temp", "colour", "scene", "light_countdown"):
            widgets[key]["__root__"].set_sensitive(available)
        widgets["do_not_disturb"].set_sensitive(device.online)

    def sync_enum(self, widgets, value):
        entry = widgets.get(value)
        if entry:
            entry.set_active(True)

    def send(self, device, dp, value, work_mode=None):
        def work():
            self.set_busy(True)
            try:
                if work_mode is not None and device.dps.get(DP_LIGHT_WORK_MODE) != work_mode:
                    device.apply(DP_LIGHT_WORK_MODE, work_mode)
                device.apply(dp, value)
                time.sleep(COMMAND_SETTLE_SECONDS)
                device.refresh()
            except Exception:
                device.online = False
            self.set_busy(False)
            GLib.idle_add(self.sync_widgets)

        self.run_background(work)

    def send_preset(self, device, values):
        def work():
            self.set_busy(True)
            try:
                device.apply_preset(values)
                time.sleep(COMMAND_SETTLE_SECONDS)
                device.refresh()
            except Exception:
                device.online = False
            self.set_busy(False)
            GLib.idle_add(self.sync_widgets)

        self.run_background(work)

    def ask_preset_name(self, device):
        dialog = Gtk.Dialog(title="Préréglage", modal=True)
        dialog.add_button("Annuler", Gtk.ResponseType.CANCEL)
        dialog.add_button("Enregistrer", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        label = Gtk.Label(label=f"Nom du préréglage pour {device.name}{NBSP}:")
        label.set_xalign(0)
        entry = Gtk.Entry()
        entry.set_activates_default(True)
        content = dialog.get_content_area()
        content.set_border_width(DIALOG_BORDER_WIDTH)
        content.set_spacing(DIALOG_SPACING)
        content.add(label)
        content.add(entry)
        dialog.show_all()
        response = dialog.run()
        name = entry.get_text().strip()
        dialog.destroy()
        return name if response == Gtk.ResponseType.OK else None

    def confirm(self, question):
        dialog = Gtk.MessageDialog(
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=question,
        )
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.OK

    def report_error(self, message):
        dialog = Gtk.MessageDialog(
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=message,
        )
        dialog.run()
        dialog.destroy()

    def on_preset_activated(self, item, device, name):
        values = self.presets.get(device.id, {}).get(name)
        if not isinstance(values, dict) or not values:
            return
        self.send_preset(device, values)

    def on_preset_save_clicked(self, item, device):
        values = device.capture_preset()
        if not values:
            self.report_error(f"Aucun état connu pour {device.name}.")
            return
        name = self.ask_preset_name(device)
        if not name:
            return
        presets = dict(self.presets.get(device.id, {}))
        if name in presets and not self.confirm(
            f"Remplacer le préréglage «{NBSP}{name}{NBSP}»{NBSP}?"
        ):
            return
        presets[name] = values
        self.store_presets(device, presets)

    def on_preset_delete_clicked(self, item, device, name):
        presets = dict(self.presets.get(device.id, {}))
        if name not in presets:
            return
        if not self.confirm(f"Supprimer le préréglage «{NBSP}{name}{NBSP}»{NBSP}?"):
            return
        del presets[name]
        self.store_presets(device, presets)

    def on_power_toggled(self, item, device):
        if self.updating_widgets:
            return
        self.send(device, device.switch_dp, item.get_active())

    def on_flag_toggled(self, item, device, dp):
        if self.updating_widgets:
            return
        self.send(device, dp, item.get_active())

    def on_temperature_selected(self, item, device, value):
        if self.updating_widgets or not item.get_active():
            return
        self.send(device, DP_AC_TEMP_SET, int(value * TEMP_SCALE))

    def on_temp_unit_selected(self, item, device, value):
        if self.updating_widgets or not item.get_active():
            return
        self.send(device, DP_AC_TEMP_UNIT, value)

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
        self.send(
            device,
            DP_LIGHT_COLOUR_TEMP,
            clamp(value, COLOUR_TEMP_MIN, COLOUR_TEMP_MAX),
            work_mode=WORK_MODE_WHITE,
        )

    def on_colour_selected(self, item, device, hue):
        if self.updating_widgets or not item.get_active():
            return
        self.send(device, DP_LIGHT_COLOUR, colour_payload(hue), work_mode=WORK_MODE_COLOUR)

    def on_scene_selected(self, item, device, data):
        if self.updating_widgets or not item.get_active():
            return
        self.send(device, DP_LIGHT_SCENE, data, work_mode=WORK_MODE_SCENE)

    def on_countdown_selected(self, item, device, seconds):
        if self.updating_widgets or not item.get_active():
            return
        self.send(device, DP_LIGHT_COUNTDOWN, seconds)

    def on_refresh_clicked(self, item):
        self.run_background(self.locate_and_refresh_all)

    def on_tv_power_clicked(self, item):
        if self.alexa_busy:
            return
        self.alexa_busy = True
        self.tv_power_item.set_sensitive(False)
        self.tv_status_item.set_label("Envoi à Alexa…")
        self.run_background(self.send_tv_power)

    def send_tv_power(self):
        error = None
        try:
            turn_on_tv_with_alexa()
        except subprocess.TimeoutExpired:
            error = "Délai dépassé, vérifiez votre connexion à Amazon et réessayez."
        except subprocess.CalledProcessError as ex:
            error = (ex.stderr or "").strip() or (ex.stdout or "").strip() or str(ex)
        except OSError as ex:
            error = str(ex)
        GLib.idle_add(self.finish_tv_power, error)

    def finish_tv_power(self, error):
        self.alexa_busy = False
        self.tv_power_item.set_sensitive(True)
        self.tv_status_item.set_label(
            "Échec de la commande Alexa" if error else "Commande envoyée à Alexa"
        )
        if error:
            self.report_error(f"Allumage de la TV impossible{NBSP}: {error}")
        return False

    def on_quit_clicked(self, item):
        Gtk.main_quit()


def main():
    TrayApplication()
    Gtk.main()


if __name__ == "__main__":
    main()
