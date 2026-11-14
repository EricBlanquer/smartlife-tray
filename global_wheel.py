import gi

gi.require_version("GLib", "2.0")

from gi.repository import GLib
from Xlib import X, display, error

WHEEL_BUTTONS = {4: 0, 5: 1}


class GlobalWheel:
    def __init__(self, on_wheel):
        self.on_wheel = on_wheel
        self.connection = None
        self.watch_id = None

    def grab(self):
        if self.connection is not None:
            return True
        try:
            connection = display.Display()
        except (error.DisplayError, OSError):
            return False
        refused = error.CatchError(error.BadAccess)
        root = connection.screen().root
        for button in WHEEL_BUTTONS:
            root.grab_button(
                button, X.AnyModifier, False, X.ButtonPressMask, X.GrabModeAsync, X.GrabModeAsync,
                X.NONE, X.NONE, onerror=refused,
            )
        connection.sync()
        if refused.get_error():
            connection.close()
            return False
        self.connection = connection
        self.watch_id = GLib.io_add_watch(connection.fileno(), GLib.IO_IN, self.on_events)
        return True

    def release(self):
        if self.connection is None:
            return
        GLib.source_remove(self.watch_id)
        self.connection.close()
        self.connection = None
        self.watch_id = None

    def on_events(self, source, condition):
        try:
            while self.connection.pending_events():
                self.dispatch(self.connection.next_event())
        except error.ConnectionClosedError:
            self.watch_id = None
            self.connection = None
            return False
        return True

    def dispatch(self, event):
        if event.type == X.ButtonPress and event.detail in WHEEL_BUTTONS:
            self.on_wheel(WHEEL_BUTTONS[event.detail], event.root_x, event.root_y)
