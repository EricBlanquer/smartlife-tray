import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import remote_window
import smartlife_tray as tray
from remote_layout import COLUMNS, POWER_ACTION, REMOTE_KEYS, REMOTE_LAYOUT
from remote_window import Gdk, GLib, RemoteWindow

WAIT_SECONDS = 2
WAIT_STEP_SECONDS = 0.005


def drain_events():
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)


def wait_until(condition):
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        drain_events()
        if condition():
            return True
        time.sleep(WAIT_STEP_SECONDS)
    return False


def key_event(name, state=0):
    return SimpleNamespace(keyval=Gdk.keyval_from_name(name), state=state)


class RemoteLayoutTests(unittest.TestCase):
    def cells(self):
        return [cell for row in REMOTE_LAYOUT for cell in row if cell is not None]

    def test_rows_fill_the_grid_and_keys_are_unique(self):
        self.assertTrue(all(len(row) == COLUMNS for row in REMOTE_LAYOUT))
        keys = [cell["key"] for cell in self.cells()]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertNotIn(POWER_ACTION, REMOTE_KEYS)
        self.assertEqual(REMOTE_KEYS, set(keys) - {POWER_ACTION})
        self.assertTrue(all(key.startswith("KEY_") for key in REMOTE_KEYS))

    def test_shortcuts_are_valid_and_never_shared(self):
        gtk_names = [name for cell in self.cells() for name in cell["gtk_keys"]]
        web_names = [name for cell in self.cells() for name in cell["web_keys"]]
        self.assertEqual(len(gtk_names), len(set(gtk_names)))
        self.assertEqual(len(web_names), len(set(web_names)))
        for name in gtk_names:
            with self.subTest(name=name):
                self.assertNotEqual(Gdk.keyval_from_name(name), Gdk.KEY_VoidSymbol)
        power = next(cell for cell in self.cells() if cell["key"] == POWER_ACTION)
        self.assertEqual((power["gtk_keys"], power["web_keys"]), ([], []))


class RemoteWindowTests(unittest.TestCase):
    def setUp(self):
        self.tv = Mock()
        self.tv.remote_open = True
        self.on_power = Mock()
        self.window = RemoteWindow(self.tv, self.on_power, tray.ICON_FILE)
        self.addCleanup(self.close_window)

    def close_window(self):
        if not self.window.closed:
            self.window.destroy()
        self.window.worker.join(WAIT_SECONDS)
        drain_events()

    def sent_keys(self):
        return [entry.args[0] for entry in self.tv.send_key.call_args_list]

    def test_buttons_send_their_key_and_power_uses_the_toggle(self):
        self.window.buttons["KEY_ENTER"].clicked()
        self.window.buttons["KEY_MUTE"].clicked()
        self.window.buttons[POWER_ACTION].clicked()
        self.assertTrue(wait_until(lambda: self.tv.send_key.call_count == 2))
        self.assertEqual(self.sent_keys(), ["KEY_ENTER", "KEY_MUTE"])
        self.on_power.assert_called_once_with()

    def test_buttons_never_take_keyboard_focus(self):
        self.assertFalse(any(button.get_can_focus() for button in self.window.buttons.values()))

    def test_keyboard_shortcuts_follow_the_repeat_policy(self):
        self.assertTrue(self.window.on_key_press(self.window, key_event("Up")))
        self.assertTrue(self.window.on_key_press(self.window, key_event("Up")))
        self.assertTrue(self.window.on_key_press(self.window, key_event("Return")))
        self.assertTrue(self.window.on_key_press(self.window, key_event("Return")))
        self.window.on_key_release(self.window, key_event("Return"))
        self.assertTrue(self.window.on_key_press(self.window, key_event("KP_Enter")))
        self.assertTrue(self.window.on_key_press(self.window, key_event("M")))
        self.assertTrue(wait_until(lambda: self.tv.send_key.call_count == 5))
        self.assertEqual(self.sent_keys(), ["KEY_UP", "KEY_UP", "KEY_ENTER", "KEY_ENTER", "KEY_MUTE"])

    def test_unmapped_and_modified_keys_are_left_to_the_desktop(self):
        self.assertFalse(self.window.on_key_press(self.window, key_event("q")))
        self.assertFalse(self.window.on_key_press(
            self.window, key_event("m", Gdk.ModifierType.CONTROL_MASK)
        ))
        self.assertTrue(self.window.on_key_press(
            self.window, key_event("plus", Gdk.ModifierType.SHIFT_MASK)
        ))
        self.assertTrue(wait_until(lambda: self.tv.send_key.call_count == 1))
        self.assertEqual(self.sent_keys(), ["KEY_VOLUP"])

    def test_focus_loss_forgets_held_keys(self):
        self.window.on_key_press(self.window, key_event("Return"))
        self.window.on_focus_out(self.window, None)
        self.window.on_key_press(self.window, key_event("Return"))
        self.assertTrue(wait_until(lambda: self.tv.send_key.call_count == 2))

    def test_held_button_repeats_until_release(self):
        press = SimpleNamespace(type=Gdk.EventType.BUTTON_PRESS, button=Gdk.BUTTON_PRIMARY)
        with (
            patch.object(remote_window, "REPEAT_DELAY_MS", 20),
            patch.object(remote_window, "REPEAT_INTERVAL_MS", 10),
        ):
            button = self.window.buttons["KEY_VOLUP"]
            self.window.on_repeat_button_pressed(button, press, "KEY_VOLUP")
            self.assertTrue(wait_until(lambda: self.tv.send_key.call_count >= 4))
            self.window.on_repeat_button_released(button, press)
        count = self.tv.send_key.call_count
        time.sleep(0.05)
        drain_events()
        self.assertLessEqual(self.tv.send_key.call_count, count + 1)
        self.assertIsNone(self.window.repeat_source_id)
        self.assertEqual(set(self.sent_keys()), {"KEY_VOLUP"})

    def test_double_click_events_do_not_restart_the_repeat(self):
        double = SimpleNamespace(type=Gdk.EventType._2BUTTON_PRESS, button=Gdk.BUTTON_PRIMARY)
        secondary = SimpleNamespace(type=Gdk.EventType.BUTTON_PRESS, button=Gdk.BUTTON_SECONDARY)
        button = self.window.buttons["KEY_UP"]
        self.window.on_repeat_button_pressed(button, double, "KEY_UP")
        self.window.on_repeat_button_pressed(button, secondary, "KEY_UP")
        drain_events()
        self.assertIsNone(self.window.repeat_source_id)
        self.assertTrue(self.window.keys.empty())

    def test_failure_is_shown_and_drops_queued_keys(self):
        started = []

        def fail(key):
            started.append(key)
            if len(started) == 1:
                time.sleep(0.05)
                raise OSError("network unavailable")

        self.tv.send_key.side_effect = fail
        for key in ("KEY_UP", "KEY_DOWN", "KEY_LEFT"):
            self.window.queue_key(key)
        self.assertTrue(wait_until(
            lambda: self.window.status_label.get_label() == "Échec : network unavailable"
        ))
        self.assertEqual(started, ["KEY_UP"])
        self.window.queue_key("KEY_RIGHT")
        self.assertTrue(wait_until(lambda: self.window.status_label.get_label() == "Prêt"))
        self.assertEqual(started, ["KEY_UP", "KEY_RIGHT"])

    def test_first_key_announces_the_connection(self):
        self.tv.remote_open = False
        statuses = []
        original = self.window.show_status

        def record(text):
            statuses.append(text)
            return original(text)

        self.window.show_status = record
        self.window.queue_key("KEY_UP")
        self.assertTrue(wait_until(lambda: "Prêt" in statuses))
        self.assertEqual(statuses, ["Connexion à la TV…", "Prêt"])

    def test_full_queue_drops_extra_keys(self):
        self.tv.send_key.side_effect = lambda key: time.sleep(0.2)
        for _ in range(remote_window.QUEUE_LIMIT + 5):
            self.window.queue_key("KEY_UP")
        self.assertLessEqual(self.window.keys.qsize(), remote_window.QUEUE_LIMIT)

    def test_closing_stops_the_worker_and_releases_the_connection(self):
        self.window.destroy()
        self.window.worker.join(WAIT_SECONDS)
        self.assertFalse(self.window.worker.is_alive())
        self.tv.close_remote.assert_called_once_with()
        self.assertFalse(self.window.show_status("late status"))


class TrayRemoteTests(unittest.TestCase):
    def setUp(self):
        self.app = tray.TrayApplication.__new__(tray.TrayApplication)
        self.app.devices = []
        self.app.device_widgets = {}
        self.app.menu = tray.Gtk.Menu()
        self.app.tv_busy = False
        self.app.remote_window = None
        self.app.tv = Mock(spec=tray.Television)
        self.app.tv.configured = True
        self.app.tv.is_on = True
        self.app.tv.remote_open = True
        self.app.status_label = None
        self.app.busy = False
        self.errors = []
        self.app.report_error = self.errors.append
        self.app.build_menu()
        self.addCleanup(self.app.menu.destroy)
        self.addCleanup(self.close_remote_window)
        settle = patch.object(tray, "COMMAND_SETTLE_SECONDS", 0)
        settle.start()
        self.addCleanup(settle.stop)

    def close_remote_window(self):
        window = self.app.remote_window
        if window is not None:
            window.destroy()
            window.worker.join(WAIT_SECONDS)
        drain_events()

    def test_remote_item_opens_a_single_window(self):
        self.app.tv_remote_item.activate()
        window = self.app.remote_window
        self.assertIsInstance(window, RemoteWindow)
        self.app.tv_remote_item.activate()
        self.assertIs(self.app.remote_window, window)
        window.destroy()
        window.worker.join(WAIT_SECONDS)
        self.assertIsNone(self.app.remote_window)

    def test_remote_item_requires_a_configured_tv(self):
        self.app.sync_tv_widgets()
        self.assertTrue(self.app.tv_remote_item.get_sensitive())
        self.app.tv.configured = False
        self.app.sync_tv_widgets()
        self.assertFalse(self.app.tv_remote_item.get_sensitive())

    def test_remote_power_toggles_from_the_real_state_and_reports_progress(self):
        self.app.tv_remote_item.activate()
        window = self.app.remote_window
        self.app.run_background = lambda work: work()
        window.buttons[POWER_ACTION].clicked()
        drain_events()
        self.app.tv.toggle_power.assert_called_once_with()
        self.app.tv.set_power.assert_not_called()
        self.assertEqual(window.status_label.get_label(), "Commande envoyée")
        self.assertEqual(self.app.tv_status_item.get_label(), "Commande envoyée")
        self.assertFalse(self.app.tv_busy)

    def test_remote_power_failure_is_visible_in_the_window(self):
        self.app.tv_remote_item.activate()
        self.app.run_background = lambda work: work()
        self.app.tv.toggle_power.side_effect = TimeoutError("not confirmed")
        self.app.remote_window.buttons[POWER_ACTION].clicked()
        drain_events()
        self.assertEqual(self.app.remote_window.status_label.get_label(), "Échec de la commande")
        self.assertIn("not confirmed", self.errors[-1])

    def test_power_click_while_busy_is_ignored(self):
        self.app.tv_busy = True
        self.app.toggle_tv_power()
        self.app.tv.toggle_power.assert_not_called()


if __name__ == "__main__":
    unittest.main()
