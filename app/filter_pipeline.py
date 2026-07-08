import json
import os
import random
import sys
import uuid

from . import collage, comfyui_client, config, db, filters, immich_client, ollama_client


def process_asset(asset, album_id):
    asset_id = asset["id"]
    filename = asset["originalFileName"]
    print(f"[{asset_id}] downloading {filename}...")
    original_bytes = immich_client.download_original(asset_id)

    tmp_path = f"/tmp/aifilter_{asset_id}{os.path.splitext(filename)[1]}"
    with open(tmp_path, "wb") as f:
        f.write(original_bytes)

    try:
        print(f"[{asset_id}] selecting filter via Ollama vision model...")
        preset_name = ollama_client.select_best_filter(tmp_path)
        print(f"[{asset_id}] chosen filter: {preset_name!r}")

        print(f"[{asset_id}] running ComfyUI filter...")
        output_bytes = comfyui_client.apply_filter_image(original_bytes, filename, preset_name)

        out_dir = os.path.join(config.OUTPUT_DIR, config.FILTER_OUTPUT_SUBDIR)
        os.makedirs(out_dir, exist_ok=True)
        out_name = f"{os.path.splitext(filename)[0]}_{preset_name}.png"
        out_path = os.path.join(out_dir, out_name)
        with open(out_path, "wb") as f:
            f.write(output_bytes)
        print(f"[{asset_id}] saved output to {out_path}")

        new_asset_id = immich_client.upload_asset(output_bytes, out_name)
        immich_client.add_to_album(album_id, new_asset_id)
        immich_client.set_asset_description(
            new_asset_id,
            f"AI Filter: {preset_name!r} preset - {filters.FILTER_PRESETS[preset_name]['description']}",
        )
        print(f"[{asset_id}] uploaded to Immich as {new_asset_id} and added to album")

        db.record_enhancement_run(
            immich_asset_id=asset_id,
            original_filename=filename,
            prompt_id=None,
            output_path=out_path,
            status="success",
            immich_album_asset_id=new_asset_id,
            kind="filter",
            variant=preset_name,
        )
        return True
    except Exception as e:
        print(f"[{asset_id}] FAILED: {e}", file=sys.stderr)
        db.record_enhancement_run(
            immich_asset_id=asset_id,
            original_filename=filename,
            prompt_id=None,
            output_path=None,
            status="failed",
            error=str(e),
            kind="filter",
        )
        return False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _download_plain_candidates(person_ids, count, exclude_asset_ids):
    """Download `count` random photos of the target people straight from Immich,
    with no filter/enhancement applied - collages shouldn't require every source
    photo to have gone through the AI filter worker first."""
    if count <= 0:
        return []
    assets = immich_client.pick_random_images_for_people(
        person_ids, count, exclude_ids=exclude_asset_ids
    )
    photos = []
    for asset in assets:
        data = immich_client.download_original(asset["id"])
        ext = os.path.splitext(asset["originalFileName"])[1] or ".jpg"
        path = f"/tmp/aicollage_{asset['id']}{ext}"
        with open(path, "wb") as f:
            f.write(data)
        face_box = immich_client.get_face_box(asset["id"], person_id=asset.get("_matched_person_id"))
        photos.append(collage.Photo(path, face_box))
    return photos


def maybe_build_collage(album_id, person_ids):
    """Composite a random collage template and upload it. Mixes in already-
    filtered outputs (if any are sitting around unused) with freshly-picked
    plain random photos of the target people, so a collage never requires
    every source photo to have gone through the AI filter first."""
    target_count = random.randint(config.COLLAGE_PHOTO_COUNT_MIN, config.COLLAGE_PHOTO_COUNT_MAX)

    filtered = db.get_uncollaged_filter_outputs(target_count * 2)
    filtered = [c for c in filtered if c["output_path"] and os.path.exists(c["output_path"])]
    filtered_sample = random.sample(filtered, min(len(filtered), target_count // 2))

    exclude = db.get_processed_asset_ids(kind="filter") | {c["immich_asset_id"] for c in filtered_sample}
    plain_photos = _download_plain_candidates(
        person_ids, target_count - len(filtered_sample), exclude
    )
    filtered_photos = [
        collage.Photo(c["output_path"], immich_client.get_face_box(c["immich_asset_id"]))
        for c in filtered_sample
    ]

    all_photos = filtered_photos + plain_photos
    if len(all_photos) < config.COLLAGE_PHOTO_COUNT_MIN:
        for photo in plain_photos:
            os.remove(photo.path)
        return

    # Use whatever's actually available up to the target - collage.build_collage
    # now has a template for any count from COLLAGE_PHOTO_COUNT_MIN up, so there's
    # no need to tier down through a fixed set of sizes like before.
    final_count = min(target_count, len(all_photos))
    random.shuffle(all_photos)
    used_photos, unused_plain = all_photos[:final_count], [
        photo for photo in all_photos[final_count:] if photo in plain_photos
    ]
    for photo in unused_plain:
        os.remove(photo.path)

    print(
        f"Building a {final_count}-photo collage "
        f"({len(filtered_sample)} filtered + {len(plain_photos)} plain candidates)..."
    )
    image, template_name = collage.build_collage(used_photos)

    for photo in plain_photos:
        if os.path.exists(photo.path):
            os.remove(photo.path)

    representative_asset_id = (
        filtered_sample[0]["immich_asset_id"] if filtered_sample else "plain-random"
    )
    _finalize_collage(
        album_id,
        image,
        template_name,
        description=(
            f"AI Collage: {template_name!r} template composited from {len(filtered_sample)} "
            f"AI-filtered + {len(used_photos) - len(filtered_sample)} plain photo(s)."
        ),
        meta={
            "filtered_run_ids": [c["id"] for c in filtered_sample],
            "plain_photo_count": len(used_photos) - len(filtered_sample),
        },
        representative_asset_id=representative_asset_id,
    )
    if filtered_sample:
        db.mark_collaged([c["id"] for c in filtered_sample])


def _finalize_collage(album_id, image, template_name, description, meta, representative_asset_id):
    """Shared save/upload/describe/record tail for every collage style (regular
    mixed-photo and then-and-now alike)."""
    out_dir = os.path.join(config.OUTPUT_DIR, config.COLLAGE_OUTPUT_SUBDIR)
    os.makedirs(out_dir, exist_ok=True)
    out_name = f"collage_{template_name}_{uuid.uuid4().hex[:8]}.png"
    out_path = os.path.join(out_dir, out_name)
    image.save(out_path)
    print(f"saved collage to {out_path}")

    with open(out_path, "rb") as f:
        output_bytes = f.read()
    new_asset_id = immich_client.upload_asset(output_bytes, out_name)
    immich_client.add_to_album(album_id, new_asset_id)
    immich_client.set_asset_description(new_asset_id, description)
    print(f"uploaded collage to Immich as {new_asset_id} and added to album")

    db.record_enhancement_run(
        immich_asset_id=representative_asset_id,
        original_filename=None,
        prompt_id=None,
        output_path=out_path,
        status="success",
        immich_album_asset_id=new_asset_id,
        kind="collage",
        variant=template_name,
        meta=json.dumps(meta),
    )


def _face_box_is_upright(face_box):
    """A face bounding box that's noticeably wider than tall usually means the
    source photo is stored sideways with no EXIF orientation tag to correct
    it (common with old WhatsApp-forwarded images, verified live: a wedding
    photo with no orientation metadata at all, face box 123x81px) - a
    correctly-oriented face is normally at least as tall as wide."""
    x1, y1, x2, y2 = face_box
    return (y2 - y1) >= (x2 - x1) * 0.9


def _download_and_score(asset, face_box):
    """Download one candidate asset and face-sharpness-score it (see
    collage.face_sharpness_score). Returns (path, score); caller owns
    cleaning up `path`."""
    data = immich_client.download_original(asset["id"])
    ext = os.path.splitext(asset["originalFileName"])[1] or ".jpg"
    path = f"/tmp/aicollage_thenandnow_{asset['id']}{ext}"
    with open(path, "wb") as f:
        f.write(data)
    score = collage.face_sharpness_score(path, face_box)
    return path, score


def _pick_sharpest(candidates, person_id, pool_size):
    """Download up to pool_size candidates (a random sample if there are more)
    and keep the sharpest/least-blurry one that clears
    COLLAGE_THEN_AND_NOW_MIN_SHARPNESS - every other download in the pool is
    cleaned up immediately. face_box is scoped to person_id specifically (not
    the union of everyone recognized in the photo - see
    immich_client.get_face_box), and candidates whose face box looks sideways
    (see _face_box_is_upright) are skipped before even downloading. Returns
    (asset, path, face_box, score), or None if nothing in the pool qualifies.
    """
    if not candidates:
        return None
    pool = candidates if len(candidates) <= pool_size else random.sample(candidates, pool_size)
    best = None
    for asset in pool:
        face_box = immich_client.get_face_box(asset["id"], person_id=person_id)
        if face_box is None or not _face_box_is_upright(face_box):
            continue
        path, score = _download_and_score(asset, face_box)
        if score < config.COLLAGE_THEN_AND_NOW_MIN_SHARPNESS:
            os.remove(path)
            continue
        if best is None or score > best[3]:
            if best is not None:
                os.remove(best[1])
            best = (asset, path, face_box, score)
        else:
            os.remove(path)
    return best


def _build_then_and_now_photo(asset, path, face_box, tag):
    label = f"{tag} · {asset['_created_dt'].year}"
    if config.COLLAGE_THEN_AND_NOW_EMOJI:
        label = f"{label} {ollama_client.select_mood_emoji(path)}"
    return collage.Photo(path, face_box, label)


def _try_build_then_and_now(album_id, person_ids_by_name):
    """Try each target person, in random order, for a qualifying then-and-now
    pair. "now" is picked (for sharpness) from a pool of their most recent
    real photos, and "then" from a pool of real photos at least
    COLLAGE_THEN_AND_NOW_MIN_GAP_DAYS older than the chosen "now" - both
    picks favor the sharpest/least-blurry candidate in their pool (see
    _pick_sharpest) over just taking whatever the date rule lands on.

    Returns True and uploads a collage on the first person that qualifies;
    returns False if none do, so the caller falls back to the regular
    maybe_build_collage for the day."""
    names = list(person_ids_by_name.items())
    random.shuffle(names)
    exclude_ids = db.get_ai_generated_asset_ids()
    pool_size = config.COLLAGE_THEN_AND_NOW_QUALITY_POOL

    for name, person_id in names:
        photos = immich_client.get_person_photo_history(person_id, exclude_ids=exclude_ids)
        if len(photos) < 2:
            continue

        now_pick = _pick_sharpest(photos[-pool_size:], person_id, pool_size)
        if now_pick is None:
            continue
        now_asset, now_path, now_face_box, now_score = now_pick

        then_candidates = [
            p for p in photos
            if p["id"] != now_asset["id"]
            and (now_asset["_created_dt"] - p["_created_dt"]).days
            >= config.COLLAGE_THEN_AND_NOW_MIN_GAP_DAYS
        ]
        then_pick = _pick_sharpest(then_candidates, person_id, pool_size)
        if then_pick is None:
            os.remove(now_path)
            continue
        then_asset, then_path, then_face_box, then_score = then_pick

        paths = [then_path, now_path]
        try:
            print(
                f"Building a then-and-now collage for {name}: "
                f"{then_asset['_created_dt'].year} vs {now_asset['_created_dt'].year} "
                f"(sharpness then={then_score:.0f} now={now_score:.0f})..."
            )
            photos_for_collage = [
                _build_then_and_now_photo(then_asset, then_path, then_face_box, "THEN"),
                _build_then_and_now_photo(now_asset, now_path, now_face_box, "NOW"),
            ]
            image, template_name = collage.build_collage(photos_for_collage)
            gap_days = (now_asset["_created_dt"] - then_asset["_created_dt"]).days
            _finalize_collage(
                album_id,
                image,
                template_name,
                description=(
                    f"AI Collage: {template_name!r} then-and-now for {name}, "
                    f"{then_asset['_created_dt'].year} vs {now_asset['_created_dt'].year}."
                ),
                meta={
                    "person_name": name,
                    "then_year": then_asset["_created_dt"].year,
                    "now_year": now_asset["_created_dt"].year,
                    "gap_days": gap_days,
                    "then_sharpness": then_score,
                    "now_sharpness": now_score,
                },
                representative_asset_id=then_asset["id"],
            )
            return True
        finally:
            for path in paths:
                if os.path.exists(path):
                    os.remove(path)
    return False


def run(count=None):
    count = count or config.FILTER_IMAGES_PER_DAY
    person_ids = immich_client.get_person_ids_by_names(config.TARGET_PEOPLE)
    if not person_ids:
        print("No target people resolved in Immich, nothing to do.")
        return

    processed_ids = db.get_processed_asset_ids(kind="filter")
    album_id = immich_client.get_or_create_album_id(config.FILTER_IMMICH_ALBUM_NAME)
    assets = immich_client.pick_random_images_for_people(
        list(person_ids.values()), count, exclude_ids=processed_ids
    )

    if not assets:
        print("No unprocessed images found for the target people.")
        return

    print(f"Picked {len(assets)} image(s) to process.")
    results = [process_asset(asset, album_id) for asset in assets]
    print(f"Done: {sum(results)}/{len(results)} succeeded.")

    if config.COLLAGE_ENABLE:
        collage_album_id = immich_client.get_or_create_album_id(config.COLLAGE_IMMICH_ALBUM_NAME)
        built = False
        if random.random() < config.COLLAGE_THEN_AND_NOW_PROBABILITY:
            built = _try_build_then_and_now(collage_album_id, person_ids)
        if not built:
            maybe_build_collage(collage_album_id, list(person_ids.values()))


if __name__ == "__main__":
    run()
