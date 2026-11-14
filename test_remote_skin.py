import os
import struct
import tempfile
import unittest

import remote_skin
from remote_layout import PANEL_ACTION, PLAY_PAUSE_KEY, POWER_ACTION

PROBES = {
    (77, 60): POWER_ACTION,
    (70, 196): PANEL_ACTION,
    (170, 272): "KEY_UP",
    (270, 372): "KEY_RIGHT",
    (170, 472): "KEY_DOWN",
    (70, 372): "KEY_LEFT",
    (170, 372): "KEY_ENTER",
    (70, 551): "KEY_RETURN",
    (170, 580): "KEY_HOME",
    (270, 550): PLAY_PAUSE_KEY,
    (100, 640): "KEY_VOLUP",
    (100, 673): "KEY_MUTE",
    (100, 710): "KEY_VOLDOWN",
    (240, 640): "KEY_CHUP",
    (240, 673): "KEY_GUIDE",
    (240, 710): "KEY_CHDOWN",
    (270, 193): "KEY_AMBIENT",
    (68, 784): "APP_NETFLIX",
    (169, 784): "APP_PRIME_VIDEO",
    (270, 784): "APP_RAKUTEN_TV",
    (170, 159): "KEY_MIC",
    (170, 225): None,
    (100, 615): None,
    (100, 735): None,
    (170, 1200): None,
    (5, 5): None,
}


def png_header(width, height, signature=remote_skin.PNG_SIGNATURE, chunk=b"IHDR"):
    return signature + struct.pack(">I", 13) + chunk + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"


class SkinGeometryTests(unittest.TestCase):
    def test_hotspots_match_the_calibrated_keys(self):
        for (x, y), key in PROBES.items():
            with self.subTest(point=(x, y)):
                spot = remote_skin.REMOTE_SKIN.hotspot_at(x, y)
                self.assertEqual(spot["key"] if spot else None, key)

    def test_ring_sectors_split_on_the_diagonals(self):
        ring = next(spot for spot in remote_skin.HOTSPOTS if spot["key"] == "KEY_UP")
        radius = (remote_skin.DPAD_INNER_RADIUS + remote_skin.DPAD_OUTER_RADIUS) / 2
        for degrees, key in (
            (270, "KEY_UP"), (226, "KEY_UP"), (314, "KEY_UP"), (316, "KEY_RIGHT"), (0, "KEY_RIGHT"),
            (44, "KEY_RIGHT"), (46, "KEY_DOWN"), (134, "KEY_DOWN"), (136, "KEY_LEFT"), (224, "KEY_LEFT"),
        ):
            with self.subTest(degrees=degrees):
                self.assertEqual(remote_skin.REMOTE_SKIN.hotspot_at(*remote_skin.polar(ring, radius, degrees))["key"], key)
        for distance, key in (
            (remote_skin.DPAD_INNER_RADIUS - 1, "KEY_ENTER"),
            (remote_skin.DPAD_INNER_RADIUS + 1, "KEY_UP"),
            (remote_skin.DPAD_OUTER_RADIUS + 2, None),
        ):
            with self.subTest(distance=distance):
                spot = remote_skin.REMOTE_SKIN.hotspot_at(*remote_skin.polar(ring, distance, 270))
                self.assertEqual(spot["key"] if spot else None, key)

    def test_svg_paths_are_closed_and_cover_every_hotspot(self):
        skin = remote_skin.REMOTE_SKIN.web("/photo.png")
        self.assertEqual(
            (skin["width"], skin["height"], skin["image"]), (remote_skin.SKIN_WIDTH, remote_skin.SKIN_HEIGHT, "/photo.png")
        )
        self.assertEqual([spot["key"] for spot in skin["hotspots"]], [spot["key"] for spot in remote_skin.HOTSPOTS])
        for spot in skin["hotspots"]:
            with self.subTest(key=spot["key"]):
                self.assertTrue(spot["path"].startswith("M"))
                self.assertTrue(spot["path"].endswith("Z"))
                self.assertTrue(spot["title"])
        up = next(spot for spot in skin["hotspots"] if spot["key"] == "KEY_UP")
        self.assertEqual(up["path"], "M75.95,278.35A133,133 0 0 1 264.05,278.35L218.08,324.32A68,68 0 0 0 121.92,324.32Z")
        wheels = {spot["key"]: spot["wheel"] for spot in skin["hotspots"]}
        for key in ("KEY_VOLUP", "KEY_MUTE", "KEY_VOLDOWN"):
            self.assertEqual(wheels[key], ["KEY_VOLUP", "KEY_VOLDOWN"])
        for key in ("KEY_CHUP", "KEY_GUIDE", "KEY_CHDOWN"):
            self.assertEqual(wheels[key], ["KEY_CHUP", "KEY_CHDOWN"])

    def test_committed_skin_matches_the_geometry(self):
        self.assertEqual(remote_skin.skin_file(), remote_skin.SKIN_FILE)

    def test_only_a_png_of_the_calibrated_size_is_used(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "remote-skin.png")
            self.assertIsNone(remote_skin.skin_file(path))
            cases = (
                (png_header(remote_skin.SKIN_WIDTH, remote_skin.SKIN_HEIGHT), path),
                (png_header(remote_skin.SKIN_WIDTH + 1, remote_skin.SKIN_HEIGHT), None),
                (png_header(remote_skin.SKIN_WIDTH, remote_skin.SKIN_HEIGHT, signature=b"\xffJPEGxxx"), None),
                (png_header(remote_skin.SKIN_WIDTH, remote_skin.SKIN_HEIGHT, chunk=b"IDAT"), None),
                (b"\x89PNG", None),
            )
            for content, expected in cases:
                with self.subTest(content=content[:12]):
                    with open(path, "wb") as handle:
                        handle.write(content)
                    self.assertEqual(remote_skin.skin_file(path), expected)


if __name__ == "__main__":
    unittest.main()
