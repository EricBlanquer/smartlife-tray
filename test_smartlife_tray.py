import subprocess
import threading
import unittest
from unittest.mock import patch

import smartlife_tray as tray


class AlexaCommandTests(unittest.TestCase):
    def test_desktop_launch_finds_alexa_outside_path(self):
        with (
            patch.object(tray.shutil, "which", return_value=None),
            patch.object(tray.os, "access", return_value=True),
            patch.object(tray.subprocess, "run") as run,
        ):
            tray.turn_on_tv_with_alexa()
        self.assertEqual(run.call_args.args[0][0], tray.ALEXA_DEFAULT_PATH)
        self.assertEqual(run.call_args.args[0][1:], ["send", "allume", "la", "télé"])
        self.assertTrue(run.call_args.kwargs["check"])
        self.assertGreater(run.call_args.kwargs["timeout"], 300)
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_path_installation_takes_precedence(self):
        with (
            patch.object(tray.shutil, "which", return_value="/opt/alexa"),
            patch.object(tray.os, "access") as access,
            patch.object(tray.subprocess, "run") as run,
        ):
            tray.turn_on_tv_with_alexa()
        self.assertEqual(run.call_args.args[0][0], "/opt/alexa")
        access.assert_not_called()

    def test_missing_installation_does_not_start_a_command(self):
        with (
            patch.object(tray.shutil, "which", return_value=None),
            patch.object(tray.os, "access", return_value=False),
            patch.object(tray.subprocess, "run") as run,
        ):
            with self.assertRaisesRegex(FileNotFoundError, "alexa-cmd"):
                tray.turn_on_tv_with_alexa()
        run.assert_not_called()


class TelevisionMenuTests(unittest.TestCase):
    def setUp(self):
        self.app = tray.TrayApplication.__new__(tray.TrayApplication)
        self.app.devices = []
        self.app.device_widgets = {}
        self.app.menu = tray.Gtk.Menu()
        self.app.alexa_busy = False
        self.app.status_label = None
        self.app.busy = False
        self.errors = []
        self.app.report_error = self.errors.append
        self.app.build_menu()

    def tearDown(self):
        self.app.menu.destroy()

    def drain_events(self):
        context = tray.GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

    def test_menu_is_available_without_tuya_devices(self):
        labels = [item.get_label() for item in self.app.menu.get_children()]
        self.assertIn("Télévision", labels)
        self.assertTrue(self.app.tv_power_item.get_sensitive())
        self.assertFalse(self.app.tv_status_item.get_sensitive())

    def test_command_runs_in_background_and_prevents_duplicate_clicks(self):
        started = threading.Event()
        release = threading.Event()
        completed = threading.Event()

        def command():
            started.set()
            release.wait(5)

        send = self.app.send_tv_power

        def work():
            try:
                send()
            finally:
                completed.set()

        self.app.send_tv_power = work
        with patch.object(tray, "turn_on_tv_with_alexa", side_effect=command) as execute:
            try:
                self.app.tv_power_item.activate()
                self.assertTrue(started.wait(2))
                self.assertTrue(self.app.alexa_busy)
                self.assertFalse(self.app.tv_power_item.get_sensitive())
                self.app.tv_power_item.activate()
                self.app.sync_widgets()
                self.assertEqual(self.app.tv_status_item.get_label(), "Envoi à Alexa…")
            finally:
                release.set()
                self.assertTrue(completed.wait(2))
                self.drain_events()
            execute.assert_called_once_with()
        self.assertFalse(self.app.alexa_busy)
        self.assertTrue(self.app.tv_power_item.get_sensitive())
        self.assertEqual(self.app.tv_status_item.get_label(), "Commande envoyée à Alexa")
        self.assertEqual(self.errors, [])

    def test_failures_are_visible_and_allow_retry(self):
        failures = (
            (FileNotFoundError("alexa missing"), "alexa missing"),
            (PermissionError("not executable"), "not executable"),
            (subprocess.TimeoutExpired("alexa", 360), "connexion à Amazon"),
            (subprocess.CalledProcessError(1, "alexa", stderr="login failed\n"), "login failed"),
            (subprocess.CalledProcessError(1, "alexa", output="network failed"), "network failed"),
            (subprocess.CalledProcessError(1, "alexa", stderr="\n", output="network failed"), "network failed"),
            (subprocess.CalledProcessError(1, "alexa", stderr="\n", output="\n"), "exit status 1"),
            (subprocess.CalledProcessError(1, "alexa"), "exit status 1"),
        )
        for failure, message in failures:
            with self.subTest(failure=failure):
                self.app.alexa_busy = True
                self.app.tv_power_item.set_sensitive(False)
                with patch.object(tray, "turn_on_tv_with_alexa", side_effect=failure):
                    self.app.send_tv_power()
                    self.drain_events()
                self.assertFalse(self.app.alexa_busy)
                self.assertTrue(self.app.tv_power_item.get_sensitive())
                self.assertEqual(self.app.tv_status_item.get_label(), "Échec de la commande Alexa")
                self.assertIn(message, self.errors[-1])
        with patch.object(tray, "turn_on_tv_with_alexa"):
            self.app.send_tv_power()
            self.drain_events()
        self.assertEqual(self.app.tv_status_item.get_label(), "Commande envoyée à Alexa")


if __name__ == "__main__":
    unittest.main()
