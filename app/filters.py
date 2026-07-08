"""Google Photos-style color-grade presets, expressed as an ordered list of
primitive steps that comfyui_client._build_filter_workflow() interprets into
a ComfyUI node graph. Presets differ only in parameters, not structure, so
this stays data rather than one hand-built workflow function per preset.

Each step's "op" must be one comfyui_client._build_filter_workflow understands:
  color_transfer(ref, method, strength) - grade toward a data/filter_assets/ reference
  brightness(factor) / contrast(factor)  - AdjustBrightness/AdjustContrast
  grayscale_yuv()                        - swap to the YUV Y-channel (true grayscale)
  add_noise(strength)                    - film grain
  quantize(colors, dither)               - posterize/banding for a faded look
  blend_with_blurred(blend_mode, factor) - soft-focus glow (blend with a blurred copy)
  blend_with_self(blend_mode, factor)    - self-overlay punch/contrast trick
  blend_with_asset(ref, blend_mode, factor) - blend with a data/filter_assets/ reference

color_transfer's method must be "reinhard_lab" or "histogram" - NOT "mkl_lab",
which crashes with "aten::_linalg_eigh not implemented" on the Mac's MPS backend
(confirmed live against the ComfyUI host).

A vignette blend is appended after every preset by the pipeline itself
(comfyui_client.apply_filter_image), not baked in here.
"""

FILTER_PRESETS = {
    "vivid": {
        "description": "Bright, punchy, highly saturated colors - good for landscapes, food, bold scenes.",
        "steps": [
            # No saturation node is installed on the ComfyUI host, and grading
            # toward a reference image (as the other presets do) blows out skin
            # tones badly (verified live on a real portrait: faces turned red).
            # Self-overlay is the classic punch trick - boosts contrast/perceived
            # saturation from luminance alone, without any reference-driven hue skew.
            {"op": "blend_with_self", "blend_mode": "overlay", "factor": 0.4},
            {"op": "contrast", "factor": 1.18},
            {"op": "brightness", "factor": 1.03},
        ],
    },
    "bw_noir": {
        "description": "Classic dramatic black & white - good for portraits, moody or high-contrast shots.",
        "steps": [
            {"op": "grayscale_yuv"},
            {"op": "contrast", "factor": 1.15},
        ],
    },
    "warm_golden": {
        "description": "Warm golden-hour tone - good for sunsets, outdoor portraits, cozy scenes.",
        "steps": [
            {"op": "color_transfer", "ref": "warm.png", "method": "reinhard_lab", "strength": 0.45},
            {"op": "brightness", "factor": 1.04},
        ],
    },
    "cool_blue": {
        "description": "Cool cinematic blue/teal tone - good for city, night, or overcast shots.",
        "steps": [
            {"op": "color_transfer", "ref": "cool.png", "method": "reinhard_lab", "strength": 0.45},
            {"op": "contrast", "factor": 1.05},
        ],
    },
    "vintage_faded": {
        "description": "Faded retro film look with light grain - good for nostalgic or candid photos.",
        "steps": [
            {"op": "color_transfer", "ref": "vintage.png", "method": "histogram", "strength": 0.35},
            {"op": "contrast", "factor": 0.9},
            {"op": "add_noise", "strength": 0.06},
            {"op": "quantize", "colors": 48, "dither": "floyd-steinberg"},
        ],
    },
    "soft_glow": {
        "description": "Soft dreamy glow - flattering for portraits, kids, close-ups.",
        "steps": [
            {"op": "blend_with_blurred", "blend_mode": "soft_light", "factor": 0.3},
            {"op": "brightness", "factor": 1.03},
        ],
    },
    "clarendon": {
        "description": "Bright punchy contrast with a cool-tinted highlight - Instagram's iconic go-to look.",
        "steps": [
            {"op": "contrast", "factor": 1.15},
            {"op": "color_transfer", "ref": "cool.png", "method": "reinhard_lab", "strength": 0.2},
            {"op": "brightness", "factor": 1.05},
        ],
    },
    "teal_orange": {
        "description": "Cinematic movie-poster grade - teal shadows, warm orange skin/highlights.",
        "steps": [
            {"op": "color_transfer", "ref": "teal_orange.png", "method": "reinhard_lab", "strength": 0.4},
            {"op": "contrast", "factor": 1.08},
        ],
    },
    "matte_faded": {
        "description": "Flat matte look with lifted blacks and muted tone - everyday VSCO-style look.",
        "steps": [
            # screen-blending a flat gray lifts the black point more than the highlights,
            # which is the actual mechanism behind a "matte" curve (no curves node exists).
            {"op": "blend_with_asset", "ref": "flat_gray.png", "blend_mode": "screen", "factor": 0.14},
            {"op": "color_transfer", "ref": "warm.png", "method": "reinhard_lab", "strength": 0.2},
            {"op": "contrast", "factor": 0.88},
        ],
    },
    "cozy_golden": {
        "description": "Warm golden-hour tone plus a soft glow - cozy and flattering for warm indoor/portrait shots.",
        "steps": [
            {"op": "color_transfer", "ref": "warm.png", "method": "reinhard_lab", "strength": 0.4},
            {"op": "blend_with_blurred", "blend_mode": "soft_light", "factor": 0.25},
            {"op": "brightness", "factor": 1.03},
        ],
    },
    "pastel_dream": {
        "description": "Soft, light, low-contrast pastel look - dreamy and airy, good for bright/minimal scenes.",
        "steps": [
            {"op": "contrast", "factor": 0.85},
            {"op": "color_transfer", "ref": "pastel.png", "method": "reinhard_lab", "strength": 0.3},
            {"op": "blend_with_blurred", "blend_mode": "soft_light", "factor": 0.2},
            {"op": "brightness", "factor": 1.06},
        ],
    },
}
