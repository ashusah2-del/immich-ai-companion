"""Pure-PIL collage templates, composited from a mix of filter-worker output
and plain random photos (see filter_pipeline.maybe_build_collage). No ComfyUI
involved - this is plain image layout, not generation, so there's nothing for
a GPU to do here.
"""
import math
import random
from collections import namedtuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

from . import frames

BG = (235, 230, 220)

# A path string with an optional face_box - the (x1, y1, x2, y2) union of every
# recognized face in the photo, as 0-1 fractions of the displayed image (see
# immich_client.get_face_box) - and an optional caption label (used by
# two_photo_captioned; every other template ignores it). Every template accepts
# either plain path strings or Photo entries interchangeably, since paths only
# ever flow into _cover().
Photo = namedtuple("Photo", ["path", "face_box", "label"], defaults=[None])


def _crop_to_face(img, w, h, face_box, target_face_frac=0.34):
    """Crop+zoom the already-oriented `img` to (w, h), centered and zoomed on
    face_box, instead of _cover's resize-whole-photo-then-crop. Sized so the
    face(s) fill about target_face_frac of the block's height, with a bit
    more headroom above (forehead/hair) than below (chin/shoulders)."""
    src_w, src_h = img.size
    x1, y1, x2, y2 = face_box
    fx1, fy1, fx2, fy2 = x1 * src_w, y1 * src_h, x2 * src_w, y2 * src_h
    face_cx, face_cy = (fx1 + fx2) / 2, (fy1 + fy2) / 2
    face_h = fy2 - fy1

    crop_h = min(face_h / target_face_frac, src_h)
    crop_w = crop_h * w / h
    if crop_w > src_w:
        crop_w = src_w
        crop_h = crop_w * h / w

    left = min(max(face_cx - crop_w / 2, 0), src_w - crop_w)
    top = min(max(face_cy - crop_h * 0.42, 0), src_h - crop_h)

    crop = img.crop((round(left), round(top), round(left + crop_w), round(top + crop_h)))
    return crop.resize((round(w), round(h)), Image.LANCZOS)


_LAPLACIAN_KERNEL = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1)


def face_sharpness_score(path, face_box=None):
    """Variance of the Laplacian - a classic, GPU-free blur metric (a sharp
    photo has strong, varied edge responses; a blurry one smooths them out,
    collapsing the variance). Reusable anywhere a candidate photo needs a
    quality/not-blurry check before it's picked (see
    filter_pipeline._pick_sharpest for the then-and-now worker's use).

    Scored on just the recognized-face region when face_box is given (0-1
    fractions, same convention as Photo.face_box), rather than the whole
    photo - a portrait with a deliberately blurred background (bokeh)
    shouldn't be penalized, and a photo with a sharp background but a
    motion-blurred face should be.
    """
    img = ImageOps.exif_transpose(Image.open(path)).convert("L")
    if face_box is not None:
        w, h = img.size
        x1, y1, x2, y2 = face_box
        img = img.crop((round(x1 * w), round(y1 * h), round(x2 * w), round(y2 * h)))
    if min(img.size) < 20:
        return 0.0
    img.thumbnail((400, 400))
    laplacian = img.filter(_LAPLACIAN_KERNEL)
    return ImageStat.Stat(laplacian).var[0]


def _cover(photo, w, h, top_bias=0.85):
    """Resize+crop to exactly (w, h), like CSS object-fit: cover.

    If `photo` carries a face_box, zooms/centers on the recognized face(s)
    instead (see _crop_to_face). Otherwise falls back to a horizontally
    centered, vertically top-weighted crop: only (1 - top_bias) of the
    excess height is trimmed off the top, the rest off the bottom. These are
    mostly upright portraits/group photos, so a plain centered crop tends to
    slice through faces while leaving headroom above them - trimming
    feet/legs instead is the safer default tradeoff.
    """
    if isinstance(photo, Photo):
        path, face_box = photo.path, photo.face_box
    else:
        path, face_box = photo, None
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")

    if face_box is not None:
        return _crop_to_face(img, w, h, face_box)

    src_w, src_h = img.size
    scale = max(w / src_w, h / src_h)
    new_w, new_h = round(src_w * scale), round(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - w) // 2
    top = round((new_h - h) * (1 - top_bias))
    return img.crop((left, top, left + w, top + h))


def grid_2x2(paths):
    gutter, cell = 24, 800
    size = cell * 2 + gutter * 3
    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    positions = [
        (gutter, gutter),
        (gutter * 2 + cell, gutter),
        (gutter, gutter * 2 + cell),
        (gutter * 2 + cell, gutter * 2 + cell),
    ]
    for path, (x, y) in zip(paths, positions):
        canvas.paste(_cover(path, cell, cell), (x, y))
    return canvas


def hero_duo(paths):
    gutter = 24
    hero_w, hero_h = 1000, 1200
    small_w = 600
    small_h = (hero_h - gutter) // 2
    canvas_w = hero_w + gutter * 3 + small_w
    canvas_h = hero_h + gutter * 2
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    canvas.paste(_cover(paths[0], hero_w, hero_h), (gutter, gutter))
    x2 = gutter * 2 + hero_w
    canvas.paste(_cover(paths[1], small_w, small_h), (x2, gutter))
    canvas.paste(_cover(paths[2], small_w, small_h), (x2, gutter * 2 + small_h))
    return canvas


def filmstrip_3(paths):
    gutter, cell_w, cell_h, pad = 20, 700, 900, 40
    canvas_w = cell_w * 3 + gutter * 4
    canvas_h = cell_h + pad * 2
    canvas = Image.new("RGB", (canvas_w, canvas_h), (18, 18, 18))
    for i, path in enumerate(paths):
        x = gutter + i * (cell_w + gutter)
        canvas.paste(_cover(path, cell_w, cell_h), (x, pad))
    return canvas


_SCATTER_CANVAS_BUDGET = 1800


def _scattered_collage(paths, add_tape):
    """Shared polaroid-style scatter+rotate mechanic for polaroid_scatter and
    washi_scrapbook (which is just this plus a washi-tape corner accent).

    Divides the canvas into a roughly square grid sized to len(paths) - not a
    fixed 4 quadrants - so any photo count scatters cleanly instead of extra
    photos silently being dropped by zip(). Cell size (and so photo/border
    size) scales down as the grid grows, off a fixed canvas budget, so a
    3-4 photo collage looks the same size as before while a 10-photo one
    still fits without the canvas ballooning."""
    n = len(paths)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    cell = _SCATTER_CANVAS_BUDGET // max(cols, rows)
    photo_size = round(cell * 0.68)
    border = round(cell * 0.06)
    bottom_border = round(cell * 0.18)
    poly_w = photo_size + border * 2
    poly_h = photo_size + border + bottom_border

    canvas_w, canvas_h = cell * cols, cell * rows
    canvas = Image.new("RGB", (canvas_w, canvas_h), BG)

    cells = [(c * cell, r * cell) for r in range(rows) for c in range(cols)]
    random.shuffle(cells)

    for path, (cx, cy) in zip(paths, cells):
        x = random.randint(cx, max(cx, cx + cell - poly_w))
        y = random.randint(cy, max(cy, cy + cell - poly_h))
        angle = random.uniform(-8, 8)

        if add_tape:
            poly = Image.new("RGBA", (poly_w, poly_h), (255, 255, 255, 255))
        else:
            poly = Image.new("RGB", (poly_w, poly_h), (255, 255, 255))
        poly.paste(_cover(path, photo_size, photo_size), (border, border))

        if add_tape:
            tape = Image.new("RGBA", (poly_w, poly_h), (0, 0, 0, 0))
            ImageDraw.Draw(tape).rectangle(
                (-20, 10, poly_w * 0.55, 45), fill=random.choice(_TAPE_COLORS)
            )
            tape = tape.rotate(-25, resample=Image.BICUBIC)
            poly.alpha_composite(tape)
            poly = poly.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
        else:
            poly = poly.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=BG)

        px = min(max(x, 0), canvas_w - poly.width)
        py = min(max(y, 0), canvas_h - poly.height)
        canvas.paste(poly, (px, py), poly if add_tape else None)
    return canvas.convert("RGB") if add_tape else canvas


def polaroid_scatter(paths):
    return _scattered_collage(paths, add_tape=False)


def photo_booth_strip(paths):
    # Classic vertical photo-booth print: photos stacked in one tall strip.
    gutter, cell_w, cell_h, pad = 16, 500, 500, 28
    strip_w = cell_w + pad * 2
    strip_h = cell_h * len(paths) + gutter * (len(paths) - 1) + pad * 2
    canvas = Image.new("RGB", (strip_w, strip_h), (255, 255, 255))
    for i, path in enumerate(paths):
        y = pad + i * (cell_h + gutter)
        canvas.paste(_cover(path, cell_w, cell_h), (pad, y))
    return canvas


def circle_frame(paths):
    # Photos cropped into circles, laid out in a clean row.
    gutter, diameter = 40, 500
    n = len(paths)
    canvas_w = diameter * n + gutter * (n + 1)
    canvas_h = diameter + gutter * 2
    canvas = Image.new("RGB", (canvas_w, canvas_h), (250, 248, 244))
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
    for i, path in enumerate(paths):
        x = gutter + i * (diameter + gutter)
        canvas.paste(_cover(path, diameter, diameter), (x, gutter), mask)
    return canvas


_TAPE_COLORS = [
    (235, 200, 120, 190),
    (200, 225, 235, 190),
    (235, 180, 190, 190),
    (200, 235, 190, 190),
]


def washi_scrapbook(paths):
    # Same scattered-polaroid mechanic as polaroid_scatter, plus a colored
    # "washi tape" strip drawn across one corner of each photo.
    return _scattered_collage(paths, add_tape=True)


def mosaic_5(paths):
    # 1 large hero photo + a 2x2 grid of small tiles beside it.
    gutter, hero_size = 20, 900
    small = (hero_size - gutter) // 2
    canvas_w = hero_size + small * 2 + gutter * 4
    canvas_h = hero_size + gutter * 2
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    canvas.paste(_cover(paths[0], hero_size, hero_size), (gutter, gutter))

    x2 = gutter * 2 + hero_size
    positions = [
        (x2, gutter),
        (x2 + small + gutter, gutter),
        (x2, gutter * 2 + small),
        (x2 + small + gutter, gutter * 2 + small),
    ]
    for path, (x, y) in zip(paths[1:], positions):
        canvas.paste(_cover(path, small, small), (x, y))
    return canvas


def retro_filmstrip(paths):
    # Horizontal strip of sepia-toned frames divided by thin gutters, bordered top
    # and bottom by sprocket-hole bars - a physical cut-of-35mm-film look, reusing
    # app.frames' sepia/sprocket-hole helpers (same ones the cartoon worker's
    # retro_film style uses for a single photo).
    gutter, cell_w, cell_h = 12, 650, 850
    n = len(paths)
    strip_w = cell_w * n + gutter * (n + 1)
    canvas = Image.new("RGB", (strip_w, cell_h), (5, 5, 5))
    for i, path in enumerate(paths):
        x = gutter + i * (cell_w + gutter)
        frame = frames.sepia_tone(_cover(path, cell_w, cell_h))
        canvas.paste(frame, (x, 0))
    return frames.add_horizontal_sprocket_bars(canvas, bar_height=70)


_CAPTION_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_EMOJI_FONT_PATH = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
# NotoColorEmoji ships a single embedded bitmap strike - any other requested size
# raises "OSError: invalid pixel size" - so render at its native size and resize
# the glyph ourselves rather than asking freetype for an arbitrary size.
_EMOJI_NATIVE_SIZE = 109


def _load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _render_emoji(emoji, target_size):
    """Render a single emoji glyph as its own tightly-cropped RGBA image, scaled
    to target_size on its longest side - see _EMOJI_NATIVE_SIZE for why this
    can't just be ImageFont.truetype(path, target_size)."""
    font = ImageFont.truetype(_EMOJI_FONT_PATH, _EMOJI_NATIVE_SIZE)
    pad = _EMOJI_NATIVE_SIZE
    glyph = Image.new("RGBA", (pad * 2, pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(glyph).text((0, 0), emoji, font=font, embedded_color=True)
    bbox = glyph.getbbox()
    if not bbox:
        return glyph.crop((0, 0, 1, 1))
    glyph = glyph.crop(bbox)
    scale = target_size / max(glyph.size)
    new_size = (max(1, round(glyph.width * scale)), max(1, round(glyph.height * scale)))
    return glyph.resize(new_size, Image.LANCZOS)


def _split_caption_emoji(label):
    """Split a "THEN · 2025 \U0001F389"-style label into (text, emoji), where emoji
    is "" if the label has no trailing emoji accent. Emoji codepoints all sit well
    above the accented-Latin range, so a cheap codepoint check on the last
    whitespace-separated token is enough - we only ever feed this our own
    text-plus-optional-single-emoji labels, not arbitrary user text."""
    if not label:
        return "", ""
    text, sep, last = label.rpartition(" ")
    if sep and any(ord(ch) > 0x2100 for ch in last):
        return text, last
    return label, ""


def two_photo_captioned(paths):
    # Two photos side by side, each with a caption drawn underneath (plus an
    # optional mood emoji accent - see _split_caption_emoji). Generic layout
    # reused by both the daily Collage worker's then-and-now style (captions
    # "THEN · <year>"/"NOW · <year>", see filter_pipeline._build_then_and_now_photo)
    # and the cartoon worker's cartoon-vs-original comparison (captions
    # "Cartoon"/"Original", see cartoon_pipeline._build_comparison_collage).
    # paths must be exactly 2 Photo entries carrying a `label`.
    gutter, cell_w, cell_h, caption_h = 30, 850, 1050, 160
    canvas_w = cell_w * 2 + gutter * 3
    canvas_h = cell_h + caption_h + gutter * 2
    canvas = Image.new("RGB", (canvas_w, canvas_h), (20, 20, 20))
    draw = ImageDraw.Draw(canvas)
    text_font = _load_font(_CAPTION_FONT_PATH, 56)

    for i, photo in enumerate(paths):
        x = gutter + i * (cell_w + gutter)
        canvas.paste(_cover(photo, cell_w, cell_h), (x, gutter))

        label = photo.label if isinstance(photo, Photo) and photo.label else ""
        text, emoji = _split_caption_emoji(label)
        caption_top = gutter + cell_h

        tx1, ty1, tx2, ty2 = draw.textbbox((0, 0), text, font=text_font)
        draw.text(
            (x + (cell_w - (tx2 - tx1)) // 2, caption_top + 15),
            text, font=text_font, fill=(255, 255, 255),
        )
        if emoji:
            emoji_img = _render_emoji(emoji, target_size=70)
            ex = x + (cell_w - emoji_img.width) // 2
            ey = caption_top + 80
            canvas.paste(emoji_img, (ex, ey), emoji_img)
    return canvas


# Templates whose canvas size is computed from a hardcoded cell count, so they
# only work for that one exact photo count. two_photo_captioned is further
# restricted to *only* ever be picked for 2 (see build_collage) since callers
# (then-and-now, cartoon-vs-original) rely on it specifically to draw their
# captions - a randomly-chosen alternative template would silently drop them.
FIXED_COUNT_TEMPLATES = {
    2: [two_photo_captioned],
    3: [hero_duo, filmstrip_3],
    4: [grid_2x2],
    5: [mosaic_5],
}
# polaroid_scatter/washi_scrapbook/circle_frame/photo_booth_strip/retro_filmstrip
# all size their canvas/grid from len(paths) directly, so they're genuinely
# count-agnostic - the only templates that can render a 6-10 photo collage
# (see config.COLLAGE_PHOTO_COUNT_MAX) as well as backfill more variety into
# the smaller fixed counts above.
FLEXIBLE_TEMPLATES = [
    polaroid_scatter, washi_scrapbook, circle_frame, photo_booth_strip, retro_filmstrip,
]


def build_collage(paths):
    """Pick a random template that supports len(paths) and composite it.

    Returns (PIL.Image, template_name) so the caller can record which template
    was used alongside the output.
    """
    n = len(paths)
    if n == 2:
        templates = FIXED_COUNT_TEMPLATES[2]
    else:
        templates = list(FIXED_COUNT_TEMPLATES.get(n, [])) + FLEXIBLE_TEMPLATES
    if not templates:
        raise ValueError(f"no collage template supports {n} photos")
    template = random.choice(templates)
    return template(paths), template.__name__
