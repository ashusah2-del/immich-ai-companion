"""A library of 50 procedurally-drawn, light-toned collage background
"scenes", reusable across any app.collage template the same way
app.frame_styles' 50 skins are. Every entry renders at an arbitrary (w, h)
via BACKGROUNDS[name]["apply"](w, h), or let random_background(w, h) pick one.

Kept deliberately light and low-contrast: these sit *behind* framed photos,
so any decoration (dots, confetti, stripes, stars, ...) is drawn at low
opacity over a light base color - present enough to read as texture, never
competing with the photos on top of it. Same reasoning as app.frame_styles'
"none of these are sourced from an external asset" - drawn procedurally with
PIL rather than a downloaded texture of unclear licensing.
"""
import math
import random
from functools import partial

from PIL import Image, ImageDraw, ImageFilter

# A light, airy palette - distinct from app.frame_styles' bolder ring/skin
# colors (this is background, not foreground), but warm enough to feel like
# one coherent app rather than two unrelated visual languages.
_IVORY = (250, 247, 240)
_CREAM = (250, 244, 232)
_LINEN = (245, 238, 224)
_BLUSH = (248, 230, 227)
_POWDER_BLUE = (223, 236, 241)
_MINT = (225, 238, 226)
_LILAC = (236, 226, 240)
_PALE_GOLD = (248, 238, 210)
_PALE_PEACH = (250, 226, 206)
_PALE_SAGE = (231, 236, 216)
_PALE_GRAY = (236, 234, 229)
_PALE_TERRACOTTA = (246, 221, 211)

# Muted accent colors for low-opacity decoration drawn over the bases above.
_ACCENT_ROSE = (196, 130, 130)
_ACCENT_SAGE = (120, 140, 95)
_ACCENT_NAVY = (60, 80, 110)
_ACCENT_GOLD = (176, 130, 60)
_ACCENT_TERRACOTTA = (176, 96, 76)
_ACCENT_PLUM = (110, 79, 100)
_ACCENT_SKY = (100, 140, 160)
_ACCENT_CHARCOAL = (70, 66, 60)


def _base(w, h, color):
    return Image.new("RGB", (w, h), color)


# --- Recipes -------------------------------------------------------------
# Each takes (w, h, ...) and returns an RGB image. Decoration is always drawn
# through an "L" alpha mask so opacity stays low and consistent regardless of
# how many shapes get layered on.

def solid(w, h, color=_IVORY):
    """Plain flat light color - the simplest possible background, for when
    the frames/photos alone should carry all the visual interest."""
    return _base(w, h, color)


# Gradients are rendered at this tiny resolution and bilinear-upscaled to the
# real canvas size: a per-pixel Python loop over a ~2-megapixel collage canvas
# takes seconds, and upscaling a smooth ramp is indistinguishable by eye.
_GRADIENT_RES = 128


def linear_gradient(w, h, color1=_IVORY, color2=_CREAM, angle="vertical"):
    """A subtle two-tone gradient between two close light colors."""
    if angle == "vertical":
        sw, sh = 1, _GRADIENT_RES
    elif angle == "horizontal":
        sw, sh = _GRADIENT_RES, 1
    else:  # diagonal
        sw = sh = _GRADIENT_RES
    img = Image.new("RGB", (sw, sh))
    px = img.load()
    for y in range(sh):
        for x in range(sw):
            t = (y / max(sh - 1, 1)) if angle == "vertical" else (x / max(sw - 1, 1)) if angle == "horizontal" else ((x + y) / (sw + sh - 2))
            px[x, y] = tuple(round(color1[i] + (color2[i] - color1[i]) * t) for i in range(3))
    return img.resize((w, h), Image.BILINEAR)


def radial_gradient(w, h, inner=_IVORY, outer=_CREAM):
    """A soft radial gradient, lighter at the center, from one light color to
    another - reads as a gentle vignette-like glow rather than true shadow.
    Rendered square then stretched to (w, h), so on non-square canvases the
    glow is elliptical - it reaches all four edges evenly, which is exactly
    what a vignette should do."""
    s = _GRADIENT_RES
    img = Image.new("RGB", (s, s))
    px = img.load()
    c = (s - 1) / 2
    max_r = math.hypot(c, c)
    for y in range(s):
        for x in range(s):
            t = min(1.0, math.hypot(x - c, y - c) / max_r)
            px[x, y] = tuple(round(inner[i] + (outer[i] - inner[i]) * t) for i in range(3))
    return img.resize((w, h), Image.BILINEAR)


def paper_grain(w, h, base=_LINEN, accent=_ACCENT_TERRACOTTA, strokes=5, alpha=55):
    """Warm paper base with a few soft diagonal brush-stroke accents (the
    original app.collage._paper_background look, now parametrized)."""
    bg = _base(w, h, base)
    draw = ImageDraw.Draw(bg, "RGBA")
    for _ in range(strokes):
        x1, y1 = random.randint(0, w), random.randint(0, h)
        x2, y2 = x1 + random.randint(-w // 5, w // 5), y1 + random.randint(-h // 20, h // 20)
        draw.line([(x1, y1), (x2, y2)], fill=accent + (alpha,), width=random.randint(w // 90, w // 45) or 4)
    return bg


def polka_dots(w, h, base=_CREAM, dot_color=_ACCENT_TERRACOTTA, dot_r=16, spacing=76, alpha=45):
    """A faint, evenly-spaced polka-dot grid."""
    bg = _base(w, h, base)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(spacing // 2, h + spacing, spacing):
        offset = (spacing // 2) if (y // spacing) % 2 else 0
        for x in range(offset, w + spacing, spacing):
            draw.ellipse((x - dot_r, y - dot_r, x + dot_r, y + dot_r), fill=dot_color + (alpha,))
    bg.paste(overlay, (0, 0), overlay)
    return bg


def stripes(w, h, base=_IVORY, stripe_color=_ACCENT_SKY, stripe_w=48, angle_deg=32, alpha=30):
    """Soft diagonal pinstripes, drawn oversized and rotated to avoid gaps at
    the corners, then cropped back to (w, h)."""
    diag = round(math.hypot(w, h)) + stripe_w * 4
    big = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    for x in range(0, diag, stripe_w * 2):
        draw.rectangle((x, 0, x + stripe_w, diag), fill=stripe_color + (alpha,))
    big = big.rotate(angle_deg, resample=Image.BICUBIC)
    left, top = (big.width - w) // 2, (big.height - h) // 2
    overlay = big.crop((left, top, left + w, top + h))
    bg = _base(w, h, base)
    bg.paste(overlay, (0, 0), overlay)
    return bg


def confetti(w, h, base=_CREAM, colors=None, count=45, alpha=60, seed=None):
    """Small scattered rotated rectangles and circles, like faint confetti."""
    rng = random.Random(seed)
    colors = colors or [_ACCENT_ROSE, _ACCENT_GOLD, _ACCENT_SKY, _ACCENT_SAGE, _ACCENT_PLUM]
    bg = _base(w, h, base)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for _ in range(count):
        color = rng.choice(colors) + (alpha,)
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        s = rng.uniform(6, 16)
        if rng.random() < 0.5:
            piece = Image.new("RGBA", (round(s * 2), round(s)), (0, 0, 0, 0))
            ImageDraw.Draw(piece).rectangle((0, 0, piece.width, piece.height), fill=color)
            piece = piece.rotate(rng.uniform(0, 360), expand=True)
            overlay.alpha_composite(piece, (round(cx - piece.width / 2), round(cy - piece.height / 2)))
        else:
            d = ImageDraw.Draw(overlay)
            d.ellipse((cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2), fill=color)
    bg.paste(overlay, (0, 0), overlay)
    return bg


def grid_lines(w, h, base=_IVORY, line_color=_ACCENT_CHARCOAL, spacing=64, alpha=22):
    """A faint architectural grid of thin horizontal/vertical lines."""
    bg = _base(w, h, base)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for x in range(0, w, spacing):
        draw.line([(x, 0), (x, h)], fill=line_color + (alpha,), width=1)
    for y in range(0, h, spacing):
        draw.line([(0, y), (w, y)], fill=line_color + (alpha,), width=1)
    bg.paste(overlay, (0, 0), overlay)
    return bg


def bokeh(w, h, base=_LILAC, colors=None, count=22, alpha=40, seed=None):
    """Soft, blurred, out-of-focus circles drifting across the background."""
    rng = random.Random(seed)
    colors = colors or [_ACCENT_ROSE, _ACCENT_GOLD, _ACCENT_SKY, _ACCENT_PLUM]
    bg = _base(w, h, base)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for _ in range(count):
        r = rng.uniform(min(w, h) * 0.03, min(w, h) * 0.09)
        cx, cy = rng.uniform(-r, w + r), rng.uniform(-r, h + r)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=rng.choice(colors) + (alpha,))
    overlay = overlay.filter(ImageFilter.GaussianBlur(min(w, h) * 0.015))
    bg.paste(overlay, (0, 0), overlay)
    return bg


def color_halves(w, h, color1=_POWDER_BLUE, color2=_BLUSH, blend=0.18):
    """Two close light tones split diagonally, softly blended at the seam
    rather than a hard edge."""
    bg1 = Image.new("RGB", (w, h), color1)
    bg2 = Image.new("RGB", (w, h), color2)
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.polygon([(0, h), (w, 0), (w, h)], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(round(min(w, h) * blend)))
    bg1.paste(bg2, (0, 0), mask)
    return bg1


def sunburst(w, h, base=_PALE_GOLD, ray_color=_ACCENT_GOLD, rays=14, alpha=26):
    """Faint rays radiating from one corner, like soft morning light."""
    bg = _base(w, h, base)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = 0, 0
    r = math.hypot(w, h) * 1.2
    for i in range(rays):
        a0 = i * (math.pi / 2) / rays
        a1 = a0 + (math.pi / 2) / rays / 2
        draw.polygon([
            (cx, cy),
            (cx + r * math.cos(a0), cy + r * math.sin(a0)),
            (cx + r * math.cos(a1), cy + r * math.sin(a1)),
        ], fill=ray_color + (alpha,))
    bg.paste(overlay, (0, 0), overlay)
    return bg


def starfield(w, h, base=_POWDER_BLUE, star_color=_ACCENT_NAVY, count=28, alpha=50, seed=None):
    """Small four-point sparkle marks scattered across the background."""
    rng = random.Random(seed)
    bg = _base(w, h, base)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for _ in range(count):
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        s = rng.uniform(5, 12)
        draw.line([(cx - s, cy), (cx + s, cy)], fill=star_color + (alpha,), width=2)
        draw.line([(cx, cy - s), (cx, cy + s)], fill=star_color + (alpha,), width=2)
    bg.paste(overlay, (0, 0), overlay)
    return bg


def chevron(w, h, base=_MINT, chevron_color=_ACCENT_SAGE, size=52, alpha=26):
    """A faint zigzag/chevron pattern."""
    bg = _base(w, h, base)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(-size, h + size, size):
        points = []
        x = -size
        up = True
        while x < w + size:
            points.append((x, y + (0 if up else size)))
            x += size
            up = not up
        draw.line(points, fill=chevron_color + (alpha,), width=4)
    bg.paste(overlay, (0, 0), overlay)
    return bg


def soft_blobs(w, h, base=_PALE_SAGE, colors=None, count=5, alpha=35, seed=None):
    """A handful of large, soft, blurred organic blobs - abstract marble-like
    texture rather than distinct shapes."""
    rng = random.Random(seed)
    colors = colors or [_ACCENT_SAGE, _ACCENT_GOLD, _ACCENT_TERRACOTTA]
    bg = _base(w, h, base)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for _ in range(count):
        r = rng.uniform(min(w, h) * 0.18, min(w, h) * 0.32)
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=rng.choice(colors) + (alpha,))
    overlay = overlay.filter(ImageFilter.GaussianBlur(min(w, h) * 0.06))
    bg.paste(overlay, (0, 0), overlay)
    return bg


# --- 50 named backgrounds --------------------------------------------------
# Combines the recipes above with curated color variants, same approach as
# app.frame_styles.SKINS - reads as one cohesive light, airy library.

BACKGROUNDS = {
    "plain_ivory": {"description": "Flat ivory, no decoration.", "apply": partial(solid, color=_IVORY)},
    "plain_cream": {"description": "Flat cream, no decoration.", "apply": partial(solid, color=_CREAM)},
    "plain_linen": {"description": "Flat linen, no decoration.", "apply": partial(solid, color=_LINEN)},
    "plain_blush": {"description": "Flat blush pink, no decoration.", "apply": partial(solid, color=_BLUSH)},
    "plain_powder_blue": {"description": "Flat powder blue, no decoration.", "apply": partial(solid, color=_POWDER_BLUE)},
    "plain_mint": {"description": "Flat mint, no decoration.", "apply": partial(solid, color=_MINT)},
    "plain_lilac": {"description": "Flat lilac, no decoration.", "apply": partial(solid, color=_LILAC)},
    "plain_pale_gray": {"description": "Flat pale gray, no decoration.", "apply": partial(solid, color=_PALE_GRAY)},
    "gradient_ivory_cream": {"description": "Soft vertical gradient, ivory to cream.", "apply": partial(linear_gradient, color1=_IVORY, color2=_CREAM, angle="vertical")},
    "gradient_blush_peach": {"description": "Soft diagonal gradient, blush to pale peach.", "apply": partial(linear_gradient, color1=_BLUSH, color2=_PALE_PEACH, angle="diagonal")},
    "gradient_sky_lilac": {"description": "Soft horizontal gradient, powder blue to lilac.", "apply": partial(linear_gradient, color1=_POWDER_BLUE, color2=_LILAC, angle="horizontal")},
    "gradient_mint_gray": {"description": "Soft vertical gradient, mint to pale gray.", "apply": partial(linear_gradient, color1=_MINT, color2=_PALE_GRAY, angle="vertical")},
    "radial_ivory_gold": {"description": "Radial glow, ivory center fading to pale gold.", "apply": partial(radial_gradient, inner=_IVORY, outer=_PALE_GOLD)},
    "radial_cream_terracotta": {"description": "Radial glow, cream center fading to pale terracotta.", "apply": partial(radial_gradient, inner=_CREAM, outer=_PALE_TERRACOTTA)},
    "radial_blush_lilac": {"description": "Radial glow, blush center fading to lilac.", "apply": partial(radial_gradient, inner=_BLUSH, outer=_LILAC)},
    "paper_linen": {"description": "Warm linen paper grain with faint terracotta brush strokes.", "apply": partial(paper_grain, base=_LINEN, accent=_ACCENT_TERRACOTTA)},
    "paper_cream": {"description": "Cream paper grain with faint gold brush strokes.", "apply": partial(paper_grain, base=_CREAM, accent=_ACCENT_GOLD)},
    "paper_sage": {"description": "Pale sage paper grain with faint sage-green brush strokes.", "apply": partial(paper_grain, base=_PALE_SAGE, accent=_ACCENT_SAGE)},
    "dots_cream_terracotta": {"description": "Cream background with a faint terracotta polka-dot grid.", "apply": partial(polka_dots, base=_CREAM, dot_color=_ACCENT_TERRACOTTA)},
    "dots_blush_rose": {"description": "Blush background with a faint dusty-rose polka-dot grid.", "apply": partial(polka_dots, base=_BLUSH, dot_color=_ACCENT_ROSE, dot_r=13, spacing=60)},
    "dots_powder_navy": {"description": "Powder-blue background with a faint navy polka-dot grid.", "apply": partial(polka_dots, base=_POWDER_BLUE, dot_color=_ACCENT_NAVY)},
    "dots_mint_sage": {"description": "Mint background with a faint sage polka-dot grid.", "apply": partial(polka_dots, base=_MINT, dot_color=_ACCENT_SAGE, dot_r=20, spacing=90)},
    "stripes_ivory_sky": {"description": "Ivory background with faint diagonal sky-blue pinstripes.", "apply": partial(stripes, base=_IVORY, stripe_color=_ACCENT_SKY)},
    "stripes_cream_gold": {"description": "Cream background with faint diagonal gold pinstripes.", "apply": partial(stripes, base=_CREAM, stripe_color=_ACCENT_GOLD, angle_deg=-32)},
    "stripes_lilac_plum": {"description": "Lilac background with faint diagonal plum pinstripes.", "apply": partial(stripes, base=_LILAC, stripe_color=_ACCENT_PLUM, stripe_w=36)},
    "confetti_cream": {"description": "Cream background with faint scattered multicolor confetti.", "apply": partial(confetti, base=_CREAM)},
    "confetti_ivory": {"description": "Ivory background with faint scattered multicolor confetti, sparser.", "apply": partial(confetti, base=_IVORY, count=28, alpha=45)},
    "confetti_blush": {"description": "Blush background with faint scattered warm-toned confetti.", "apply": partial(confetti, base=_BLUSH, colors=[_ACCENT_ROSE, _ACCENT_GOLD, _ACCENT_TERRACOTTA])},
    "grid_ivory": {"description": "Ivory background with a faint charcoal architectural grid.", "apply": partial(grid_lines, base=_IVORY, line_color=_ACCENT_CHARCOAL)},
    "grid_powder_navy": {"description": "Powder-blue background with a faint navy grid.", "apply": partial(grid_lines, base=_POWDER_BLUE, line_color=_ACCENT_NAVY, spacing=80)},
    "grid_pale_gray": {"description": "Pale gray background with a very faint fine grid.", "apply": partial(grid_lines, base=_PALE_GRAY, line_color=_ACCENT_CHARCOAL, spacing=48, alpha=16)},
    "bokeh_lilac": {"description": "Lilac background with soft, blurred multicolor bokeh circles.", "apply": partial(bokeh, base=_LILAC)},
    "bokeh_cream": {"description": "Cream background with soft, blurred warm-toned bokeh circles.", "apply": partial(bokeh, base=_CREAM, colors=[_ACCENT_GOLD, _ACCENT_TERRACOTTA, _ACCENT_ROSE])},
    "bokeh_powder_blue": {"description": "Powder-blue background with soft, blurred cool-toned bokeh circles.", "apply": partial(bokeh, base=_POWDER_BLUE, colors=[_ACCENT_SKY, _ACCENT_NAVY, _ACCENT_PLUM], count=16)},
    "halves_sky_blush": {"description": "Powder blue and blush split diagonally, softly blended.", "apply": partial(color_halves, color1=_POWDER_BLUE, color2=_BLUSH)},
    "halves_mint_gold": {"description": "Mint and pale gold split diagonally, softly blended.", "apply": partial(color_halves, color1=_MINT, color2=_PALE_GOLD)},
    "halves_lilac_peach": {"description": "Lilac and pale peach split diagonally, softly blended.", "apply": partial(color_halves, color1=_LILAC, color2=_PALE_PEACH)},
    "sunburst_gold": {"description": "Pale gold background with faint golden rays from one corner.", "apply": partial(sunburst, base=_PALE_GOLD, ray_color=_ACCENT_GOLD)},
    "sunburst_peach": {"description": "Pale peach background with faint terracotta rays from one corner.", "apply": partial(sunburst, base=_PALE_PEACH, ray_color=_ACCENT_TERRACOTTA, rays=10)},
    "sunburst_sage": {"description": "Pale sage background with faint sage-green rays from one corner.", "apply": partial(sunburst, base=_PALE_SAGE, ray_color=_ACCENT_SAGE, rays=18)},
    "starfield_navy": {"description": "Powder-blue background with faint navy sparkle marks.", "apply": partial(starfield, base=_POWDER_BLUE, star_color=_ACCENT_NAVY)},
    "starfield_gold": {"description": "Ivory background with faint gold sparkle marks.", "apply": partial(starfield, base=_IVORY, star_color=_ACCENT_GOLD, count=36)},
    "starfield_plum": {"description": "Lilac background with faint plum sparkle marks.", "apply": partial(starfield, base=_LILAC, star_color=_ACCENT_PLUM, count=20)},
    "chevron_mint": {"description": "Mint background with a faint sage-green chevron pattern.", "apply": partial(chevron, base=_MINT, chevron_color=_ACCENT_SAGE)},
    "chevron_cream": {"description": "Cream background with a faint gold chevron pattern.", "apply": partial(chevron, base=_CREAM, chevron_color=_ACCENT_GOLD, size=40)},
    "chevron_blush": {"description": "Blush background with a faint dusty-rose chevron pattern.", "apply": partial(chevron, base=_BLUSH, chevron_color=_ACCENT_ROSE, size=64)},
    "blobs_sage": {"description": "Pale sage background with large, soft, blurred sage/gold blobs.", "apply": partial(soft_blobs, base=_PALE_SAGE)},
    "blobs_ivory": {"description": "Ivory background with large, soft, blurred warm-toned blobs.", "apply": partial(soft_blobs, base=_IVORY, colors=[_ACCENT_GOLD, _ACCENT_TERRACOTTA, _ACCENT_ROSE], count=4)},
    "blobs_powder_blue": {"description": "Powder-blue background with large, soft, blurred cool-toned blobs.", "apply": partial(soft_blobs, base=_POWDER_BLUE, colors=[_ACCENT_SKY, _ACCENT_NAVY, _ACCENT_PLUM], count=6)},
    "plain_pale_peach": {"description": "Flat pale peach, no decoration.", "apply": partial(solid, color=_PALE_PEACH)},
}


def apply_background(name, w, h):
    """Render the named BACKGROUNDS style at (w, h)."""
    return BACKGROUNDS[name]["apply"](w, h)


def random_background(w, h, exclude=()):
    """Pick a random background style, render it at (w, h), and return
    (image, name)."""
    names = [n for n in BACKGROUNDS if n not in exclude] or list(BACKGROUNDS)
    name = random.choice(names)
    return BACKGROUNDS[name]["apply"](w, h), name
