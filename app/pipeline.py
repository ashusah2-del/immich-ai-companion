import os
import sys

from . import comfyui_client, config, db, immich_client


def process_asset(asset, album_id):
    asset_id = asset["id"]
    filename = asset["originalFileName"]
    print(f"[{asset_id}] downloading {filename}...")
    original_bytes = immich_client.download_original(asset_id)

    try:
        print(f"[{asset_id}] running ComfyUI enhancement...")
        output_bytes = comfyui_client.enhance_image(original_bytes, filename)

        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        out_name = f"{os.path.splitext(filename)[0]}_enhanced.png"
        out_path = os.path.join(config.OUTPUT_DIR, out_name)
        with open(out_path, "wb") as f:
            f.write(output_bytes)
        print(f"[{asset_id}] saved output to {out_path}")

        new_asset_id = immich_client.upload_asset(output_bytes, out_name)
        immich_client.add_to_album(album_id, new_asset_id)
        immich_client.set_asset_description(
            new_asset_id,
            f"AI Restore: {config.COMFYUI_UPSCALE_MODEL} upscale + "
            f"{config.COMFYUI_FACERESTORE_MODEL} face restoration (identity-preserving enhancement).",
        )
        print(f"[{asset_id}] uploaded to Immich as {new_asset_id} and added to album")

        db.record_enhancement_run(
            immich_asset_id=asset_id,
            original_filename=filename,
            prompt_id=None,
            output_path=out_path,
            status="success",
            immich_album_asset_id=new_asset_id,
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
        )
        return False


def run(count=None):
    count = count or config.IMAGES_PER_DAY
    person_ids = immich_client.get_person_ids_by_names(config.TARGET_PEOPLE)
    if not person_ids:
        print("No target people resolved in Immich, nothing to do.")
        return

    processed_ids = db.get_processed_asset_ids(kind="restore")
    album_id = immich_client.get_or_create_album_id()
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
