import queue
import threading

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")

from gi.repository import Gdk, GLib, Gtk

from remote_layout import POWER_ACTION, REMOTE_LAYOUT, STYLE_ACCENT, STYLE_POWER

WINDOW_TITLE = "Télécommande"
NBSP = " "
READY_TEXT = "Prêt"
CONNECTING_TEXT = "Connexion à la TV…"
BORDER_WIDTH = 12
GRID_SPACING = 6
BUTTON_WIDTH = 76
BUTTON_HEIGHT = 44
REPEAT_DELAY_MS = 400
REPEAT_INTERVAL_MS = 150
QUEUE_LIMIT = 8
POWER_LABEL_SIZE = "x-large"
STOP_SIGNAL = None
MODIFIER_MASK = (
    Gdk.ModifierType.CONTROL_MASK
    | Gdk.ModifierType.MOD1_MASK
    | Gdk.ModifierType.SUPER_MASK
    | Gdk.ModifierType.META_MASK
)
STYLE_CLASSES = {
    STYLE_POWER: Gtk.STYLE_CLASS_DESTRUCTIVE_ACTION,
    STYLE_ACCENT: Gtk.STYLE_CLASS_SUGGESTED_ACTION,
}


class RemoteWindow(Gtk.Window):
    def __init__(self, tv, on_power, icon_file):
        super().__init__(title=WINDOW_TITLE)
        self.tv = tv
        self.on_power = on_power
        self.keys = queue.Queue(maxsize=QUEUE_LIMIT)
        self.closed = False
        self.repeat_source_id = None
        self.pressed_keyvals = set()
        self.shortcuts = {}
        self.buttons = {}
        self.set_resizable(False)
        self.set_border_width(BORDER_WIDTH)
        self.set_icon_from_file(icon_file)
        grid = Gtk.Grid(
            row_spacing=GRID_SPACING,
            column_spacing=GRID_SPACING,
            column_homogeneous=True,
        )
        for row_index, row in enumerate(REMOTE_LAYOUT):
            for column, cell in enumerate(row):
                if cell is not None:
                    grid.attach(self.create_button(cell), column, row_index, 1, 1)
        self.status_label = Gtk.Label(label=READY_TEXT, xalign=0)
        self.status_label.set_line_wrap(True)
        self.status_label.set_max_width_chars(1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=BORDER_WIDTH)
        box.pack_start(grid, False, False, 0)
        box.pack_start(self.status_label, False, False, 0)
        self.add(box)
        self.connect("key-press-event", self.on_key_press)
        self.connect("key-release-event", self.on_key_release)
        self.connect("focus-out-event", self.on_focus_out)
        self.connect("destroy", self.on_destroy)
        self.worker = threading.Thread(target=self.send_keys, daemon=True)
        self.worker.start()
        self.show_all()

    def create_button(self, cell):
        button = Gtk.Button(label=cell["label"])
        button.set_can_focus(False)
        button.set_size_request(BUTTON_WIDTH, BUTTON_HEIGHT)
        button.set_tooltip_text(cell["title"])
        style_class = STYLE_CLASSES.get(cell["style"])
        if style_class:
            button.get_style_context().add_class(style_class)
        if cell["style"] == STYLE_POWER:
            button.get_child().set_markup(
                f'<span size="{POWER_LABEL_SIZE}">{GLib.markup_escape_text(cell["label"])}</span>'
            )
        if cell["key"] == POWER_ACTION:
            button.connect("clicked", self.on_power_clicked)
        elif cell["repeat"]:
            button.connect("button-press-event", self.on_repeat_button_pressed, cell["key"])
            button.connect("button-release-event", self.on_repeat_button_released)
        else:
            button.connect("clicked", self.on_key_clicked, cell["key"])
        for name in cell["gtk_keys"]:
            self.shortcuts[Gdk.keyval_from_name(name)] = cell
        self.buttons[cell["key"]] = button
        return button

    def on_power_clicked(self, button):
        self.on_power()

    def on_key_clicked(self, button, key):
        self.queue_key(key)

    def on_repeat_button_pressed(self, button, event, key):
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_PRIMARY:
            self.start_repeat(key)
        return False

    def on_repeat_button_released(self, button, event):
        self.stop_repeat()
        return False

    def start_repeat(self, key):
        self.stop_repeat()
        self.queue_key(key)
        self.repeat_source_id = GLib.timeout_add(REPEAT_DELAY_MS, self.begin_repeat, key)

    def begin_repeat(self, key):
        self.queue_key(key)
        self.repeat_source_id = GLib.timeout_add(REPEAT_INTERVAL_MS, self.repeat_key, key)
        return False

    def repeat_key(self, key):
        self.queue_key(key)
        return True

    def stop_repeat(self):
        if self.repeat_source_id is not None:
            GLib.source_remove(self.repeat_source_id)
            self.repeat_source_id = None

    def on_key_press(self, window, event):
        if event.state & MODIFIER_MASK:
            return False
        keyval = Gdk.keyval_to_lower(event.keyval)
        cell = self.shortcuts.get(keyval)
        if cell is None:
            return False
        held = keyval in self.pressed_keyvals
        self.pressed_keyvals.add(keyval)
        if not held or cell["repeat"]:
            self.queue_key(cell["key"])
        return True

    def on_key_release(self, window, event):
        self.pressed_keyvals.discard(Gdk.keyval_to_lower(event.keyval))
        return False

    def on_focus_out(self, window, event):
        self.pressed_keyvals.clear()
        self.stop_repeat()
        return False

    def queue_key(self, key):
        try:
            self.keys.put_nowait(key)
        except queue.Full:
            pass

    def drop_pending_keys(self):
        try:
            while True:
                self.keys.get_nowait()
        except queue.Empty:
            pass

    def send_keys(self):
        while True:
            key = self.keys.get()
            if key is STOP_SIGNAL:
                break
            if not self.tv.remote_open:
                GLib.idle_add(self.show_status, CONNECTING_TEXT)
            try:
                self.tv.send_key(key)
            except Exception as ex:
                self.drop_pending_keys()
                GLib.idle_add(self.show_status, f"Échec{NBSP}: {str(ex) or type(ex).__name__}")
                continue
            GLib.idle_add(self.show_status, READY_TEXT)
        self.tv.close_remote()

    def show_status(self, text):
        if not self.closed and self.status_label.get_label() != text:
            self.status_label.set_label(text)
        return False

    def on_destroy(self, window):
        self.closed = True
        self.stop_repeat()
        self.drop_pending_keys()
        self.keys.put(STOP_SIGNAL)
