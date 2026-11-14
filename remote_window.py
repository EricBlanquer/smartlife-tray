import queue
import threading

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

from remote_layout import (
    EXTRA_LAYOUT,
    KEYS,
    PANEL_ACTION,
    POWER_ACTION,
    REMOTE_LAYOUT,
    STYLE_ACCENT,
    STYLE_POWER,
)
from remote_skin import SKIN_HEIGHT, SKIN_WIDTH, hotspot_at, trace

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
POINTER_CURSOR = "pointer"
HOVER_RGBA = (1, 1, 1, 0.3)
PRESSED_RGBA = (0, 0, 0, 0.2)
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
WHEEL_INDEXES = {Gdk.ScrollDirection.UP: 0, Gdk.ScrollDirection.DOWN: 1}


def is_primary_press(event):
    return event.type == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_PRIMARY


class SkinView(Gtk.DrawingArea):
    def __init__(self, path, on_press, on_release, on_wheel):
        super().__init__()
        self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
        self.on_press = on_press
        self.on_release = on_release
        self.on_wheel = on_wheel
        self.hovered = None
        self.pressed = None
        self.set_size_request(SKIN_WIDTH, SKIN_HEIGHT)
        self.set_has_tooltip(True)
        self.add_events(
            Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
            | Gdk.EventMask.SCROLL_MASK
        )
        self.connect("draw", self.on_draw)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("leave-notify-event", self.on_leave)
        self.connect("button-press-event", self.on_button_press)
        self.connect("button-release-event", self.on_button_release)
        self.connect("scroll-event", self.on_scroll)
        self.connect("query-tooltip", self.on_query_tooltip)

    def on_draw(self, widget, context):
        Gdk.cairo_set_source_pixbuf(context, self.pixbuf, 0, 0)
        context.paint()
        spot = self.pressed or self.hovered
        if spot is not None:
            trace(context, spot)
            context.set_source_rgba(*(PRESSED_RGBA if self.pressed else HOVER_RGBA))
            context.fill()
        return False

    def set_hovered(self, spot):
        if spot is self.hovered:
            return
        self.hovered = spot
        window = self.get_window()
        if window is not None:
            cursor = Gdk.Cursor.new_from_name(self.get_display(), POINTER_CURSOR) if spot else None
            window.set_cursor(cursor)
        self.queue_draw()

    def on_motion(self, widget, event):
        self.set_hovered(hotspot_at(event.x, event.y))
        return False

    def on_leave(self, widget, event):
        if self.pressed is None:
            self.set_hovered(None)
        return False

    def on_button_press(self, widget, event):
        spot = hotspot_at(event.x, event.y)
        if spot is None or not is_primary_press(event):
            return False
        self.pressed = spot
        self.queue_draw()
        self.on_press(spot)
        return True

    def on_button_release(self, widget, event):
        if self.pressed is None:
            return False
        self.pressed = None
        self.set_hovered(hotspot_at(event.x, event.y))
        self.queue_draw()
        self.on_release()
        return True

    def on_scroll(self, widget, event):
        spot = hotspot_at(event.x, event.y)
        index = WHEEL_INDEXES.get(event.direction)
        if spot is None or spot["wheel"] is None or index is None:
            return False
        self.on_wheel(spot["wheel"][index])
        return True

    def on_query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        spot = hotspot_at(x, y)
        if spot is None:
            return False
        tooltip.set_text(spot["title"])
        return True


class RemoteWindow(Gtk.Window):
    def __init__(self, tv, on_power, icon_file, skin_path):
        super().__init__(title=WINDOW_TITLE)
        self.tv = tv
        self.on_power = on_power
        self.keys = queue.Queue(maxsize=QUEUE_LIMIT)
        self.closed = False
        self.repeat_source_id = None
        self.pressed_keyvals = set()
        self.buttons = {}
        self.shortcuts = {
            Gdk.keyval_from_name(name): cell
            for cell in KEYS.values()
            for name in cell["gtk_keys"]
        }
        self.set_resizable(False)
        self.set_border_width(BORDER_WIDTH)
        self.set_icon_from_file(icon_file)
        self.skin = self.load_skin(skin_path)
        self.panel = None
        if self.skin is None:
            remote = self.create_grid(REMOTE_LAYOUT)
        else:
            self.panel = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_RIGHT)
            self.panel.add(self.create_grid(EXTRA_LAYOUT))
            remote = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=BORDER_WIDTH)
            remote.pack_start(self.skin, False, False, 0)
            remote.pack_start(self.panel, False, False, 0)
        self.status_label = Gtk.Label(label=READY_TEXT, xalign=0)
        self.status_label.set_line_wrap(True)
        self.status_label.set_max_width_chars(1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=BORDER_WIDTH)
        box.pack_start(remote, False, False, 0)
        box.pack_start(self.status_label, False, False, 0)
        self.add(box)
        self.connect("key-press-event", self.on_key_press)
        self.connect("key-release-event", self.on_key_release)
        self.connect("focus-out-event", self.on_focus_out)
        self.connect("destroy", self.on_destroy)
        self.worker = threading.Thread(target=self.send_keys, daemon=True)
        self.worker.start()
        self.show_all()

    def load_skin(self, skin_path):
        if skin_path is None:
            return None
        try:
            return SkinView(skin_path, self.on_hotspot_pressed, self.stop_repeat, self.queue_key)
        except GLib.Error:
            return None

    def create_grid(self, layout):
        grid = Gtk.Grid(
            row_spacing=GRID_SPACING,
            column_spacing=GRID_SPACING,
            column_homogeneous=True,
        )
        for row_index, row in enumerate(layout):
            for column, cell in enumerate(row):
                if cell is not None:
                    grid.attach(self.create_button(cell), column, row_index, 1, 1)
        return grid

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
        if cell["repeat"]:
            button.connect("button-press-event", self.on_repeat_button_pressed, cell["key"])
            button.connect("button-release-event", self.on_repeat_button_released)
        else:
            button.connect("clicked", self.on_button_clicked, cell["key"])
        self.buttons[cell["key"]] = button
        return button

    def activate(self, key):
        if key == POWER_ACTION:
            self.on_power()
        elif key == PANEL_ACTION:
            self.toggle_panel()
        else:
            self.queue_key(key)

    def toggle_panel(self):
        if self.panel is not None:
            self.panel.set_reveal_child(not self.panel.get_reveal_child())

    def on_button_clicked(self, button, key):
        self.activate(key)

    def on_hotspot_pressed(self, spot):
        if spot["repeat"]:
            self.start_repeat(spot["key"])
        else:
            self.activate(spot["key"])

    def on_repeat_button_pressed(self, button, event, key):
        if is_primary_press(event):
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
            self.activate(cell["key"])
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
