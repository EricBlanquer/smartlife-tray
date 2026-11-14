import math
import os
import struct

from remote_layout import KEYS, PANEL_ACTION, PLAY_PAUSE_KEY, POWER_ACTION

SKIN_FILENAME = "remote-skin.png"
SKIN_SOURCE_SHA256 = "e0528b51be097441ab213106f49e2a87fcd6c3b71a7c4fae506cfb2f45cf55c1"
SKIN_ROTATION_DEGREES = -0.64
SKIN_CROP_BOX = (4, 0, 322, 735)
SKIN_WIDTH = SKIN_CROP_BOX[2] - SKIN_CROP_BOX[0]
SKIN_HEIGHT = SKIN_CROP_BOX[3] - SKIN_CROP_BOX[1]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_HEADER_SIZE = 24
PNG_HEADER_CHUNK = b"IHDR"
SHAPE_RECT = "rect"
SHAPE_CIRCLE = "circle"
SHAPE_SECTOR = "sector"
DPAD_CENTER_X = 156
DPAD_CENTER_Y = 369
DPAD_OUTER_RADIUS = 122
DPAD_INNER_RADIUS = 63
FULL_TURN_DEGREES = 360
VOLUME_WHEEL = ("KEY_VOLUP", "KEY_VOLDOWN")
CHANNEL_WHEEL = ("KEY_CHUP", "KEY_CHDOWN")
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


def sector(key, start, end):
    return hotspot(
        key, SHAPE_SECTOR, None, cx=DPAD_CENTER_X, cy=DPAD_CENTER_Y,
        inner=DPAD_INNER_RADIUS, outer=DPAD_OUTER_RADIUS, start=start, end=end,
    )


HOTSPOTS = [
    rect(POWER_ACTION, 42, 30, 118, 81, 25),
    rect(PANEL_ACTION, 34, 196, 100, 250, 8),
    circle("KEY_ENTER", DPAD_CENTER_X, DPAD_CENTER_Y, DPAD_INNER_RADIUS),
    sector("KEY_UP", 225, 315),
    sector("KEY_RIGHT", 315, 405),
    sector("KEY_DOWN", 45, 135),
    sector("KEY_LEFT", 135, 225),
    rect("KEY_RETURN", 34, 495, 108, 552, 8),
    circle("KEY_HOME", 156, 547, 40),
    rect(PLAY_PAUSE_KEY, 206, 495, 284, 552, 8),
    rect("KEY_VOLUP", 37, 600, 157, 636, 6, VOLUME_WHEEL),
    rect("KEY_VOLDOWN", 37, 636, 157, 684, 6, VOLUME_WHEEL),
    rect("KEY_CHUP", 158, 600, 277, 636, 6, CHANNEL_WHEEL),
    rect("KEY_CHDOWN", 158, 636, 277, 684, 6, CHANNEL_WHEEL),
]


def skin_file(config_dir):
    path = os.path.join(config_dir, SKIN_FILENAME)
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


def hotspot_at(x, y):
    return next((spot for spot in HOTSPOTS if contains(spot, x, y)), None)


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


def web_skin():
    return {
        "width": SKIN_WIDTH,
        "height": SKIN_HEIGHT,
        "hotspots": [
            {
                "key": spot["key"],
                "title": spot["title"],
                "repeat": spot["repeat"],
                "wheel": spot["wheel"],
                "path": svg_path(spot),
            }
            for spot in HOTSPOTS
        ],
    }
