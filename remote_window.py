import math
import queue
import threading

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

from global_wheel import GlobalWheel
from remote_keypad import KEYPAD, keypad_svg
from remote_layout import (
    KEYS,
    PANEL_ACTION,
    POWER_ACTION,
    REMOTE_LAYOUT,
    STYLE_ACCENT,
    STYLE_POWER,
    send,
)
from remote_skin import KEY_PANEL_BOTTOM, REMOTE_SKIN, trace

WINDOW_TITLE = "Télécommande"
NBSP = " "
READY_TEXT = "Prêt"
CONNECTING_TEXT = "Connexion à la TV…"
BORDER_WIDTH = 12
GRID_SPACING = 6
BUTTON_WIDTH = 76
BUTTON_HEIGHT = 44
SKIN_DISPLAY_SCALE = 0.5
ICON_SIZES = (16, 24, 32, 48, 64, 128)
SETTLE_DELAY_MS = 300
SLIDE_DURATION_MICROSECONDS = 220_000
UNTUCK_DISTANCE = 24
MINIMUM_VISIBLE_HEIGHT = 1
ANIMATIONS_SETTING = "gtk-enable-animations"
ICON_ANGLE_DEGREES = 45
SVG_LOADER = "svg"
TOAST_MARGIN = 8
TOAST_MAX_WIDTH_CHARS = 20
TOAST_HIDE_DELAY_MS = 5000
CLOSE_TEXT = "Fermer la télécommande"
MENU_STYLE_CLASS = "remote-menu"
MENU_CSS = b"""
menu.remote-menu {
  background-color: #ffffff;
  color: #16181d;
}
menu.remote-menu menuitem {
  color: #16181d;
}
menu.remote-menu menuitem:hover {
  background-color: #1f6feb;
  color: #ffffff;
}
menu.remote-menu menuitem:disabled {
  color: #6b7280;
}
"""
TOAST_STYLE_CLASS = "remote-toast"
TOAST_CSS = b"""
.remote-toast {
  background-color: rgba(22, 24, 29, 0.85);
  color: #ffffff;
  border-radius: 8px;
  padding: 4px 10px;
}
"""
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
VOLUME_WHEEL = ("KEY_VOLUP", "KEY_VOLDOWN")


def is_primary_press(event):
    return event.type == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_PRIMARY


def rocker_key(spot, index):
    return spot["wheel"][index] if spot is not None and spot["wheel"] else None


def add_css(widget, css, style_class):
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    style = widget.get_style_context()
    style.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    style.add_class(style_class)
    return provider


def remove_source(source_id):
    if source_id is not None:
        GLib.source_remove(source_id)
    return None


def display_size(geometry):
    return round(geometry.width * SKIN_DISPLAY_SCALE), round(geometry.height * SKIN_DISPLAY_SCALE)


def load_photo(path, geometry):
    return GdkPixbuf.Pixbuf.new_from_file(path).scale_simple(
        *display_size(geometry), GdkPixbuf.InterpType.HYPER
    )


def tilted_icon(pixbuf, size):
    angle = math.radians(ICON_ANGLE_DEGREES)
    width, height = pixbuf.get_width(), pixbuf.get_height()
    scale = size / (width * math.cos(angle) + height * math.sin(angle))
    scaled = pixbuf.scale_simple(
        max(1, round(width * scale)), max(1, round(height * scale)), GdkPixbuf.InterpType.HYPER
    )
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    context = cairo.Context(surface)
    context.translate(size / 2, size / 2)
    context.rotate(angle)
    Gdk.cairo_set_source_pixbuf(context, scaled, -scaled.get_width() / 2, -scaled.get_height() / 2)
    context.paint()
    return Gdk.pixbuf_get_from_surface(surface, 0, 0, size, size)


def load_svg(data, geometry):
    loader = GdkPixbuf.PixbufLoader.new_with_type(SVG_LOADER)
    loader.set_size(*display_size(geometry))
    try:
        loader.write(data)
    finally:
        loader.close()
    return loader.get_pixbuf()


class SkinView(Gtk.DrawingArea):
    def __init__(self, pixbuf, geometry, on_press, on_release, on_wheel, on_menu):
        super().__init__()
        self.pixbuf = pixbuf
        self.geometry = geometry
        width, height = pixbuf.get_width(), pixbuf.get_height()
        self.scale_x = width / geometry.width
        self.scale_y = height / geometry.height
        self.on_press = on_press
        self.on_release = on_release
        self.on_wheel = on_wheel
        self.on_menu = on_menu
        self.hovered = None
        self.pressed = None
        self.set_size_request(width, height)
        self.set_has_tooltip(True)
        self.add_events(
            Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
            | Gdk.EventMask.SCROLL_MASK
        )
        self.connect("draw", self.on_draw)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("enter-notify-event", self.on_motion)
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
            context.scale(self.scale_x, self.scale_y)
            trace(context, spot)
            context.set_source_rgba(*(PRESSED_RGBA if self.pressed else HOVER_RGBA))
            context.fill()
        return False

    def spot_at(self, x, y):
        return self.geometry.hotspot_at(x / self.scale_x, y / self.scale_y)

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
        self.set_hovered(self.spot_at(event.x, event.y))
        return False

    def on_leave(self, widget, event):
        if self.pressed is None:
            self.set_hovered(None)
        return False

    def on_button_press(self, widget, event):
        if event.type != Gdk.EventType.BUTTON_PRESS:
            return False
        if event.button == Gdk.BUTTON_SECONDARY:
            self.on_menu(event)
            return True
        if event.button != Gdk.BUTTON_PRIMARY:
            return False
        spot = self.spot_at(event.x, event.y)
        if spot is None:
            self.get_toplevel().begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
            return True
        self.pressed = spot
        self.queue_draw()
        self.on_press(spot)
        return True

    def on_button_release(self, widget, event):
        if self.pressed is None:
            return False
        self.pressed = None
        self.set_hovered(self.spot_at(event.x, event.y))
        self.queue_draw()
        self.on_release()
        return True

    def on_scroll(self, widget, event):
        index = WHEEL_INDEXES.get(event.direction)
        key = None if index is None else rocker_key(self.spot_at(event.x, event.y), index)
        if key is None:
            return False
        self.on_wheel(key)
        return True

    def contains_point(self, x, y):
        allocation = self.get_allocation()
        return 0 <= x < allocation.width and 0 <= y < allocation.height

    def on_query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        spot = self.spot_at(x, y)
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
        self.status_label = Gtk.Label(label=READY_TEXT)
        self.status_label.set_line_wrap(True)
        self.toast_source_id = None
        self.settle_source_id = None
        self.settled_top = None
        self.remote_view = None
        self.transparent = False
        self.clip_rows = None
        self.keypad_open = False
        self.tuck = 0
        self.rest_top = None
        self.open_top = None
        self.slide_tick_id = None
        self.slide_x = None
        self.slide_top = None
        self.slide_origin = None
        self.slide_target = None
        self.slide_started_at = None
        self.context_menu = None
        self.skin, self.keypad = self.load_views(skin_path)
        self.set_window_icon(icon_file)
        content = self.create_grid_view() if self.skin is None else self.create_photo_view()
        content.show_all()
        self.add(content)
        self.place_in_bottom_right_corner()
        self.global_wheel = GlobalWheel(self.on_global_wheel)
        self.add_events(Gdk.EventMask.SCROLL_MASK)
        self.connect("scroll-event", self.on_scroll)
        self.connect("key-press-event", self.on_key_press)
        self.connect("key-release-event", self.on_key_release)
        self.connect("focus-in-event", self.on_focus_in)
        self.connect("focus-out-event", self.on_focus_out)
        self.connect("destroy", self.on_destroy)
        self.worker = threading.Thread(target=self.send_keys, daemon=True)
        self.worker.start()
        self.show_all()

    def set_window_icon(self, icon_file):
        if self.skin is None:
            self.set_icon_from_file(icon_file)
        else:
            self.set_icon_list([tilted_icon(self.skin.pixbuf, size) for size in ICON_SIZES])

    def load_views(self, skin_path):
        if skin_path is None:
            return None, None
        try:
            photo = load_photo(skin_path, REMOTE_SKIN)
            keypad = load_svg(keypad_svg().encode(), KEYPAD)
        except GLib.Error:
            return None, None
        return self.create_view(photo, REMOTE_SKIN), self.create_view(keypad, KEYPAD)

    def create_view(self, pixbuf, geometry):
        return SkinView(
            pixbuf, geometry, self.on_hotspot_pressed, self.stop_repeat, self.queue_key, self.show_context_menu
        )

    def work_area(self):
        display = self.get_display()
        gdk_window = self.get_window()
        if gdk_window is not None:
            return display.get_monitor_at_window(gdk_window).get_workarea()
        return (display.get_primary_monitor() or display.get_monitor(0)).get_workarea()

    def work_area_bottom(self):
        area = self.work_area()
        return area.y + area.height

    def place_in_bottom_right_corner(self):
        area = self.work_area()
        size = self.get_preferred_size().natural_size
        self.move(area.x + area.width - size.width, area.y + area.height - size.height)

    def create_grid_view(self):
        self.set_border_width(BORDER_WIDTH)
        self.status_label.set_xalign(0)
        self.status_label.set_max_width_chars(1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=BORDER_WIDTH)
        box.pack_start(self.create_grid(REMOTE_LAYOUT), False, False, 0)
        box.pack_start(self.status_label, False, False, 0)
        return box

    def create_photo_view(self):
        self.set_decorated(False)
        self.use_transparent_background()
        self.context_menu = self.create_context_menu()
        self.style_toast()
        self.remote_view = Gtk.Overlay()
        self.remote_view.add(self.skin)
        self.remote_view.add_overlay(self.place_keypad())
        self.remote_view.add_overlay(self.status_label)
        self.remote_view.set_overlay_pass_through(self.status_label, True)
        self.show_tuck(self.full_height() - round(KEY_PANEL_BOTTOM * self.skin.scale_y), None)
        self.connect("map", self.on_map)
        self.connect("configure-event", self.on_configure)
        return self.remote_view

    def on_map(self, window):
        self.apply_clip()

    def full_height(self):
        return self.skin.pixbuf.get_height()

    def frame_position(self):
        gdk_window = self.get_window()
        if gdk_window is None:
            return None
        frame = gdk_window.get_frame_extents()
        return frame.x, frame.y

    def show_tuck(self, tuck, top):
        self.tuck = tuck
        self.remote_view.set_margin_top(tuck)
        self.skin.set_size_request(self.skin.pixbuf.get_width(), self.full_height() - tuck)
        self.clip_at(top)

    def clip_at(self, top):
        bottom = self.full_height() if top is None else min(self.full_height(), self.work_area_bottom() - top)
        bottom = max(bottom, self.tuck + MINIMUM_VISIBLE_HEIGHT)
        self.status_label.set_margin_bottom(TOAST_MARGIN + self.full_height() - bottom)
        if (self.tuck, bottom) != self.clip_rows:
            self.clip_rows = (self.tuck, bottom)
            self.apply_clip()

    def apply_clip(self):
        first, end = self.clip_rows
        region = cairo.Region(cairo.RectangleInt(0, first, self.skin.pixbuf.get_width(), end - first))
        self.input_shape_combine_region(region)
        if not self.transparent:
            self.shape_combine_region(region)
        self.queue_draw()

    def animated(self):
        return self.get_mapped() and self.get_settings().get_property(ANIMATIONS_SETTING)

    def current_position(self):
        return (self.slide_x, self.slide_top) if self.slide_tick_id is not None else self.frame_position()

    def slide(self, tuck, top):
        self.slide_x, self.slide_top = self.current_position()
        self.stop_slide()
        self.slide_origin = (self.tuck, self.slide_top)
        self.slide_target = (tuck, top)
        if self.slide_origin == self.slide_target or not self.animated():
            self.land()
            return
        self.slide_started_at = None
        self.slide_tick_id = self.add_tick_callback(self.on_slide_tick)

    def on_slide_tick(self, window, frame_clock):
        now = frame_clock.get_frame_time()
        if self.slide_started_at is None:
            self.slide_started_at = now
        progress = min(1, (now - self.slide_started_at) / SLIDE_DURATION_MICROSECONDS)
        if progress == 1:
            self.slide_tick_id = None
            self.land()
            return GLib.SOURCE_REMOVE
        eased = progress * progress * (3 - 2 * progress)
        steps = zip(self.slide_origin, self.slide_target)
        self.show_slide(*(round(start + (end - start) * eased) for start, end in steps))
        return GLib.SOURCE_CONTINUE

    def show_slide(self, tuck, top):
        if top != self.slide_top:
            self.slide_top = top
            self.move(self.slide_x, top)
        self.show_tuck(tuck, top)

    def land(self):
        self.show_slide(*self.slide_target)
        self.keypad.set_visible(self.keypad_open)
        if self.keypad_open:
            self.open_top = self.slide_top

    def stop_slide(self):
        if self.slide_tick_id is not None:
            self.remove_tick_callback(self.slide_tick_id)
            self.slide_tick_id = None

    def overflow(self, top):
        return top + self.full_height() - self.work_area_bottom()

    def untuck_away_from_the_edge(self, top):
        if not self.keypad_open and self.tuck and self.overflow(top) < -UNTUCK_DISTANCE:
            self.slide(0, top)

    def on_configure(self, window, event):
        if self.slide_tick_id is None:
            top = self.frame_position()[1]
            self.clip_at(top)
            if self.dragging():
                self.untuck_away_from_the_edge(top)
        self.settle_source_id = remove_source(self.settle_source_id)
        self.settle_source_id = GLib.timeout_add(SETTLE_DELAY_MS, self.settle)
        return False

    def dragging(self):
        gdk_window = self.get_window()
        if gdk_window is None:
            return False
        pointer = self.get_display().get_default_seat().get_pointer()
        return bool(gdk_window.get_device_position(pointer).mask & Gdk.ModifierType.BUTTON1_MASK)

    def settle(self):
        self.settle_source_id = None
        if self.slide_tick_id is not None:
            return False
        if self.dragging():
            self.settle_source_id = GLib.timeout_add(SETTLE_DELAY_MS, self.settle)
            return False
        position = self.frame_position()
        if position is None or position[1] == self.settled_top:
            return False
        top = self.settled_top = position[1]
        if not self.keypad_open:
            self.untuck_away_from_the_edge(top)
        elif top != self.open_top:
            self.rest_top = top
            self.slide(0, top - max(0, self.overflow(top)))
        return False

    def place_keypad(self):
        origin_x, origin_y = KEYPAD.origin
        self.keypad.set_halign(Gtk.Align.START)
        self.keypad.set_valign(Gtk.Align.START)
        self.keypad.set_margin_start(round(origin_x * self.skin.scale_x))
        self.keypad.set_margin_top(round(origin_y * self.skin.scale_y))
        self.keypad.set_no_show_all(True)
        return self.keypad

    def use_transparent_background(self):
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is None or not screen.is_composited():
            return
        self.transparent = True
        self.set_visual(visual)
        self.set_app_paintable(True)
        self.connect("draw", self.on_draw_background)
        self.connect_after("draw", self.on_draw_clip)

    def on_draw_background(self, window, context):
        context.set_operator(cairo.OPERATOR_CLEAR)
        context.paint()
        context.set_operator(cairo.OPERATOR_OVER)
        return False

    def on_draw_clip(self, window, context):
        end = self.clip_rows[1]
        context.set_operator(cairo.OPERATOR_CLEAR)
        context.rectangle(0, end, self.skin.pixbuf.get_width(), self.full_height() - end)
        context.fill()
        context.set_operator(cairo.OPERATOR_OVER)
        return False

    def create_context_menu(self):
        menu = Gtk.Menu()
        provider = add_css(menu, MENU_CSS, MENU_STYLE_CLASS)
        item = Gtk.MenuItem(label=CLOSE_TEXT)
        item.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        item.connect("activate", self.on_close_activated)
        menu.append(item)
        menu.attach_to_widget(self)
        menu.show_all()
        return menu

    def show_context_menu(self, event):
        self.context_menu.popup_at_pointer(event)

    def on_close_activated(self, item):
        self.close()

    def style_toast(self):
        label = self.status_label
        label.set_justify(Gtk.Justification.CENTER)
        label.set_max_width_chars(TOAST_MAX_WIDTH_CHARS)
        label.set_halign(Gtk.Align.CENTER)
        label.set_valign(Gtk.Align.END)
        label.set_property("margin", TOAST_MARGIN)
        label.set_no_show_all(True)
        add_css(label, TOAST_CSS, TOAST_STYLE_CLASS)

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
        if self.keypad is None:
            return
        self.keypad_open = not self.keypad_open
        top = self.current_position()[1]
        if not self.keypad_open:
            self.slide(self.rest_top - top, top)
            return
        self.keypad.show()
        if self.slide_tick_id is None:
            self.rest_top = top + self.tuck
        self.slide(0, top - max(0, self.overflow(top)))

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
        self.repeat_source_id = remove_source(self.repeat_source_id)

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

    def on_focus_in(self, window, event):
        self.global_wheel.grab()
        return False

    def on_focus_out(self, window, event):
        self.global_wheel.release()
        self.pressed_keyvals.clear()
        self.stop_repeat()
        return False

    def on_scroll(self, window, event):
        index = WHEEL_INDEXES.get(event.direction)
        if index is None:
            return False
        self.queue_key(VOLUME_WHEEL[index])
        return True

    def on_global_wheel(self, index, root_x, root_y):
        self.queue_key(self.rocker_key_at(index, root_x, root_y) or VOLUME_WHEEL[index])

    def rocker_key_at(self, index, root_x, root_y):
        skin_window = self.skin.get_window() if self.skin is not None else None
        if skin_window is None:
            return None
        _, origin_x, origin_y = skin_window.get_origin()
        scale = self.get_scale_factor()
        x, y = root_x / scale - origin_x, root_y / scale - origin_y
        if not self.skin.contains_point(x, y):
            return None
        return rocker_key(self.skin.spot_at(x, y), index)

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
                GLib.idle_add(self.show_status, CONNECTING_TEXT, True)
            try:
                send(self.tv, key)
            except Exception as ex:
                self.drop_pending_keys()
                GLib.idle_add(self.show_status, f"Échec{NBSP}: {str(ex) or type(ex).__name__}")
                continue
            GLib.idle_add(self.show_status, READY_TEXT)
        self.tv.close_remote()

    def show_status(self, text, in_progress=False):
        if self.closed:
            return False
        if self.status_label.get_label() != text:
            self.status_label.set_label(text)
        if self.skin is not None:
            self.update_toast(text != READY_TEXT, in_progress)
        return False

    def update_toast(self, visible, in_progress):
        self.toast_source_id = remove_source(self.toast_source_id)
        self.status_label.set_visible(visible)
        if visible and not in_progress:
            self.toast_source_id = GLib.timeout_add(TOAST_HIDE_DELAY_MS, self.hide_toast)

    def hide_toast(self):
        self.toast_source_id = None
        self.status_label.hide()
        return False

    def on_destroy(self, window):
        self.closed = True
        self.global_wheel.release()
        self.stop_slide()
        self.stop_repeat()
        self.toast_source_id = remove_source(self.toast_source_id)
        self.settle_source_id = remove_source(self.settle_source_id)
        self.drop_pending_keys()
        self.keys.put(STOP_SIGNAL)
