import random
import re
import sys
import uuid
from datetime import datetime, timezone

import requests

from . import cartoon_styles, config, filters

DEVICE_ID = "aienh"

# ComfyUI's LoadImage node only handles standard raster formats; skip HEIC/RAW/etc.
SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Every AI worker's own uploaded output follows one of these deterministic filename
# patterns (see pipeline.py's "_enhanced", design_pipeline.py's "_designed",
# filter_pipeline.py's "_{preset}"/"collage_*", cartoon_pipeline.py's "_{style}").
# This Immich instance ingests OUTPUT_DIR both via our direct API upload AND via a
# second, untracked external-library filesystem scan of the same folder, so a
# db-only exclusion list misses that second copy - filtering by filename shape
# catches both, independent of our own bookkeeping. Used to keep our own outputs
# out of "then and now" candidate pools (see get_person_photo_history).
_SYNTHETIC_FILENAME_MARKERS = ("_enhanced.png", "_designed.png") + tuple(
    f"_{name}.png" for name in list(filters.FILTER_PRESETS) + list(cartoon_styles.STYLE_PRESETS)
)

# A handful of assets have no real EXIF capture date and Immich fills in a
# ~1980 epoch placeholder for fileCreatedAt - not a real "then" candidate.
_MIN_VALID_PHOTO_YEAR = 1990

# WhatsApp's own filename convention (IMG-YYYYMMDD-WAxxxx.jpg / VID-...) bakes
# in the true send/forward date. Forwarded media routinely has no real
# embedded EXIF capture date at all, and Immich then backfills
# fileCreatedAt/exif.dateTimeOriginal with the *import* date instead -
# silently mislabeling e.g. a 2016 "then" photo as a 2025 one. The filename
# date is more trustworthy than the API-reported one whenever it's present.
_WHATSAPP_FILENAME_RE = re.compile(r"(?:IMG|VID)-(\d{4})(\d{2})(\d{2})-WA\d+", re.IGNORECASE)


def _whatsapp_filename_date(filename):
    match = _WHATSAPP_FILENAME_RE.search(filename)
    if not match:
        return None
    year, month, day = (int(g) for g in match.groups())
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def _headers():
    return {"x-api-key": config.IMMICH_API_KEY}


def _looks_ai_generated(filename):
    fn = filename.lower()
    return fn.startswith("collage_") or fn.endswith(_SYNTHETIC_FILENAME_MARKERS)


def get_or_create_album_id(name=None):
    name = name or config.IMMICH_ALBUM_NAME
    resp = requests.get(f"{config.IMMICH_BASE_URL}/api/albums", headers=_headers(), timeout=15)
    resp.raise_for_status()
    for album in resp.json():
        if album["albumName"] == name:
            return album["id"]
    resp = requests.post(
        f"{config.IMMICH_BASE_URL}/api/albums",
        headers=_headers(),
        json={"albumName": name},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def get_person_ids_by_names(names):
    """Resolve tagged-person names to Immich person ids (case-insensitive exact match).

    Returns {name: id} only for names that were found; missing names are
    printed as a warning rather than raising, since the filter worker should
    still run against whichever target people it *can* resolve.
    """
    resp = requests.get(f"{config.IMMICH_BASE_URL}/api/people", headers=_headers(), timeout=15)
    resp.raise_for_status()
    people = resp.json().get("people", [])
    by_lower_name = {}
    for person in people:
        if person.get("name"):
            by_lower_name.setdefault(person["name"].strip().lower(), person["id"])

    resolved = {}
    for name in names:
        person_id = by_lower_name.get(name.strip().lower())
        if person_id:
            resolved[name] = person_id
        else:
            print(f"WARNING: no Immich person tagged '{name}', skipping", file=sys.stderr)
    return resolved


def pick_random_images_for_people(person_ids, count, exclude_ids=None, max_attempts=30):
    """Pick up to `count` random IMAGE assets that contain ANY of person_ids.

    Immich's /search/random personIds filter is AND (asset must contain all
    listed people), which isn't what "photos of A or B or C" needs. So instead
    of a single call with all ids, each attempt targets one randomly-chosen
    person id and results are merged/deduped, approximating OR across the group.

    Each returned asset dict is stamped with "_matched_person_id" - the
    specific person this attempt searched for, not necessarily every tagged
    person in the photo. Callers that crop to a face (see get_face_box)
    should scope to this one person rather than unioning everyone recognized
    in the shot: a candid photo with two family members at very different
    heights/depths (e.g. an adult holding a baby) produces a union box that
    can span most of the frame and crop the actual subject out entirely.
    """
    exclude_ids = exclude_ids or set()
    person_ids = list(person_ids)
    picked = {}
    if not person_ids:
        return []
    for _ in range(max_attempts):
        if len(picked) >= count:
            break
        target_person = random.choice(person_ids)
        resp = requests.post(
            f"{config.IMMICH_BASE_URL}/api/search/random",
            headers=_headers(),
            json={
                "size": (count - len(picked)) * 3,
                "type": "IMAGE",
                "visibility": "timeline",
                "personIds": [target_person],
            },
            timeout=30,
        )
        resp.raise_for_status()
        for asset in resp.json():
            if asset["id"] in exclude_ids or asset["id"] in picked:
                continue
            if asset.get("originalMimeType") not in SUPPORTED_MIME_TYPES:
                continue
            asset["_matched_person_id"] = target_person
            picked[asset["id"]] = asset
            if len(picked) >= count:
                break
    return list(picked.values())


def get_person_photo_history(person_id, exclude_ids=None, page_size=1000):
    """Fetch up to page_size real (non-synthetic) IMAGE assets of person_id, sorted
    oldest-to-newest by fileCreatedAt (corrected by _whatsapp_filename_date
    where it applies).

    Filters to PIL-openable mime types (same reason as SUPPORTED_MIME_TYPES
    elsewhere), drops our own AI-generated uploads (see _looks_ai_generated) so a
    then-and-now pair is never one of our own composited/derivative images, and
    drops assets with no/placeholder capture date.

    Only fetches a single page (up to page_size); a couple years' worth of a
    typical personal library fits in one page, so this is a practical, not
    exhaustive, cap. Raise page_size if your library is much larger.

    Pairing candidates by date is only half the picture - callers that need a
    quality/not-blurry check (e.g. filter_pipeline._pick_sharpest) do that on
    top of this, since it requires downloading pixels, which is out of scope
    for this API-only module.
    """
    exclude_ids = exclude_ids or set()
    resp = requests.post(
        f"{config.IMMICH_BASE_URL}/api/search/metadata",
        headers=_headers(),
        json={"personIds": [person_id], "type": "IMAGE", "size": page_size},
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("assets", {}).get("items", [])

    photos = []
    for asset in items:
        if asset["id"] in exclude_ids:
            continue
        if asset.get("originalMimeType") not in SUPPORTED_MIME_TYPES:
            continue
        if _looks_ai_generated(asset.get("originalFileName", "")):
            continue
        created_at = asset.get("fileCreatedAt")
        if not created_at:
            continue
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        dt = _whatsapp_filename_date(asset.get("originalFileName", "")) or dt
        if dt.year < _MIN_VALID_PHOTO_YEAR:
            continue
        asset["_created_dt"] = dt
        photos.append(asset)

    photos.sort(key=lambda a: a["_created_dt"])
    return photos


def get_face_box(asset_id, person_id=None):
    """Return a bounding box (x1, y1, x2, y2), as 0-1 fractions of the asset's
    displayed (EXIF-oriented) image, covering *recognized* face(s) Immich found
    in the photo - or None if it has none (no face data yet, or only
    unidentified bystanders).

    Restricting to faces with a linked `person` keeps the box tight around the
    tagged family members rather than ballooning out to include a stranger in
    the background. If person_id is given, the box is scoped to just that
    person's own face(s), not the union of everyone recognized - important
    for a specific-subject crop (e.g. then-and-now): a group photo's
    union-of-everyone box can span far wider than any one person and crop
    them out of the frame entirely. Without person_id, every recognized face
    is unioned (used by the general collage random-photo picker, where
    "whichever family members are in frame" is the right box).
    """
    resp = requests.get(
        f"{config.IMMICH_BASE_URL}/api/faces",
        headers=_headers(),
        params={"id": asset_id},
        timeout=15,
    )
    resp.raise_for_status()
    faces = [f for f in resp.json() if f.get("person")]
    if person_id is not None:
        faces = [f for f in faces if f["person"]["id"] == person_id]
    if not faces:
        return None
    x1 = min(f["boundingBoxX1"] / f["imageWidth"] for f in faces)
    y1 = min(f["boundingBoxY1"] / f["imageHeight"] for f in faces)
    x2 = max(f["boundingBoxX2"] / f["imageWidth"] for f in faces)
    y2 = max(f["boundingBoxY2"] / f["imageHeight"] for f in faces)
    return (x1, y1, x2, y2)


def download_original(asset_id):
    resp = requests.get(
        f"{config.IMMICH_BASE_URL}/api/assets/{asset_id}/original",
        headers=_headers(),
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content


def upload_asset(image_bytes, filename):
    now = datetime.now(timezone.utc).isoformat()
    resp = requests.post(
        f"{config.IMMICH_BASE_URL}/api/assets",
        headers=_headers(),
        data={
            "deviceAssetId": f"{DEVICE_ID}-{uuid.uuid4()}",
            "deviceId": DEVICE_ID,
            "fileCreatedAt": now,
            "fileModifiedAt": now,
        },
        files={"assetData": (filename, image_bytes, "image/jpeg")},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def set_asset_description(asset_id, description):
    resp = requests.put(
        f"{config.IMMICH_BASE_URL}/api/assets/{asset_id}",
        headers=_headers(),
        json={"description": description},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def add_to_album(album_id, asset_id):
    resp = requests.put(
        f"{config.IMMICH_BASE_URL}/api/albums/{album_id}/assets",
        headers=_headers(),
        json={"ids": [asset_id]},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()
