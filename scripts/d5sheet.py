"""d5sheet - contact sheet of screenshots (thumbnails with frame numbers).

Usage:
  python d5sheet.py <out.png> <image> [<image> ...] [--cols 6] [--width 320] [--crop x,y,w,h]
  python d5sheet.py --resets <image> [<image> ...]
  --crop takes fractions (0..1) of each image, e.g. the HUD clock: 0.03,0.04,0.2,0.13
  --resets counts car resets: the game covers the screen with a yellow DIRT 5 wipe
           whenever it puts a crashed/flipped car back on track; a run of such
           frames = one reset. Prints "resets=<n> frames=<k>".
"""
import re
import sys

from PIL import Image, ImageDraw


def is_wipe(path):
    """True if most of the frame is the saturated yellow of the reset wipe."""
    im = Image.open(path).convert("RGB").resize((64, 36))
    px = list(im.getdata())
    yellow = sum(1 for r, g, b in px if r > 200 and g > 190 and b < 90)
    return yellow > 0.6 * len(px)


def resets(files):
    flags = [is_wipe(f) for f in sorted(files)]
    runs = sum(1 for k, w in enumerate(flags) if w and (k == 0 or not flags[k - 1]))
    print(f"resets={runs} frames={sum(flags)}")
    return 0


def main(argv):
    if len(argv) > 2 and argv[1] == "--resets":
        return resets(argv[2:])
    args, opts, i = [], {"cols": "6", "width": "320", "crop": ""}, 1
    while i < len(argv):
        if argv[i].startswith("--"):
            opts[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            args.append(argv[i])
            i += 1
    if len(args) < 2:
        print(__doc__)
        return 2
    out, files = args[0], sorted(args[1:])
    cols, width = int(opts["cols"]), int(opts["width"])
    crop = [float(v) for v in opts["crop"].split(",")] if opts["crop"] else None
    thumbs = []
    for f in files:
        im = Image.open(f).convert("RGB")
        if crop:
            w, h = im.size
            im = im.crop((int(crop[0] * w), int(crop[1] * h),
                          int((crop[0] + crop[2]) * w), int((crop[1] + crop[3]) * h)))
        im = im.resize((width, int(im.height * width / im.width)))
        m = re.search(r"(\d+)\D*$", f)
        thumbs.append((im, m.group(1) if m else ""))
    th = thumbs[0][0].height
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * width, rows * th))
    d = ImageDraw.Draw(sheet)
    for k, (im, label) in enumerate(thumbs):
        x, y = (k % cols) * width, (k // cols) * th
        sheet.paste(im, (x, y))
        d.rectangle([x, y, x + 8 * len(label) + 4, y + 13], fill="black")
        d.text((x + 2, y + 1), label, fill="yellow")
    sheet.save(out)
    print(f"{out} {sheet.size[0]}x{sheet.size[1]} ({len(thumbs)} frames)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
