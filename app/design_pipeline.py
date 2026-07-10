import os
import sys

from . import comfyui_client, config, db, immich_client, ollama_client


def process_asset(asset, album_id):
    asset_id = asset["id"]
    filename = asset["originalFileName"]
    print(f"[{asset_id}] downloading {filename}...")
    original_bytes = immich_client.download_original(asset_id)

    tmp_path = f"/tmp/aidesign_{asset_id}{os.path.splitext(filename)[1]}"
    with open(tmp_path, "wb") as f:
        f.write(original_bytes)

    try:
        print(f"[{asset_id}] selecting prompt via Ollama vision model...")
        prompt = ollama_client.select_best_prompt(tmp_path)
        print(f"[{asset_id}] chosen prompt: {prompt['title']!r} ({prompt['category']})")

        print(f"[{asset_id}] running ComfyUI design generation...")
        output_bytes = comfyui_client.design_image(
            original_bytes, filename, prompt["prompt_text"],
            face_boxes=immich_client.get_all_face_boxes(asset_id),
        )

        out_dir = os.path.join(config.OUTPUT_DIR, config.DESIGN_OUTPUT_SUBDIR)
        os.makedirs(out_dir, exist_ok=True)
        out_name = f"{os.path.splitext(filename)[0]}_designed.png"
        out_path = os.path.join(out_dir, out_name)
        with open(out_path, "wb") as f:
            f.write(output_bytes)
        print(f"[{asset_id}] saved output to {out_path}")

        new_asset_id = immich_client.upload_asset(output_bytes, out_name)
        immich_client.add_to_album(album_id, new_asset_id)
        immich_client.set_asset_description(
            new_asset_id,
            f"AI Design: SDXL restyle using prompt {prompt['title']!r} ({prompt['category']}) "
            "from the prompt library, with identity-preserving face-swap.",
        )
        print(f"[{asset_id}] uploaded to Immich as {new_asset_id} and added to album")

        db.record_enhancement_run(
            immich_asset_id=asset_id,
            original_filename=filename,
            prompt_id=prompt["id"],
            output_path=out_path,
            status="success",
            immich_album_asset_id=new_asset_id,
            kind="design",
        )
        db.mark_prompt_used(prompt["id"])
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
            kind="design",
        )
        return False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def run(count=None):
    count = count or config.DESIGN_IMAGES_PER_DAY
    person_ids = immich_client.get_person_ids_by_names(config.TARGET_PEOPLE)
    if not person_ids:
        print("No target people resolved in Immich, nothing to do.")
        return

    processed_ids = db.get_processed_asset_ids(kind="design")
    album_id = immich_client.get_or_create_album_id(config.DESIGN_IMMICH_ALBUM_NAME)
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
