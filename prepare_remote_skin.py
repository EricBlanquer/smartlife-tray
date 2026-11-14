#!/usr/bin/env python3

import argparse
import hashlib
import io
import os
import tempfile

from PIL import Image, ImageDraw, ImageFilter

from app_paths import CONFIG_DIR
from remote_skin import SKIN_CROP_BOX, SKIN_FILENAME, SKIN_ROTATION_DEGREES, SKIN_SOURCE_SHA256

WHITE = (255, 255, 255)
BACKGROUND_THRESHOLD = 238
LIGHT = 255
DARK = 0
BACKGROUND_MARK = 128
TRANSPARENT = 0
OPAQUE = 255
EDGE_SOFTNESS = 0.7
SPECK_SIZE = 5


def straighten(photo):
    return photo.convert("RGB").rotate(
        SKIN_ROTATION_DEGREES, resample=Image.BICUBIC, fillcolor=WHITE
    ).crop(SKIN_CROP_BOX)


def remove_background(image):
    light = image.convert("L").point(lambda value: LIGHT if value > BACKGROUND_THRESHOLD else DARK)
    width, height = light.size
    for corner in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        if light.getpixel(corner) == LIGHT:
            ImageDraw.floodfill(light, corner, BACKGROUND_MARK)
    mask = light.point(lambda value: TRANSPARENT if value == BACKGROUND_MARK else OPAQUE)
    mask = mask.filter(ImageFilter.MinFilter(SPECK_SIZE)).filter(ImageFilter.MaxFilter(SPECK_SIZE))
    alpha = fill_rows(mask).filter(ImageFilter.GaussianBlur(EDGE_SOFTNESS))
    result = image.convert("RGBA")
    result.putalpha(alpha)
    return result


def fill_rows(mask):
    filled = mask.copy()
    draw = ImageDraw.Draw(filled)
    width, height = mask.size
    for y in range(height):
        bounds = mask.crop((0, y, width, y + 1)).getbbox()
        if bounds:
            draw.line([(bounds[0], y), (bounds[2] - 1, y)], fill=OPAQUE)
    return filled


def save(image, path):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    handle, temporary_path = tempfile.mkstemp(dir=directory, prefix=SKIN_FILENAME + ".", suffix=".png")
    os.close(handle)
    try:
        image.save(temporary_path, "PNG")
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def main():
    parser = argparse.ArgumentParser(
        description="Turn the Samsung One Remote product photo into the remote control skin."
    )
    parser.add_argument("photo", help="the product photo the key positions are calibrated for")
    parser.add_argument(
        "--output", default=os.path.join(CONFIG_DIR, SKIN_FILENAME), help="PNG file to write"
    )
    arguments = parser.parse_args()
    with open(arguments.photo, "rb") as handle:
        data = handle.read()
    if hashlib.sha256(data).hexdigest() != SKIN_SOURCE_SHA256:
        parser.error("this is not the photo the key positions are calibrated for")
    save(remove_background(straighten(Image.open(io.BytesIO(data)))), arguments.output)
    print(arguments.output)


if __name__ == "__main__":
    main()
