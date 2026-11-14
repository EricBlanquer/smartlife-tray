import time
import unittest

from Xlib import X, display
from Xlib.ext import xtest

import global_wheel
from global_wheel import GLib, GlobalWheel

WAIT_SECONDS = 2
WAIT_STEP_SECONDS = 0.005
WHEEL_UP_BUTTON = 4
WHEEL_DOWN_BUTTON = 5
POINTER_POSITION = (40, 30)


def wait_until(condition):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if condition():
            return True
        time.sleep(WAIT_STEP_SECONDS)
    return False


class GlobalWheelTests(unittest.TestCase):
    def setUp(self):
        self.received = []
        self.wheel = GlobalWheel(lambda index, x, y: self.received.append((index, x, y)))
        self.addCleanup(self.wheel.release)
        self.other_client = display.Display()
        self.addCleanup(self.other_client.close)

    def roll(self, button):
        self.other_client.screen().root.warp_pointer(*POINTER_POSITION)
        xtest.fake_input(self.other_client, X.ButtonPress, button)
        xtest.fake_input(self.other_client, X.ButtonRelease, button)
        self.other_client.sync()

    def test_wheel_anywhere_on_screen_reaches_the_grabbing_client(self):
        self.assertTrue(self.wheel.grab())
        self.assertTrue(self.wheel.grab())
        self.roll(WHEEL_UP_BUTTON)
        self.roll(WHEEL_DOWN_BUTTON)
        self.assertTrue(wait_until(lambda: len(self.received) == 2))
        self.assertEqual(self.received, [(0, *POINTER_POSITION), (1, *POINTER_POSITION)])

    def test_released_wheel_is_no_longer_captured(self):
        self.assertTrue(self.wheel.grab())
        self.wheel.release()
        self.wheel.release()
        self.roll(WHEEL_UP_BUTTON)
        self.assertFalse(wait_until(lambda: self.received))

    def test_wheel_already_grabbed_by_another_client_is_left_alone(self):
        root = self.other_client.screen().root
        for button in global_wheel.WHEEL_BUTTONS:
            root.grab_button(button, X.AnyModifier, False, X.ButtonPressMask, X.GrabModeAsync, X.GrabModeAsync, X.NONE, X.NONE)
        self.other_client.sync()
        self.assertFalse(self.wheel.grab())
        self.assertIsNone(self.wheel.connection)


if __name__ == "__main__":
    unittest.main()
