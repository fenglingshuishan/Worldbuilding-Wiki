#!/usr/bin/env python3
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

WIDTH = 1200
HEIGHT = 800
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src" / "worldbuilding_wiki" / "sample_data" / "tidal-archive-map.webp"


def gradient_background() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = image.load()
    rng = random.Random(413)
    for y in range(HEIGHT):
        ratio = y / (HEIGHT - 1)
        for x in range(WIDTH):
            glow = max(0.0, 1.0 - math.hypot((x - 620) / 900, (y - 390) / 620))
            noise = rng.randint(-3, 3)
            pixels[x, y] = (
                int(18 + ratio * 9 + glow * 9 + noise),
                int(49 + ratio * 20 + glow * 14 + noise),
                int(65 + ratio * 24 + glow * 18 + noise),
            )
    return image


def draw_island(
    image: Image.Image,
    points: list[tuple[int, int]],
    fill: tuple[int, int, int],
) -> None:
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    shadow = mask.filter(ImageFilter.GaussianBlur(18))
    shadow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_layer.putalpha(shadow.point(lambda value: int(value * 0.42)))
    image.paste((3, 19, 25), (13, 18), shadow_layer)

    coast = ImageDraw.Draw(image)
    coast.line(points + [points[0]], fill=(153, 207, 194), width=16, joint="curve")
    coast.polygon(points, fill=fill)
    coast.line(points + [points[0]], fill=(223, 210, 166), width=4, joint="curve")


def main() -> None:
    rng = random.Random(811)
    image = gradient_background()
    draw = ImageDraw.Draw(image, "RGBA")

    for offset in (0, 28, 58):
        draw.arc(
            (110 + offset, 80 + offset, 1090 - offset, 760 - offset),
            195,
            342,
            fill=(94, 159, 160, 45),
            width=2,
        )

    main_island = [
        (225, 205),
        (330, 145),
        (485, 125),
        (630, 155),
        (770, 215),
        (900, 315),
        (945, 430),
        (890, 548),
        (785, 635),
        (640, 680),
        (510, 650),
        (410, 585),
        (352, 505),
        (280, 445),
        (205, 355),
        (175, 275),
    ]
    draw_island(image, main_island, (183, 181, 129))
    draw_island(
        image,
        [(185, 135), (245, 102), (302, 122), (324, 166), (278, 198), (214, 188)],
        (122, 157, 125),
    )
    draw_island(
        image,
        [(947, 530), (1005, 505), (1056, 548), (1040, 606), (978, 625), (930, 584)],
        (204, 176, 119),
    )
    draw_island(
        image,
        [(746, 90), (808, 67), (861, 105), (847, 153), (779, 164), (730, 128)],
        (137, 166, 132),
    )

    # Mountain spine.
    for index in range(9):
        x = 335 + index * 38
        y = 385 + int(math.sin(index * 0.8) * 35)
        height = 52 + rng.randint(-10, 18)
        draw.polygon([(x - 28, y + 28), (x, y - height), (x + 31, y + 28)], fill=(66, 82, 72, 220))
        draw.line(
            [(x, y - height), (x + 9, y - 18), (x + 31, y + 28)], fill=(221, 214, 178, 180), width=3
        )

    # Mirror lake and waterways.
    draw.ellipse(
        (560, 328, 690, 424), fill=(52, 135, 148, 235), outline=(220, 220, 184, 230), width=5
    )
    draw.ellipse((590, 350, 650, 392), fill=(116, 204, 198, 120))
    draw.line([(620, 420), (605, 480), (650, 535), (720, 580)], fill=(67, 145, 153, 190), width=7)

    # Glass desert.
    for _ in range(90):
        x = rng.randint(710, 890)
        y = rng.randint(390, 560)
        if ((x - 800) / 130) ** 2 + ((y - 475) / 105) ** 2 < 1:
            size = rng.randint(2, 7)
            draw.polygon(
                [(x, y - size), (x + size, y), (x, y + size), (x - size, y)],
                fill=(240, 208, 150, rng.randint(80, 190)),
            )

    # Forests and settlements.
    for _ in range(95):
        x = rng.randint(430, 765)
        y = rng.randint(210, 570)
        if rng.random() < 0.45 and not (530 < x < 715 and 300 < y < 450):
            radius = rng.randint(4, 9)
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=(50, 104, 78, rng.randint(100, 180)),
            )
    for x, y in ((335, 218), (625, 377), (858, 485), (430, 455)):
        draw.ellipse(
            (x - 13, y - 13, x + 13, y + 13),
            fill=(213, 109, 80, 245),
            outline=(247, 230, 187, 255),
            width=4,
        )
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 244, 203, 255))

    # Dashed sea routes.
    routes = [((335, 218), (620, 377)), ((620, 377), (858, 485)), ((335, 218), (235, 150))]
    for (x1, y1), (x2, y2) in routes:
        steps = 24
        for index in range(0, steps, 2):
            a = index / steps
            b = min(1, (index + 1) / steps)
            draw.line(
                [
                    (x1 + (x2 - x1) * a, y1 + (y2 - y1) * a),
                    (x1 + (x2 - x1) * b, y1 + (y2 - y1) * b),
                ],
                fill=(232, 219, 174, 145),
                width=3,
            )

    # Paper-like finishing layer.
    texture = Image.new("RGBA", image.size, (0, 0, 0, 0))
    texture_draw = ImageDraw.Draw(texture)
    for _ in range(9000):
        x = rng.randrange(WIDTH)
        y = rng.randrange(HEIGHT)
        shade = rng.choice(((255, 244, 210, 8), (10, 30, 30, 7)))
        texture_draw.point((x, y), fill=shade)
    image = Image.alpha_composite(image.convert("RGBA"), texture).convert("RGB")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, "WEBP", quality=88, method=6)
    print(OUTPUT)


if __name__ == "__main__":
    main()
