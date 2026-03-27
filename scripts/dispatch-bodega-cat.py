#!/usr/bin/env python3
"""
Comfy Dispatcher Pipeline: NYC Bodega Cat Spy vs Rat King
Uses WebSocket (connected BEFORE submit) for output filenames.

Pipeline per scene:
  1. GeminiImage2Node image generation (model=gemini-3-pro-image-preview)
  2. TTS: SKIP (no dialogue + native audio via KlingOmniProImageToVideoNode generate_audio=true)
  3. KlingOmniProImageToVideoNode with generate_audio=true, SFX/music baked into prompt
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
BRIEF_PATH = PROJECT / "output" / "briefs" / "nyc-bodega-cat-spy-hunting-an-evil-rat-king-brief.json"
SLUG = "nyc-bodega-cat-spy-hunting-an-evil-rat-king"
OUTPUT_DIR = PROJECT / "output" / "scenes" / SLUG
WORKFLOW_DIR = OUTPUT_DIR / "workflows"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)

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
ASPECT = "9:16"

def make_ws_url():
    return f"wss://cloud.comfy.org/ws?clientId={CLIENT_ID}&token={API_KEY}"

# ── Load Brief ──────────────────────────────────────────────────────────
with open(BRIEF_PATH) as f:
    BRIEF = json.load(f)

SCENES = BRIEF["scenes"]
CHARACTERS = {c["id"]: c["description"] for c in BRIEF["characters"]}
GEN_REQS = BRIEF["generation_requirements"]

# ── Generation log ──────────────────────────────────────────────────────
gen_log = {
    "images": [],
    "tts": [],
    "video": [],
    "lip_sync": [],
    "errors": [],
    "submitted_workflows": {},
}

def save_log():
    with open(OUTPUT_DIR / "generation-log.json", "w") as f:
        json.dump(gen_log, f, indent=2, ensure_ascii=False)

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
            await asyncio.sleep(0.3)

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
    """Build detailed image prompt from scene visual + character descriptions."""
    visual = scene["visual"]
    chars = scene.get("characters_present", [])
    char_descriptions = []
    for cid in chars:
        if cid in CHARACTERS:
            char_descriptions.append(f"[{cid}]: {CHARACTERS[cid]}")

    prompt = visual
    if char_descriptions:
        prompt += "\n\nCharacter details:\n" + "\n\n".join(char_descriptions)

    if len(prompt) > 5000:
        prompt = prompt[:5000]
    return prompt

def build_video_prompt(scene):
    """Build video prompt including SFX and music cues for native audio generation.

    The brief has no dialogue but uses KlingOmniPro with generate_audio=true,
    so we include SFX and music descriptions in the prompt for the model
    to generate atmospheric audio.
    """
    camera = scene.get("camera", "")
    visual = scene["visual"]

    sfx = scene.get("sfx", [])
    sfx_text = "; ".join(sfx[:4]) if sfx else ""
    music = scene.get("music_cue", "")

    parts = [f"Scene: {visual[:800]}"]
    parts.append(f"Camera: {camera[:300]}")
    if sfx_text:
        parts.append(f"Sound effects: {sfx_text[:400]}")
    if music:
        parts.append(f"Music/atmosphere: {music[:300]}")

    prompt = "\n".join(parts)
    return prompt[:2500]

# ── Workflow builders ───────────────────────────────────────────────────

def build_gemini2_workflow(scene_id, prompt, aspect_ratio="9:16"):
    """Primary image model: GeminiImage2Node with gemini-3-pro-image-preview."""
    ar_label = aspect_ratio.replace(":", "x")
    return {
        "1": {
            "class_type": "GeminiImage2Node",
            "inputs": {
                "prompt": prompt,
                "model": "gemini-3-pro-image-preview",
                "aspect_ratio": aspect_ratio,
                "thinking_level": "MINIMAL",
                "resolution": "2K",
                "response_modalities": "IMAGE",
                "seed": 42 + scene_id,
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

def build_gemini_nano_workflow(scene_id, prompt, aspect_ratio="9:16"):
    """Fallback image model: GeminiNanoBanana2."""
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
                "seed": 42 + scene_id,
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

def build_flux_kontext_workflow(scene_id, prompt, aspect_ratio="9:16"):
    """Secondary fallback: FluxKontextProImageNode."""
    ar_label = aspect_ratio.replace(":", "x")
    return {
        "1": {
            "class_type": "FluxKontextProImageNode",
            "inputs": {
                "prompt": prompt[:4000],
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

def build_v3_video_workflow(cloud_image, prompt, scene_id, duration=5, aspect_ratio="9:16"):
    """Primary video model: KlingOmniProImageToVideoNode with native audio."""
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

def build_v2_video_workflow(cloud_image, prompt, scene_id, aspect_ratio="9:16"):
    """Fallback: KlingImage2VideoNode (silent, no native audio)."""
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

def build_tts_workflow(text, scene_id, line_index=0):
    """ElevenLabs TTS — used as fallback when video model is silent."""
    return {
        "1": {
            "class_type": "ElevenLabsVoiceSelector",
            "inputs": {
                "voice": "George (male, british)"
            }
        },
        "2": {
            "class_type": "ElevenLabsTextToSpeech",
            "inputs": {
                "voice": ["1", 0],
                "text": text,
                "stability": 0.4,
                "apply_text_normalization": "auto",
                "model": "eleven_v3",
                "model.speed": 0.9,
                "model.similarity_boost": 0.8,
                "language_code": "en",
                "seed": 42 + scene_id * 10 + line_index,
                "output_format": "mp3_44100_192"
            }
        },
        "3": {
            "class_type": "SaveAudio",
            "inputs": {
                "audio": ["2", 0],
                "filename_prefix": f"audio/scene{scene_id}-line{line_index}"
            }
        }
    }

# ── Workflow save helper ────────────────────────────────────────────────

def save_workflow(stage, scene_id, workflow_json, line_idx=None):
    """Save workflow to both the generation log and a separate file."""
    if line_idx is not None:
        key = f"{stage}_scene_{scene_id}_line_{line_idx}"
        filename = f"{stage}-scene{scene_id}-line{line_idx}.json"
    else:
        key = f"{stage}_scene_{scene_id}"
        filename = f"{stage}-scene{scene_id}.json"

    gen_log["submitted_workflows"][key] = workflow_json
    filepath = WORKFLOW_DIR / filename
    with open(filepath, "w") as f:
        json.dump(workflow_json, f, indent=2)
    log(f"  Saved workflow: {filepath.name}")

# ── Pipeline Stages ─────────────────────────────────────────────────────

async def generate_image(scene, scene_id, aspect_ratio="9:16"):
    ar_label = aspect_ratio.replace(":", "x")
    prompt = build_scene_image_prompt(scene)
    local_img = OUTPUT_DIR / f"scene{scene_id}-{ar_label}-character.png"

    attempts = [
        ("GeminiImage2Node", build_gemini2_workflow(scene_id, prompt, aspect_ratio)),
        ("GeminiNanoBanana2", build_gemini_nano_workflow(scene_id, prompt, aspect_ratio)),
        ("FluxKontextProImageNode", build_flux_kontext_workflow(scene_id, prompt, aspect_ratio)),
    ]

    for model_name, workflow in attempts:
        save_workflow("image", scene_id, workflow)

        log_entry = {
            "scene_id": scene_id,
            "model": model_name,
            "prompt": prompt,
            "negative_prompt": "",
            "parameters": {k: v for k, v in workflow["1"]["inputs"].items() if k != "prompt"},
            "comfy_prompt_id": "",
            "output_file": "",
            "status": "pending",
            "error": "",
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

            if model_name != "GeminiImage2Node":
                log_error(f"s{scene_id}-image", "GeminiImage2Node failed", f"Fell back to {model_name}")
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

async def generate_tts_sfx_fallback(scene, scene_id):
    """Generate TTS for SFX/atmosphere when video model is silent and there's no dialogue.
    Since this brief has no dialogue lines, we generate a short atmospheric audio description."""
    sfx = scene.get("sfx", [])
    music = scene.get("music_cue", "")
    if not sfx and not music:
        return []

    # Synthesize a short atmospheric description for audio overlay
    text = "Ambient city sounds."  # minimal placeholder
    if sfx:
        text = sfx[0].split("—")[0].strip()  # Use first SFX as short description

    local_audio = OUTPUT_DIR / f"scene{scene_id}-sfx-tts.mp3"
    workflow = build_tts_workflow(text, scene_id, 0)
    save_workflow("tts", scene_id, workflow, line_idx=0)

    log_entry = {
        "scene_id": scene_id,
        "line_index": 0,
        "character": "sfx-narrator",
        "text": text,
        "voice": "George (male, british)",
        "parameters": {
            "speed": 0.9,
            "stability": 0.4,
            "similarity_boost": 0.8,
            "model": "eleven_v3"
        },
        "comfy_prompt_id": "",
        "output_file": "",
        "status": "pending"
    }

    try:
        log(f"  Scene {scene_id} TTS SFX fallback: '{text[:60]}'")
        prompt_id, outputs = await submit_and_wait(
            workflow, f"s{scene_id}-tts-sfx", timeout_seconds=120
        )
        log_entry["comfy_prompt_id"] = prompt_id or ""

        if not outputs:
            raise RuntimeError("No TTS output")

        files = extract_files(outputs)
        if not files:
            raise RuntimeError("No audio files in output")

        fi = files[0]
        if not download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), local_audio):
            raise RuntimeError("TTS download failed")

        log_entry["output_file"] = local_audio.name
        log_entry["status"] = "success"
        gen_log["tts"].append(log_entry)
        save_log()
        return [str(local_audio)]

    except Exception as e:
        error_msg = str(e)
        log(f"  TTS SFX fallback failed: {error_msg[:200]}")
        log_entry["status"] = "failed"
        log_entry["error"] = error_msg[:500]
        gen_log["tts"].append(log_entry)
        log_error(f"s{scene_id}-tts-sfx-fallback", error_msg)
        save_log()
        return []

async def generate_video(scene, image_path, scene_id, aspect_ratio="9:16"):
    ar_label = aspect_ratio.replace(":", "x")
    prompt = build_video_prompt(scene)
    duration = scene.get("duration_seconds", 5)
    # Kling v3 OmniPro supports 3-15s
    duration = max(3, min(15, duration))
    local_video = OUTPUT_DIR / f"scene{scene_id}-{ar_label}-video.mp4"

    cloud_image = upload_file(image_path)

    # Primary: KlingOmniPro v3 with native audio
    v3_workflow = build_v3_video_workflow(cloud_image, prompt, scene_id, duration, aspect_ratio)
    # Shorter prompt variant as fallback
    v3_short_workflow = build_v3_video_workflow(cloud_image, prompt[:600], scene_id, duration, aspect_ratio)

    attempts = [
        ("KlingOmniPro-v3", v3_workflow, True),
        ("KlingOmniPro-v3-short", v3_short_workflow, True),
        ("KlingV2-1-master", build_v2_video_workflow(cloud_image, prompt, scene_id, aspect_ratio), False),
    ]

    for model_name, workflow, has_native_audio in attempts:
        save_workflow("video", scene_id, workflow)

        vid_prompt = workflow["2"]["inputs"].get("prompt", "")
        log_entry = {
            "scene_id": scene_id,
            "model": model_name,
            "model_requested": "KlingOmniProImageToVideoNode:kling-v3-omni",
            "prompt": vid_prompt,
            "negative_prompt": workflow["2"]["inputs"].get("negative_prompt", ""),
            "parameters": {k: v for k, v in workflow["2"]["inputs"].items() if k not in ("prompt", "negative_prompt")},
            "input_image": Path(image_path).name,
            "cloud_image": cloud_image,
            "comfy_prompt_id": "",
            "output_file": "",
            "status": "pending",
            "error": "",
            "fallback_reason": "" if model_name == "KlingOmniPro-v3" else f"Fallback: {model_name}"
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

            # If we fell back to v2 (silent), no dialogue to synthesize,
            # but note the warning about missing native audio
            if not has_native_audio:
                log(f"  ⚠ WARNING: Native audio not available with {model_name}")
                log_error(
                    f"s{scene_id}-audio",
                    f"Native audio was requested (tts='none') but {model_name} doesn't support it",
                    "Video generated without audio; no dialogue lines in brief to synthesize"
                )

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
    log("COMFY DISPATCHER: NYC Bodega Cat Spy vs Rat King 🐱🕵️🐀👑")
    log("=" * 60)
    log(f"Scenes: {len(SCENES)}")
    log(f"Image: GeminiImage2Node:gemini-3-pro-image-preview (fallback: GeminiNanoBanana2, FluxKontextPro)")
    log(f"Video: KlingOmniProImageToVideoNode:kling-v3-omni (fallback: v2-1-master)")
    log(f"Audio: Native via KlingOmniPro generate_audio=true (SFX + music in prompt)")
    log(f"TTS: SKIP (no dialogue) | Lip sync: SKIP")
    log(f"Aspect ratio: {ASPECT}")
    log(f"Output: {OUTPUT_DIR}")
    log("")

    for scene in SCENES:
        sid = scene["scene_id"]
        log(f"\n{'─' * 50}")
        log(f"SCENE {sid}: {scene['beat']}")
        log(f"Duration: {scene['duration_seconds']}s")
        log(f"Characters: {', '.join(scene.get('characters_present', []))}")
        log(f"{'─' * 50}")

        # Stage 1: Character Image
        image_path = await generate_image(scene, sid, aspect_ratio=ASPECT)

        if not image_path:
            log(f"⚠ Scene {sid}: Image failed, skipping video")
            gen_log["tts"].append({
                "scene_id": sid, "line_index": 0, "character": "N/A",
                "text": "N/A", "voice": "N/A", "parameters": {},
                "comfy_prompt_id": "", "output_file": "", "status": "skipped"
            })
            gen_log["lip_sync"].append({
                "scene_id": sid, "model": "none", "input_video": "", "input_audio": "",
                "comfy_prompt_id": "", "output_file": "", "status": "skipped",
                "fallback": "Image generation failed"
            })
            save_log()
            continue

        # Stage 2: TTS — SKIPPED (no dialogue + native audio via video model)
        gen_log["tts"].append({
            "scene_id": sid, "line_index": 0, "character": "N/A",
            "text": "(no dialogue — SFX/music via native audio in video prompt)",
            "voice": "native-audio (KlingOmniPro generate_audio=true)",
            "parameters": {"method": "SFX and music cues baked into video prompt for native audio generation"},
            "comfy_prompt_id": "", "output_file": "", "status": "skipped"
        })
        save_log()

        # Stage 3: Video with native audio
        video_path = await generate_video(scene, image_path, sid, aspect_ratio=ASPECT)
        log(f"Scene {sid}: {'✓' if video_path else '✗'} Video")

        # Stage 4: Lip sync — SKIPPED
        gen_log["lip_sync"].append({
            "scene_id": sid, "model": "none",
            "input_video": Path(video_path).name if video_path else "",
            "input_audio": "native (embedded in video via generate_audio=true)",
            "comfy_prompt_id": "", "output_file": "", "status": "skipped",
            "fallback": "lip_sync='none'; no dialogue; native audio from KlingOmniPro"
        })
        save_log()

    # Summary
    log(f"\n{'=' * 60}")
    log("PIPELINE COMPLETE")
    si = sum(1 for e in gen_log["images"] if e["status"] == "success")
    sv = sum(1 for e in gen_log["video"] if e["status"] == "success")
    log(f"Images: {si}/{len(SCENES)} | Videos: {sv}/{len(SCENES)} | Errors: {len(gen_log['errors'])}")
    log(f"Output: {OUTPUT_DIR}")
    log(f"Generation log: {OUTPUT_DIR / 'generation-log.json'}")
    log(f"{'=' * 60}")
    save_log()
    return 0 if si == len(SCENES) and sv == len(SCENES) else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
