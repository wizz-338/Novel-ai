#!/usr/bin/env python3
"""Human-initiated, one-image NovelAI V4.5 bridge. No retries or scheduled calls."""
import argparse
import base64
import binascii
import io
import json
import os
from pathlib import Path
import struct
import sys
from urllib import error, request
import zipfile

API_URL = "https://image.novelai.net/ai/generate-image"
MODEL = "nai-diffusion-4-5-full"
ROOT = Path(__file__).resolve().parent
MAX_RESPONSE = 30 * 1024 * 1024
NEGATIVE = ("chibi, oversized head, oversized eyes, glossy plastic skin, shiny hair, "
            "exaggerated smile, excessive blush, childlike anatomy, distorted body, "
            "extra fingers, bad hands, watermark, text, signature")


class BridgeError(ValueError):
    pass


def parse_scene(raw):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 12000:
        raise BridgeError("Invalid or oversized request.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise BridgeError("Scene must be JSON.") from None
    if not isinstance(data, dict):
        raise BridgeError("Scene must be an object.")
    keys = {"prompt", "negative_prompt", "width", "height", "steps", "scale",
            "seed", "reference", "dry_run"}
    if set(data) - keys:
        raise BridgeError("Unsupported scene field.")
    prompt = data.get("prompt")
    negative = data.get("negative_prompt", "")
    if not isinstance(prompt, str) or not 3 <= len(prompt) <= 2400:
        raise BridgeError("prompt length must be 3..2400.")
    if not isinstance(negative, str) or len(negative) > 2400:
        raise BridgeError("Invalid negative_prompt.")
    width, height = data.get("width", 1024), data.get("height", 1024)
    if type(width) is not int or type(height) is not int or (width, height) not in (
        (1024, 1024), (832, 1216), (1216, 832)
    ):
        raise BridgeError("Unsupported image dimensions.")
    steps, scale, seed = data.get("steps", 24), data.get("scale", 5), data.get("seed", 0)
    if type(steps) is not int or not 1 <= steps <= 28:
        raise BridgeError("Invalid steps.")
    if type(scale) not in (int, float) or not 1 <= scale <= 10:
        raise BridgeError("Invalid scale.")
    if type(seed) is not int or not 0 <= seed <= 4294967295:
        raise BridgeError("Invalid seed.")
    ref = data.get("reference")
    if ref not in (None, "nari", "kangchan"):
        raise BridgeError("Unsupported reference.")
    dry = data.get("dry_run", True)
    if type(dry) is not bool:
        raise BridgeError("dry_run must be boolean.")
    return dict(prompt=prompt, negative_prompt=negative, width=width, height=height,
                steps=steps, scale=scale, seed=seed, reference=ref, dry_run=dry)


def scene_from_event(path, event_name):
    event = json.loads(Path(path).read_text("utf-8"))
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    actor = os.environ.get("GITHUB_ACTOR", "")
    if owner and actor != owner:
        raise BridgeError("Only repository owner may initiate requests.")
    if event_name == "issues":
        issue = event.get("issue") or {}
        if not isinstance(issue, dict) or not str(issue.get("title", "")).startswith("[NAI] "):
            raise BridgeError("Not a NovelAI generation issue.")
        if owner and (issue.get("user") or {}).get("login") != owner:
            raise BridgeError("Issue creator must be repository owner.")
        raw = issue.get("body")
    elif event_name == "workflow_dispatch":
        raw = (event.get("inputs") or {}).get("scene_json")
    else:
        raise BridgeError("Unrecognized event.")
    return parse_scene(raw)


def build_payload(scene, root=ROOT):
    prompt = scene["prompt"]
    negative = NEGATIVE + ", " + scene["negative_prompt"]
    parameters = {
        "params_version": 3, "width": scene["width"], "height": scene["height"],
        "steps": scene["steps"], "scale": scene["scale"],
        "seed": scene["seed"], "n_samples": 1, "sampler": "k_euler_ancestral",
        "noise_schedule": "karras", "negative_prompt": negative,
        "v4_prompt": {"caption": {"base_caption": prompt, "char_captions": []},
                      "use_coords": False, "use_order": True},
        "v4_negative_prompt": {"caption": {"base_caption": negative, "char_captions": []},
                               "legacy_uc": False},
    }
    if scene["reference"]:
        # Never commit private original artwork to this public repository.
        ref = Path(root) / "references" / (scene["reference"] + ".png")
        if not ref.is_file():
            raise BridgeError("Reference is not configured; no generation attempted.")
        image = ref.read_bytes()
        if len(image) < 24 or len(image) > 15 * 1024 * 1024 or not image.startswith(b"\x89PNG\r\n\x1a\n"):
            raise BridgeError("Reference must be a suitable PNG.")
        shape = struct.unpack(">II", image[16:24])
        if shape not in ((1472, 1472), (1024, 1536), (1536, 1024)):
            raise BridgeError("Unsupported reference dimensions.")
        parameters.update({
            "director_reference_images": [base64.b64encode(image).decode("ascii")],
            "director_reference_descriptions": [{"caption": {
                "base_caption": "character&style", "char_captions": []}}],
            "director_reference_strength_values": [0.65],
            "director_reference_secondary_strength_values": [0.35],
            "director_reference_information_extracted": [1.0],
        })
    return {"action": "generate", "model": MODEL,
            "input": prompt, "parameters": parameters}


def decode_image(raw, content_type):
    if len(raw) > MAX_RESPONSE:
        raise BridgeError("NovelAI response too large.")
    if "json" in content_type:
        obj = json.loads(raw)
        images = obj.get("images") if isinstance(obj, dict) else None
        if not isinstance(images, list) or len(images) != 1:
            raise BridgeError("Unexpected JSON image count.")
        encoded = images[0].get("image")
        if not isinstance(encoded, str):
            raise BridgeError("Unexpected image value.")
        if encoded.startswith("data:"):
            encoded = encoded.partition(",")[2]
        try:
            image = base64.b64decode(encoded, validate=True)
        except binascii.Error:
            raise BridgeError("Invalid encoded image.") from None
    elif zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files = [f for f in archive.infolist()
                     if not f.is_dir() and f.filename.lower().endswith(".png")]
            if len(files) != 1 or files[0].file_size > 20 * 1024 * 1024:
                raise BridgeError("Unexpected ZIP image contents.")
            image = archive.read(files[0])
    else:
        raise BridgeError("Unknown image response.")
    if not (image.startswith(b"\x89PNG\r\n\x1a\n") or
            (image[:4] == b"RIFF" and image[8:12] == b"WEBP")):
        raise BridgeError("Unexpected generated image type.")
    return image


def generate_once(payload, token):
    if not token or len(token) < 10:
        raise BridgeError("NOVELAI_API_TOKEN secret not set.")
    req = request.Request(
        API_URL, method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "Nodnaba-NovelAI-Bridge/0.1"})
    try:
        with request.urlopen(req, timeout=115) as response:
            binary = response.read(MAX_RESPONSE + 1)
            return decode_image(binary, response.headers.get("Content-Type", ""))
    except error.HTTPError as exc:
        # Never log server body, token, headers or prompt. Never retry a failed call.
        raise BridgeError("NovelAI HTTP " + str(exc.code) + " (no retry).") from None
    except error.URLError:
        raise BridgeError("NovelAI network connection failed (no retry).") from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--event-path", required=True)
    parser.add_argument("--out", default="output")
    args = parser.parse_args()
    try:
        scene = scene_from_event(args.event_path, args.event_name)
        payload = build_payload(scene)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        if scene["dry_run"]:
            (out / "dry-run.json").write_text(json.dumps({
                "validated": True, "model": MODEL, "generated": False,
                "reference": scene["reference"],
                "dimensions": [scene["width"], scene["height"]]
            }, indent=2), "utf-8")
            print("Dry run passed: no NovelAI call; no Anlas used.")
            return 0
        result = generate_once(payload, os.environ.get("NOVELAI_API_TOKEN"))
        ext = ".png" if result.startswith(b"\x89PNG") else ".webp"
        (out / ("image" + ext)).write_bytes(result)
        print("One image generated. Inspect the artifact before fal video generation.")
        return 0
    except (BridgeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print("Rejected: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
