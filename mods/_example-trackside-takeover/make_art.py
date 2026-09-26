"""Draws the Trackside Takeover banner layers (our own art, no game pixels).
Layer layouts match the game's branding_array_<country>_c.gtx (512x512 per layer):
  L0 / L3  2 x 4 grid of logo cells (256x128)
  L1       4 full-width rows (512x128)
  L2       2 x 2 grid of big cells (256x256)
  L4       4 vertical columns (128x512), text rotated
Run from anywhere: python make_art.py  ->  layer0.png layer1.png layer3.png layer4.png"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = "C:/Windows/Fonts/"
PINK, CYAN, YELLOW, BLACK, WHITE = (255, 0, 170), (0, 230, 255), (255, 225, 40), (12, 8, 20), (250, 250, 250)
PURPLE, RED, GREEN = (60, 20, 110), (220, 30, 40), (40, 190, 80)
SPONSORS = [  # text, fg, bg, font
    ("D5ML", PINK, BLACK, "impact.ttf"), ("UwU ENERGY", CYAN, BLACK, "impact.ttf"),
    ("GO TO BED", WHITE, PURPLE, "impact.ttf"), ("FREIBIER", YELLOW, RED, "impact.ttf"),
    ("TOUCH GRASS", GREEN, WHITE, "impact.ttf"), ("PING 999ms", RED, WHITE, "impact.ttf"),
    ("NO BRAKES", BLACK, YELLOW, "impact.ttf"), ("MACHA", WHITE, PINK, "impact.ttf"),
]


def logo(w, h, text, fg, bg, font, vertical=False):
    W, H = (h, w) if vertical else (w, h)
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    size = H
    while size > 8:
        f = ImageFont.truetype(FONTS + font, size)
        l, t, r, b = d.textbbox((0, 0), text, font=f)
        if r - l <= W * 0.86 and b - t <= H * 0.72:
            break
        size -= 2
    d.text((W / 2, H / 2), text, font=f, fill=fg, anchor="mm")
    d.rectangle([3, 3, W - 4, H - 4], outline=fg, width=3)
    return im.rotate(90, expand=True) if vertical else im


def grid(order):
    im = Image.new("RGB", (512, 512))
    for i, k in enumerate(order):
        im.paste(logo(256, 128, *SPONSORS[k]), ((i % 2) * 256, (i // 2) * 128))
    return im


def quads(order):
    im = Image.new("RGB", (512, 512))
    for i, k in enumerate(order):
        im.paste(logo(256, 256, *SPONSORS[k]), ((i % 2) * 256, (i // 2) * 256))
    return im


def rows(order):
    im = Image.new("RGB", (512, 512))
    for i, k in enumerate(order):
        im.paste(logo(512, 128, *SPONSORS[k]), (0, i * 128))
    return im


def columns(order):
    im = Image.new("RGB", (512, 512))
    for i, k in enumerate(order):
        im.paste(logo(128, 512, *SPONSORS[k], vertical=True), (i * 128, 0))
    return im


if __name__ == "__main__":
    grid([0, 1, 2, 3, 4, 5, 6, 7]).save(os.path.join(HERE, "layer0.png"))
    rows([0, 1, 2, 3]).save(os.path.join(HERE, "layer1.png"))
    quads([4, 5, 6, 0]).save(os.path.join(HERE, "layer2.png"))
    grid([1, 0, 3, 2, 5, 4, 7, 6]).save(os.path.join(HERE, "layer3.png"))
    columns([0, 1, 2, 3]).save(os.path.join(HERE, "layer4.png"))
    print("layers written to", HERE)
