"""Look at one frame of the Makkah live camera.

kaaba(img)  -> the Kaaba's box if this is a wide view with the Kaaba in it, else None.
crowd(img, box) -> share (0-1) of the mataf floor around the Kaaba that is covered by people.

Plain pixel rules, no AI service:
- The Kaaba is the one big, solid, near-black block in the picture, away from the frame edges.
  Black abayas are dark too, but in small scattered bits, so they fail the "solid block" test.
- Bare mataf floor is bright, grey-white and smooth. People (even in white ihram) make texture:
  shadows, heads, gaps. So "covered" = not smooth bright floor.
"""
import sys, json
from collections import deque
import numpy as np
from PIL import Image

W, H = 640, 360          # analysis size (people are ~2-4 px here, enough to see floor gaps)
CAPTION = 0.80           # the bottom 20% holds Quran TV's caption bars: ignore it
DEBUG = False

def load(path):
    return load_image(Image.open(path))

def load_image(im):
    im = im.convert("RGB").resize((W, H), Image.BILINEAR)
    a = np.asarray(im).astype(np.float32)
    luma = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    sat = a.max(-1) - a.min(-1)
    return luma, sat

def _shift_all(m, op):
    p = np.pad(m, 1, mode="edge")
    out = p[1:-1, 1:-1].copy()
    for dy in range(3):
        for dx in range(3):
            out = op(out, p[dy:dy + m.shape[0], dx:dx + m.shape[1]])
    return out

def _largest(mask):
    h, w = mask.shape
    seen = np.zeros_like(mask); best = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        q = deque([(y0, x0)]); seen[y0, x0] = True; pts = []
        while q:
            y, x = q.popleft(); pts.append((y, x))
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True; q.append((ny, nx))
        if len(pts) > len(best):
            best = pts
    return best

def kaaba(luma, sat):
    """The Kaaba's box (in W x H pixels) if this is a wide shot with the whole Kaaba in view, else None."""
    # Work at half size. Opening (erode then grow back) removes people-sized dark bits (black abayas,
    # shadows) and cuts the thin links between them and the Kaaba, so only big solid blocks survive.
    l2 = luma.reshape(H // 2, 2, W // 2, 2).mean((1, 3)); s2 = sat.reshape(H // 2, 2, W // 2, 2).mean((1, 3))
    h, w = l2.shape
    dark = (l2 < 40) & (s2 < 40)
    dark[int(h * CAPTION):] = False
    core = dark
    for _ in range(3):
        core = _shift_all(core, np.logical_and)
    best = _largest(core)
    if not best:
        return None
    blob = np.zeros_like(dark)
    ys, xs = zip(*best); blob[ys, xs] = True
    for _ in range(3):
        blob = _shift_all(blob, np.logical_or) & dark
    ys, xs = np.nonzero(blob)
    y1, y2, x1, x2 = ys.min(), ys.max(), xs.min(), xs.max()
    bw, bh = x2 - x1 + 1, y2 - y1 + 1
    area = int(blob.sum())
    fill = area / (bw * bh)
    share = area / (w * h)
    edge = x1 <= 2 or y1 <= 2 or x2 >= w - 3
    black = float(l2[blob].mean())
    cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
    # The wide Kaaba view: a small solid black block near the middle of the picture. Close-ups, dark arcade
    # windows and doorways (off to the sides or up in the wall) and crossfades (not truly black) all fail.
    ok = (0.004 <= share <= 0.04 and fill >= 0.6 and 0.9 <= bw / bh <= 2.4 and not edge and black < 12
          and 0.25 <= cx <= 0.75 and 0.3 <= cy <= 0.72)
    if ok:
        # Above the black block is either the rest of the kiswa (above the gold band) or, seen from high up,
        # the Kaaba's white roof. A dark doorway has grey wall or an arch there instead.
        uy1, uy2 = max(0, y1 - int(bh * 0.6)), max(1, y1 - 1)
        up, us = l2[uy1:uy2, x1:x2 + 1], s2[uy1:uy2, x1:x2 + 1]
        ok = up.size > 0 and ((up < 45).mean() >= 0.66 or ((up > 170) & (us < 40)).mean() >= 0.5)
    info = {"box": [int(x1) * 2, int(y1) * 2, int(x2) * 2 + 1, int(y2) * 2 + 1],
            "share": round(share, 4), "fill": round(float(fill), 2), "black": round(black, 1), "edge": bool(edge)}
    if DEBUG: print(info, file=sys.stderr)
    return info if ok else None

def crowd(luma, sat, box):
    """Share (0-1) of the floor around the Kaaba that is covered by people."""
    x1, y1, x2, y2 = box
    kw, kh = x2 - x1 + 1, y2 - y1 + 1
    y1 -= int(kh * 0.6)      # the gold band splits the kiswa: the dark block is the lower part, the white roof sits above
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    yy, xx = np.mgrid[0:H, 0:W]
    # Ring around the Kaaba, scaled by its own size so any zoom works.
    d = np.sqrt(((xx - cx) / (kw * 3.5)) ** 2 + ((yy - cy) / ((y2 - y1) * 2.6)) ** 2)
    ring = (d <= 1) & ~((xx >= x1 - 4) & (xx <= x2 + 4) & (yy >= y1 - 4) & (yy <= y2 + 4))
    ring[int(H * CAPTION):] = False
    ring[:int(cy)] = False   # only the mataf beside and in front of the Kaaba: above it the camera sees arcades and walls
    # Bare floor = bright, grey-white and smooth. People, even in white ihram, add texture (heads, folds, gaps).
    p = np.pad(luma, 1, mode="edge")
    stack = np.stack([p[dy:dy + H, dx:dx + W] for dy in range(3) for dx in range(3)])
    tex = stack.max(0) - stack.min(0)
    floor = (luma > 150) & (sat < 50) & (tex < 16)
    n = ring.sum()
    return round(1 - floor[ring].sum() / n, 3) if n > 800 else None

def level(c):
    return "quiet" if c < 0.65 else "moderate" if c < 0.85 else "busy" if c < 0.95 else "packed"

if __name__ == "__main__":
    out = []
    for f in sys.argv[1:]:
        L, S = load(f); k = kaaba(L, S)
        c = crowd(L, S, k["box"]) if k else None
        out.append({"file": f.split("/")[-1], "kaaba": k, "crowd": c, "level": level(c) if c is not None else None})
    print(json.dumps(out, indent=None if len(out) > 1 else 1))
