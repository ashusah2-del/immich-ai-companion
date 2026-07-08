import json
import os
import sys

from . import cartoon_styles, collage, comfyui_client, config, db, frames, immich_client, ollama_client


def _build_comparison_collage(asset_id, original_path, cartoon_path, person_id=None):
    """Cartoon-vs-original side by side, cartoon on the left / real photo on
    the right (app.collage.two_photo_captioned - the same layout the Collage
    worker's then-and-now style uses, just with plain "Cartoon"/"Original"
    captions instead of dates). Reuses the original asset's real Immich face
    box for the original photo's crop, scoped to person_id (the specific
    target person this asset was picked for - see
    immich_client.pick_random_images_for_people) rather than every recognized
    face in the shot: a candid photo with another family member at a very
    different height/depth (e.g. an adult holding a baby) produces a union
    box that can span most of the frame and crop the actual subject out
    entirely. The freshly-generated cartoon has no face data of its own, so
    it falls back to _cover's top-biased crop."""
    face_box = immich_client.get_face_box(asset_id, person_id=person_id)
    photos = [
        collage.Photo(cartoon_path, None, "Cartoon"),
        collage.Photo(original_path, face_box, "Original"),
    ]
    return collage.build_collage(photos)


def process_asset(asset, album_id):
    asset_id = asset["id"]
    filename = asset["originalFileName"]
    print(f"[{asset_id}] downloading {filename}...")
    original_bytes = immich_client.download_original(asset_id)

    tmp_path = f"/tmp/aicartoon_{asset_id}{os.path.splitext(filename)[1]}"
    with open(tmp_path, "wb") as f:
        f.write(original_bytes)

    try:
        print(f"[{asset_id}] selecting character style via Ollama vision model...")
        recent_styles = db.get_recent_variants("cartoon", len(cartoon_styles.STYLE_PRESETS) - 1)
        style_name = ollama_client.select_best_character_style(tmp_path, exclude=recent_styles)
        style = cartoon_styles.STYLE_PRESETS[style_name]
        print(f"[{asset_id}] chosen style: {style_name!r}")

        print(f"[{asset_id}] composing {style_name} prompt via Ollama vision model...")
        prompt_text = ollama_client.compose_character_prompt(tmp_path, style_name)
        print(f"[{asset_id}] composed prompt: {prompt_text!r}")

        print(f"[{asset_id}] running ComfyUI {style_name} generation...")
        output_bytes = comfyui_client.design_image(
            original_bytes, filename, prompt_text,
            preserve_identity=False,
            denoise_base=style.get("denoise_base", config.CARTOON_DENOISE_BASE),
            denoise_refiner=style.get("denoise_refiner", config.CARTOON_DENOISE_REFINER),
        )

        if style.get("post_process"):
            print(f"[{asset_id}] applying {style['post_process']} post-process...")
            output_bytes = frames.apply(style["post_process"], output_bytes)

        out_dir = os.path.join(config.OUTPUT_DIR, config.CARTOON_OUTPUT_SUBDIR)
        os.makedirs(out_dir, exist_ok=True)
        out_name = f"{os.path.splitext(filename)[0]}_{style_name}.png"
        out_path = os.path.join(out_dir, out_name)
        with open(out_path, "wb") as f:
            f.write(output_bytes)
        print(f"[{asset_id}] saved output to {out_path}")

        new_asset_id = immich_client.upload_asset(output_bytes, out_name)
        immich_client.add_to_album(album_id, new_asset_id)
        immich_client.set_asset_description(
            new_asset_id,
            f"AI Cartoon: {style_name!r} style ({style['description']}), "
            f"Ollama-composed prompt: {prompt_text}",
        )
        print(f"[{asset_id}] uploaded to Immich as {new_asset_id} and added to album")

        db.record_enhancement_run(
            immich_asset_id=asset_id,
            original_filename=filename,
            prompt_id=None,
            output_path=out_path,
            status="success",
            immich_album_asset_id=new_asset_id,
            kind="cartoon",
            variant=style_name,
            meta=json.dumps({"composed_prompt": prompt_text}),
        )

        if config.CARTOON_COMPARE_ENABLE:
            print(f"[{asset_id}] building cartoon-vs-original comparison collage...")
            compare_image, template_name = _build_comparison_collage(
                asset_id, tmp_path, out_path, person_id=asset.get("_matched_person_id")
            )
            compare_name = f"{os.path.splitext(filename)[0]}_{style_name}_compare.png"
            compare_path = os.path.join(out_dir, compare_name)
            compare_image.save(compare_path)
            print(f"[{asset_id}] saved comparison collage to {compare_path}")

            with open(compare_path, "rb") as f:
                compare_bytes = f.read()
            compare_asset_id = immich_client.upload_asset(compare_bytes, compare_name)
            immich_client.add_to_album(album_id, compare_asset_id)
            immich_client.set_asset_description(
                compare_asset_id,
                f"AI Cartoon comparison: {style_name!r} style vs. original photo.",
            )
            print(f"[{asset_id}] uploaded comparison collage to Immich as {compare_asset_id}")

            db.record_enhancement_run(
                immich_asset_id=asset_id,
                original_filename=filename,
                prompt_id=None,
                output_path=compare_path,
                status="success",
                immich_album_asset_id=compare_asset_id,
                kind="cartoon",
                variant=f"{style_name}_compare",
                meta=json.dumps({"composed_prompt": prompt_text, "compare_template": template_name}),
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
            kind="cartoon",
        )
        return False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def run(count=None):
    count = count or config.CARTOON_IMAGES_PER_DAY
    person_ids = immich_client.get_person_ids_by_names(config.TARGET_PEOPLE)
    if not person_ids:
        print("No target people resolved in Immich, nothing to do.")
        return

    processed_ids = db.get_processed_asset_ids(kind="cartoon")
    album_id = immich_client.get_or_create_album_id(config.CARTOON_IMMICH_ALBUM_NAME)
    assets = immich_client.pick_random_images_for_people(
        list(person_ids.values()), count, exclude_ids=processed_ids
    )

    if not assets:
        print("No unprocessed images found.")
        return

    print(f"Picked {len(assets)} image(s) to process.")
    results = [process_asset(asset, album_id) for asset in assets]
    print(f"Done: {sum(results)}/{len(results)} succeeded.")


if __name__ == "__main__":
    run()
