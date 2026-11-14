import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import remote_window
import smartlife_tray as tray
from remote_keypad import KEYPAD, KEYPAD_HOTSPOTS, center
from remote_layout import (
    ACTIONS,
    DIGIT_ROWS,
    KEYPAD_FUNCTION_ROWS,
    KEYS,
    LAYOUT_COLUMNS,
    PANEL_ACTION,
    PLAY_PAUSE_KEY,
    POWER_ACTION,
    REMOTE_KEYS,
    REMOTE_LAYOUT,
)
from remote_skin import HOTSPOTS, SKIN_HEIGHT, SKIN_WIDTH
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


def make_skin(directory):
    path = os.path.join(directory, "remote-skin.png")
    remote_window.GdkPixbuf.Pixbuf.new(
        remote_window.GdkPixbuf.Colorspace.RGB, True, 8, SKIN_WIDTH, SKIN_HEIGHT
    ).savev(path, "png", [], [])
    return path


def press_event(x, y, button=Gdk.BUTTON_PRIMARY, event_type=Gdk.EventType.BUTTON_PRESS):
    return SimpleNamespace(x=x, y=y, x_root=x + 1000.5, y_root=y + 500.5, time=42, button=button, type=event_type)


def frame_corner(window):
    gdk_window = window.get_window()
    if gdk_window is None or not window.get_mapped():
        return None
    frame = gdk_window.get_frame_extents()
    return frame.x + frame.width, frame.y + frame.height


def work_area_corner(window):
    display = window.get_display()
    area = (display.get_primary_monitor() or display.get_monitor(0)).get_workarea()
    return area.x + area.width, area.y + area.height


class CornerPlacementTests(unittest.TestCase):
    def open_window(self, skin_path):
        tv = Mock()
        tv.remote_open = True
        window = RemoteWindow(tv, Mock(), tray.ICON_FILE, skin_path)
        self.addCleanup(window.worker.join, WAIT_SECONDS)
        self.addCleanup(window.destroy)
        return window

    def test_window_opens_against_the_bottom_right_corner_of_the_work_area(self):
        with tempfile.TemporaryDirectory() as directory:
            for skin_path in (None, make_skin(directory)):
                with self.subTest(photo=skin_path is not None):
                    window = self.open_window(skin_path)
                    self.assertEqual(window.get_gravity(), Gdk.Gravity.SOUTH_EAST)
                    self.assertTrue(wait_until(lambda: frame_corner(window) == work_area_corner(window)))


class RemoteLayoutTests(unittest.TestCase):
    def cells(self, layout):
        return [cell for row in layout for cell in row if cell is not None]

    def test_grids_are_complete_and_keys_are_unique(self):
        for layout in (REMOTE_LAYOUT, KEYPAD_FUNCTION_ROWS + DIGIT_ROWS):
            with self.subTest(layout=len(layout)):
                self.assertTrue(all(len(row) == LAYOUT_COLUMNS for row in layout))
                keys = [cell["key"] for cell in self.cells(layout)]
                self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(key.startswith("KEY_") or KEYS[key]["app"] for key in REMOTE_KEYS))
        self.assertTrue(all(KEYS[key]["app"] is None for key in REMOTE_KEYS if key.startswith("KEY_")))
        self.assertEqual(REMOTE_KEYS | ACTIONS, set(KEYS))

    def test_every_key_is_reachable_without_the_photo(self):
        grid_keys = {cell["key"] for cell in self.cells(REMOTE_LAYOUT)}
        self.assertEqual(grid_keys, set(KEYS) - {PANEL_ACTION})

    def test_every_key_is_reachable_with_the_photo(self):
        reachable = {spot["key"] for spot in HOTSPOTS + KEYPAD_HOTSPOTS}
        self.assertEqual(reachable, set(KEYS))

    def test_shortcuts_are_valid_and_never_shared(self):
        gtk_names = [name for cell in KEYS.values() for name in cell["gtk_keys"]]
        web_names = [name for cell in KEYS.values() for name in cell["web_keys"]]
        self.assertEqual(len(gtk_names), len(set(gtk_names)))
        self.assertEqual(len(web_names), len(set(web_names)))
        for name in gtk_names:
            with self.subTest(name=name):
                self.assertNotEqual(Gdk.keyval_from_name(name), Gdk.KEY_VoidSymbol)

    def test_requested_keyboard_mapping(self):
        expected = {
            POWER_ACTION: (["XF86Sleep"], ["Standby"]),
            "KEY_MENU": (["XF86HomePage"], ["BrowserHome"]),
            PLAY_PAUSE_KEY: (["space"], [" "]),
            "KEY_CH_LIST": (["c"], ["c"]),
            "KEY_CHUP": (["Page_Up"], ["PageUp"]),
            "KEY_CHDOWN": (["Page_Down"], ["PageDown"]),
        }
        for key, (gtk_keys, web_keys) in expected.items():
            with self.subTest(key=key):
                self.assertEqual((KEYS[key]["gtk_keys"], KEYS[key]["web_keys"]), (gtk_keys, web_keys))


class RemoteWindowTests(unittest.TestCase):
    def setUp(self):
        self.tv = Mock()
        self.tv.remote_open = True
        self.on_power = Mock()
        self.window = RemoteWindow(self.tv, self.on_power, tray.ICON_FILE, None)
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

        def record(text, in_progress=False):
            statuses.append(text)
            return original(text, in_progress)

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


class SkinWindowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.tv = Mock()
        self.tv.remote_open = True
        self.on_power = Mock()
        self.window = RemoteWindow(self.tv, self.on_power, tray.ICON_FILE, make_skin(self.directory.name))
        self.addCleanup(self.close_window)

    def close_window(self):
        if not self.window.closed:
            self.window.destroy()
        self.window.worker.join(WAIT_SECONDS)
        drain_events()

    def sent_keys(self):
        return [entry.args[0] for entry in self.tv.send_key.call_args_list]

    def point(self, x, y, view=None):
        view = view or self.window.skin
        return {"x": x * view.scale_x, "y": y * view.scale_y}

    def press(self, x, y, view=None, **kwargs):
        view = view or self.window.skin
        position = self.point(x, y, view)
        return view.on_button_press(view, press_event(position["x"], position["y"], **kwargs))

    def release(self, x, y, view=None):
        view = view or self.window.skin
        position = self.point(x, y, view)
        return view.on_button_release(view, press_event(position["x"], position["y"]))

    def scroll(self, x, y, direction):
        return self.window.skin.on_scroll(self.window.skin, SimpleNamespace(**self.point(x, y), direction=direction))

    def click(self, x, y, view=None):
        self.press(x, y, view)
        self.release(x, y, view)

    def test_photo_is_shown_reduced_without_margins(self):
        size = (round(SKIN_WIDTH * remote_window.SKIN_DISPLAY_SCALE), round(SKIN_HEIGHT * remote_window.SKIN_DISPLAY_SCALE))
        self.assertEqual(self.window.skin.get_size_request(), size)
        self.assertEqual((self.window.skin.pixbuf.get_width(), self.window.skin.pixbuf.get_height()), size)
        self.assertEqual(self.window.get_border_width(), 0)
        drain_events()
        self.assertEqual(self.window.get_size(), size)

    def test_photo_replaces_the_grid_and_hides_the_extra_keys(self):
        self.assertIsNotNone(self.window.skin)
        self.assertFalse(self.window.panel.get_reveal_child())
        self.assertEqual(self.window.buttons, {})
        self.assertIs(self.window.panel.get_child(), self.window.keypad)

    def test_drawn_keypad_sends_its_keys(self):
        keypad = self.window.keypad
        size = (round(KEYPAD.width * remote_window.KEYPAD_DISPLAY_SCALE), round(KEYPAD.height * remote_window.KEYPAD_DISPLAY_SCALE))
        self.assertEqual((keypad.pixbuf.get_width(), keypad.pixbuf.get_height()), size)
        for count, spot in enumerate(KEYPAD_HOTSPOTS, start=1):
            self.click(*center(spot), view=keypad)
            self.assertTrue(wait_until(lambda: self.tv.send_key.call_count == count))
        self.assertEqual(self.sent_keys(), [spot["key"] for spot in KEYPAD_HOTSPOTS])
        self.assertIsNone(KEYPAD.hotspot_at(5, 5))

    def test_hotspots_send_their_keys(self):
        for x, y in ((170, 272), (270, 372), (170, 472), (70, 372), (170, 372), (70, 551), (170, 580), (270, 550)):
            self.click(x, y)
        self.assertTrue(wait_until(lambda: self.tv.send_key.call_count == 8))
        self.assertEqual(self.sent_keys(), [
            "KEY_UP", "KEY_RIGHT", "KEY_DOWN", "KEY_LEFT", "KEY_ENTER", "KEY_RETURN", "KEY_HOME", PLAY_PAUSE_KEY,
        ])

    def test_rocker_presses_mute_and_open_the_guide_without_repeating(self):
        with (
            patch.object(remote_window, "REPEAT_DELAY_MS", 20),
            patch.object(remote_window, "REPEAT_INTERVAL_MS", 10),
        ):
            self.press(100, 673)
            time.sleep(0.08)
            drain_events()
            self.release(100, 673)
            self.click(240, 673)
        self.assertTrue(wait_until(lambda: self.tv.send_key.call_count == 2))
        self.assertEqual(self.sent_keys(), ["KEY_MUTE", "KEY_GUIDE"])

    def test_app_hotspots_launch_netflix_and_prime_video(self):
        self.click(68, 784)
        self.click(169, 784)
        self.assertTrue(wait_until(lambda: self.tv.launch_app.call_count == 2))
        self.assertEqual(
            [entry.args[0] for entry in self.tv.launch_app.call_args_list], ["3201907018807", "3201512006785"]
        )
        self.click(270, 193)
        self.assertTrue(wait_until(lambda: self.tv.send_key.call_count == 1))
        self.assertEqual(self.sent_keys(), ["KEY_AMBIENT"])

    def test_power_and_123_hotspots_trigger_their_actions(self):
        self.click(77, 60)
        self.on_power.assert_called_once_with()
        self.click(70, 196)
        self.assertTrue(self.window.panel.get_reveal_child())
        self.click(70, 196)
        self.assertFalse(self.window.panel.get_reveal_child())
        drain_events()
        self.tv.send_key.assert_not_called()

    def test_inert_areas_and_other_buttons_do_nothing(self):
        with patch.object(self.window, "begin_move_drag"), patch.object(self.window.context_menu, "popup_at_pointer"):
            for x, y in ((170, 225), (300, 120), (5, 5)):
                self.assertFalse(self.press(x, y, button=Gdk.BUTTON_MIDDLE))
                self.assertFalse(self.press(x, y, event_type=Gdk.EventType._2BUTTON_PRESS))
        drain_events()
        self.tv.send_key.assert_not_called()

    def test_photo_window_has_no_title_bar(self):
        self.assertFalse(self.window.get_decorated())

    def test_dragging_outside_the_keys_moves_the_window(self):
        with patch.object(self.window, "begin_move_drag") as move:
            self.assertTrue(self.press(170, 225))
            self.assertTrue(self.press(5, 5, self.window.keypad))
        position = self.point(170, 225)
        self.assertEqual(move.call_args_list[0].args, (Gdk.BUTTON_PRIMARY, int(position["x"] + 1000.5), int(position["y"] + 500.5), 42))
        self.assertEqual(move.call_count, 2)
        self.assertIsNone(self.window.skin.pressed)
        drain_events()
        self.tv.send_key.assert_not_called()

    def test_right_click_offers_to_close_the_remote(self):
        with patch.object(self.window.context_menu, "popup_at_pointer") as popup:
            self.assertTrue(self.press(170, 372, button=Gdk.BUTTON_SECONDARY))
            self.assertTrue(self.press(5, 5, self.window.keypad, button=Gdk.BUTTON_SECONDARY))
        self.assertEqual(popup.call_count, 2)
        items = self.window.context_menu.get_children()
        self.assertEqual([item.get_label() for item in items], ["Fermer la télécommande"])
        items[0].activate()
        self.assertTrue(wait_until(lambda: self.window.closed))
        drain_events()
        self.tv.send_key.assert_not_called()

    def test_wheel_over_volume_and_channels(self):
        for x, y, direction in (
            (100, 640, Gdk.ScrollDirection.UP), (100, 710, Gdk.ScrollDirection.DOWN), (100, 673, Gdk.ScrollDirection.UP),
            (240, 710, Gdk.ScrollDirection.UP), (240, 640, Gdk.ScrollDirection.DOWN), (240, 673, Gdk.ScrollDirection.DOWN),
        ):
            self.assertTrue(self.scroll(x, y, direction))
        self.assertFalse(self.scroll(170, 372, Gdk.ScrollDirection.UP))
        self.assertTrue(wait_until(lambda: self.tv.send_key.call_count == 6))
        self.assertEqual(self.sent_keys(), [
            "KEY_VOLUP", "KEY_VOLDOWN", "KEY_VOLUP", "KEY_CHUP", "KEY_CHDOWN", "KEY_CHDOWN",
        ])

    def test_held_volume_hotspot_repeats_until_release(self):
        with (
            patch.object(remote_window, "REPEAT_DELAY_MS", 20),
            patch.object(remote_window, "REPEAT_INTERVAL_MS", 10),
        ):
            self.press(100, 640)
            self.assertIsNotNone(self.window.skin.pressed)
            self.assertTrue(wait_until(lambda: self.tv.send_key.call_count >= 4))
            self.release(100, 640)
        self.assertIsNone(self.window.repeat_source_id)
        self.assertIsNone(self.window.skin.pressed)
        self.assertEqual(set(self.sent_keys()), {"KEY_VOLUP"})

    def test_hover_and_tooltip_follow_the_hotspots(self):
        tooltip = Mock()
        self.window.skin.on_motion(self.window.skin, SimpleNamespace(**self.point(170, 580)))
        self.assertEqual(self.window.skin.hovered["key"], "KEY_HOME")
        home = self.point(170, 580)
        self.assertTrue(self.window.skin.on_query_tooltip(self.window.skin, home["x"], home["y"], False, tooltip))
        tooltip.set_text.assert_called_once_with("Accueil")
        self.window.skin.on_leave(self.window.skin, None)
        self.assertIsNone(self.window.skin.hovered)
        inert = self.point(170, 225)
        self.assertFalse(self.window.skin.on_query_tooltip(self.window.skin, inert["x"], inert["y"], False, tooltip))

    def test_status_appears_over_the_photo_only_when_useful(self):
        toast = self.window.status_label
        self.assertFalse(toast.get_visible())
        self.assertTrue(toast.get_parent().get_overlay_pass_through(toast))
        with patch.object(remote_window, "TOAST_HIDE_DELAY_MS", 20):
            self.window.show_status("Connexion à la TV…", True)
            self.assertTrue(toast.get_visible())
            time.sleep(0.05)
            drain_events()
            self.assertTrue(toast.get_visible())
            self.window.show_status("Prêt")
            self.assertFalse(toast.get_visible())
            self.window.show_status("Échec : network unavailable")
            self.assertTrue(toast.get_visible())
            self.assertEqual(toast.get_label(), "Échec : network unavailable")
            self.assertTrue(wait_until(lambda: not toast.get_visible()))
        self.assertIsNone(self.window.toast_source_id)

    def test_closing_cancels_the_pending_status_timeout(self):
        self.window.show_status("Commande envoyée")
        self.assertIsNotNone(self.window.toast_source_id)
        self.window.destroy()
        self.assertIsNone(self.window.toast_source_id)

    def test_keyboard_actions_work_with_the_photo(self):
        self.assertTrue(self.window.on_key_press(self.window, key_event("XF86Sleep")))
        self.on_power.assert_called_once_with()
        self.assertTrue(self.window.on_key_press(self.window, key_event("XF86Sleep")))
        self.on_power.assert_called_once_with()
        for name in ("space", "XF86HomePage", "c"):
            self.assertTrue(self.window.on_key_press(self.window, key_event(name)))
        self.assertTrue(wait_until(lambda: self.tv.send_key.call_count == 3))
        self.assertEqual(self.sent_keys(), [PLAY_PAUSE_KEY, "KEY_MENU", "KEY_CH_LIST"])

    def test_unreadable_photo_falls_back_to_the_grid(self):
        broken = os.path.join(self.directory.name, "broken.png")
        with open(broken, "wb") as handle:
            handle.write(b"not a png")
        window = RemoteWindow(self.tv, self.on_power, tray.ICON_FILE, broken)
        self.addCleanup(window.worker.join, WAIT_SECONDS)
        self.addCleanup(window.destroy)
        self.assertIsNone(window.skin)
        self.assertIn("KEY_UP", window.buttons)
        self.assertTrue(window.get_decorated())


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
        skin = patch.object(tray, "skin_file", return_value=None)
        self.skin_file = skin.start()
        self.addCleanup(skin.stop)
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

    def test_remote_item_uses_the_photo_from_the_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            self.skin_file.return_value = make_skin(directory)
            self.app.tv_remote_item.activate()
            self.skin_file.assert_called_once_with()
            self.assertIsNotNone(self.app.remote_window.skin)

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
