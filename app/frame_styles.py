"""A composable library of decorative photo-frame "skins" (color/decoration
treatments) and "shapes" (silhouettes) for wrapping a single already-cropped
photo, reusable across any app.collage template or the then-and-now/
comparison layouts.

Skins and shapes are fully decoupled: any of the 50 SKINS can be applied to
any of the 10 SHAPES via apply_frame(img, skin_name, shape_name) - a "classic
polaroid" skin can wrap a heart or a hexagon just as easily as a rectangle,
same as a "torn paper" skin can wrap a circle. A handful of skins that are
inherently about tracing a shape's straight edges (dashed/scalloped/torn/
stitched lines) only make full sense on a polygon-ish shape and gracefully
fall back to a plain solid ring on curved shapes (circle/oval/heart/star) -
see _EDGE_TRACING_SKINS below.

Every style here is drawn procedurally with PIL (shapes, color, masks) - none
of them are sourced from an external asset file or image, same reasoning as
app.frames' sprocket-hole border: precise deterministic graphic elements are
drawn directly rather than left to chance (or to a downloaded asset with
unclear licensing).
"""
import math
import random
from functools import partial

from PIL import Image, ImageDraw, ImageFilter

from . import frames as _frames

# A small curated palette, reused across skins so combinations feel like one
# coherent set rather than random clashing colors.
_WHITE = (255, 255, 255)
_CREAM = (250, 244, 232)
_BLACK = (20, 20, 20)
_CHARCOAL = (40, 38, 36)
_KRAFT = (214, 178, 145)
_DUSTY_ROSE = (212, 165, 165)
_SAGE = (163, 177, 138)
_NAVY = (42, 58, 84)
_GOLD = (196, 154, 74)
_TERRACOTTA = (196, 106, 84)
_SKY = (168, 197, 208)
_PLUM = (110, 79, 100)

_TAPE_COLORS = [
    (235, 200, 120, 190), (200, 225, 235, 190), (235, 180, 190, 190),
    (200, 235, 190, 190), (220, 200, 235, 190),
]


# --- Shapes ------------------------------------------------------------
# Each shape is an outline_fn(draw, box) that fills the silhouette into box
# (a (x0, y0, x1, y1) rectangle) on a mask. "rectangle" is the trivial/default
# case every skin was originally built around.

def _rectangle_outline(draw, box):
    draw.rectangle(box, fill=255)


def _rounded_rect_outline(draw, box, radius=36):
    draw.rounded_rectangle(box, radius=radius, fill=255)


def _circle_outline(draw, box):
    draw.ellipse(box, fill=255)


def _oval_outline(draw, box):
    x0, y0, x1, y1 = box
    pad_y = (y1 - y0) * 0.12
    draw.ellipse((x0, y0 + pad_y, x1, y1 - pad_y), fill=255)


def _hexagon_outline(draw, box):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    draw.polygon([
        (x0 + w * 0.25, y0), (x0 + w * 0.75, y0), (x1, y0 + h * 0.5),
        (x0 + w * 0.75, y1), (x0 + w * 0.25, y1), (x0, y0 + h * 0.5),
    ], fill=255)


def _octagon_outline(draw, box):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    c = 0.29
    draw.polygon([
        (x0 + w * c, y0), (x1 - w * c, y0), (x1, y0 + h * c),
        (x1, y1 - h * c), (x1 - w * c, y1), (x0 + w * c, y1),
        (x0, y1 - h * c), (x0, y0 + h * c),
    ], fill=255)


def _diamond_outline(draw, box):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    draw.polygon([
        (x0 + w / 2, y0), (x1, y0 + h / 2), (x0 + w / 2, y1), (x0, y0 + h / 2),
    ], fill=255)


def _arch_outline(draw, box):
    """Rounded-top rectangle, like a window/doorway arch."""
    x0, y0, x1, y1 = box
    r = (x1 - x0) / 2
    draw.pieslice((x0, y0, x1, y0 + 2 * r), 180, 360, fill=255)
    draw.rectangle((x0, y0 + r, x1, y1), fill=255)


def _star_outline(draw, box):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    outer_r, inner_r = min(x1 - x0, y1 - y0) / 2, min(x1 - x0, y1 - y0) / 2 * 0.42
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        r = outer_r if i % 2 == 0 else inner_r
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    draw.polygon(pts, fill=255)


def _heart_outline(draw, box):
    x0, y0, x1, y1 = box
    w = x1 - x0
    lobe_r = w * 0.28
    draw.ellipse((x0, y0, x0 + 2 * lobe_r, y0 + 2 * lobe_r), fill=255)
    draw.ellipse((x1 - 2 * lobe_r, y0, x1, y0 + 2 * lobe_r), fill=255)
    draw.polygon([(x0, y0 + lobe_r * 0.9), (x1, y0 + lobe_r * 0.9), ((x0 + x1) / 2, y1)], fill=255)


SHAPES = {
    "rectangle": _rectangle_outline,
    "rounded_rect": _rounded_rect_outline,
    "circle": _circle_outline,
    "oval": _oval_outline,
    "hexagon": _hexagon_outline,
    "octagon": _octagon_outline,
    "diamond": _diamond_outline,
    "arch": _arch_outline,
    "heart": _heart_outline,
    "star": _star_outline,
}

# Skins that trace individual straight edges (dashes/scallops/torn jags/
# stitches) only make sense on a polygon-ish silhouette - on a curved shape
# they fall back to a plain solid ring of the same color instead of crashing
# or drawing something nonsensical.
_EDGE_TRACING_SHAPES = {"rectangle", "rounded_rect", "hexagon", "octagon", "diamond"}


# --- Core compositing primitive ---------------------------------------------

def _shape_mask(outline_fn, box, size):
    mask = Image.new("L", size, 0)
    outline_fn(ImageDraw.Draw(mask), box)
    return mask


def _ring(img, outline_fn, color=_WHITE, width=24):
    """The one primitive every skin below is built from: expand the canvas by
    width on each side, fill the shape at the new (bigger) bounds with color,
    and show the original photo through the same shape inset by width - so
    every skin adds a decorative surround without cropping any more of the
    photo than the shape itself requires."""
    img = img.convert("RGB")
    w, h = img.size
    cw, ch = w + width * 2, h + width * 2

    outer = _shape_mask(outline_fn, (0, 0, cw, ch), (cw, ch))
    ring = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ring.paste(Image.new("RGBA", (cw, ch), color + (255,)), (0, 0), outer)

    inner = _shape_mask(outline_fn, (width, width, width + w, width + h), (cw, ch))
    photo = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    photo.paste(img, (width, width))
    photo.putalpha(inner)

    ring.alpha_composite(photo)
    return ring


def _polygon_points(outline_fn, box):
    """Best-effort list of vertices for a polygon-shaped outline_fn, used by
    the edge-tracing skins (dashed/scalloped/torn/stitched) to walk the
    silhouette's actual edges instead of assuming a plain rectangle. Returns
    None for curved shapes (circle/oval/arch/heart/star), which callers treat
    as "not edge-traceable"."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if outline_fn is _rectangle_outline or outline_fn is _rounded_rect_outline:
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if outline_fn is _hexagon_outline:
        return [
            (x0 + w * 0.25, y0), (x0 + w * 0.75, y0), (x1, y0 + h * 0.5),
            (x0 + w * 0.75, y1), (x0 + w * 0.25, y1), (x0, y0 + h * 0.5),
        ]
    if outline_fn is _octagon_outline:
        c = 0.29
        return [
            (x0 + w * c, y0), (x1 - w * c, y0), (x1, y0 + h * c),
            (x1, y1 - h * c), (x1 - w * c, y1), (x0 + w * c, y1),
            (x0, y1 - h * c), (x0, y0 + h * c),
        ]
    if outline_fn is _diamond_outline:
        return [(x0 + w / 2, y0), (x1, y0 + h / 2), (x0 + w / 2, y1), (x0, y0 + h / 2)]
    return None


# --- Skins -------------------------------------------------------------
# Every skin takes (img, shape) - shape defaults to "rectangle" - and returns
# an RGBA image. Each is a decoration *recipe*, independent of which shape
# it's applied to.

def solid_ring(img, shape="rectangle", color=_WHITE, width=24):
    """A plain colored ring of the chosen shape around the photo."""
    return _ring(img, SHAPES[shape], color, width)


def bottom_heavy_ring(img, shape="rectangle", color=_WHITE, width=26, bottom_extra=90):
    """Classic Polaroid proportions: a solid ring, then extra plain color
    padding added below (any shape - the "print" still reads as a print)."""
    card = solid_ring(img, shape, color, width)
    w, h = card.size
    out = Image.new("RGBA", (w, h + bottom_extra), color + (255,))
    out.paste(card, (0, 0), card)
    return out


def sepia_ring(img, shape="rectangle", color=_CREAM, width=26):
    """Sepia-toned photo inside a plain ring, for a vintage look."""
    return solid_ring(_frames.sepia_tone(img.convert("RGB")), shape, color, width)


def double_ring(img, shape="rectangle", inner_color=_WHITE, outer_color=_BLACK,
                 inner_width=10, gap=8, outer_width=6):
    """Two nested rings of the chosen shape with a plain gap between them."""
    step1 = solid_ring(img, shape, inner_color, inner_width)
    step2 = solid_ring(step1, shape, _WHITE, gap)
    return solid_ring(step2, shape, outer_color, outer_width)


def shadow_card(img, shape="rectangle", card_color=_WHITE, width=20, shadow_opacity=90, blur=18):
    """A ring of the chosen shape with a soft drop shadow instead of (or
    alongside) a hard edge - looks like a cut-out print resting on a table."""
    base = solid_ring(img, shape, card_color, width)
    w, h = base.size
    pad = blur * 2
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    shadow_alpha = base.split()[-1].filter(ImageFilter.GaussianBlur(blur // 2))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, shadow_opacity))
    shadow.putalpha(Image.eval(shadow_alpha, lambda a: min(a, shadow_opacity)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(shadow, (pad, pad + 10))
    canvas.alpha_composite(base, (pad, pad))
    return canvas


def tape_ring(img, shape="rectangle", base_color=_WHITE, width=24, tape_color=None, seed=None):
    """A ring with a single colored washi-tape strip drawn across one corner
    of its bounding box. Tape is drawn/rotated in its own small canvas (not
    the full card) since Image.rotate() pivots around its canvas center -
    rotating a corner-positioned rectangle within the full card would swing
    it away from the corner entirely."""
    rng = random.Random(seed)
    card = solid_ring(img, shape, base_color, width)
    w, h = card.size
    tape_w, tape_h = round(w * 0.4), round(h * 0.08)
    tape = Image.new("RGBA", (tape_w, tape_h), tape_color or rng.choice(_TAPE_COLORS))
    tape = tape.rotate(-25, expand=True, resample=Image.BICUBIC)
    tx, ty = -tape.width * 0.1, -tape.height * 0.12
    card.alpha_composite(tape, (round(tx), round(ty)))
    return card


def corner_ornament_ring(img, shape="rectangle", base_color=_WHITE, ornament_color=_GOLD,
                          width=24, ornament_size=26):
    """A ring plus a small filled triangle "ornament" tucked into each corner
    of the bounding box - works for any shape since it decorates the box
    corners, not the silhouette's own edges."""
    card = solid_ring(img, shape, base_color, width)
    draw = ImageDraw.Draw(card)
    w, h = card.size
    s = ornament_size
    draw.polygon([(0, 0), (s, 0), (0, s)], fill=ornament_color)
    draw.polygon([(w, 0), (w - s, 0), (w, s)], fill=ornament_color)
    draw.polygon([(0, h), (s, h), (0, h - s)], fill=ornament_color)
    draw.polygon([(w, h), (w - s, h), (w, h - s)], fill=ornament_color)
    return card


def dashed_ring(img, shape="rectangle", color=_CHARCOAL, base_color=_WHITE, width=24,
                dash_len=22, gap_len=14, dash_width=6):
    """A ring with a dashed line traced along the shape's own edges (polygon
    shapes only - falls back to a plain ring on curved shapes)."""
    card = solid_ring(img, shape, base_color, width)
    outline_fn = SHAPES[shape]
    w, h = card.size
    pts = _polygon_points(outline_fn, (width // 2, width // 2, w - width // 2, h - width // 2))
    if pts is None:
        return card
    draw = ImageDraw.Draw(card)
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        length = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(length // (dash_len + gap_len)))
        for i in range(steps + 1):
            t0 = i * (dash_len + gap_len) / length
            t1 = min(1.0, t0 + dash_len / length)
            if t0 >= 1:
                break
            draw.line([
                (x1 + (x2 - x1) * t0, y1 + (y2 - y1) * t0),
                (x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1),
            ], fill=color, width=dash_width)
    return card


def stitched_ring(img, shape="rectangle", color=_WHITE, stitch_color=_TERRACOTTA, width=26,
                   stitch_len=14, stitch_gap=10):
    """A ring with small perpendicular "stitch" tick marks traced along the
    shape's own edges (polygon shapes only - falls back to a plain ring on
    curved shapes), like a hand-sewn fabric photo mount."""
    card = solid_ring(img, shape, color, width)
    outline_fn = SHAPES[shape]
    w, h = card.size
    pts = _polygon_points(outline_fn, (width // 2, width // 2, w - width // 2, h - width // 2))
    if pts is None:
        return card
    draw = ImageDraw.Draw(card)
    tick = 7
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        length = math.hypot(x2 - x1, y2 - y1)
        nx, ny = -(y2 - y1) / length * tick, (x2 - x1) / length * tick
        steps = max(1, int(length // (stitch_len + stitch_gap)))
        for i in range(steps + 1):
            t = i * (stitch_len + stitch_gap) / length
            if t >= 1:
                break
            px, py = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            draw.line([(px - nx, py - ny), (px + nx, py + ny)], fill=stitch_color, width=3)
    return card


def scalloped_ring(img, shape="rectangle", color=_CREAM, width=34, scallop_r=16):
    """A ring whose outer edge is cut into a repeating scalloped (semicircle)
    pattern along the shape's own edges (polygon shapes only - falls back to
    a plain ring on curved shapes)."""
    card = solid_ring(img, shape, color, width)
    outline_fn = SHAPES[shape]
    w, h = card.size
    pts = _polygon_points(outline_fn, (0, 0, w, h))
    if pts is None:
        return card
    mask = Image.new("L", (w, h), 255)
    mdraw = ImageDraw.Draw(mask)
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        length = math.hypot(x2 - x1, y2 - y1)
        n = max(1, round(length / (scallop_r * 2)))
        for i in range(n + 1):
            t = i / n
            cx, cy = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            mdraw.ellipse((cx - scallop_r, cy - scallop_r, cx + scallop_r, cy + scallop_r), fill=0)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(card, (0, 0), mask)
    return out


def torn_ring(img, shape="rectangle", color=_CREAM, width=30, jag=10, seed=None):
    """A ring whose outer edge is a jagged, torn-paper silhouette traced
    along the shape's own edges (polygon shapes only - falls back to a plain
    ring on curved shapes)."""
    rng = random.Random(seed)
    card = solid_ring(img, shape, color, width)
    outline_fn = SHAPES[shape]
    w, h = card.size
    pts = _polygon_points(outline_fn, (0, 0, w, h))
    if pts is None:
        return card
    jagged = []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        n = 8
        for i in range(n):
            t = i / n
            x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            if i > 0:
                x += rng.uniform(-jag, jag)
                y += rng.uniform(-jag, jag)
            jagged.append((x, y))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(jagged, fill=255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(card, (0, 0), mask)
    return out


def film_sprocket(img, shape="rectangle", vertical=True):
    """35mm-filmstrip sprocket-hole border - inherently rectangle-specific
    (sprocket holes on a heart don't make sense), so `shape` is accepted for
    API consistency but always renders as a rectangle."""
    rgb = img.convert("RGB")
    if vertical:
        return _frames.add_filmstrip_border(rgb).convert("RGBA")
    return _frames.add_horizontal_sprocket_bars(rgb, bar_height=50).convert("RGBA")


# --- 50 named skins ----------------------------------------------------
# Each entry: description + the callable(img, shape=...) -> RGBA image.
# Combines the recipes above with curated color/parameter variants so the set
# reads as one cohesive library. Every skin here works with any SHAPES key
# via apply_frame(img, skin_name, shape_name) - see _EDGE_TRACING_SHAPES for
# the few that gracefully degrade to a plain ring on curved shapes.

SKINS = {
    "classic_polaroid": {"description": "White polaroid print, thick bottom border.", "apply": partial(bottom_heavy_ring, color=_WHITE)},
    "cream_polaroid": {"description": "Warm cream-toned polaroid print.", "apply": partial(bottom_heavy_ring, color=_CREAM)},
    "black_polaroid": {"description": "Black-bordered polaroid print, modern gallery look.", "apply": partial(bottom_heavy_ring, color=_BLACK, bottom_extra=70)},
    "kraft_polaroid": {"description": "Kraft-paper-toned polaroid print.", "apply": partial(bottom_heavy_ring, color=_KRAFT)},
    "sepia_polaroid": {"description": "Vintage sepia-toned photo in a cream polaroid frame.", "apply": partial(bottom_heavy_ring, color=_CREAM)},
    "thin_white_ring": {"description": "Slim clean white ring.", "apply": partial(solid_ring, color=_WHITE, width=14)},
    "thick_white_ring": {"description": "Bold wide white ring, gallery-print look.", "apply": partial(solid_ring, color=_WHITE, width=46)},
    "black_ring": {"description": "Bold solid black ring.", "apply": partial(solid_ring, color=_BLACK, width=24)},
    "charcoal_ring": {"description": "Softer charcoal-gray solid ring.", "apply": partial(solid_ring, color=_CHARCOAL, width=24)},
    "kraft_ring": {"description": "Warm kraft-paper solid ring.", "apply": partial(solid_ring, color=_KRAFT, width=28)},
    "rose_ring": {"description": "Dusty rose solid ring.", "apply": partial(solid_ring, color=_DUSTY_ROSE, width=24)},
    "sage_ring": {"description": "Muted sage-green solid ring.", "apply": partial(solid_ring, color=_SAGE, width=24)},
    "navy_ring": {"description": "Deep navy solid ring.", "apply": partial(solid_ring, color=_NAVY, width=24)},
    "gold_ring": {"description": "Warm gold solid ring.", "apply": partial(solid_ring, color=_GOLD, width=22)},
    "sky_ring": {"description": "Soft sky-blue solid ring.", "apply": partial(solid_ring, color=_SKY, width=24)},
    "plum_ring": {"description": "Deep plum solid ring.", "apply": partial(solid_ring, color=_PLUM, width=24)},
    "thin_black_line": {"description": "Very slim black line ring, minimal modern look.", "apply": partial(solid_ring, color=_BLACK, width=8)},
    "thin_gold_line": {"description": "Very slim gold line ring, elegant minimal look.", "apply": partial(solid_ring, color=_GOLD, width=8)},
    "double_classic": {"description": "White inner line + black outer line, gallery-mat look.", "apply": partial(double_ring, inner_color=_WHITE, outer_color=_BLACK)},
    "double_gold_black": {"description": "Gold inner line + black outer line, formal portrait look.", "apply": partial(double_ring, inner_color=_GOLD, outer_color=_BLACK, inner_width=8)},
    "double_navy_cream": {"description": "Navy inner line + cream outer line.", "apply": partial(double_ring, inner_color=_NAVY, outer_color=_CREAM, inner_width=8)},
    "dashed_charcoal": {"description": "White ring with a dashed charcoal line traced along the edges.", "apply": partial(dashed_ring, color=_CHARCOAL)},
    "dashed_terracotta": {"description": "Cream ring with a dashed terracotta line traced along the edges.", "apply": partial(dashed_ring, color=_TERRACOTTA, base_color=_CREAM)},
    "dashed_navy": {"description": "White ring with a dashed navy line traced along the edges.", "apply": partial(dashed_ring, color=_NAVY)},
    "scalloped_cream": {"description": "Cream ring with a scalloped (semicircle-cut) outer edge.", "apply": partial(scalloped_ring, color=_CREAM)},
    "scalloped_white": {"description": "White ring with a scalloped outer edge, dainty vintage look.", "apply": partial(scalloped_ring, color=_WHITE, scallop_r=13)},
    "scalloped_rose": {"description": "Dusty rose ring with a scalloped outer edge.", "apply": partial(scalloped_ring, color=_DUSTY_ROSE)},
    "torn_cream": {"description": "Cream ring with a jagged, hand-torn-paper edge.", "apply": partial(torn_ring, color=_CREAM)},
    "torn_kraft": {"description": "Kraft-paper ring with a jagged torn edge, rustic scrapbook look.", "apply": partial(torn_ring, color=_KRAFT, jag=14)},
    "torn_white": {"description": "White ring with a subtle torn-paper edge.", "apply": partial(torn_ring, color=_WHITE, jag=7)},
    "ornament_gold": {"description": "White ring with gold triangle ornaments in each corner.", "apply": partial(corner_ornament_ring, base_color=_WHITE, ornament_color=_GOLD)},
    "ornament_navy": {"description": "Cream ring with navy corner ornaments.", "apply": partial(corner_ornament_ring, base_color=_CREAM, ornament_color=_NAVY)},
    "ornament_terracotta": {"description": "White ring with terracotta corner ornaments.", "apply": partial(corner_ornament_ring, base_color=_WHITE, ornament_color=_TERRACOTTA, ornament_size=32)},
    "tape_white": {"description": "White ring with a single washi-tape accent across one corner.", "apply": partial(tape_ring, base_color=_WHITE)},
    "tape_kraft": {"description": "Kraft-paper ring with a washi-tape accent.", "apply": partial(tape_ring, base_color=_KRAFT)},
    "tape_cream": {"description": "Cream ring with a washi-tape accent.", "apply": partial(tape_ring, base_color=_CREAM)},
    "shadow_white": {"description": "Clean white ring with a soft drop shadow.", "apply": partial(shadow_card, card_color=_WHITE)},
    "shadow_cream": {"description": "Cream ring with a soft drop shadow.", "apply": partial(shadow_card, card_color=_CREAM)},
    "shadow_black": {"description": "Black ring with a soft drop shadow, dramatic gallery look.", "apply": partial(shadow_card, card_color=_BLACK, shadow_opacity=140)},
    "film_vertical": {"description": "35mm filmstrip sprocket holes down both sides (rectangle only).", "apply": partial(film_sprocket, vertical=True)},
    "film_horizontal": {"description": "35mm filmstrip sprocket bars across top and bottom (rectangle only).", "apply": partial(film_sprocket, vertical=False)},
    "stitched_cream": {"description": "Cream ring with terracotta hand-stitched tick marks along the edges.", "apply": partial(stitched_ring, color=_CREAM)},
    "stitched_white": {"description": "White ring with navy hand-stitched tick marks along the edges.", "apply": partial(stitched_ring, color=_WHITE, stitch_color=_NAVY)},
    "stitched_kraft": {"description": "Kraft-paper ring with cream hand-stitched tick marks.", "apply": partial(stitched_ring, color=_KRAFT, stitch_color=_CREAM)},
    "wide_kraft_polaroid": {"description": "Polaroid print with an extra-wide kraft-paper border.", "apply": partial(bottom_heavy_ring, color=_KRAFT, width=40, bottom_extra=110)},
    "wide_black_polaroid": {"description": "Polaroid print with an extra-wide black border, bold modern look.", "apply": partial(bottom_heavy_ring, color=_BLACK, width=36, bottom_extra=100)},
    "vintage_cream": {"description": "Cream ring around a warm, slightly faded vintage tone.", "apply": partial(sepia_ring, color=_CREAM, width=26)},
    "vintage_kraft": {"description": "Kraft-paper ring around a warm vintage tone.", "apply": partial(sepia_ring, color=_KRAFT, width=30)},
    "mat_black_gold": {"description": "Thick black ring with a slim gold inner accent, formal gallery mat.", "apply": partial(double_ring, inner_color=_GOLD, outer_color=_BLACK, inner_width=6, gap=4, outer_width=30)},
    "mat_white_navy": {"description": "Thick white ring with a slim navy inner accent.", "apply": partial(double_ring, inner_color=_NAVY, outer_color=_WHITE, inner_width=6, gap=4, outer_width=30)},
}


def apply_frame(img, skin_name, shape_name="rectangle"):
    """Apply a named SKINS decoration to img, cropped into a named SHAPES
    silhouette first. Any skin can be combined with any shape."""
    return SKINS[skin_name]["apply"](img, shape=shape_name)


def random_frame(exclude_skins=()):
    """Pick a random (skin_name, shape_name) pair, optionally excluding some
    skins (e.g. to force rotation the way cartoon style selection does)."""
    skin_names = [n for n in SKINS if n not in exclude_skins] or list(SKINS)
    return random.choice(skin_names), random.choice(list(SHAPES))
