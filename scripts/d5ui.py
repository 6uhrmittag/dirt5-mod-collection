"""d5ui.py - read DIRT 5 menu state from a screenshot (used by Test-Dirt5Mod.ps1).

  python scripts/d5ui.py selected-tile <png>   -> "x y w h" crop fractions of the selected tile's label
                                                  in the Event Setup LOCATION / TRACK strip, or "none"

The strips are a row of tiles at the bottom of Event Setup; the selected tile has a yellow + magenta
frame along its top edge (y ~ 515 of 720) and its label sits at y ~ 610..634. Works while the
strip scrolls, because the tile is found by its frame, not by a fixed grid.
"""
import sys

import numpy as np
from PIL import Image


def selected_tile(path):
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    h, w = a.shape[:2]
    band = a[int(0.705 * h):int(0.725 * h)]                        # rows around the frame line
    r, g, b = band[..., 0], band[..., 1], band[..., 2]
    frame = ((r > 230) & (g > 200) & (b < 60)) | ((r > 230) & (g < 140) & (b > 190))  # UI yellow / magenta
    cols = frame.sum(axis=0) >= 3                                  # a column that crosses the frame
    runs, start = [], None
    for x, on in enumerate(list(cols) + [False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            if x - start < 0.01 * w:                                 # specks in the tile art
                pass
            elif runs and start - runs[-1][1] <= 0.035 * w:         # the yellow -> magenta blend breaks the line
                runs[-1] = (runs[-1][0], x)
            else:
                runs.append((start, x))
            start = None
    x0, x1 = max(runs, key=lambda r: r[1] - r[0], default=(0, 0))
    if x1 - x0 < 0.12 * w:                                         # no tile-wide frame
        return None
    return x0 / w, 0.845, (x1 - x0) / w, 0.038


def main(argv):
    if len(argv) == 3 and argv[1] == "selected-tile":
        r = selected_tile(argv[2])
        print("none" if r is None else " ".join(f"{v:.4f}" for v in r))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
