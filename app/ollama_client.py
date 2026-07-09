import base64
import json
import re

import requests

from . import cartoon_styles, config, db, filters


def _chat(image_b64, prompt_text, options=None):
    resp = requests.post(
        f"{config.OLLAMA_BASE_URL}/api/chat",
        json={
            "model": config.OLLAMA_VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": prompt_text,
                    "images": [image_b64],
                }
            ],
            "stream": False,
            "options": options or {"temperature": 0.2, "num_ctx": 8192},
        },
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _load_image_b64(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _extract_id(text, valid_ids):
    """Pull the first integer in the response that matches a valid id."""
    for match in re.findall(r"\d+", text):
        n = int(match)
        if n in valid_ids:
            return n
    return None


def choose_category(image_b64):
    categories = db.get_categories()
    listing = "\n".join(f"- {name} ({count} prompts)" for name, count in categories)
    prompt = (
        "You are choosing the best-fitting photo-enhancement style category for the "
        "attached photo. Look at the subject, mood, lighting, and condition of the photo.\n\n"
        f"Categories:\n{listing}\n\n"
        "Reply with ONLY the exact category name from the list above that best fits this "
        "photo, nothing else."
    )
    reply = _chat(image_b64, prompt).strip()
    names = [c[0] for c in categories]
    if reply in names:
        return reply
    # fuzzy fallback: pick the category name that appears as a substring of the reply
    for name in names:
        if name.lower() in reply.lower():
            return name
    return names[0]


def select_best_character_style(image_path, exclude=()):
    """Vision-pick the best-fitting app.cartoon_styles.STYLE_PRESETS entry for this
    photo (e.g. a playful kid photo might suit Minecraft/LEGO, an action pose might
    suit superhero), the same selection pattern as select_best_filter.

    exclude removes style names from consideration entirely (not just as a
    tiebreak) - verified live that without this, the vision model develops a
    strong "anime" favorite and several styles (minecraft, superhero, lego,
    claymation, figurine_3d, funko_pop, retro_film) never got picked at all
    across real runs. cartoon_pipeline passes in the N most recently used
    styles so every style gets a turn before any repeat, rather than trusting
    the model's "best fit" judgment alone to naturally rotate.

    Returns a style name (key into STYLE_PRESETS, never one in exclude unless
    exclude covers everything); falls back to the first eligible style if the
    model's reply doesn't match one.
    """
    image_b64 = _load_image_b64(image_path)
    names = [n for n in cartoon_styles.STYLE_PRESETS if n not in exclude] or list(
        cartoon_styles.STYLE_PRESETS
    )
    listing = "\n".join(
        f"- {name}: {cartoon_styles.STYLE_PRESETS[name]['description']}" for name in names
    )
    prompt = (
        "You are choosing the best-fitting character-transformation style for the "
        "attached photo - the subject will be turned into an animated/stylized "
        "character in this style. Look at the subject's age, pose, mood, and setting.\n\n"
        f"Styles:\n{listing}\n\n"
        "Reply with ONLY the exact style name from the list above that best fits this "
        "photo, nothing else."
    )
    reply = _chat(image_b64, prompt).strip()
    if reply in names:
        return reply
    for name in names:
        if name.lower() in reply.lower():
            return name
    return names[0]


def compose_character_prompt(image_path, style_name):
    """Have Ollama look at the photo and author a fresh SDXL prompt: transform the
    subject into the given style (app.cartoon_styles.STYLE_PRESETS) and invent a new,
    contextually-fitting background different from the photo's current one - unlike
    select_best_prompt/choose_category, this doesn't pick from the prompt library, it
    writes new prompt text tailored to this specific photo.

    Returns an SDXL-ready prompt string; falls back to the style's base prompt if
    Ollama's reply comes back empty or malformed.
    """
    style = cartoon_styles.STYLE_PRESETS[style_name]
    image_b64 = _load_image_b64(image_path)
    prompt = (
        "Look at the attached photo: its subject(s), pose, and current background/setting.\n\n"
        "Write a single SDXL image-generation prompt (one paragraph, comma-separated "
        "descriptive phrases, no more than ~90 words) that will:\n"
        "1. START by explicitly describing the subject(s) you see - exactly how many "
        "people, adult or child, gender, hair, build, outfit colors - so the person "
        "stays the unmistakable focus of the generated image. Never add, remove, or "
        "replace people, and never turn a person into an animal or object.\n"
        f"2. Turn that subject into this style: {style['style_prompt']} - while keeping "
        "their same rough pose and outfit recognizable.\n"
        "3. Replace the background with a NEW scene (in the same style) that suits the "
        "photo's mood but is different from and more visually interesting than the "
        "current background - use what you see in the current background as a clue "
        "for what kind of new setting would fit. The background must stay secondary "
        "to the subject.\n\n"
        "Reply with ONLY the prompt text itself, nothing else - no preamble, no quotes, "
        "no explanation."
    )
    reply = _chat(image_b64, prompt, options={"temperature": 0.7, "num_ctx": 8192}).strip()
    if len(reply) < 15:
        return style["style_prompt"]
    return reply


def select_best_filter(image_path):
    """Vision-pick the best-fitting app.filters.FILTER_PRESETS entry for this photo.

    Returns a preset name (key into FILTER_PRESETS); falls back to the first
    preset if the model's reply doesn't match one.
    """
    image_b64 = _load_image_b64(image_path)
    names = list(filters.FILTER_PRESETS.keys())
    listing = "\n".join(f"- {name}: {filters.FILTER_PRESETS[name]['description']}" for name in names)
    prompt = (
        "You are choosing the best-fitting photo filter preset for the attached photo, "
        "the way Google Photos' one-tap filters work. Look at the subject, lighting, mood, "
        "and colors already in the photo.\n\n"
        f"Presets:\n{listing}\n\n"
        "Reply with ONLY the exact preset name from the list above that best fits this "
        "photo, nothing else."
    )
    reply = _chat(image_b64, prompt).strip()
    if reply in names:
        return reply
    for name in names:
        if name.lower() in reply.lower():
            return name
    return names[0]


# Decorative accent for app.collage.two_photo_captioned captions (app.config.
# COLLAGE_THEN_AND_NOW_EMOJI) - deliberately a small fixed set so the vision
# model's reply can be matched exactly, same as FILTER_PRESETS/STYLE_PRESETS.
MOOD_EMOJIS = {
    "joyful": "😄",
    "celebratory": "🎉",
    "cozy": "🥰",
    "playful": "😜",
    "proud": "🥳",
    "calm": "😊",
}


def select_mood_emoji(image_path):
    """Vision-pick a single emoji that best matches the mood of this photo.

    Returns an emoji character; falls back to a neutral smile if the model's
    reply doesn't match a known mood.
    """
    image_b64 = _load_image_b64(image_path)
    names = list(MOOD_EMOJIS.keys())
    listing = "\n".join(f"- {name}" for name in names)
    prompt = (
        "Look at the attached photo and pick the single mood word that best "
        "describes its overall feeling.\n\n"
        f"Moods:\n{listing}\n\n"
        "Reply with ONLY the exact mood word from the list above, nothing else."
    )
    reply = _chat(image_b64, prompt).strip().lower()
    if reply in MOOD_EMOJIS:
        return MOOD_EMOJIS[reply]
    for name in names:
        if name in reply:
            return MOOD_EMOJIS[name]
    return MOOD_EMOJIS["calm"]


def detect_subject_gender(image_b64):
    """Return 'male', 'female', or 'neutral' (no person / unclear / multiple people)."""
    prompt = (
        "Look at the main human subject in this photo, if there is one.\n"
        "Reply with ONLY one word: 'male' if the main subject presents as male, "
        "'female' if the main subject presents as female, or 'neutral' if there is "
        "no person, the photo has multiple equally-prominent people of different "
        "genders, or you can't tell. Nothing else."
    )
    reply = _chat(image_b64, prompt, options={"temperature": 0.0, "num_ctx": 8192}).strip().lower()
    # check "female" before "male" since "male" is a substring of "female"
    for word in ("female", "male", "neutral"):
        if word in reply:
            return word
    return "neutral"


def choose_prompt_in_category(image_b64, category, gender=None):
    candidates = db.get_prompts_by_category(category, gender=gender)
    listing = "\n".join(f"{pid}: {title}" for pid, title in candidates)
    valid_ids = {pid for pid, _ in candidates}
    prompt = (
        f"You are choosing the single best-fitting prompt for the attached photo, from the "
        f"'{category}' category below. Consider subject, pose, framing, and current condition "
        f"(damaged/faded/blurry/already good, etc.) of the photo.\n\n"
        f"Options (id: title):\n{listing}\n\n"
        "Reply with ONLY the numeric id of the single best option, nothing else."
    )
    reply = _chat(image_b64, prompt).strip()
    chosen_id = _extract_id(reply, valid_ids)
    if chosen_id is None:
        chosen_id = candidates[0][0]
    return chosen_id


def select_best_prompt(image_path):
    """Three-stage vision selection: category, subject gender, then specific prompt within it.

    Returns the full prompt record (dict) from the DB.
    """
    image_b64 = _load_image_b64(image_path)
    category = choose_category(image_b64)
    gender = detect_subject_gender(image_b64)
    prompt_id = choose_prompt_in_category(image_b64, category, gender=gender)
    return db.get_prompt_by_id(prompt_id)


def ping():
    r = requests.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=10)
    r.raise_for_status()
    models = [m["name"] for m in r.json().get("models", [])]
    return config.OLLAMA_VISION_MODEL in models, models
