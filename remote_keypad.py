from xml.sax.saxutils import escape, quoteattr

from remote_layout import DIGIT_ROWS, KEYPAD_FUNCTION_ROWS, KEYS
from remote_skin import SKIN_HEIGHT, SKIN_WIDTH, SkinGeometry, circle, rect, svg_path

KEYPAD_WIDTH = SKIN_WIDTH
KEYPAD_HEIGHT = SKIN_HEIGHT
COLUMN_CENTERS = (64, 150, 236)
FUNCTION_ROW_TOP = 56
FUNCTION_ROW_PITCH = 70
PILL_WIDTH = 78
PILL_HEIGHT = 46
DIGIT_ROW_TOP = 380
DIGIT_ROW_PITCH = 86
DIGIT_RADIUS = 33
BODY_RADIUS = 16
FACE_INSET = 15
FACE_RADIUS = 12
LABEL_FONT = "Noto Sans, DejaVu Sans, Helvetica, Arial, sans-serif"
LABEL_COLOR = "#3a3638"
LABEL_SIZE = 16
DIGIT_SIZE = 26
ICON_STROKE = 1.8
KEY_OUTLINE = "#4b4647"
KEY_OUTLINE_WIDTH = 1.6
KEY_HIGHLIGHT = "#ffffff"
KEY_HIGHLIGHT_OPACITY = 0.65
KEY_HIGHLIGHT_INSET = 2
LABEL_BASELINE_SHIFT = 0.36
BODY_STOPS = (
    (0, "#8f8b88"), (0.015, "#d2d0ce"), (0.035, "#a6a29f"), (0.048, "#6d6869"),
    (0.06, "#bdbdbf"), (0.5, "#cdcdd0"), (0.94, "#dadadd"),
    (0.952, "#6d6869"), (0.965, "#a6a29f"), (0.985, "#d2d0ce"), (1, "#8f8b88"),
)
FACE_STOPS = ((0, "#d6d6d8"), (0.45, "#c4c4c7"), (1, "#d3d3d6"))
KEY_STOPS = ((0, "#ececed"), (0.55, "#d3d3d5"), (1, "#b9b9bc"))
BRUSHED_FREQUENCY = "0.9 0.012"
BRUSHED_OPACITY = 0.07
ICONS = {
    "KEY_REWIND": "M-1,-7L-11,0L-1,7ZM10,-7L0,0L10,7Z",
    "KEY_PLAY": "M-5,-8L8,0L-5,8Z",
    "KEY_FF": "M1,-7L11,0L1,7ZM-10,-7L0,0L-10,7Z",
    "KEY_STOP": "M-7,-7H7V7H-7Z",
    "KEY_PAUSE": "M-7,-8H-2V8H-7ZM2,-8H7V8H2Z",
}


def function_hotspot(key, column, row_index):
    center_x = COLUMN_CENTERS[column]
    top = FUNCTION_ROW_TOP + row_index * FUNCTION_ROW_PITCH
    return rect(
        key, center_x - PILL_WIDTH // 2, top, center_x + PILL_WIDTH // 2, top + PILL_HEIGHT, PILL_HEIGHT // 2
    )


def digit_hotspot(key, column, row_index):
    return circle(key, COLUMN_CENTERS[column], DIGIT_ROW_TOP + row_index * DIGIT_ROW_PITCH, DIGIT_RADIUS)


def hotspots(rows, factory):
    return [
        factory(cell["key"], column, row_index)
        for row_index, row in enumerate(rows)
        for column, cell in enumerate(row)
        if cell is not None
    ]


KEYPAD_HOTSPOTS = [
    *hotspots(KEYPAD_FUNCTION_ROWS, function_hotspot),
    *hotspots(DIGIT_ROWS, digit_hotspot),
]
KEYPAD = SkinGeometry(KEYPAD_WIDTH, KEYPAD_HEIGHT, KEYPAD_HOTSPOTS)


def gradient(identifier, stops, horizontal):
    end = 'x2="1" y2="0"' if horizontal else 'x2="0" y2="1"'
    offsets = "".join(f'<stop offset="{offset}" stop-color="{color}"/>' for offset, color in stops)
    return f'<linearGradient id="{identifier}" x1="0" y1="0" {end}>{offsets}</linearGradient>'


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
            f'<path d="{icon}" transform="translate({x},{y})" fill="none" stroke="{LABEL_COLOR}" '
            f'stroke-width="{ICON_STROKE}" stroke-linejoin="round"/>'
        )
    size = DIGIT_SIZE if "cx" in spot else LABEL_SIZE
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
    face = FACE_INSET
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{KEYPAD_WIDTH}" height="{KEYPAD_HEIGHT}" '
        f'viewBox="0 0 {KEYPAD_WIDTH} {KEYPAD_HEIGHT}">'
        "<defs>"
        f"{gradient('body', BODY_STOPS, True)}{gradient('face', FACE_STOPS, False)}{gradient('key', KEY_STOPS, False)}"
        '<filter id="brushed" x="0" y="0" width="1" height="1">'
        f'<feTurbulence type="fractalNoise" baseFrequency="{BRUSHED_FREQUENCY}" numOctaves="2" seed="7"/>'
        f'<feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 {BRUSHED_OPACITY * 4} 0"/>'
        '<feComposite in2="SourceGraphic" operator="in"/>'
        "</filter>"
        "</defs>"
        f'<rect width="{KEYPAD_WIDTH}" height="{KEYPAD_HEIGHT}" rx="{BODY_RADIUS}" fill="url(#body)"/>'
        f'<rect x="{face}" y="{face}" width="{KEYPAD_WIDTH - 2 * face}" height="{KEYPAD_HEIGHT - 2 * face}" '
        f'rx="{FACE_RADIUS}" fill="url(#face)" stroke="{KEY_OUTLINE}" stroke-width="1"/>'
        f'<rect width="{KEYPAD_WIDTH}" height="{KEYPAD_HEIGHT}" rx="{BODY_RADIUS}" fill="#000000" filter="url(#brushed)"/>'
        f"{''.join(key_shape(spot) for spot in KEYPAD_HOTSPOTS)}"
        "</svg>"
    )
