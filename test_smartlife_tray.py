import threading
import unittest
from unittest.mock import Mock, patch

import smartlife_tray as tray


class TelevisionMenuTests(unittest.TestCase):
    def setUp(self):
        self.app = tray.TrayApplication.__new__(tray.TrayApplication)
        self.app.devices = []
        self.app.device_widgets = {}
        self.app.menu = tray.Gtk.Menu()
        self.app.tv_busy = False
        self.app.remote_window = None
        self.app.tv = Mock(spec=tray.Television)
        self.app.tv.configured = True
        self.app.tv.is_on = None
        self.app.status_label = None
        self.app.busy = False
        self.errors = []
        self.app.report_error = self.errors.append
        self.app.build_menu()
        self.addCleanup(self.app.menu.destroy)
        settle = patch.object(tray, "COMMAND_SETTLE_SECONDS", 0)
        settle.start()
        self.addCleanup(settle.stop)

    def drain_events(self):
        context = tray.GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

    def test_known_power_state_offers_the_opposite_action(self):
        for state, enabled in ((True, False), (False, True)):
            with self.subTest(state=state):
                self.app.tv.is_on = state
                self.app.sync_tv_widgets()
                self.assertTrue(self.app.tv_power_items[enabled].get_sensitive())
                self.assertFalse(self.app.tv_power_items[not enabled].get_sensitive())
                self.assertIn("allumée" if state else "en veille", self.app.tv_root_item.get_label())

    def test_unknown_state_keeps_both_explicit_actions_available(self):
        self.assertIn("état inconnu", self.app.tv_root_item.get_label())
        self.assertTrue(all(item.get_sensitive() for item in self.app.tv_power_items.values()))
        self.assertFalse(self.app.tv_status_item.get_sensitive())

    def test_unconfigured_tv_does_not_offer_nonfunctional_actions(self):
        self.app.tv.configured = False
        self.app.sync_tv_widgets()
        self.assertIn("non configurée", self.app.tv_root_item.get_label())
        self.assertFalse(any(item.get_sensitive() for item in self.app.tv_power_items.values()))

    def test_command_runs_in_background_and_prevents_conflicting_clicks(self):
        started = threading.Event()
        release = threading.Event()
        completed = threading.Event()

        def command(power):
            started.set()
            release.wait(5)

        send = self.app.send_tv_power

        def work(command):
            try:
                send(command)
            finally:
                completed.set()

        self.app.send_tv_power = work
        self.app.tv.set_power.side_effect = command
        try:
            self.app.tv_power_items[True].activate()
            self.assertTrue(started.wait(2))
            self.assertTrue(self.app.tv_busy)
            self.assertFalse(any(item.get_sensitive() for item in self.app.tv_power_items.values()))
            self.app.tv_power_items[False].activate()
            self.app.sync_widgets()
            self.assertEqual(self.app.tv_status_item.get_label(), "Allumage en cours…")
        finally:
            release.set()
            self.assertTrue(completed.wait(2))
            self.drain_events()
        self.app.tv.set_power.assert_called_once_with(True)
        self.assertFalse(self.app.tv_busy)
        self.assertEqual(self.app.tv_status_item.get_label(), "Commande envoyée")
        self.assertEqual(self.errors, [])

    def test_power_off_uses_an_explicit_off_command_and_refreshes_real_state(self):
        self.app.tv.is_on = True
        self.app.tv.refresh.side_effect = lambda: setattr(self.app.tv, "is_on", False)
        self.app.run_background = lambda work: work()
        self.app.tv_power_items[False].activate()
        self.drain_events()
        self.app.tv.set_power.assert_called_once_with(False)
        self.assertIn("en veille", self.app.tv_root_item.get_label())
        self.assertTrue(self.app.tv_power_items[True].get_sensitive())

    def test_failures_are_visible_and_allow_retry(self):
        for failure in (OSError("network unavailable"), ValueError("invalid configuration"), RuntimeError()):
            with self.subTest(failure=failure):
                self.app.tv_busy = True
                self.app.tv.set_power.side_effect = failure
                self.app.send_tv_power(lambda: self.app.tv.set_power(False))
                self.drain_events()
                self.assertFalse(self.app.tv_busy)
                self.assertTrue(all(item.get_sensitive() for item in self.app.tv_power_items.values()))
                self.assertEqual(self.app.tv_status_item.get_label(), "Échec de la commande")
                self.assertIn(str(failure) or type(failure).__name__, self.errors[-1])
        self.app.tv.set_power.side_effect = None
        self.app.send_tv_power(lambda: self.app.tv.set_power(True))
        self.drain_events()
        self.assertEqual(self.app.tv_status_item.get_label(), "Commande envoyée")


class RefreshTests(unittest.TestCase):
    DEVICE_ID = "bf0123456789"

    def setUp(self):
        self.app = tray.TrayApplication.__new__(tray.TrayApplication)
        self.device = tray.Device({"id": self.DEVICE_ID, "name": "Lamp", "key": "0123456789abcdef"})
        self.device.refresh = Mock()
        self.app.devices = [self.device]
        self.app.busy = False
        self.app.tv = Mock(spec=tray.Television)
        for name in ("sync_widgets", "sync_status_label", "sync_tv_widgets"):
            setattr(self.app, name, Mock(return_value=False))

    def discovered(self, info):
        return patch.object(tray, "discover_devices", return_value={self.DEVICE_ID: info})

    def test_discovery_broadcast_locates_the_device(self):
        with self.discovered({"gwId": self.DEVICE_ID, "ip": "192.0.2.5", "version": "3.3"}):
            self.app.locate_and_refresh_all()
        self.assertEqual((self.device.ip, self.device.version), ("192.0.2.5", 3.3))
        self.device.refresh.assert_called_once_with()
        self.assertFalse(self.app.busy)

    def test_malformed_discovery_broadcast_is_ignored(self):
        for info in ({"gwId": self.DEVICE_ID}, {"ip": "192.0.2.5"}, {"ip": "192.0.2.5", "version": "new"},
                     {"ip": "192.0.2.5", "version": None}):
            with self.subTest(info=info), self.discovered(info):
                self.app.locate_and_refresh_all()
                self.assertIsNone(self.device.ip)
                self.assertIsNone(self.device.version)
                self.assertFalse(self.app.busy)

    def test_busy_state_is_released_when_a_refresh_fails(self):
        self.app.tv.refresh.side_effect = RuntimeError("unexpected")
        for refresh in (self.app.refresh_all, self.app.locate_and_refresh_all):
            with self.subTest(refresh=refresh.__name__), self.discovered({}):
                with self.assertRaisesRegex(RuntimeError, "unexpected"):
                    refresh()
                self.assertFalse(self.app.busy)

    def test_periodic_refresh_rediscovers_only_missing_devices(self):
        with self.discovered({"ip": "192.0.2.5", "version": "3.3"}) as discover:
            self.app.refresh_all()
            self.app.refresh_all()
        discover.assert_called_once_with()
        self.assertEqual(self.device.refresh.call_count, 2)

    def test_failing_device_is_reported_offline(self):
        self.device.online = True
        self.device.refresh.side_effect = OSError("unreachable")
        with self.discovered({}):
            self.app.refresh_all()
        self.assertFalse(self.device.online)
        self.assertFalse(self.app.busy)


if __name__ == "__main__":
    unittest.main()
