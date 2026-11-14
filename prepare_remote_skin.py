#!/usr/bin/env python3

import argparse
import math
import os
import tempfile

import numpy
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from remote_skin import DPAD_CENTER_X, DPAD_CENTER_Y, IMAGES_DIR, SKIN_FILE, SKIN_HEIGHT, SKIN_WIDTH

DETAIL_PHOTO = os.path.join(IMAGES_DIR, "remote-detail.jpg")
TONES_PHOTO = os.path.join(IMAGES_DIR, "remote-tones.png")
RING_PHOTO = os.path.join(IMAGES_DIR, "remote-ring.png")
ROCKER_PHOTO = os.path.join(IMAGES_DIR, "remote-rocker.png")
DETAIL_SIZE = (358, 1500)
TONES_SIZE = (781, 1200)
RING_SIZE = (300, 300)
ROCKER_SIZE = (290, 65)
DETAIL_QUAD = ((5.7, 4.0), (329.9, 4.0), (351.6, 1499.5), (10.3, 1499.5))
TONES_QUAD = ((243.21, 23.28), (503.93, 23.28), (501.52, 1160.43), (243.23, 1160.43))
TONE_RADIUS = 6
CLOSE_UP_ANGLE = 0.7
RING_CENTER = (150.1, 150.4)
RING_RADII = (132.5, 131.7)
SKIN_RING_RADII = (133.9, 131.4)
ROCKER_CENTER = (143.5, 31.5)
ROCKER_EXTENT = (258, 30)
SKIN_ROCKER_BOX = (35, 658, 306, 690)
PASTE_MARGIN = 2.5
ROCKER_MARGIN = 6
STAIN_BOX = (198, 4, 270, 38)
STAIN_EDGE_SAMPLE = 3
STAIN_GRAIN_WINDOW = 7
STAIN_FEATHER = 3
TOP_EDGE = 4
TOP_RADIUS = 14
BOTTOM_RADIUS = 24
EDGE_FEATHER = 1.2
SUPERSAMPLING = 4
WHITE = (255, 255, 255)
BACKGROUND_THRESHOLD = 238
LIGHT = 255
DARK = 0
BACKGROUND_MARK = 128
TRANSPARENT = 0
OPAQUE = 255
EDGE_SOFTNESS = 0.7
SPECK_SIZE = 5
CHANNELS = 3
MINIMUM_WEIGHT = 1e-3


def perspective_coefficients(quad):
    corners = ((0, 0), (SKIN_WIDTH, 0), (SKIN_WIDTH, SKIN_HEIGHT), (0, SKIN_HEIGHT))
    rows, values = [], []
    for (x, y), (u, v) in zip(corners, quad):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        values.extend((u, v))
    return numpy.linalg.solve(numpy.array(rows, float), numpy.array(values, float)).tolist()


def rectify(photo, quad):
    return photo.convert("RGB").transform(
        (SKIN_WIDTH, SKIN_HEIGHT), Image.PERSPECTIVE, perspective_coefficients(quad), Image.BICUBIC, fillcolor=WHITE
    )


def remove_background(image):
    light = image.convert("L").point(lambda value: LIGHT if value > BACKGROUND_THRESHOLD else DARK)
    width, height = light.size
    for corner in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        if light.getpixel(corner) == LIGHT:
            ImageDraw.floodfill(light, corner, BACKGROUND_MARK)
    mask = light.point(lambda value: TRANSPARENT if value == BACKGROUND_MARK else OPAQUE)
    mask = mask.filter(ImageFilter.MinFilter(SPECK_SIZE)).filter(ImageFilter.MaxFilter(SPECK_SIZE))
    return fill_rows(mask).filter(ImageFilter.GaussianBlur(EDGE_SOFTNESS))


def fill_rows(mask):
    filled = mask.copy()
    draw = ImageDraw.Draw(filled)
    width, height = mask.size
    for y in range(height):
        bounds = mask.crop((0, y, width, y + 1)).getbbox()
        if bounds:
            draw.line([(bounds[0], y), (bounds[2] - 1, y)], fill=OPAQUE)
    return filled


def rounded_shape(top, radius):
    size = (SKIN_WIDTH * SUPERSAMPLING, SKIN_HEIGHT * SUPERSAMPLING)
    shape = Image.new("L", size, TRANSPARENT)
    ImageDraw.Draw(shape).rounded_rectangle(
        (0, top * SUPERSAMPLING, size[0] - 1, size[1] - 1), radius=radius * SUPERSAMPLING, fill=OPAQUE
    )
    return shape


def body_mask():
    top = rounded_shape(TOP_EDGE, TOP_RADIUS).crop((0, 0, SKIN_WIDTH * SUPERSAMPLING, SKIN_HEIGHT * SUPERSAMPLING))
    bottom = rounded_shape(-BOTTOM_RADIUS, BOTTOM_RADIUS)
    return ImageChops.multiply(top, bottom).resize((SKIN_WIDTH, SKIN_HEIGHT), Image.LANCZOS)


def silhouette(detail):
    return ImageChops.multiply(remove_background(detail), body_mask())


def erase_stain(image):
    left, top, right, bottom = STAIN_BOX
    width = right - left
    pixels = numpy.asarray(image, float)
    left_edge = pixels[top:bottom, left - STAIN_EDGE_SAMPLE:left].mean(axis=1)
    right_edge = pixels[top:bottom, right:right + STAIN_EDGE_SAMPLE].mean(axis=1)
    weights = (numpy.arange(width) + 0.5)[None, :, None] / width
    fill = left_edge[:, None, :] * (1 - weights) + right_edge[:, None, :] * weights
    neighbour = pixels[top:bottom, left - width:left]
    padded = numpy.pad(neighbour, ((0, 0), (STAIN_GRAIN_WINDOW // 2,) * 2, (0, 0)), mode="edge")
    kernel = numpy.ones(STAIN_GRAIN_WINDOW) / STAIN_GRAIN_WINDOW
    smoothed = numpy.apply_along_axis(lambda line: numpy.convolve(line, kernel, mode="valid"), 1, padded)
    patch = Image.fromarray(numpy.uint8(numpy.clip(fill + neighbour - smoothed, 0, OPAQUE)))
    mask = Image.new("L", patch.size, OPAQUE)
    ImageDraw.Draw(mask).rectangle((0, patch.height - STAIN_FEATHER, patch.width, patch.height), fill=TRANSPARENT)
    image.paste(patch, (left, top), mask.filter(ImageFilter.GaussianBlur(STAIN_FEATHER / 2)))


def affine(photo_center, skin_center, scale_x, scale_y):
    angle = math.radians(CLOSE_UP_ANGLE)
    a, b = math.cos(angle) * scale_x, math.sin(angle) * scale_y
    d, e = -math.sin(angle) * scale_x, math.cos(angle) * scale_y
    return (
        a, b, photo_center[0] - a * skin_center[0] - b * skin_center[1],
        d, e, photo_center[1] - d * skin_center[0] - e * skin_center[1],
    )


def supersampled(size, draw_shape):
    mask = Image.new("L", (size[0] * SUPERSAMPLING, size[1] * SUPERSAMPLING), TRANSPARENT)
    draw_shape(ImageDraw.Draw(mask), SUPERSAMPLING)
    return mask.resize(size, Image.LANCZOS).filter(ImageFilter.GaussianBlur(EDGE_FEATHER))


def paste(image, photo, coefficients, mask):
    part = photo.convert("RGB").transform(image.size, Image.AFFINE, coefficients, Image.BICUBIC, fillcolor=WHITE)
    image.paste(part, (0, 0), mask)


def paste_ring(image, ring_photo):
    center = (DPAD_CENTER_X, DPAD_CENTER_Y)
    radius_x, radius_y = SKIN_RING_RADII[0] + PASTE_MARGIN, SKIN_RING_RADII[1] + PASTE_MARGIN

    def draw_ring(draw, scale):
        draw.ellipse(
            ((center[0] - radius_x) * scale, (center[1] - radius_y) * scale,
             (center[0] + radius_x) * scale, (center[1] + radius_y) * scale),
            fill=OPAQUE,
        )

    coefficients = affine(
        RING_CENTER, center, RING_RADII[0] / SKIN_RING_RADII[0], RING_RADII[1] / SKIN_RING_RADII[1]
    )
    paste(image, ring_photo, coefficients, supersampled(image.size, draw_ring))


def paste_rocker(image, rocker_photo):
    left, top, right, bottom = SKIN_ROCKER_BOX
    radius = (bottom - top) / 2 + ROCKER_MARGIN

    def draw_rocker(draw, scale):
        draw.rounded_rectangle(
            ((left - ROCKER_MARGIN) * scale, (top - ROCKER_MARGIN) * scale,
             (right + ROCKER_MARGIN) * scale, (bottom + ROCKER_MARGIN) * scale),
            radius=radius * scale,
            fill=OPAQUE,
        )

    coefficients = affine(
        ROCKER_CENTER, ((left + right) / 2, (top + bottom) / 2),
        ROCKER_EXTENT[0] / (right - left), ROCKER_EXTENT[1] / (bottom - top),
    )
    paste(image, rocker_photo, coefficients, supersampled(image.size, draw_rocker))


def smooth(image, mask, radius):
    coverage = numpy.asarray(mask, float) / OPAQUE
    pixels = numpy.asarray(image, float)
    weight = numpy.asarray(mask.filter(ImageFilter.GaussianBlur(radius)), float) / OPAQUE
    channels = [
        numpy.asarray(
            Image.fromarray(numpy.uint8(numpy.clip(pixels[..., channel] * coverage, 0, OPAQUE)))
            .filter(ImageFilter.GaussianBlur(radius)),
            float,
        )
        for channel in range(CHANNELS)
    ]
    return numpy.stack(channels, axis=-1) / numpy.maximum(weight, MINIMUM_WEIGHT)[..., None]


def blend(detail, tones, mask):
    mixed = numpy.asarray(detail, float) + smooth(tones, mask, TONE_RADIUS) - smooth(detail, mask, TONE_RADIUS)
    return Image.fromarray(numpy.uint8(numpy.clip(mixed, 0, OPAQUE)))


def compose(detail_photo, tones_photo, ring_photo, rocker_photo):
    detail = rectify(detail_photo, DETAIL_QUAD)
    mask = silhouette(detail)
    result = blend(detail, rectify(tones_photo, TONES_QUAD), mask)
    erase_stain(result)
    paste_ring(result, ring_photo)
    paste_rocker(result, rocker_photo)
    result.putalpha(mask)
    return result


def save(image, path):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    handle, temporary_path = tempfile.mkstemp(dir=directory, prefix=os.path.basename(path) + ".", suffix=".png")
    os.close(handle)
    try:
        image.save(temporary_path, "PNG", optimize=True)
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def open_photo(parser, path, size):
    try:
        photo = Image.open(path)
        photo.load()
    except OSError as ex:
        parser.error(f"cannot read {path}: {ex}")
    if photo.size != size:
        parser.error(f"{path} must be {size[0]}x{size[1]}, the size the key positions are calibrated for")
    return photo


def main():
    parser = argparse.ArgumentParser(
        description="Build the remote control skin from a sharp photo and a photo with neutral tones."
    )
    parser.add_argument("--detail", default=DETAIL_PHOTO, help="sharp photo providing the details")
    parser.add_argument("--tones", default=TONES_PHOTO, help="photo providing the neutral tones")
    parser.add_argument("--ring", default=RING_PHOTO, help="close-up providing the directional ring")
    parser.add_argument("--rocker", default=ROCKER_PHOTO, help="close-up providing the volume and channel rocker")
    parser.add_argument("--output", default=SKIN_FILE, help="PNG file to write")
    arguments = parser.parse_args()
    detail = open_photo(parser, arguments.detail, DETAIL_SIZE)
    tones = open_photo(parser, arguments.tones, TONES_SIZE)
    ring = open_photo(parser, arguments.ring, RING_SIZE)
    rocker = open_photo(parser, arguments.rocker, ROCKER_SIZE)
    save(compose(detail, tones, ring, rocker), arguments.output)
    print(arguments.output)


if __name__ == "__main__":
    main()
