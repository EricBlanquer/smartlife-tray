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


class PrepareSkinTests(unittest.TestCase):
    def test_background_becomes_transparent_without_holes_or_specks(self):
        image = Image.new("RGB", (120, 200), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 10, 100, 199), fill=(200, 200, 205))
        draw.rectangle((60, 10, 70, 14), fill=(255, 255, 255))
        draw.point((110, 100), fill=(220, 220, 220))
        alpha = prepare_remote_skin.remove_background(image)
        self.assertEqual(alpha.getpixel((0, 0)), 0)
        self.assertEqual(alpha.getpixel((119, 199)), 0)
        self.assertEqual(alpha.getpixel((60, 100)), 255)
        self.assertGreater(alpha.getpixel((65, 12)), 240)
        self.assertEqual(alpha.getpixel((110, 100)), 0)

    def test_silhouette_has_a_straight_top_and_rounded_corners(self):
        mask = prepare_remote_skin.body_mask()
        width, height = mask.size
        self.assertEqual(mask.size, (remote_skin.SKIN_WIDTH, remote_skin.SKIN_HEIGHT))
        for point in ((width // 2, 0), (0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
            self.assertEqual(mask.getpixel(point), 0)
        first_row = prepare_remote_skin.TOP_EDGE + 1
        self.assertEqual(mask.getpixel((width // 2, prepare_remote_skin.TOP_EDGE - 2)), 0)
        for point in ((width // 2, first_row), (0, height // 2), (width - 1, height // 2), (width // 2, height - 1)):
            self.assertEqual(mask.getpixel(point), 255)
        self.assertEqual({mask.getpixel((x, first_row)) for x in range(20, width - 20)}, {255})

    def test_photos_are_straightened_to_the_skin_size(self):
        for size, quad in (
            (prepare_remote_skin.DETAIL_SIZE, prepare_remote_skin.DETAIL_QUAD),
            (prepare_remote_skin.TONES_SIZE, prepare_remote_skin.TONES_QUAD),
        ):
            with self.subTest(size=size):
                photo = Image.new("RGB", size, (255, 255, 255))
                self.assertEqual(
                    prepare_remote_skin.rectify(photo, quad).size, (remote_skin.SKIN_WIDTH, remote_skin.SKIN_HEIGHT)
                )

    def test_tones_replace_the_colour_cast_but_keep_the_details(self):
        size = (60, 60)
        detail = Image.new("RGB", size, (150, 160, 200))
        ImageDraw.Draw(detail).line([(30, 0), (30, 59)], fill=(20, 30, 70))
        tones = Image.new("RGB", size, (180, 180, 180))
        mask = Image.new("L", size, 255)
        result = prepare_remote_skin.blend(detail, tones, mask)
        self.assertEqual(result.getpixel((5, 30)), (180, 180, 180))
        line = result.getpixel((30, 30))
        self.assertLess(max(line), 100)
        self.assertLessEqual(max(line) - min(line), 2)

    def test_stain_is_rebuilt_from_its_surroundings(self):
        left, top, right, bottom = prepare_remote_skin.STAIN_BOX
        image = Image.new("RGB", (remote_skin.SKIN_WIDTH, 80), (200, 200, 200))
        ImageDraw.Draw(image).rectangle((left + 10, top + 4, right - 10, bottom - 8), fill=(90, 90, 90))
        prepare_remote_skin.erase_stain(image)
        self.assertEqual(image.getpixel(((left + right) // 2, (top + bottom) // 2)), (200, 200, 200))
        self.assertEqual(image.getpixel((left - 5, top + 5)), (200, 200, 200))

    def test_ring_is_pasted_only_inside_the_directional_pad(self):
        image = Image.new("RGB", (remote_skin.SKIN_WIDTH, remote_skin.SKIN_HEIGHT), (200, 200, 200))
        ring = Image.new("RGB", prepare_remote_skin.RING_SIZE, (10, 10, 10))
        prepare_remote_skin.paste_ring(image, ring)
        center = (round(remote_skin.DPAD_CENTER_X), round(remote_skin.DPAD_CENTER_Y))
        self.assertEqual(image.getpixel(center), (10, 10, 10))
        self.assertEqual(image.getpixel((center[0] + remote_skin.DPAD_OUTER_RADIUS - 2, center[1])), (10, 10, 10))
        self.assertEqual(image.getpixel((center[0], center[1] - remote_skin.DPAD_OUTER_RADIUS - 8)), (200, 200, 200))
        self.assertEqual(image.getpixel((5, 5)), (200, 200, 200))

    def test_rocker_is_pasted_only_over_the_bar(self):
        left, top, right, bottom = prepare_remote_skin.SKIN_ROCKER_BOX
        image = Image.new("RGB", (remote_skin.SKIN_WIDTH, remote_skin.SKIN_HEIGHT), (200, 200, 200))
        rocker = Image.new("RGB", prepare_remote_skin.ROCKER_SIZE, (10, 10, 10))
        prepare_remote_skin.paste_rocker(image, rocker)
        middle = round((top + bottom) / 2)
        for x in (round(left) + 15, round((left + right) / 2), round(right) - 15):
            self.assertEqual(image.getpixel((x, middle)), (10, 10, 10))
        outside = prepare_remote_skin.ROCKER_MARGIN + 4
        self.assertEqual(image.getpixel((round((left + right) / 2), round(bottom) + outside)), (200, 200, 200))
        self.assertEqual(image.getpixel((round(left) - outside, middle)), (200, 200, 200))

    def test_photos_of_another_size_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.write_photos(directory, detail_size=(329, 1358))
            output = os.path.join(directory, "skin.png")
            with self.assertRaises(SystemExit) as raised:
                self.run_main(paths, output, patch("sys.stderr"))
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(os.path.exists(output))

    def test_calibrated_photos_produce_a_usable_skin(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.write_photos(directory)
            output = os.path.join(directory, "skin.png")
            self.run_main(paths, output, patch("sys.stdout"))
            self.assertEqual(remote_skin.skin_file(output), output)
            self.assertEqual(
                sorted(os.listdir(directory)), sorted(["detail.jpg", "tones.png", "ring.png", "rocker.png", "skin.png"])
            )

    def test_committed_skin_matches_the_geometry(self):
        self.assertEqual(remote_skin.skin_file(), remote_skin.SKIN_FILE)

    def write_photos(self, directory, detail_size=prepare_remote_skin.DETAIL_SIZE):
        paths = {
            "detail": (os.path.join(directory, "detail.jpg"), detail_size),
            "tones": (os.path.join(directory, "tones.png"), prepare_remote_skin.TONES_SIZE),
            "ring": (os.path.join(directory, "ring.png"), prepare_remote_skin.RING_SIZE),
            "rocker": (os.path.join(directory, "rocker.png"), prepare_remote_skin.ROCKER_SIZE),
        }
        for path, size in paths.values():
            Image.new("RGB", size, (200, 200, 200)).save(path)
        return {name: path for name, (path, _) in paths.items()}

    def run_main(self, paths, output, quiet):
        arguments = ["prepare_remote_skin.py", "--output", output]
        for name, path in paths.items():
            arguments += [f"--{name}", path]
        with patch("sys.argv", arguments), quiet:
            prepare_remote_skin.main()


if __name__ == "__main__":
    unittest.main()
