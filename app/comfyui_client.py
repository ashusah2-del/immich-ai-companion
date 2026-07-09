import io
import os
import time
import uuid

import requests
from PIL import Image

from . import config, filters

# Working size for the ESRGAN pass; the model's fixed 4x scale then brings this
# back up before the final resize to the original photo's resolution.
GENERATION_MEGAPIXELS = 1.5


def _megapixels(image_bytes):
    with Image.open(io.BytesIO(image_bytes)) as img:
        w, h = img.size
    return max(0.05, min((w * h) / 1_000_000, 16.0))


def _build_workflow(image_name, output_megapixels):
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {
                "image": ["1", 0],
                "upscale_method": "lanczos",
                "megapixels": GENERATION_MEGAPIXELS,
                "resolution_steps": 8,
            },
        },
        "3": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": config.COMFYUI_UPSCALE_MODEL}},
        "4": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["3", 0], "image": ["2", 0]}},
        "5": {"class_type": "FaceRestoreModelLoader", "inputs": {"model_name": config.COMFYUI_FACERESTORE_MODEL}},
        "6": {
            "class_type": "FaceRestoreCFWithModel",
            "inputs": {
                "facerestore_model": ["5", 0],
                "image": ["4", 0],
                "facedetection": config.COMFYUI_FACEDETECTION,
                "codeformer_fidelity": config.COMFYUI_CODEFORMER_FIDELITY,
            },
        },
        "7": {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {
                "image": ["6", 0],
                "upscale_method": "lanczos",
                "megapixels": output_megapixels,
                "resolution_steps": 8,
            },
        },
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "aienh"}},
    }


def _build_design_workflow(image_name, prompt_text, seed, output_megapixels,
                            preserve_identity=True, denoise_base=None, denoise_refiner=None):
    negative = config.DESIGN_NEGATIVE_PROMPT
    denoise_base = config.DESIGN_DENOISE_BASE if denoise_base is None else denoise_base
    denoise_refiner = config.DESIGN_DENOISE_REFINER if denoise_refiner is None else denoise_refiner
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": config.DESIGN_BASE_CKPT}},
        "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": config.DESIGN_REFINER_CKPT}},
        "3": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "13": {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {
                "image": ["3", 0],
                "upscale_method": "lanczos",
                "megapixels": 1.0,
                "resolution_steps": 64,
            },
        },
        "4": {"class_type": "VAEEncode", "inputs": {"pixels": ["13", 0], "vae": ["1", 2]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt_text, "clip": ["1", 1]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["5", 0],
                "negative": ["6", 0],
                "latent_image": ["4", 0],
                "seed": seed,
                "steps": config.DESIGN_STEPS_BASE,
                "cfg": config.DESIGN_CFG,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": denoise_base,
            },
        },
        "8": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt_text, "clip": ["2", 1]}},
        "9": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 1]}},
        "10": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["2", 0],
                "positive": ["8", 0],
                "negative": ["9", 0],
                "latent_image": ["7", 0],
                "seed": seed,
                "steps": config.DESIGN_STEPS_REFINER,
                "cfg": config.DESIGN_CFG,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": denoise_refiner,
            },
        },
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["1", 2]}},
        "14": {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {
                # wired below to either the ReActor identity-preserving output (default)
                # or straight from VAEDecode, when preserve_identity=False lets the
                # generated face itself stay stylized (e.g. a cartoon face) instead of
                # having the real face swapped back in.
                "image": ["11", 0],
                "upscale_method": "lanczos",
                "megapixels": output_megapixels,
                "resolution_steps": 8,
            },
        },
        "12": {"class_type": "SaveImage", "inputs": {"images": ["14", 0], "filename_prefix": "aidesign"}},
    }

    if preserve_identity:
        workflow["16"] = {
            "class_type": "ReActorFaceSwap",
            "inputs": {
                "enabled": True,
                "input_image": ["11", 0],
                "source_image": ["3", 0],
                "swap_model": config.DESIGN_SWAP_MODEL,
                "facedetection": config.DESIGN_FACEDETECTION,
                "face_restore_model": config.DESIGN_FACERESTORE_MODEL,
                "face_restore_visibility": config.DESIGN_FACE_RESTORE_VISIBILITY,
                "codeformer_weight": config.DESIGN_CODEFORMER_WEIGHT,
                "detect_gender_input": "no",
                "detect_gender_source": "no",
                "input_faces_index": "0",
                "source_faces_index": "0",
                "console_log_level": 1,
            },
        }
        if config.DESIGN_FACE_BOOST:
            # inswapper_128 swaps at 128x128, so the pasted face comes out
            # soft/plasticky at photo resolution. FaceBoost restores and
            # upscales the swapped face *before* it's pasted back, which is
            # where most of the "distorted/waxy face" complaints came from.
            workflow["17"] = {
                "class_type": "ReActorFaceBoost",
                "inputs": {
                    "enabled": True,
                    "boost_model": config.DESIGN_FACE_BOOST_MODEL,
                    "interpolation": "Lanczos",
                    "visibility": 1.0,
                    "codeformer_weight": config.DESIGN_CODEFORMER_WEIGHT,
                    "restore_with_main_after": False,
                },
            }
            workflow["16"]["inputs"]["face_boost"] = ["17", 0]
        workflow["14"]["inputs"]["image"] = ["16", 0]

    return workflow


def _upload_image(image_bytes, filename):
    resp = requests.post(
        f"{config.COMFYUI_BASE_URL}/upload/image",
        files={"image": (filename, io.BytesIO(image_bytes))},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["name"]


def _queue_prompt(workflow, client_id):
    resp = requests.post(
        f"{config.COMFYUI_BASE_URL}/prompt",
        json={"prompt": workflow, "client_id": client_id},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("node_errors"):
        raise RuntimeError(f"ComfyUI workflow validation failed: {data['node_errors']}")
    return data["prompt_id"]


def _wait_for_history(prompt_id, timeout=None):
    timeout = timeout or config.COMFYUI_POLL_TIMEOUT
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(f"{config.COMFYUI_BASE_URL}/history/{prompt_id}", timeout=15)
        resp.raise_for_status()
        history = resp.json()
        if prompt_id in history:
            entry = history[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI run failed: {status}")
            return entry
        time.sleep(2)
    raise TimeoutError(f"ComfyUI prompt {prompt_id} did not finish within {timeout}s")


def _fetch_output_image(history_entry):
    for node_output in history_entry["outputs"].values():
        for image in node_output.get("images", []):
            resp = requests.get(
                f"{config.COMFYUI_BASE_URL}/view",
                params={
                    "filename": image["filename"],
                    "subfolder": image["subfolder"],
                    "type": image["type"],
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.content
    raise RuntimeError("ComfyUI run produced no output image")


def enhance_image(image_bytes, filename):
    """Run the ESRGAN upscale + CodeFormer face-restore workflow and return the output PNG bytes.

    Unlike SDXL img2img, this is deterministic and identity-preserving: ESRGAN
    sharpens/denoises the whole frame while CodeFormer only touches detected
    face regions, so it can't hallucinate unrelated content.
    """
    output_megapixels = _megapixels(image_bytes)
    image_name = _upload_image(image_bytes, filename)
    workflow = _build_workflow(image_name, output_megapixels)
    client_id = str(uuid.uuid4())
    prompt_id = _queue_prompt(workflow, client_id)
    history_entry = _wait_for_history(prompt_id)
    return _fetch_output_image(history_entry)


def design_image(image_bytes, filename, prompt_text, seed=None,
                  preserve_identity=True, denoise_base=None, denoise_refiner=None):
    """Run the SDXL base+refiner img2img workflow, creatively restyling the photo per prompt_text.

    Unlike enhance_image, this is a stylistic reimagining (high denoise) and
    does not preserve identity/composition faithfully.

    preserve_identity=True (default) swaps the real face back in via ReActor, matching
    every existing design-worker style. Set False for styles where the face itself
    should be stylized (e.g. cartoonizing) - the ReActor step is skipped entirely.
    denoise_base/denoise_refiner override config.DESIGN_DENOISE_* when a style needs a
    stronger (or weaker) transformation than the identity-preserving default.
    """
    seed = seed if seed is not None else uuid.uuid4().int & 0xFFFFFFFF
    output_megapixels = _megapixels(image_bytes)
    image_name = _upload_image(image_bytes, filename)
    workflow = _build_design_workflow(
        image_name, prompt_text, seed, output_megapixels,
        preserve_identity=preserve_identity, denoise_base=denoise_base, denoise_refiner=denoise_refiner,
    )
    client_id = str(uuid.uuid4())
    prompt_id = _queue_prompt(workflow, client_id)
    history_entry = _wait_for_history(prompt_id)
    return _fetch_output_image(history_entry)


def _upload_filter_asset(local_filename):
    path = os.path.join(config.FILTER_ASSETS_DIR, local_filename)
    with open(path, "rb") as f:
        return _upload_image(f.read(), local_filename)


def _build_filter_workflow(image_name, steps, vignette_asset, vignette_factor):
    """Interpret an app.filters.FILTER_PRESETS step list into a ComfyUI graph.

    Only AdjustBrightness/AdjustContrast/ImageBlend/ImageBlur/ImageAddNoise/
    ImageQuantize/ImageRGBToYUV/ColorTransfer/GetImageSize/ImageScale are used,
    since that's what's actually installed on the ComfyUI host (verified via
    /object_info - no dedicated saturation/hue/vignette node exists there).
    Reference/vignette images are dynamically rescaled to the source photo's
    own dimensions via GetImageSize + ImageScale before every blend, since
    ImageBlend/ColorTransfer require matching dimensions and source photos
    vary in size.
    """
    workflow = {}
    next_id = [0]

    def new_id():
        next_id[0] += 1
        return str(next_id[0])

    src_id = new_id()
    workflow[src_id] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    size_id = new_id()
    workflow[size_id] = {"class_type": "GetImageSize", "inputs": {"image": [src_id, 0]}}

    def scaled_ref(local_asset_filename):
        uploaded_name = _upload_filter_asset(local_asset_filename)
        ref_id = new_id()
        workflow[ref_id] = {"class_type": "LoadImage", "inputs": {"image": uploaded_name}}
        scale_id = new_id()
        workflow[scale_id] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": [ref_id, 0],
                "upscale_method": "lanczos",
                "width": [size_id, 0],
                "height": [size_id, 1],
                "crop": "center",
            },
        }
        return [scale_id, 0]

    current = [src_id, 0]
    for step in steps:
        op = step["op"]
        if op == "color_transfer":
            ref_slot = scaled_ref(step["ref"])
            node_id = new_id()
            workflow[node_id] = {
                "class_type": "ColorTransfer",
                "inputs": {
                    "image_target": current,
                    "image_ref": ref_slot,
                    "method": step["method"],
                    "source_stats": "uniform",
                    "strength": step["strength"],
                },
            }
        elif op == "brightness":
            node_id = new_id()
            workflow[node_id] = {
                "class_type": "AdjustBrightness",
                "inputs": {"images": current, "factor": step["factor"]},
            }
        elif op == "contrast":
            node_id = new_id()
            workflow[node_id] = {
                "class_type": "AdjustContrast",
                "inputs": {"images": current, "factor": step["factor"]},
            }
        elif op == "grayscale_yuv":
            # ImageRGBToYUV's first output (Y) is a ready-made grayscale image
            # (R=G=B=luma per pixel) - no dedicated desaturate node is installed.
            node_id = new_id()
            workflow[node_id] = {"class_type": "ImageRGBToYUV", "inputs": {"image": current}}
        elif op == "add_noise":
            node_id = new_id()
            workflow[node_id] = {
                "class_type": "ImageAddNoise",
                "inputs": {
                    "image": current,
                    "seed": uuid.uuid4().int & 0xFFFFFFFF,
                    "strength": step["strength"],
                },
            }
        elif op == "quantize":
            node_id = new_id()
            workflow[node_id] = {
                "class_type": "ImageQuantize",
                "inputs": {"image": current, "colors": step["colors"], "dither": step["dither"]},
            }
        elif op == "blend_with_blurred":
            blur_id = new_id()
            workflow[blur_id] = {
                "class_type": "ImageBlur",
                "inputs": {"image": current, "blur_radius": 8, "sigma": 4.0},
            }
            node_id = new_id()
            workflow[node_id] = {
                "class_type": "ImageBlend",
                "inputs": {
                    "image1": current,
                    "image2": [blur_id, 0],
                    "blend_factor": step["factor"],
                    "blend_mode": step["blend_mode"],
                },
            }
        elif op == "blend_with_self":
            node_id = new_id()
            workflow[node_id] = {
                "class_type": "ImageBlend",
                "inputs": {
                    "image1": current,
                    "image2": current,
                    "blend_factor": step["factor"],
                    "blend_mode": step["blend_mode"],
                },
            }
        elif op == "blend_with_asset":
            asset_slot = scaled_ref(step["ref"])
            node_id = new_id()
            workflow[node_id] = {
                "class_type": "ImageBlend",
                "inputs": {
                    "image1": current,
                    "image2": asset_slot,
                    "blend_factor": step["factor"],
                    "blend_mode": step["blend_mode"],
                },
            }
        else:
            raise ValueError(f"unknown filter step op: {op!r}")
        current = [node_id, 0]

    if vignette_asset and vignette_factor:
        vignette_slot = scaled_ref(vignette_asset)
        node_id = new_id()
        workflow[node_id] = {
            "class_type": "ImageBlend",
            "inputs": {
                "image1": current,
                "image2": vignette_slot,
                "blend_factor": vignette_factor,
                "blend_mode": "multiply",
            },
        }
        current = [node_id, 0]

    save_id = new_id()
    workflow[save_id] = {"class_type": "SaveImage", "inputs": {"images": current, "filename_prefix": "aifilter"}}
    return workflow


def apply_filter_image(image_bytes, filename, preset_name):
    """Apply a Google Photos-style color-grade preset (app.filters.FILTER_PRESETS)
    plus a vignette, and return the output PNG bytes."""
    preset = filters.FILTER_PRESETS[preset_name]
    image_name = _upload_image(image_bytes, filename)
    workflow = _build_filter_workflow(
        image_name, preset["steps"], "vignette.png", config.FILTER_VIGNETTE_FACTOR
    )
    client_id = str(uuid.uuid4())
    prompt_id = _queue_prompt(workflow, client_id)
    history_entry = _wait_for_history(prompt_id)
    return _fetch_output_image(history_entry)


def ping():
    resp = requests.get(f"{config.COMFYUI_BASE_URL}/system_stats", timeout=10)
    resp.raise_for_status()
    return resp.json()
