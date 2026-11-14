import math
import os
import struct

from remote_layout import KEYS, PANEL_ACTION, PLAY_PAUSE_KEY, POWER_ACTION

IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
SKIN_FILE = os.path.join(IMAGES_DIR, "remote-skin.png")
SKIN_WIDTH = 340
SKIN_HEIGHT = 1496
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_HEADER_SIZE = 24
PNG_HEADER_CHUNK = b"IHDR"
SHAPE_RECT = "rect"
SHAPE_CIRCLE = "circle"
SHAPE_SECTOR = "sector"
DPAD_CENTER_X = 170
DPAD_CENTER_Y = 372.4
DPAD_OUTER_RADIUS = 133
DPAD_INNER_RADIUS = 68
FULL_TURN_DEGREES = 360
ROCKER_TOP = 625
ROCKER_BAR_TOP = 659
ROCKER_BAR_BOTTOM = 689
ROCKER_BOTTOM = 726
ROCKER_RADIUS = 8
KEY_RADIUS = 39
PATH_PRECISION = 2


def hotspot(key, shape, wheel, **geometry):
    cell = KEYS[key]
    return {
        "key": key,
        "title": cell["title"],
        "repeat": cell["repeat"],
        "wheel": list(wheel) if wheel else None,
        "shape": shape,
        **geometry,
    }


def rect(key, left, top, right, bottom, radius, wheel=None):
    return hotspot(key, SHAPE_RECT, wheel, left=left, top=top, right=right, bottom=bottom, radius=radius)


def circle(key, center_x, center_y, radius):
    return hotspot(key, SHAPE_CIRCLE, None, cx=center_x, cy=center_y, radius=radius)


def rocker(left, right, up, press, down):
    wheel = (up, down)
    return [
        rect(up, left, ROCKER_TOP, right, ROCKER_BAR_TOP, ROCKER_RADIUS, wheel),
        rect(press, left, ROCKER_BAR_TOP, right, ROCKER_BAR_BOTTOM, ROCKER_RADIUS, wheel),
        rect(down, left, ROCKER_BAR_BOTTOM, right, ROCKER_BOTTOM, ROCKER_RADIUS, wheel),
    ]


def sector(key, start, end):
    return hotspot(
        key, SHAPE_SECTOR, None, cx=DPAD_CENTER_X, cy=DPAD_CENTER_Y,
        inner=DPAD_INNER_RADIUS, outer=DPAD_OUTER_RADIUS, start=start, end=end,
    )


HOTSPOTS = [
    rect(POWER_ACTION, 37, 36, 117, 84, 24),
    circle(PANEL_ACTION, 70, 196, KEY_RADIUS),
    circle("KEY_MIC", 170, 159, KEY_RADIUS),
    circle("KEY_AMBIENT", 270, 193, KEY_RADIUS),
    circle("KEY_ENTER", DPAD_CENTER_X, DPAD_CENTER_Y, DPAD_INNER_RADIUS),
    sector("KEY_UP", 225, 315),
    sector("KEY_RIGHT", 315, 405),
    sector("KEY_DOWN", 45, 135),
    sector("KEY_LEFT", 135, 225),
    circle("KEY_RETURN", 70, 551, KEY_RADIUS),
    circle("KEY_HOME", 170, 580, KEY_RADIUS),
    circle(PLAY_PAUSE_KEY, 270, 550, KEY_RADIUS),
    *rocker(36, 171, "KEY_VOLUP", "KEY_MUTE", "KEY_VOLDOWN"),
    *rocker(172, 305, "KEY_CHUP", "KEY_GUIDE", "KEY_CHDOWN"),
    circle("APP_NETFLIX", 68, 784, KEY_RADIUS),
    circle("APP_PRIME_VIDEO", 169, 784, KEY_RADIUS),
    circle("APP_RAKUTEN_TV", 270, 784, KEY_RADIUS),
]


def skin_file(path=None):
    path = path or SKIN_FILE
    try:
        with open(path, "rb") as handle:
            header = handle.read(PNG_HEADER_SIZE)
    except OSError:
        return None
    if (
        len(header) != PNG_HEADER_SIZE
        or not header.startswith(PNG_SIGNATURE)
        or header[12:16] != PNG_HEADER_CHUNK
        or struct.unpack(">II", header[16:24]) != (SKIN_WIDTH, SKIN_HEIGHT)
    ):
        return None
    return path


def contains(spot, x, y):
    if spot["shape"] == SHAPE_RECT:
        return spot["left"] <= x <= spot["right"] and spot["top"] <= y <= spot["bottom"]
    distance = math.hypot(x - spot["cx"], y - spot["cy"])
    if spot["shape"] == SHAPE_CIRCLE:
        return distance <= spot["radius"]
    if not spot["inner"] < distance <= spot["outer"]:
        return False
    angle = math.degrees(math.atan2(y - spot["cy"], x - spot["cx"]))
    return (angle - spot["start"]) % FULL_TURN_DEGREES < spot["end"] - spot["start"]


class SkinGeometry:
    def __init__(self, width, height, hotspots):
        self.width = width
        self.height = height
        self.hotspots = hotspots

    def hotspot_at(self, x, y):
        return next((spot for spot in self.hotspots if contains(spot, x, y)), None)

    def web(self, image):
        return {
            "width": self.width,
            "height": self.height,
            "image": image,
            "hotspots": [
                {
                    "key": spot["key"],
                    "title": spot["title"],
                    "repeat": spot["repeat"],
                    "wheel": spot["wheel"],
                    "path": svg_path(spot),
                }
                for spot in self.hotspots
            ],
        }


REMOTE_SKIN = SkinGeometry(SKIN_WIDTH, SKIN_HEIGHT, HOTSPOTS)


def polar(spot, radius, degrees):
    angle = math.radians(degrees)
    return spot["cx"] + radius * math.cos(angle), spot["cy"] + radius * math.sin(angle)


def number(value):
    return f"{round(value, PATH_PRECISION):g}"


def point(coordinates):
    return f"{number(coordinates[0])},{number(coordinates[1])}"


def svg_path(spot):
    if spot["shape"] == SHAPE_RECT:
        left, top, right, bottom, radius = (
            spot["left"], spot["top"], spot["right"], spot["bottom"], spot["radius"],
        )
        arc = f"A{radius},{radius} 0 0 1 "
        return (
            f"M{left + radius},{top}H{right - radius}{arc}{right},{top + radius}"
            f"V{bottom - radius}{arc}{right - radius},{bottom}"
            f"H{left + radius}{arc}{left},{bottom - radius}"
            f"V{top + radius}{arc}{left + radius},{top}Z"
        )
    if spot["shape"] == SHAPE_CIRCLE:
        radius = spot["radius"]
        left = point((spot["cx"] - radius, spot["cy"]))
        right = point((spot["cx"] + radius, spot["cy"]))
        arc = f"A{radius},{radius} 0 1 0 "
        return f"M{left}{arc}{right}{arc}{left}Z"
    outer, inner = spot["outer"], spot["inner"]
    return (
        f"M{point(polar(spot, outer, spot['start']))}"
        f"A{outer},{outer} 0 0 1 {point(polar(spot, outer, spot['end']))}"
        f"L{point(polar(spot, inner, spot['end']))}"
        f"A{inner},{inner} 0 0 0 {point(polar(spot, inner, spot['start']))}Z"
    )


def trace(context, spot):
    context.new_sub_path()
    if spot["shape"] == SHAPE_RECT:
        left, top, right, bottom, radius = (
            spot["left"], spot["top"], spot["right"], spot["bottom"], spot["radius"],
        )
        context.arc(right - radius, top + radius, radius, -math.pi / 2, 0)
        context.arc(right - radius, bottom - radius, radius, 0, math.pi / 2)
        context.arc(left + radius, bottom - radius, radius, math.pi / 2, math.pi)
        context.arc(left + radius, top + radius, radius, math.pi, 3 * math.pi / 2)
    elif spot["shape"] == SHAPE_CIRCLE:
        context.arc(spot["cx"], spot["cy"], spot["radius"], 0, 2 * math.pi)
    else:
        start, end = math.radians(spot["start"]), math.radians(spot["end"])
        context.arc(spot["cx"], spot["cy"], spot["outer"], start, end)
        context.arc_negative(spot["cx"], spot["cy"], spot["inner"], end, start)
    context.close_path()

