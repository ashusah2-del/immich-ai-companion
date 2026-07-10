import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Host running Ollama + ComfyUI (e.g. an Apple Silicon Mac or any GPU box on
# your LAN) - set AIENH_MAC_HOST to yours, or override AIENH_OLLAMA_URL /
# AIENH_COMFYUI_URL directly below if the two services live on different hosts.
MAC_HOST = os.environ.get("AIENH_MAC_HOST", "localhost")

OLLAMA_BASE_URL = os.environ.get("AIENH_OLLAMA_URL", f"http://{MAC_HOST}:11434")
OLLAMA_VISION_MODEL = os.environ.get("AIENH_OLLAMA_VISION_MODEL", "qwen2.5vl:7b")

COMFYUI_BASE_URL = os.environ.get("AIENH_COMFYUI_URL", f"http://{MAC_HOST}:8188")
COMFYUI_UPSCALE_MODEL = os.environ.get("AIENH_COMFYUI_UPSCALE_MODEL", "RealESRGAN_x4plus.pth")
COMFYUI_FACERESTORE_MODEL = os.environ.get("AIENH_COMFYUI_FACERESTORE_MODEL", "codeformer.pth")
COMFYUI_FACEDETECTION = os.environ.get("AIENH_COMFYUI_FACEDETECTION", "retinaface_resnet50")
# CodeFormer fidelity: 0 = max restoration/quality, 1 = max identity preservation.
COMFYUI_CODEFORMER_FIDELITY = float(os.environ.get("AIENH_COMFYUI_CODEFORMER_FIDELITY", "0.7"))
COMFYUI_POLL_TIMEOUT = int(os.environ.get("AIENH_COMFYUI_POLL_TIMEOUT", "600"))

DB_PATH = os.environ.get(
    "AIENH_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "prompts.db"),
)

OUTPUT_DIR = os.environ.get("AIENH_OUTPUT_DIR", "/mnt/photos/AI Images")

IMMICH_BASE_URL = os.environ.get("AIENH_IMMICH_URL", "http://localhost:2283")
IMMICH_API_KEY = os.environ.get("AIENH_IMMICH_API_KEY", "")
IMMICH_ALBUM_NAME = os.environ.get("AIENH_IMMICH_ALBUM_NAME", "AI")

IMAGES_PER_DAY = int(os.environ.get("AIENH_IMAGES_PER_DAY", "2"))

# All four workers (restore/design/filter/cartoon) only ever touch photos of these
# tagged Immich people - resolved to person ids via immich_client.get_person_ids_by_names.
# Set AIENH_TARGET_PEOPLE to a comma-separated list of names exactly as you've
# tagged them in Immich's People view, e.g. "Alice Smith,Bob Smith".
TARGET_PEOPLE = [
    name.strip()
    for name in os.environ.get("AIENH_TARGET_PEOPLE", "").split(",")
    if name.strip()
]

# --- Design worker: creative SDXL restyling using the prompt library, separate from
# the identity-preserving restore worker above. ---
DESIGN_BASE_CKPT = os.environ.get("AIENH_DESIGN_BASE_CKPT", "sd_xl_base_1.0.safetensors")
DESIGN_REFINER_CKPT = os.environ.get("AIENH_DESIGN_REFINER_CKPT", "sd_xl_refiner_1.0.safetensors")
DESIGN_NEGATIVE_PROMPT = os.environ.get(
    "AIENH_DESIGN_NEGATIVE_PROMPT",
    "blurry, low quality, low detail, jpeg artifacts, watermark, text, distorted, deformed",
)
DESIGN_STEPS_BASE = int(os.environ.get("AIENH_DESIGN_STEPS_BASE", "30"))
DESIGN_STEPS_REFINER = int(os.environ.get("AIENH_DESIGN_STEPS_REFINER", "20"))
DESIGN_DENOISE_BASE = float(os.environ.get("AIENH_DESIGN_DENOISE_BASE", "0.25"))
DESIGN_DENOISE_REFINER = float(os.environ.get("AIENH_DESIGN_DENOISE_REFINER", "0.12"))
DESIGN_CFG = float(os.environ.get("AIENH_DESIGN_CFG", "7.0"))

DESIGN_OUTPUT_SUBDIR = os.environ.get("AIENH_DESIGN_OUTPUT_SUBDIR", "Designed")
DESIGN_IMMICH_ALBUM_NAME = os.environ.get("AIENH_DESIGN_IMMICH_ALBUM_NAME", "AI Designed")
DESIGN_IMAGES_PER_DAY = int(os.environ.get("AIENH_DESIGN_IMAGES_PER_DAY", "2"))

# Face-swap settings for the design worker (kept separate from the restore worker's
# COMFYUI_FACE* settings above, since tuning one shouldn't risk affecting the other).
DESIGN_SWAP_MODEL = os.environ.get("AIENH_DESIGN_SWAP_MODEL", "inswapper_128.onnx")
# retinaface_resnet50 aligns faces noticeably better than YOLOv5l (ReActor's
# own recommendation) - misalignment was one source of distorted swaps.
DESIGN_FACEDETECTION = os.environ.get("AIENH_DESIGN_FACEDETECTION", "retinaface_resnet50")
DESIGN_FACERESTORE_MODEL = os.environ.get("AIENH_DESIGN_FACERESTORE_MODEL", "codeformer.pth")
DESIGN_FACE_RESTORE_VISIBILITY = float(os.environ.get("AIENH_DESIGN_FACE_RESTORE_VISIBILITY", "1.0"))
# CodeFormer weight: higher = more fidelity to the swapped-in (real) face,
# lower = more hallucinated "beautification". 0.5 drifted identity; ReActor
# docs recommend ~0.75.
DESIGN_CODEFORMER_WEIGHT = float(os.environ.get("AIENH_DESIGN_CODEFORMER_WEIGHT", "0.75"))
# Restore+upscale the swapped face BEFORE pasting it back (ReActorFaceBoost) -
# inswapper_128 works at 128px, so without this the pasted face is soft and
# waxy at photo resolution.
DESIGN_FACE_BOOST = os.environ.get("AIENH_DESIGN_FACE_BOOST", "true").lower() in ("1", "true", "yes")
DESIGN_FACE_BOOST_MODEL = os.environ.get("AIENH_DESIGN_FACE_BOOST_MODEL", "GFPGANv1.4.pth")
# Shield every Immich-detected face region from SDXL denoising entirely
# (latent noise mask, see comfyui_client._face_shield_mask_bytes) so faces
# keep their original photographic features while the rest restyles - the
# ReActor swap alone couldn't preserve likeness for every person in a group
# photo.
DESIGN_PROTECT_FACES = os.environ.get("AIENH_DESIGN_PROTECT_FACES", "true").lower() in ("1", "true", "yes")
# How much each face box grows before masking (fraction of the box's own
# width/height per side) and how far the mask edge feathers (px at 1024px
# mask scale) so shielded faces blend into the restyled surroundings.
DESIGN_FACE_MASK_GROW = float(os.environ.get("AIENH_DESIGN_FACE_MASK_GROW", "0.3"))
DESIGN_FACE_MASK_FEATHER = float(os.environ.get("AIENH_DESIGN_FACE_MASK_FEATHER", "24"))

# --- Filter worker: Google Photos-style color-grade presets, chosen via Ollama and
# applied via ComfyUI's built-in image nodes. ---
FILTER_OUTPUT_SUBDIR = os.environ.get("AIENH_FILTER_OUTPUT_SUBDIR", "Filtered")
FILTER_IMMICH_ALBUM_NAME = os.environ.get("AIENH_FILTER_IMMICH_ALBUM_NAME", "AI Filtered")
FILTER_IMAGES_PER_DAY = int(os.environ.get("AIENH_FILTER_IMAGES_PER_DAY", "2"))
FILTER_VIGNETTE_FACTOR = float(os.environ.get("AIENH_FILTER_VIGNETTE_FACTOR", "0.25"))
FILTER_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "filter_assets")

# --- Collage worker: composited from a mix of the filter worker's recent output and
# plain random photos of the target people, no ComfyUI involved since it's pure
# layout/compositing over already-downloaded images. ---
COLLAGE_ENABLE = os.environ.get("AIENH_COLLAGE_ENABLE", "true").lower() in ("1", "true", "yes")
# Target photo count to gather per collage is randomized within this inclusive
# range each run (see filter_pipeline.maybe_build_collage), not a fixed number -
# app.collage.build_collage tiers down to whatever's actually available rather
# than failing if the target isn't met.
COLLAGE_PHOTO_COUNT_MIN = int(os.environ.get("AIENH_COLLAGE_PHOTO_COUNT_MIN", "3"))
COLLAGE_PHOTO_COUNT_MAX = int(os.environ.get("AIENH_COLLAGE_PHOTO_COUNT_MAX", "10"))
COLLAGE_OUTPUT_SUBDIR = os.environ.get("AIENH_COLLAGE_OUTPUT_SUBDIR", "Collages")
COLLAGE_IMMICH_ALBUM_NAME = os.environ.get("AIENH_COLLAGE_IMMICH_ALBUM_NAME", "AI Collages")

# Chance the day's single collage attempt is a "then and now" comparison (oldest vs
# newest available real photo of one randomly-tried target person) instead of the
# regular random-mixed-photos collage. Falls back to the regular collage if the roll
# hits but no target person has a qualifying pair this run (see
# COLLAGE_THEN_AND_NOW_MIN_GAP_DAYS) - a collage is still always built.
COLLAGE_THEN_AND_NOW_PROBABILITY = float(
    os.environ.get("AIENH_COLLAGE_THEN_AND_NOW_PROBABILITY", "0.2")
)
# Minimum days between the "then" and "now" photo for a pair to count as
# valid (~3 years). 6 months proved too little - both photos read as "the
# same picture" with no visible passage of time.
COLLAGE_THEN_AND_NOW_MIN_GAP_DAYS = int(
    os.environ.get("AIENH_COLLAGE_THEN_AND_NOW_MIN_GAP_DAYS", "1095")
)
# Accent each then-and-now caption with a mood-appropriate emoji (Ollama vision pick).
COLLAGE_THEN_AND_NOW_EMOJI = os.environ.get(
    "AIENH_COLLAGE_THEN_AND_NOW_EMOJI", "true"
).lower() in ("1", "true", "yes")
# How many recent-"now" and qualifying-"then" candidates to download and
# face-sharpness-score (app.collage.face_sharpness_score) before picking the
# sharpest one, instead of just taking whichever photo the date rule lands on -
# avoids picking a blurry/low-quality shot when a better one was available.
COLLAGE_THEN_AND_NOW_QUALITY_POOL = int(
    os.environ.get("AIENH_COLLAGE_THEN_AND_NOW_QUALITY_POOL", "10")
)
# Minimum face_sharpness_score a candidate must clear to be considered at all -
# calibrated against a real sample library (scores ranged ~3 to ~900, median
# ~300); below this a photo reads as genuinely out-of-focus/motion-blurred
# rather than just a softer phone-camera shot. Tune to taste for your own library.
# If nobody in a person's pool clears it, that person is skipped for the day
# (see filter_pipeline._try_build_then_and_now) rather than settling for the
# best of a bad bunch.
COLLAGE_THEN_AND_NOW_MIN_SHARPNESS = float(
    os.environ.get("AIENH_COLLAGE_THEN_AND_NOW_MIN_SHARPNESS", "50")
)

# --- Cartoon worker: SDXL restyle with a dynamically Ollama-composed prompt (cartoonize
# the subject + a new contextual background) rather than a fixed prompt-library entry.
# No local background-segmentation model is installed on the ComfyUI host (checked
# RemoveBackground/SAM3 - no models loaded; BriaRemoveImageBackground needs a paid
# comfy.org API key we don't have), so this is a whole-image SDXL regeneration like the
# design worker, not a precise cutout-and-composite. ReActor face-swap is skipped
# (preserve_identity=False) so the face itself actually cartoonizes, which needs a
# stronger denoise than the identity-preserving design worker uses.
CARTOON_OUTPUT_SUBDIR = os.environ.get("AIENH_CARTOON_OUTPUT_SUBDIR", "Cartoon")
CARTOON_IMMICH_ALBUM_NAME = os.environ.get("AIENH_CARTOON_IMMICH_ALBUM_NAME", "AI Cartoon")
CARTOON_IMAGES_PER_DAY = int(os.environ.get("AIENH_CARTOON_IMAGES_PER_DAY", "1"))
# 0.6/0.3 only produced a subtle toon-shaded photo; 0.78/0.45 (verified live) actually
# reads as a cartoon/comic illustration - bold outlines, flat cel-shaded color - at the
# cost of exact facial likeness, which is expected/fine since preserve_identity=False.
CARTOON_DENOISE_BASE = float(os.environ.get("AIENH_CARTOON_DENOISE_BASE", "0.78"))
CARTOON_DENOISE_REFINER = float(os.environ.get("AIENH_CARTOON_DENOISE_REFINER", "0.45"))
# Also build and upload a side-by-side "Cartoon"/"Original" comparison collage
# (app.collage.two_photo_captioned) alongside the standalone cartoon output.
CARTOON_COMPARE_ENABLE = os.environ.get(
    "AIENH_CARTOON_COMPARE_ENABLE", "true"
).lower() in ("1", "true", "yes")
