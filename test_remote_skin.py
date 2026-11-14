import io
import os
import struct
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

import prepare_remote_skin
import remote_skin
from remote_layout import PANEL_ACTION, PLAY_PAUSE_KEY, POWER_ACTION

PROBES = {
    (74, 52): POWER_ACTION,
    (60, 219): PANEL_ACTION,
    (150, 273): "KEY_UP",
    (244, 366): "KEY_RIGHT",
    (150, 459): "KEY_DOWN",
    (56, 366): "KEY_LEFT",
    (150, 366): "KEY_ENTER",
    (64, 520): "KEY_RETURN",
    (150, 544): "KEY_HOME",
    (239, 520): PLAY_PAUSE_KEY,
    (91, 605): "KEY_VOLUP",
    (91, 632): "KEY_MUTE",
    (91, 662): "KEY_VOLDOWN",
    (212, 605): "KEY_CHUP",
    (212, 632): "KEY_GUIDE",
    (212, 662): "KEY_CHDOWN",
    (150, 175): None,
    (244, 212): None,
    (91, 590): None,
    (91, 690): None,
    (5, 5): None,
}


def png_header(width, height, signature=remote_skin.PNG_SIGNATURE, chunk=b"IHDR"):
    return signature + struct.pack(">I", 13) + chunk + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"


class SkinGeometryTests(unittest.TestCase):
    def test_hotspots_match_the_calibrated_keys(self):
        for (x, y), key in PROBES.items():
            with self.subTest(point=(x, y)):
                spot = remote_skin.hotspot_at(x, y)
                self.assertEqual(spot["key"] if spot else None, key)

    def test_ring_sectors_split_on_the_diagonals(self):
        ring = remote_skin.HOTSPOTS[3]
        radius = (remote_skin.DPAD_INNER_RADIUS + remote_skin.DPAD_OUTER_RADIUS) / 2
        for degrees, key in (
            (270, "KEY_UP"), (226, "KEY_UP"), (314, "KEY_UP"), (316, "KEY_RIGHT"), (0, "KEY_RIGHT"),
            (44, "KEY_RIGHT"), (46, "KEY_DOWN"), (134, "KEY_DOWN"), (136, "KEY_LEFT"), (224, "KEY_LEFT"),
        ):
            with self.subTest(degrees=degrees):
                self.assertEqual(remote_skin.hotspot_at(*remote_skin.polar(ring, radius, degrees))["key"], key)
        for distance, key in (
            (remote_skin.DPAD_INNER_RADIUS - 1, "KEY_ENTER"),
            (remote_skin.DPAD_INNER_RADIUS + 1, "KEY_UP"),
            (remote_skin.DPAD_OUTER_RADIUS + 2, None),
        ):
            with self.subTest(distance=distance):
                spot = remote_skin.hotspot_at(*remote_skin.polar(ring, distance, 270))
                self.assertEqual(spot["key"] if spot else None, key)

    def test_svg_paths_are_closed_and_cover_every_hotspot(self):
        skin = remote_skin.web_skin()
        self.assertEqual((skin["width"], skin["height"]), (remote_skin.SKIN_WIDTH, remote_skin.SKIN_HEIGHT))
        self.assertEqual([spot["key"] for spot in skin["hotspots"]], [spot["key"] for spot in remote_skin.HOTSPOTS])
        for spot in skin["hotspots"]:
            with self.subTest(key=spot["key"]):
                self.assertTrue(spot["path"].startswith("M"))
                self.assertTrue(spot["path"].endswith("Z"))
                self.assertTrue(spot["title"])
        up = next(spot for spot in skin["hotspots"] if spot["key"] == "KEY_UP")
        self.assertEqual(up["path"], "M63.73,279.73A122,122 0 0 1 236.27,279.73L194.55,321.45A63,63 0 0 0 105.45,321.45Z")
        wheels = {spot["key"]: spot["wheel"] for spot in skin["hotspots"]}
        for key in ("KEY_VOLUP", "KEY_MUTE", "KEY_VOLDOWN"):
            self.assertEqual(wheels[key], ["KEY_VOLUP", "KEY_VOLDOWN"])
        for key in ("KEY_CHUP", "KEY_GUIDE", "KEY_CHDOWN"):
            self.assertEqual(wheels[key], ["KEY_CHUP", "KEY_CHDOWN"])

    def test_only_a_png_of_the_calibrated_size_is_used(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, remote_skin.SKIN_FILENAME)
            self.assertIsNone(remote_skin.skin_file(directory))
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
                    self.assertEqual(remote_skin.skin_file(directory), expected)


class PrepareSkinTests(unittest.TestCase):
    def test_background_becomes_transparent_without_holes_or_specks(self):
        image = Image.new("RGB", (120, 200), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 10, 100, 199), fill=(200, 200, 205))
        draw.rectangle((60, 10, 70, 14), fill=(255, 255, 255))
        draw.point((110, 100), fill=(220, 220, 220))
        result = prepare_remote_skin.remove_background(image)
        alpha = result.getchannel("A")
        self.assertEqual(alpha.getpixel((0, 0)), 0)
        self.assertEqual(alpha.getpixel((119, 199)), 0)
        self.assertEqual(alpha.getpixel((60, 100)), 255)
        self.assertGreater(alpha.getpixel((65, 12)), 240)
        self.assertEqual(alpha.getpixel((110, 100)), 0)

    def test_only_the_bottom_corners_are_rounded(self):
        image = Image.new("RGBA", (120, 200), (200, 200, 205, 255))
        alpha = prepare_remote_skin.round_bottom_corners(image).getchannel("A")
        for point in ((0, 199), (119, 199)):
            self.assertEqual(alpha.getpixel(point), 0)
        for point in ((0, 0), (119, 0), (0, 150), (60, 199)):
            self.assertEqual(alpha.getpixel(point), 255)
        self.assertTrue(0 < alpha.getpixel((3, 192)) < 255)

    def test_straightened_photo_has_the_calibrated_size(self):
        photo = Image.new("RGB", (329, 1358), (255, 255, 255))
        self.assertEqual(prepare_remote_skin.straighten(photo).size, (remote_skin.SKIN_WIDTH, remote_skin.SKIN_HEIGHT))

    def test_other_photos_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            photo = os.path.join(directory, "photo.jpg")
            output = os.path.join(directory, remote_skin.SKIN_FILENAME)
            buffer = io.BytesIO()
            Image.new("RGB", (329, 1358), (255, 255, 255)).save(buffer, "JPEG")
            with open(photo, "wb") as handle:
                handle.write(buffer.getvalue())
            with (
                patch("sys.argv", ["prepare_remote_skin.py", photo, "--output", output]),
                patch("sys.stderr"),
            ):
                with self.assertRaises(SystemExit) as raised:
                    prepare_remote_skin.main()
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(os.path.exists(output))

    def test_calibrated_photo_produces_a_usable_skin(self):
        with tempfile.TemporaryDirectory() as directory:
            photo = os.path.join(directory, "photo.jpg")
            output = os.path.join(directory, remote_skin.SKIN_FILENAME)
            buffer = io.BytesIO()
            Image.new("RGB", (329, 1358), (200, 200, 200)).save(buffer, "JPEG")
            with open(photo, "wb") as handle:
                handle.write(buffer.getvalue())
            with (
                patch.object(prepare_remote_skin, "SKIN_SOURCE_SHA256", prepare_remote_skin.hashlib.sha256(buffer.getvalue()).hexdigest()),
                patch("sys.argv", ["prepare_remote_skin.py", photo, "--output", output]),
                patch("sys.stdout"),
            ):
                prepare_remote_skin.main()
            self.assertEqual(remote_skin.skin_file(directory), output)
            self.assertEqual(sorted(os.listdir(directory)), sorted(["photo.jpg", remote_skin.SKIN_FILENAME]))


if __name__ == "__main__":
    unittest.main()
