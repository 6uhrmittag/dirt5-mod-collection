"""d5art - meme art generated ON TOP of the game's own textures at apply time
(so the repo never contains game assets). Used by d5mod texture mods.

  python d5art.py preview <file.gtx> <out.png>   render the UwU title without patching
"""
import math
import random
import sys

from PIL import Image, ImageDraw, ImageFont

FONTS = "C:/Windows/Fonts/"
CREDIT = "modded by macha :3"

# headlights on startScreen.gtx (3840x2160): (x, y, radius) - found with a grid overlay
EYES = [(2220, 712, 78), (2930, 490, 66), (640, 1380, 55), (1160, 1182, 48)]


def font(name, size):
    return ImageFont.truetype(FONTS + name, size)


def meme_text(d, xy, text, size, anchor="mm", fill="white"):
    """Classic Impact caption: white, thick black outline."""
    d.text(xy, text, font=font("impact.ttf", size), fill=fill, anchor=anchor,
           stroke_width=max(3, size // 14), stroke_fill="black")


def googly(img, x, y, r, rng):
    d = ImageDraw.Draw(img)
    R = int(r * 1.35)
    d.ellipse([x - R, y - R, x + R, y + R], fill="white", outline="black", width=max(4, R // 9))
    a = rng.uniform(0, 2 * math.pi)                       # every eye looks somewhere else
    px, py = x + math.cos(a) * R * 0.42, y + math.sin(a) * R * 0.42
    p = R * 0.52
    d.ellipse([px - p, py - p, px + p, py + p], fill="black")
    d.ellipse([px - p * 0.55, py - p * 0.7, px - p * 0.15, py - p * 0.3], fill="white")   # shine


def splash(img, xy, text, size, angle=18):
    """Minecraft-style yellow splash text, rotated."""
    f = font("comicbd.ttf", size)
    tmp = Image.new("RGBA", (int(size * len(text) * 0.75), int(size * 1.6)), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((tmp.width // 2, tmp.height // 2), text, font=f, fill=(255, 255, 0),
                             anchor="mm", stroke_width=size // 12, stroke_fill=(60, 50, 0))
    tmp = tmp.rotate(angle, expand=True, resample=Image.BICUBIC)
    img.paste(tmp, (int(xy[0] - tmp.width / 2), int(xy[1] - tmp.height / 2)), tmp)


def sparkles(img, rng, n=40):
    d = ImageDraw.Draw(img)
    for _ in range(n):
        x, y, s = rng.uniform(0, img.width), rng.uniform(0, img.height * 0.35), rng.uniform(12, 40)
        c = rng.choice([(255, 255, 255), (255, 120, 255), (120, 255, 255), (255, 255, 120)])
        d.polygon([(x, y - s), (x + s * 0.25, y - s * 0.25), (x + s, y), (x + s * 0.25, y + s * 0.25),
                   (x, y + s), (x - s * 0.25, y + s * 0.25), (x - s, y), (x - s * 0.25, y - s * 0.25)], fill=c)


def uwu_title(img: Image.Image, eyes=True) -> Image.Image:
    """The title screen, UwU EDITION. Scales with the texture size (designed on 3840x2160)."""
    base = img.convert("RGB").resize((3840, 2160)) if img.size != (3840, 2160) else img.convert("RGB")
    rng = random.Random(2020)
    if eyes:
        for x, y, r in EYES:
            googly(base, x, y, r, rng)
    sparkles(base, rng)
    d = ImageDraw.Draw(base)
    meme_text(d, (2700, 170), "UwU EDITION", 250)
    meme_text(d, (1920, 1990), "PRESS START TO YEET", 190)
    splash(base, (1560, 860), "now with 200% more uwu!", 92)
    d.text((60, 2110), CREDIT, font=font("comicbd.ttf", 54), fill=(255, 255, 255), anchor="ls",
           stroke_width=4, stroke_fill="black")
    return base.resize(img.size) if img.size != (3840, 2160) else base


def main(argv):
    if len(argv) == 4 and argv[1] == "preview":
        import d5tex
        im = d5tex.decode(open(argv[2], "rb").read())
        uwu_title(im, eyes="startScreen.gtx" in argv[2]).resize((1920, 1080)).save(argv[3])
        print(argv[3])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
