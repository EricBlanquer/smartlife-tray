import unittest
import xml.etree.ElementTree as ElementTree

import remote_keypad
from remote_layout import DIGIT_KEYS, KEYPAD_ROWS, KEYS
from remote_skin import HOTSPOTS, SHAPE_CIRCLE, SKIN_HEIGHT, SKIN_WIDTH, contains

SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"


class KeypadTests(unittest.TestCase):
    def test_every_layout_key_has_one_hotspot_inside_the_keypad(self):
        expected = [cell["key"] for row in KEYPAD_ROWS for cell in row if cell is not None]
        self.assertEqual([spot["key"] for spot in remote_keypad.KEYPAD_HOTSPOTS], expected)
        self.assertEqual(
            {spot["key"] for spot in remote_keypad.KEYPAD_HOTSPOTS if spot["shape"] == SHAPE_CIRCLE}, set(DIGIT_KEYS)
        )
        for spot in remote_keypad.KEYPAD_HOTSPOTS:
            with self.subTest(key=spot["key"]):
                x, y = remote_keypad.center(spot)
                self.assertIs(remote_keypad.KEYPAD.hotspot_at(x, y), spot)
                self.assertTrue(0 < x < remote_keypad.KEYPAD_WIDTH)
                self.assertTrue(0 < y < remote_keypad.KEYPAD_HEIGHT)

    def test_keypad_lies_on_the_handle_below_the_remote_keys(self):
        origin_x, origin_y = remote_keypad.KEYPAD.origin
        lowest_key = max(spot.get("bottom", spot.get("cy", 0) + spot.get("radius", 0)) for spot in HOTSPOTS)
        self.assertGreater(origin_y, lowest_key)
        self.assertLessEqual(origin_x + remote_keypad.KEYPAD_WIDTH, SKIN_WIDTH)
        self.assertLessEqual(origin_y + remote_keypad.KEYPAD_HEIGHT, SKIN_HEIGHT)
        for spot in remote_keypad.KEYPAD_HOTSPOTS:
            x, y = remote_keypad.center(spot)
            self.assertIsNone(remote_keypad.KEYPAD.hotspot_at(x, remote_keypad.KEYPAD_HEIGHT + 1))
            self.assertTrue(0 < y < remote_keypad.KEYPAD_HEIGHT)

    def test_keys_do_not_overlap(self):
        spots = remote_keypad.KEYPAD_HOTSPOTS
        for index, spot in enumerate(spots):
            x, y = remote_keypad.center(spot)
            for other in spots[index + 1:]:
                with self.subTest(key=spot["key"], other=other["key"]):
                    self.assertFalse(contains(other, x, y))

    def test_drawing_is_valid_svg_with_every_label(self):
        root = ElementTree.fromstring(remote_keypad.keypad_svg())
        self.assertEqual(root.tag, f"{SVG_NAMESPACE}svg")
        self.assertEqual(
            (root.get("width"), root.get("height")),
            (str(remote_keypad.KEYPAD_WIDTH), str(remote_keypad.KEYPAD_HEIGHT)),
        )
        texts = [element.text for element in root.iter(f"{SVG_NAMESPACE}text")]
        expected = [
            KEYS[spot["key"]]["label"]
            for spot in remote_keypad.KEYPAD_HOTSPOTS
            if spot["key"] not in remote_keypad.ICONS
        ]
        self.assertEqual(texts, expected)
        self.assertFalse(any(element.get("style") for element in root.iter()))
        self.assertEqual([element for element in root if element.tag == f"{SVG_NAMESPACE}rect"], [])


if __name__ == "__main__":
    unittest.main()
