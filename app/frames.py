"""Single-photo frame/border post-processing effects, applied on top of an already-
generated cartoon-worker output image. Unlike app.collage.py (multi-photo layouts),
these operate on one image - a literal sprocket-hole filmstrip border is the kind of
precise graphic element diffusion prompting can't reliably render (same lesson as
figurine_3d's packaging composition), so it's drawn deterministically with PIL instead.
"""
import io

from PIL import Image, ImageDraw, ImageOps

BORDER_WIDTH = 70
HOLE_SPACING = 100
HOLE_SIZE = 38
BORDER_COLOR = (12, 12, 12)
HOLE_COLOR = (230, 225, 214)

SEPIA_SHADOW = (40, 26, 13)
SEPIA_HIGHLIGHT = (255, 240, 192)


def sepia_tone(image):
    """Classic sepia tint - desaturate to grayscale then colorize between a warm
    shadow/highlight pair. Used for the vintage look in retro-style collages."""
    gray = ImageOps.grayscale(image)
    return ImageOps.colorize(gray, black=SEPIA_SHADOW, white=SEPIA_HIGHLIGHT)


def add_horizontal_sprocket_bars(image, bar_height=BORDER_WIDTH):
    """Add black film-strip bars with sprocket holes along the top and bottom
    edges, spanning the full width - for a horizontal multi-frame filmstrip
    (see app.collage.retro_filmstrip), as opposed to add_filmstrip_border's
    left/right holes for a single portrait-oriented photo."""
    w, h = image.size
    canvas_h = h + bar_height * 2
    canvas = Image.new("RGB", (w, canvas_h), BORDER_COLOR)
    canvas.paste(image, (0, bar_height))

    draw = ImageDraw.Draw(canvas)
    hole_y_positions = [
        (bar_height - HOLE_SIZE) // 2,
        canvas_h - bar_height + (bar_height - HOLE_SIZE) // 2,
    ]
    x = HOLE_SPACING // 2
    while x + HOLE_SIZE < w:
        for y in hole_y_positions:
            draw.rounded_rectangle((x, y, x + HOLE_SIZE, y + HOLE_SIZE), radius=6, fill=HOLE_COLOR)
        x += HOLE_SPACING
    return canvas


def add_filmstrip_border(image):
    """Add a black 35mm-film-strip border with sprocket holes down the left and
    right edges, turning a single photo into a "frame from an old movie reel"."""
    w, h = image.size
    canvas_w = w + BORDER_WIDTH * 2
    canvas = Image.new("RGB", (canvas_w, h), BORDER_COLOR)
    canvas.paste(image, (BORDER_WIDTH, 0))

    draw = ImageDraw.Draw(canvas)
    hole_x_positions = [
        (BORDER_WIDTH - HOLE_SIZE) // 2,
        canvas_w - BORDER_WIDTH + (BORDER_WIDTH - HOLE_SIZE) // 2,
    ]
    y = HOLE_SPACING // 2
    while y + HOLE_SIZE < h:
        for x in hole_x_positions:
            draw.rounded_rectangle((x, y, x + HOLE_SIZE, y + HOLE_SIZE), radius=6, fill=HOLE_COLOR)
        y += HOLE_SPACING
    return canvas


POST_PROCESSORS = {
    "filmstrip_border": add_filmstrip_border,
}


def apply(name, image_bytes):
    """Run a named post-processor (app.cartoon_styles.STYLE_PRESETS "post_process"
    values) over PNG bytes and return new PNG bytes."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    processed = POST_PROCESSORS[name](image)
    buf = io.BytesIO()
    processed.save(buf, format="PNG")
    return buf.getvalue()
