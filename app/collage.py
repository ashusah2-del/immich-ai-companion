"""Pure-PIL collage templates, composited from a mix of filter-worker output
and plain random photos (see filter_pipeline.maybe_build_collage). No ComfyUI
involved - this is plain image layout, not generation, so there's nothing for
a GPU to do here.
"""
import math
import random
from collections import namedtuple
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

from . import background_styles, frame_styles, frames

BG = (235, 230, 220)

# A path string with an optional face_box - the (x1, y1, x2, y2) union of every
# recognized face in the photo, as 0-1 fractions of the displayed image (see
# immich_client.get_face_box) - and an optional caption label (used by
# two_photo_captioned; every other template ignores it). Every template accepts
# either plain path strings or Photo entries interchangeably, since paths only
# ever flow into _cover().
Photo = namedtuple("Photo", ["path", "face_box", "label"], defaults=[None])


def _face_crop_rect(src_w, src_h, w, h, face_box, target_face_frac=0.34):
    """The (left, top, crop_w, crop_h) source rect _crop_to_face will cut for
    a (w, h) target - pure math, shared with _shape_fits_faces so shape
    compatibility can be predicted without rendering anything."""
    x1, y1, x2, y2 = face_box
    fx1, fy1, fx2, fy2 = x1 * src_w, y1 * src_h, x2 * src_w, y2 * src_h
    face_cx, face_cy = (fx1 + fx2) / 2, (fy1 + fy2) / 2
    face_h = fy2 - fy1

    crop_h = min(face_h / target_face_frac, src_h)
    crop_w = crop_h * w / h
    if crop_w > src_w:
        crop_w = src_w
        crop_h = crop_w * h / w

    # If the face sits near an image edge, a max-size crop can't center it,
    # and in a shaped frame (heart, star, circle...) the face then lands in
    # the silhouette's clipped margin. Prefer zooming in: shrink the crop to
    # the largest size that still lets the face sit centered horizontally
    # and at the 0.42 vertical anchor - but never so tight that the face
    # fills more than ~60% of the crop height.
    centerable_h = min(
        face_cy / 0.42 if face_cy > 0 else crop_h,
        (src_h - face_cy) / 0.58,
        2 * min(face_cx, src_w - face_cx) * h / w,
    )
    fit_h = max(face_h / 0.6, min(crop_h, centerable_h))
    if fit_h < crop_h:
        crop_h = fit_h
        crop_w = crop_h * w / h

    left = min(max(face_cx - crop_w / 2, 0), src_w - crop_w)
    top = min(max(face_cy - crop_h * 0.42, 0), src_h - crop_h)
    return left, top, crop_w, crop_h


def _crop_to_face(img, w, h, face_box):
    """Crop+zoom the already-oriented `img` to (w, h), centered and zoomed on
    face_box, instead of _cover's resize-whole-photo-then-crop. Sized so the
    face(s) fill about a third of the block's height, with a bit more
    headroom above (forehead/hair) than below (chin/shoulders)."""
    src_w, src_h = img.size
    left, top, crop_w, crop_h = _face_crop_rect(src_w, src_h, w, h, face_box)
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
_FONT_DIR = Path(__file__).parent / "fonts"
# Handwritten/display caption fonts for the then-and-now layouts, bundled in
# app/fonts (OFL/Apache licensed - see the license files there) so they exist
# on any machine the worker runs on, unlike system font paths. One is picked
# per collage so both captions match. Each carries a size multiplier: script
# faces render wildly different x-heights at the same nominal point size.
_CAPTION_FONTS = [
    ("Pacifico-Regular.ttf", 1.0),
    ("PermanentMarker-Regular.ttf", 0.95),
    ("Kalam-Bold.ttf", 1.0),
    ("Courgette-Regular.ttf", 1.05),
    ("GreatVibes-Regular.ttf", 1.45),
    ("AmaticSC-Bold.ttf", 1.4),
]
_CAPTION_INK = (58, 46, 38)


def _random_caption_font(base_size):
    name, scale = random.choice(_CAPTION_FONTS)
    path = _FONT_DIR / name
    if path.exists():
        return _load_font(str(path), round(base_size * scale))
    return _load_font(_CAPTION_FONT_PATH, base_size)
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


def _draw_caption_ink(canvas, x, y, w, h, label, font, band="bottom", gap=18):
    """Draw label (+ optional emoji, see _split_caption_emoji) in dark
    handwriting-style ink just *outside* the top or bottom edge of the framed
    card whose bounding box on canvas is (x, y, w, h) - close to the frame
    without ever covering it (or the face inside it). The background scenes
    are all light (see app.background_styles), so the ink needs no
    scrim/pill behind it to stay legible."""
    if not label:
        return
    text, emoji = _split_caption_emoji(label)
    draw = ImageDraw.Draw(canvas)
    tx1, ty1, tx2, ty2 = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = tx2 - tx1, ty2 - ty1
    emoji_img = _render_emoji(emoji, target_size=round(text_h * 0.9)) if emoji else None
    gap_e = round(text_h * 0.3) if emoji_img else 0
    total_w = text_w + gap_e + (emoji_img.width if emoji_img else 0)

    px = x + (w - total_w) // 2
    py = y + h + gap if band == "bottom" else y - gap - text_h
    px = min(max(px, 8), canvas.width - total_w - 8)
    py = min(max(py, 8), canvas.height - text_h - 8)

    draw.text((px - tx1, py - ty1), text, font=font, fill=_CAPTION_INK)
    if emoji_img:
        ey = py + (text_h - emoji_img.height) // 2
        canvas.paste(emoji_img, (px + text_w + gap_e, ey), emoji_img)


# Central fraction of a square card guaranteed to be inside each
# frame_styles shape silhouette (width, height) - conservative "safe boxes"
# for checking whether a photo's recognized faces survive the shape's
# cutaway. rounded_rect keeps nearly everything; a star keeps very little.
_SHAPE_SAFE_FRAC = {
    "rectangle": (0.96, 0.96),
    "rounded_rect": (0.9, 0.9),
    "circle": (0.7, 0.7),
    "oval": (0.7, 0.6),
    "hexagon": (0.7, 0.85),
    "octagon": (0.8, 0.8),
    "diamond": (0.55, 0.55),
    "arch": (0.85, 0.8),
    "heart": (0.6, 0.5),
    "star": (0.42, 0.42),
}


def _shape_fits_faces(photo, shape_name):
    """Whether every recognized face survives shape_name's silhouette: predict
    where the face union lands inside the square crop (_face_crop_rect - no
    rendering needed) and require it inside the shape's safe box. Photos
    without face data fit anything."""
    if not isinstance(photo, Photo) or photo.face_box is None:
        return True
    with Image.open(photo.path) as img:
        img = ImageOps.exif_transpose(img)
        src_w, src_h = img.size
    left, top, crop_w, crop_h = _face_crop_rect(src_w, src_h, 1, 1, photo.face_box)
    x1, y1, x2, y2 = photo.face_box
    fx1 = (x1 * src_w - left) / crop_w
    fy1 = (y1 * src_h - top) / crop_h
    fx2 = (x2 * src_w - left) / crop_w
    fy2 = (y2 * src_h - top) / crop_h
    safe_w, safe_h = _SHAPE_SAFE_FRAC.get(shape_name, (0.6, 0.6))
    return (fx1 >= 0.5 - safe_w / 2 and fx2 <= 0.5 + safe_w / 2
            and fy1 >= 0.5 - safe_h / 2 and fy2 <= 0.5 + safe_h / 2)


def _fitting_shape(photos, shape_name, tries=8):
    """Return shape_name if every photo's faces fit it, else re-roll ("if the
    image is not compatible with the frame, change the frame") - falling back
    to rounded_rect, whose safe box fits any face-centered crop."""
    for _ in range(tries):
        if all(_shape_fits_faces(p, shape_name) for p in photos):
            return shape_name
        shape_name = random.choice(list(frame_styles.SHAPES))
    return "rounded_rect"


def _framed_card(photo, size, angle, skin_name, shape_name):
    """A single photo cropped to (size, size), wrapped in a named
    app.frame_styles skin+shape combo, then rotated by angle degrees. Returns
    an RGBA image sized to its rotated bounding box."""
    square = _cover(photo, size, size)
    card = frame_styles.apply_frame(square, skin_name, shape_name)
    return card.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))


def _flex_card_size(cell_w, cell_h, fill=0.9):
    """How big a square crop should be so the framed card it becomes fills
    `fill` of the *smaller* cell dimension - basing it on the larger
    dimension (as a fixed-pixel shrink previously did) can make the square
    wider than a narrow cell and overflow into the neighboring photo."""
    return round(min(cell_w, cell_h) * fill)


def _fit_card(card, max_w, max_h):
    """Downscale a framed card if its decoration pushed it past the space its
    cell reserves for it - some skins (drop shadows, wide polaroid borders)
    grow a card 100px+ beyond the photo crop, which would otherwise eat the
    strip reserved for the ink caption beside the frame."""
    scale = min(max_w / card.width, max_h / card.height, 1.0)
    if scale < 1.0:
        card = card.resize((round(card.width * scale), round(card.height * scale)), Image.LANCZOS)
    return card


def _vertical_label(text, font, color=(35, 27, 22)):
    """Bold text rotated 90 degrees (reads bottom-to-top), for a date/caption
    placed in the margin beside a photo rather than overlaid on it - used by
    the diagonal layout, which keeps captions off the photos entirely."""
    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    bbox = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    label_img = Image.new("RGBA", (w + 10, h + 10), (0, 0, 0, 0))
    ImageDraw.Draw(label_img).text((5 - bbox[0], 5 - bbox[1]), text, font=font, fill=color + (255,))
    return label_img.rotate(90, expand=True, resample=Image.BICUBIC)


# Vertical strip each two-photo cell reserves beside the card for its ink
# caption - the card is sized/centered in what's left, so caption and frame
# sit close together but can never overlap.
_CAPTION_STRIP = 110


def _two_photo_side_by_side(paths):
    # A random app.background_styles scene behind two photos, each wrapped
    # in the same randomly-picked app.frame_styles skin+shape (see
    # TEMPLATES.md), cropped to a square so the shape reads correctly
    # regardless of layout aspect (same reasoning as framed_mosaic), with a
    # handwritten ink caption just below each frame.
    gutter, cell_w, cell_h = 30, 850, 1050
    canvas, _bg_name = background_styles.random_background(cell_w * 2 + gutter * 3, cell_h + gutter * 2)
    font = _random_caption_font(64)
    card_h = cell_h - _CAPTION_STRIP
    size = _flex_card_size(cell_w, card_h)
    skin_name, shape_name = frame_styles.random_frame()
    shape_name = _fitting_shape(paths, shape_name)
    for i, photo in enumerate(paths):
        x = gutter + i * (cell_w + gutter)
        card = _fit_card(_framed_card(photo, size, 0, skin_name, shape_name), cell_w, card_h)
        fx, fy = x + (cell_w - card.width) // 2, gutter + (card_h - card.height) // 2
        canvas.paste(card, (fx, fy), card)
        label = photo.label if isinstance(photo, Photo) else None
        _draw_caption_ink(canvas, fx, fy, card.width, card.height, label, font, band="bottom")
    return canvas


def _two_photo_stacked(paths):
    # Same app.background_styles + app.frame_styles treatment as
    # _two_photo_side_by_side, stacked vertically. Captions go on the outward
    # edges (above the top card, below the bottom one) so they stay near
    # their own frame and clear of the other photo's.
    gutter, cell_w, cell_h = 30, 950, 750
    canvas, _bg_name = background_styles.random_background(cell_w + gutter * 2, cell_h * 2 + gutter * 3)
    font = _random_caption_font(64)
    card_h = cell_h - _CAPTION_STRIP
    size = _flex_card_size(cell_w, card_h)
    skin_name, shape_name = frame_styles.random_frame()
    shape_name = _fitting_shape(paths, shape_name)
    for i, photo in enumerate(paths):
        y = gutter + i * (cell_h + gutter)
        band = "top" if i == 0 else "bottom"
        card = _fit_card(_framed_card(photo, size, 0, skin_name, shape_name), cell_w, card_h)
        fx = gutter + (cell_w - card.width) // 2
        fy = y + (card_h - card.height) // 2 + (_CAPTION_STRIP if band == "top" else 0)
        canvas.paste(card, (fx, fy), card)
        label = photo.label if isinstance(photo, Photo) else None
        _draw_caption_ink(canvas, fx, fy, card.width, card.height, label, font, band=band)
    return canvas


def _two_photo_diagonal(paths):
    # Scrapbook-diary style: a random app.background_styles scene, two photos
    # cascading diagonally at their own gentle rotation, each wrapped in the
    # same randomly-picked app.frame_styles skin+shape (see TEMPLATES.md -
    # any of the 50 skins can wrap any of the 10 shapes), with a bold
    # vertical date/label in the margin beside each photo - captions never
    # touch a photo at all in this layout, so there's no face to avoid.
    size = 620
    canvas_w, canvas_h = 1000, 1560
    canvas, _bg_name = background_styles.random_background(canvas_w, canvas_h)
    font = _random_caption_font(60)
    skin_name, shape_name = frame_styles.random_frame()
    shape_name = _fitting_shape(paths, shape_name)

    slots = [(40, 50, -6, 760, 60), (330, 840, 5, 40, 1180)]
    for photo, (px, py, angle, lx, ly) in zip(paths, slots):
        card = _framed_card(photo, size, angle, skin_name, shape_name)
        canvas.paste(card, (px, py), card)

        label = photo.label if isinstance(photo, Photo) and photo.label else ""
        text, _emoji = _split_caption_emoji(label)
        if text:
            label_img = _vertical_label(text.upper(), font)
            # Wide script fonts can render a taller-than-planned rotated
            # label - clamp so it never runs off the canvas.
            lx = min(max(lx, 10), canvas_w - label_img.width - 10)
            ly = min(max(ly, 10), canvas_h - label_img.height - 10)
            canvas.paste(label_img, (lx, ly), label_img)
    return canvas.convert("RGB")


def two_photo_captioned(paths):
    # Two captioned photos, in one of three layouts chosen at random - side
    # by side, stacked vertically, or cascading diagonally - on a random
    # background scene, framed by a random skin+shape, captioned in a random
    # handwritten font (see _CAPTION_FONTS). Captions sit in dark ink just
    # outside their own frame's edge (or in the margin beside it, for the
    # diagonal layout) - near the frame but never overlapping it or the
    # face inside it. Reused by both the daily Collage
    # worker's then-and-now style (captions "THEN · <year>"/"NOW · <year>",
    # see filter_pipeline._build_then_and_now_photo) and the cartoon worker's
    # cartoon-vs-original comparison (captions "Cartoon"/"Original", see
    # cartoon_pipeline._build_comparison_collage). paths must be exactly 2
    # Photo entries carrying a `label`.
    layout = random.choice([_two_photo_side_by_side, _two_photo_stacked, _two_photo_diagonal])
    return layout(paths)


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
def framed_mosaic(paths):
    """Showcases app.frame_styles and app.background_styles together: every
    photo in the collage gets the same randomly-picked skin (for a cohesive
    set) but its own randomly-picked shape (circle, heart, hexagon, star,
    ...), gently rotated, on a random light background scene. Each photo is
    cropped to a square before framing so every shape (including the curved
    ones) renders cleanly regardless of whether the source photo is portrait
    or landscape - the crop is what adapts to the source orientation, not
    the shape itself."""
    n = len(paths)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    cell, gutter = 480, 36
    canvas_w, canvas_h = cell * cols + gutter * (cols + 1), cell * rows + gutter * (rows + 1)
    canvas, _bg_name = background_styles.random_background(canvas_w, canvas_h)

    skin_name = random.choice(list(frame_styles.SKINS))
    size = _flex_card_size(cell, cell)
    for i, photo in enumerate(paths):
        shape_name = _fitting_shape([photo], random.choice(list(frame_styles.SHAPES)))
        square = _cover(photo, size, size)
        framed = frame_styles.apply_frame(square, skin_name, shape_name)
        framed = framed.rotate(
            random.uniform(-8, 8), expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0)
        )
        col, row = i % cols, i // cols
        x = gutter + col * (cell + gutter) + (cell - framed.width) // 2
        y = gutter + row * (cell + gutter) + (cell - framed.height) // 2
        canvas.paste(framed, (x, y), framed)
    return canvas.convert("RGB")


# polaroid_scatter/washi_scrapbook/circle_frame/photo_booth_strip/retro_filmstrip/
# framed_mosaic all size their canvas/grid from len(paths) directly, so they're
# genuinely count-agnostic - the only templates that can render a 6-10 photo
# collage (see config.COLLAGE_PHOTO_COUNT_MAX) as well as backfill more variety
# into the smaller fixed counts above.
FLEXIBLE_TEMPLATES = [
    polaroid_scatter, washi_scrapbook, circle_frame, photo_booth_strip, retro_filmstrip,
    framed_mosaic,
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
