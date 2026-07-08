#!/usr/bin/env python3
"""Generate the small reference images the filter worker's ComfyUI ColorTransfer
steps grade photos toward, plus a vignette mask. Run once (outputs are committed
static assets, regenerate only if you want to change a preset's look).
"""
import colorsys
from pathlib import Path

import numpy as np
from PIL import Image

OUT_DIR = Path(__file__).parent / "filter_assets"
SIZE = 128


def _hsv_gradient(hue_range, sat_range, val_range):
    """Diagonal gradient sweeping hue/sat/val across the given ranges, so
    ColorTransfer sees a spread of tones consistent with the preset's mood
    rather than a single flat color."""
    arr = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
    for y in range(SIZE):
        for x in range(SIZE):
            t_x, t_y = x / (SIZE - 1), y / (SIZE - 1)
            h = hue_range[0] + (hue_range[1] - hue_range[0]) * t_x
            s = sat_range[0] + (sat_range[1] - sat_range[0]) * (1 - t_y)
            v = val_range[0] + (val_range[1] - val_range[0]) * t_y
            r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
            arr[y, x] = (int(r * 255), int(g * 255), int(b * 255))
    return Image.fromarray(arr, mode="RGB")


def make_warm_golden():
    # Golden-hour palette: amber/orange hues, warm and bright.
    return _hsv_gradient(hue_range=(0.06, 0.13), sat_range=(0.45, 0.85), val_range=(0.55, 0.95))


def make_cool_blue():
    # Cinematic teal/blue palette.
    return _hsv_gradient(hue_range=(0.53, 0.63), sat_range=(0.35, 0.7), val_range=(0.4, 0.85))


def make_vintage_faded():
    # Low-saturation sepia/brown palette, muted brightness range (faded film look).
    return _hsv_gradient(hue_range=(0.08, 0.11), sat_range=(0.15, 0.35), val_range=(0.55, 0.85))


def make_teal_orange():
    # Cinematic split-tone: hue itself is correlated with luminance (teal in
    # shadows, orange in highlights), matching how the real grading technique
    # works, rather than a single-hue band like warm/cool.
    arr = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
    for y in range(SIZE):
        t = y / (SIZE - 1)  # 0 = shadow row, 1 = highlight row
        hue = 0.52 + (0.08 - 0.52) * t  # teal -> orange
        sat = 0.55
        val = 0.3 + t * 0.6
        r, g, b = colorsys.hsv_to_rgb(hue % 1.0, sat, val)
        arr[y, :] = (int(r * 255), int(g * 255), int(b * 255))
    return Image.fromarray(arr, mode="RGB")


def make_pastel():
    # Light, low-saturation hue sweep - gentler than the full-saturation rainbow
    # that blew out skin tones (see filters.py's vivid preset comment); pastel's
    # low sat/high val keeps this safe for the same reason a wash never clips.
    return _hsv_gradient(hue_range=(0.0, 1.0), sat_range=(0.15, 0.3), val_range=(0.8, 0.95))


def make_flat_gray():
    # Constant mid-gray, screen-blended at low strength for the "matte" black-lift
    # trick (screen(x, gray) raises the black point more than the highlights).
    arr = np.full((SIZE, SIZE, 3), 170, dtype=np.uint8)
    return Image.fromarray(arr, mode="RGB")


def make_vignette():
    yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    cx = cy = (SIZE - 1) / 2
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (SIZE / 2 * 1.05)
    # White center fading to black at the edges; clamp so corners aren't pure black.
    brightness = np.clip(1.0 - dist**2, 0.25, 1.0)
    gray = (brightness * 255).astype(np.uint8)
    arr = np.stack([gray, gray, gray], axis=-1)
    return Image.fromarray(arr, mode="RGB")


def main():
    OUT_DIR.mkdir(exist_ok=True)
    assets = {
        "warm.png": make_warm_golden(),
        "cool.png": make_cool_blue(),
        "vintage.png": make_vintage_faded(),
        "teal_orange.png": make_teal_orange(),
        "pastel.png": make_pastel(),
        "flat_gray.png": make_flat_gray(),
        "vignette.png": make_vignette(),
    }
    for name, img in assets.items():
        path = OUT_DIR / name
        img.save(path)
        print(f"wrote {path} ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    main()
