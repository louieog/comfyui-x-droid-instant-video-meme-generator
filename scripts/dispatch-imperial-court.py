#!/usr/bin/env python3
"""
Comfy Dispatcher Pipeline: THE IMPERIAL COURT OF MEOW (猫朝廷)
Uses WebSocket (connected BEFORE submit) for output filenames.

Pipeline per scene:
  1. GeminiNanoBanana2 image generation (thinking_level=MINIMAL, resolution=2K, response_modalities=IMAGE)
  2. TTS: SKIP (native audio via KlingOmniProImageToVideoNode)
  3. KlingOmniProImageToVideoNode with generate_audio=true
  4. Lip sync: SKIP (brief sets lip_sync='none')
"""

import asyncio
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import websockets

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()

# ── Paths & Config ──────────────────────────────────────────────────────
PROJECT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT / "output" / "scenes" / "a-satirical-mini-drama-skit-of-chinese-feudal-roya"
BRIEF_PATH = PROJECT / "output" / "briefs" / "a-satirical-mini-drama-skit-of-chinese-feudal-roya-brief.json"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load .env
env_path = PROJECT / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ[key.strip()] = val.strip().strip("'").strip('"')

API_KEY = os.environ.get("COMFY_CLOUD_API_KEY", "")
if not API_KEY:
    print("ERROR: COMFY_CLOUD_API_KEY not set")
    sys.exit(1)

BASE_URL = "https://cloud.comfy.org"
CLIENT_ID = str(uuid.uuid4())

def make_ws_url():
    return f"wss://cloud.comfy.org/ws?clientId={CLIENT_ID}&token={API_KEY}"

# ── Load Brief ──────────────────────────────────────────────────────────
with open(BRIEF_PATH) as f:
    BRIEF = json.load(f)

SCENES = BRIEF["scenes"]
CHARACTERS = BRIEF["characters"]
GEN_REQS = BRIEF["generation_requirements"]
MODELS = GEN_REQS.get("models_preferred", {})

# ── Generation log ──────────────────────────────────────────────────────
gen_log = {"images": [], "tts": [], "video": [], "lip_sync": [], "errors": []}

def save_log():
    with open(OUTPUT_DIR / "generation-log.json", "w") as f:
        json.dump(gen_log, f, indent=2)

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def log_error(stage, error, resolution=""):
    gen_log["errors"].append({"stage": stage, "error": str(error)[:1000], "resolution": resolution})
    save_log()

# ── HTTP helpers ────────────────────────────────────────────────────────
def api_post_json(path, payload):
    url = BASE_URL + path
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", "X-API-Key": API_KEY,
    })
    try:
        with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"POST {path} → {e.code}: {body}")

def upload_file(filepath):
    log(f"  Uploading {Path(filepath).name}...")
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{BASE_URL}/api/upload/image",
         "-H", f"X-API-Key: {API_KEY}",
         "-F", f"image=@{filepath}", "-F", "type=input", "-F", "overwrite=true"],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"Upload failed: {result.stderr}")
    resp = json.loads(result.stdout)
    name = resp.get("name") or resp.get("filename")
    log(f"  Uploaded as {name}")
    return name

def download_file(filename, subfolder, file_type, dest_path):
    params = urllib.parse.urlencode({
        "filename": filename, "subfolder": subfolder or "", "type": file_type or "output",
    })
    url = f"{BASE_URL}/api/view?{params}"
    result = subprocess.run(
        ["curl", "-s", "-L", "-o", str(dest_path), "-H", f"X-API-Key: {API_KEY}", url],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode == 0 and dest_path.exists() and dest_path.stat().st_size > 0:
        size_kb = dest_path.stat().st_size / 1024
        log(f"  Downloaded {dest_path.name} ({size_kb:.0f} KB)")
        return True
    log(f"  Download error for {filename}: {result.stderr}")
    return False

# ── WebSocket submit + wait ─────────────────────────────────────────────
async def submit_and_wait(prompt_json, step_name, timeout_seconds=600):
    """Connect WS FIRST, then submit prompt, then listen for outputs."""
    payload = {
        "prompt": prompt_json,
        "extra_data": {"api_key_comfy_org": API_KEY}
    }

    outputs = {}
    prompt_id = None

    try:
        async with websockets.connect(make_ws_url(), ssl=SSL_CTX, ping_interval=20, ping_timeout=60) as ws:
            # Small delay to ensure WS is ready
            await asyncio.sleep(0.3)

            # NOW submit the prompt
            log(f"  [{step_name}] submitting...")
            resp = api_post_json("/api/prompt", payload)
            prompt_id = resp.get("prompt_id") or resp.get("id")
            if not prompt_id:
                raise RuntimeError(f"No prompt_id: {json.dumps(resp)}")
            log(f"  [{step_name}] prompt_id={prompt_id}")

            deadline = asyncio.get_event_loop().time() + timeout_seconds
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    log(f"  [{step_name}] TIMEOUT")
                    return prompt_id, None

                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 30))
                except asyncio.TimeoutError:
                    log(f"  [{step_name}] waiting...")
                    continue

                if isinstance(raw, bytes):
                    continue

                msg = json.loads(raw)
                msg_type = msg.get("type", "")
                msg_data = msg.get("data", {})

                if msg_data.get("prompt_id") != prompt_id:
                    continue

                if msg_type == "executing":
                    node = msg_data.get("node")
                    if node:
                        log(f"  [{step_name}] executing node {node}")

                elif msg_type == "progress":
                    val = msg_data.get("value", 0)
                    mx = msg_data.get("max", 0)
                    log(f"  [{step_name}] progress: {val}/{mx}")

                elif msg_type == "executed" and msg_data.get("output"):
                    node_id = msg_data.get("node", "unknown")
                    outputs[node_id] = msg_data["output"]
                    log(f"  [{step_name}] node {node_id} produced output")

                elif msg_type == "execution_success":
                    log(f"  [{step_name}] SUCCESS")
                    return prompt_id, outputs

                elif msg_type == "execution_error":
                    err_msg = msg_data.get("exception_message", "Unknown error")
                    log(f"  [{step_name}] FAILED: {err_msg[:300]}")
                    return prompt_id, None

    except Exception as e:
        err = str(e)
        log(f"  [{step_name}] Error: {err[:200]}")
        return prompt_id, None

def extract_files(outputs):
    files = []
    if not outputs:
        return files
    for node_id, node_out in outputs.items():
        for key in ("images", "video", "audio", "gifs"):
            items = node_out.get(key, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and "filename" in item:
                        files.append(item)
    return files

# ── Prompt builders ─────────────────────────────────────────────────────

def build_scene_image_prompt(scene):
    visual = scene["visual"]
    chars_present = scene.get("characters_present", [])
    char_descs = [c["description"] for c in CHARACTERS if c["id"] in chars_present]
    prompt = f"{visual}\n\nCharacter details:\n" + "\n\n".join(char_descs)
    if len(prompt) > 4000:
        prompt = prompt[:4000]
    return prompt

def build_video_prompt(scene):
    camera = scene.get("camera", "")
    visual = scene["visual"]
    dialogue_parts = []
    for d in scene.get("dialogue", []):
        dialogue_parts.append(f'{d["character"]} speaks in Mandarin: "{d["line"]}" ({d.get("translation","")})')
    sfx = scene.get("sfx", [])
    sfx_text = "; ".join(sfx[:3]) if sfx else ""
    music = scene.get("music_cue", "")

    parts = [f"Scene: {visual[:600]}", f"Camera: {camera[:250]}"]
    if dialogue_parts:
        parts.append("Spoken dialogue (Mandarin Chinese): " + " | ".join(dialogue_parts))
    if sfx_text:
        parts.append(f"Sound effects: {sfx_text[:200]}")
    if music:
        parts.append(f"Music: {music[:200]}")
    prompt = "\n".join(parts)
    return prompt[:2500]

# ── Workflow builders ───────────────────────────────────────────────────

def build_gemini_workflow(scene_id, prompt, aspect_ratio="16:9"):
    ar_label = aspect_ratio.replace(":", "x")
    return {
        "1": {
            "class_type": "GeminiNanoBanana2",
            "inputs": {
                "prompt": prompt,
                "model": "Nano Banana 2 (Gemini 3.1 Flash Image)",
                "aspect_ratio": aspect_ratio,
                "thinking_level": "MINIMAL",
                "resolution": "2K",
                "response_modalities": "IMAGE",
                "seed": 42 + scene_id
            }
        },
        "2": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["1", 0],
                "filename_prefix": f"scene{scene_id}-{ar_label}-char"
            }
        }
    }

def build_flux_workflow(scene_id, prompt, aspect_ratio="16:9"):
    ar_label = aspect_ratio.replace(":", "x")
    return {
        "1": {
            "class_type": "FluxKontextProImageNode",
            "inputs": {
                "prompt": prompt[:2000],
                "aspect_ratio": aspect_ratio,
                "guidance": 3.5,
                "steps": 28,
                "seed": 42 + scene_id,
                "prompt_upsampling": False
            }
        },
        "2": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["1", 0],
                "filename_prefix": f"scene{scene_id}-{ar_label}-char"
            }
        }
    }

def build_v3_video_workflow(cloud_image, prompt, scene_id, duration=5, aspect_ratio="16:9"):
    ar_label = aspect_ratio.replace(":", "x")
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": cloud_image}
        },
        "2": {
            "class_type": "KlingOmniProImageToVideoNode",
            "inputs": {
                "model_name": "kling-v3-omni",
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "duration": duration,
                "reference_images": ["1", 0],
                "resolution": "1080p",
                "generate_audio": True,
                "seed": 100 + scene_id
            }
        },
        "3": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["2", 0],
                "filename_prefix": f"video/scene{scene_id}-{ar_label}",
                "format": "mp4",
                "codec": "h264"
            }
        }
    }

def build_v2_video_workflow(cloud_image, prompt, scene_id, aspect_ratio="16:9"):
    ar_label = aspect_ratio.replace(":", "x")
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": cloud_image}
        },
        "2": {
            "class_type": "KlingImage2VideoNode",
            "inputs": {
                "start_frame": ["1", 0],
                "prompt": prompt[:490],
                "negative_prompt": "blurry, distorted, low quality, cartoon, anime, morphing",
                "model_name": "kling-v2-1-master",
                "cfg_scale": 0.8,
                "mode": "pro",
                "aspect_ratio": aspect_ratio,
                "duration": "5"
            }
        },
        "3": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["2", 0],
                "filename_prefix": f"video/scene{scene_id}-{ar_label}",
                "format": "mp4",
                "codec": "h264"
            }
        }
    }

# ── Pipeline Stages ─────────────────────────────────────────────────────

async def generate_image(scene, scene_id, aspect_ratio="16:9"):
    ar_label = aspect_ratio.replace(":", "x")
    prompt = build_scene_image_prompt(scene)
    local_img = OUTPUT_DIR / f"scene{scene_id}-{ar_label}-character.png"

    attempts = [
        ("GeminiNanoBanana2", build_gemini_workflow(scene_id, prompt, aspect_ratio)),
        ("FluxKontextPro", build_flux_workflow(scene_id, prompt, aspect_ratio)),
    ]

    for model_name, workflow in attempts:
        log_entry = {
            "scene_id": scene_id,
            "model": model_name,
            "prompt": prompt,
            "negative_prompt": "",
            "parameters": {k: v for k, v in workflow["1"]["inputs"].items() if k != "prompt"},
            "comfy_prompt_id": "",
            "output_file": "",
            "status": "pending",
            "error": ""
        }

        try:
            log(f"Scene {scene_id} image: {model_name}...")
            prompt_id, outputs = await submit_and_wait(
                workflow, f"s{scene_id}-img-{model_name}", timeout_seconds=300
            )
            log_entry["comfy_prompt_id"] = prompt_id or ""

            if not outputs:
                raise RuntimeError("No outputs received")

            files = extract_files(outputs)
            if not files:
                debug_path = OUTPUT_DIR / f"debug-s{scene_id}-{model_name}.json"
                with open(debug_path, "w") as f2:
                    json.dump(outputs, f2, indent=2)
                raise RuntimeError("No image files in output")

            fi = files[0]
            if not download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), local_img):
                raise RuntimeError("Download failed")

            log_entry["output_file"] = local_img.name
            log_entry["status"] = "success"
            gen_log["images"].append(log_entry)
            save_log()

            if model_name != "GeminiNanoBanana2":
                log_error(f"s{scene_id}-image", "GeminiNanoBanana2 failed", f"Fell back to {model_name}")
            return str(local_img)

        except Exception as e:
            error_msg = str(e)
            log(f"  {model_name} failed: {error_msg[:300]}")
            log_entry["status"] = "failed"
            log_entry["error"] = error_msg[:800]
            gen_log["images"].append(log_entry)
            gen_log["errors"].append({
                "stage": f"s{scene_id}-image-{model_name}",
                "error": error_msg[:800],
                "resolution": ""
            })
            save_log()
            continue

    log_error(f"s{scene_id}-image", "All image attempts failed")
    return None

async def generate_video(scene, image_path, scene_id, aspect_ratio="16:9"):
    ar_label = aspect_ratio.replace(":", "x")
    prompt = build_video_prompt(scene)
    duration = scene.get("duration_seconds", 5)
    local_video = OUTPUT_DIR / f"scene{scene_id}-{ar_label}-video.mp4"

    cloud_image = upload_file(image_path)

    attempts = [
        ("KlingOmniPro-v3", build_v3_video_workflow(cloud_image, prompt, scene_id, duration, aspect_ratio)),
        ("KlingOmniPro-v3-short", build_v3_video_workflow(cloud_image, prompt[:600], scene_id, duration, aspect_ratio)),
        ("KlingV2-1-master", build_v2_video_workflow(cloud_image, prompt, scene_id, aspect_ratio)),
    ]

    for model_name, workflow in attempts:
        vid_prompt = workflow["2"]["inputs"].get("prompt", "")
        log_entry = {
            "scene_id": scene_id,
            "model": model_name,
            "model_requested": "KlingOmniProImageToVideoNode:kling-v3-omni",
            "prompt": vid_prompt,
            "negative_prompt": workflow["2"]["inputs"].get("negative_prompt", ""),
            "parameters": {k: v for k, v in workflow["2"]["inputs"].items() if k != "prompt" and k != "negative_prompt"},
            "input_image": Path(image_path).name,
            "cloud_image": cloud_image,
            "comfy_prompt_id": "",
            "output_file": "",
            "status": "pending",
            "error": "",
            "fallback_reason": "" if "v3" in model_name and "short" not in model_name else f"Fallback: {model_name}"
        }

        try:
            log(f"Scene {scene_id} video: {model_name}...")
            prompt_id, outputs = await submit_and_wait(
                workflow, f"s{scene_id}-vid-{model_name}", timeout_seconds=720
            )
            log_entry["comfy_prompt_id"] = prompt_id or ""

            if not outputs:
                raise RuntimeError("No outputs received")

            files = extract_files(outputs)
            if not files:
                debug_path = OUTPUT_DIR / f"debug-s{scene_id}-vid-{model_name}.json"
                with open(debug_path, "w") as f2:
                    json.dump(outputs, f2, indent=2)
                raise RuntimeError("No video files in output")

            fi = files[0]
            if not download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), local_video):
                raise RuntimeError("Download failed")

            log_entry["output_file"] = local_video.name
            log_entry["status"] = "success"
            gen_log["video"].append(log_entry)
            save_log()
            return str(local_video)

        except Exception as e:
            error_msg = str(e)
            log(f"  {model_name} failed: {error_msg[:300]}")
            log_entry["status"] = "failed"
            log_entry["error"] = error_msg[:800]
            gen_log["video"].append(log_entry)
            gen_log["errors"].append({
                "stage": f"s{scene_id}-video-{model_name}",
                "error": error_msg[:800],
                "resolution": ""
            })
            save_log()
            continue

    log_error(f"s{scene_id}-video", "All video attempts failed")
    return None

# ── Main Pipeline ───────────────────────────────────────────────────────

async def main():
    log("=" * 60)
    log("COMFY DISPATCHER: THE IMPERIAL COURT OF MEOW (猫朝廷)")
    log("=" * 60)
    log(f"Scenes: {len(SCENES)}")
    log(f"Image: GeminiNanoBanana2 (fallback: FluxKontextPro)")
    log(f"Video: KlingOmniProImageToVideoNode:kling-v3-omni (fallback: v2-1-master)")
    log(f"Audio: Native via KlingOmniPro generate_audio=true")
    log(f"TTS: SKIP | Lip sync: SKIP")
    log(f"Output: {OUTPUT_DIR}")
    log("")

    for scene in SCENES:
        sid = scene["scene_id"]
        log(f"\n{'─' * 50}")
        log(f"SCENE {sid}: {scene['beat']}")
        log(f"Duration: {scene['duration_seconds']}s")
        log(f"{'─' * 50}")

        # Stage 1: Image
        image_path = await generate_image(scene, sid, aspect_ratio="16:9")

        if not image_path:
            log(f"⚠ Scene {sid}: Image failed, skipping video")
            for i, d in enumerate(scene.get("dialogue", [])):
                gen_log["tts"].append({
                    "scene_id": sid, "line_index": i, "character": d["character"],
                    "text": d["line"], "voice": "N/A", "parameters": {},
                    "comfy_prompt_id": "", "output_file": "", "status": "skipped"
                })
            gen_log["lip_sync"].append({
                "scene_id": sid, "model": "none", "input_video": "", "input_audio": "",
                "comfy_prompt_id": "", "output_file": "", "status": "skipped",
                "fallback": "Image generation failed"
            })
            save_log()
            continue

        # Stage 2: TTS — SKIPPED
        for i, d in enumerate(scene.get("dialogue", [])):
            gen_log["tts"].append({
                "scene_id": sid, "line_index": i, "character": d["character"],
                "text": d["line"],
                "voice": "native-audio (KlingOmniPro generate_audio=true)",
                "parameters": {"method": "dialogue in video prompt for native speech"},
                "comfy_prompt_id": "", "output_file": "", "status": "skipped"
            })
        save_log()

        # Stage 3: Video
        video_path = await generate_video(scene, image_path, sid, aspect_ratio="16:9")
        log(f"Scene {sid}: {'✓' if video_path else '✗'} Video")

        # Stage 4: Lip sync — SKIPPED
        gen_log["lip_sync"].append({
            "scene_id": sid, "model": "none",
            "input_video": Path(video_path).name if video_path else "",
            "input_audio": "native (embedded in video)",
            "comfy_prompt_id": "", "output_file": "", "status": "skipped",
            "fallback": "lip_sync='none'; native audio from KlingOmniPro"
        })
        save_log()

    # Summary
    log(f"\n{'=' * 60}")
    log("PIPELINE COMPLETE")
    si = sum(1 for e in gen_log["images"] if e["status"] == "success")
    sv = sum(1 for e in gen_log["video"] if e["status"] == "success")
    log(f"Images: {si}/{len(SCENES)} | Videos: {sv}/{len(SCENES)} | Errors: {len(gen_log['errors'])}")
    log(f"{'=' * 60}")
    save_log()
    return 0 if si == len(SCENES) and sv == len(SCENES) else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
