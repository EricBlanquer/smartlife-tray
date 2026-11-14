from xml.sax.saxutils import escape, quoteattr

from remote_layout import DIGIT_KEYS, KEYPAD_ROWS, KEYS
from remote_skin import SKIN_WIDTH, SkinGeometry, circle, rect, svg_path

KEYPAD_ORIGIN = (0, 884)
KEYPAD_WIDTH = SKIN_WIDTH
KEYPAD_HEIGHT = 500
COLUMN_CENTERS = (70, 170, 270)
FIRST_ROW_CENTER = 44
ROW_PITCH = 70
PILL_WIDTH = 80
PILL_HEIGHT = 46
DIGIT_RADIUS = 31
LABEL_FONT = "Noto Sans, DejaVu Sans, Helvetica, Arial, sans-serif"
LABEL_COLOR = "#3a3638"
LABEL_SIZE = 17
DIGIT_SIZE = 32
ICON_SCALE = 1.3
ICON_STROKE = 1.8
KEY_OUTLINE = "#3f3b3c"
KEY_OUTLINE_WIDTH = 1.8
KEY_HIGHLIGHT = "#ffffff"
KEY_HIGHLIGHT_OPACITY = 0.65
KEY_HIGHLIGHT_INSET = 2
LABEL_BASELINE_SHIFT = 0.36
KEY_STOPS = ((0, "#ececed"), (0.55, "#d3d3d5"), (1, "#b9b9bc"))
ICONS = {
    "KEY_REWIND": "M-1,-7L-11,0L-1,7ZM10,-7L0,0L10,7Z",
    "KEY_PLAY": "M-5,-8L8,0L-5,8Z",
    "KEY_FF": "M1,-7L11,0L1,7ZM-10,-7L0,0L-10,7Z",
    "KEY_STOP": "M-7,-7H7V7H-7Z",
    "KEY_PAUSE": "M-7,-8H-2V8H-7ZM2,-8H7V8H2Z",
}


def keypad_hotspot(key, column, row_index):
    center_x = COLUMN_CENTERS[column]
    center_y = FIRST_ROW_CENTER + row_index * ROW_PITCH
    if key in DIGIT_KEYS:
        return circle(key, center_x, center_y, DIGIT_RADIUS)
    return rect(
        key,
        center_x - PILL_WIDTH / 2,
        center_y - PILL_HEIGHT / 2,
        center_x + PILL_WIDTH / 2,
        center_y + PILL_HEIGHT / 2,
        PILL_HEIGHT / 2,
    )


KEYPAD_HOTSPOTS = [
    keypad_hotspot(cell["key"], column, row_index)
    for row_index, row in enumerate(KEYPAD_ROWS)
    for column, cell in enumerate(row)
    if cell is not None
]
KEYPAD = SkinGeometry(KEYPAD_WIDTH, KEYPAD_HEIGHT, KEYPAD_HOTSPOTS, KEYPAD_ORIGIN)


def gradient(identifier, stops):
    offsets = "".join(f'<stop offset="{offset}" stop-color="{color}"/>' for offset, color in stops)
    return f'<linearGradient id="{identifier}" x1="0" y1="0" x2="0" y2="1">{offsets}</linearGradient>'


def center(spot):
    if "cx" in spot:
        return spot["cx"], spot["cy"]
    return (spot["left"] + spot["right"]) / 2, (spot["top"] + spot["bottom"]) / 2


def inset(spot, distance):
    if "cx" in spot:
        return {**spot, "radius": spot["radius"] - distance}
    return {
        **spot,
        "left": spot["left"] + distance,
        "top": spot["top"] + distance,
        "right": spot["right"] - distance,
        "bottom": spot["bottom"] - distance,
        "radius": spot["radius"] - distance,
    }


def label(spot):
    x, y = center(spot)
    icon = ICONS.get(spot["key"])
    if icon:
        return (
            f'<path d="{icon}" transform="translate({x},{y}) scale({ICON_SCALE})" fill="none" '
            f'stroke="{LABEL_COLOR}" stroke-width="{ICON_STROKE / ICON_SCALE}" stroke-linejoin="round"/>'
        )
    size = DIGIT_SIZE if spot["key"] in DIGIT_KEYS else LABEL_SIZE
    return (
        f'<text x="{x}" y="{y + size * LABEL_BASELINE_SHIFT}" text-anchor="middle" font-family={quoteattr(LABEL_FONT)} '
        f'font-size="{size}" fill="{LABEL_COLOR}">{escape(KEYS[spot["key"]]["label"])}</text>'
    )


def key_shape(spot):
    return (
        f'<path d="{svg_path(spot)}" fill="url(#key)" stroke="{KEY_OUTLINE}" stroke-width="{KEY_OUTLINE_WIDTH}"/>'
        f'<path d="{svg_path(inset(spot, KEY_HIGHLIGHT_INSET))}" fill="none" stroke="{KEY_HIGHLIGHT}" '
        f'stroke-opacity="{KEY_HIGHLIGHT_OPACITY}"/>'
        f"{label(spot)}"
    )


def keypad_svg():
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{KEYPAD_WIDTH}" height="{KEYPAD_HEIGHT}" '
        f'viewBox="0 0 {KEYPAD_WIDTH} {KEYPAD_HEIGHT}">'
        f"<defs>{gradient('key', KEY_STOPS)}</defs>"
        f"{''.join(key_shape(spot) for spot in KEYPAD_HOTSPOTS)}"
        "</svg>"
    )
