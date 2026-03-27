#!/usr/bin/env python3
"""
Comfy Dispatcher Pipeline: NYC Bodega Cat Spy Hunting Evil Bodega Rat King
Uses WebSocket (connected BEFORE submit) for output filenames.

Pipeline per scene:
  1. GeminiImage2Node image generation (model=gemini-3-pro-image-preview)
  2. TTS: SKIP (tts='none' + native audio via KlingOmniProImageToVideoNode generate_audio=true)
  3. KlingOmniProImageToVideoNode with generate_audio=true, dialogue/SFX/music baked into prompt
  4. Lip sync: SKIP (brief sets lip_sync='none')

Audio handling:
  - TTS is 'none' AND video model (KlingOmniProImageToVideoNode) supports native audio
  - Dialogue text is included directly in video generation prompt for speech generation
  - SFX and music cues are also included in video prompt for atmospheric audio
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
BRIEF_PATH = PROJECT / "output" / "briefs" / "nyc-bodega-cat-spy-hunting-a-evil-bodega-rat-king--brief.json"
SLUG = "nyc-bodega-cat-spy-hunting-a-evil-bodega-rat-king-"
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
    "brief": str(BRIEF_PATH),
    "started_at": datetime.now(timezone.utc).isoformat(),
    "config": {
        "image_model": "GeminiImage2Node:gemini-3-pro-image-preview",
        "video_model": "KlingOmniProImageToVideoNode:kling-v3-omni",
        "tts": "none (native audio via video model)",
        "lip_sync": "none",
        "aspect_ratio": ASPECT,
    },
    "images": [],
    "tts": [],
    "video": [],
    "lip_sync": [],
    "errors": [],
    "submitted_workflows": {},
}

def save_log():
    gen_log["updated_at"] = datetime.now(timezone.utc).isoformat()
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
        raise RuntimeError(f"POST {path} -> {e.code}: {body[:500]}")

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
                raise RuntimeError(f"No prompt_id: {json.dumps(resp)[:500]}")
            log(f"  [{step_name}] prompt_id={prompt_id}")

            deadline = asyncio.get_event_loop().time() + timeout_seconds
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    log(f"  [{step_name}] TIMEOUT after {timeout_seconds}s")
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

    # Trim to safe limit for GeminiImage2Node
    if len(prompt) > 5000:
        prompt = prompt[:5000]
    return prompt

def build_video_prompt(scene):
    """Build video prompt with dialogue, SFX, and music for native audio generation.
    
    Since KlingOmniProImageToVideoNode supports native audio and TTS is 'none',
    we include dialogue text in the prompt so the model generates speech audio,
    plus SFX and music cues for atmosphere.
    """
    visual = scene["visual"]
    camera = scene.get("camera", "")
    
    # Include dialogue in prompt for native audio speech generation
    dialogue_lines = scene.get("dialogue", [])
    dialogue_text = ""
    if dialogue_lines:
        dialogue_parts = []
        for d in dialogue_lines:
            char = d.get("character", "narrator")
            line = d.get("line", "")
            emotion = d.get("emotion", "")
            dialogue_parts.append(f"{char} says ({emotion}): '{line}'")
        dialogue_text = " ".join(dialogue_parts)
    
    sfx = scene.get("sfx", [])
    sfx_text = "; ".join(sfx[:3]) if sfx else ""
    music = scene.get("music_cue", "")

    parts = [f"Scene: {visual[:600]}"]
    parts.append(f"Camera: {camera[:200]}")
    if dialogue_text:
        parts.append(f"Dialogue (characters speaking): {dialogue_text[:500]}")
    if sfx_text:
        parts.append(f"Sound effects: {sfx_text[:300]}")
    if music:
        parts.append(f"Music/atmosphere: {music[:250]}")

    prompt = "\n".join(parts)
    # KlingOmniPro prompt limit is ~2500 chars
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
    """Third fallback: FluxKontextProImageNode."""
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

def build_tts_workflow(text, voice, scene_id, line_index=0):
    """ElevenLabs TTS — used as fallback when video model is silent."""
    return {
        "1": {
            "class_type": "ElevenLabsVoiceSelector",
            "inputs": {
                "voice": voice
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
    """Stage 1: Generate character image using GeminiImage2Node with fallbacks."""
    ar_label = aspect_ratio.replace(":", "x")
    prompt = build_scene_image_prompt(scene)
    local_img = OUTPUT_DIR / f"scene{scene_id}-{ar_label}-character.png"

    attempts = [
        ("GeminiImage2Node", "gemini-3-pro-image-preview", build_gemini2_workflow(scene_id, prompt, aspect_ratio)),
        ("GeminiNanoBanana2", "Nano Banana 2 (Gemini 3.1 Flash Image)", build_gemini_nano_workflow(scene_id, prompt, aspect_ratio)),
        ("FluxKontextProImageNode", "flux-kontext-pro", build_flux_kontext_workflow(scene_id, prompt, aspect_ratio)),
    ]

    for model_name, model_label, workflow in attempts:
        save_workflow("image", scene_id, workflow)

        log_entry = {
            "scene_id": scene_id,
            "model": f"{model_name}:{model_label}",
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
                log_error(f"s{scene_id}-image", f"Primary GeminiImage2Node failed", f"Fell back to {model_name}")
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
                "resolution": f"Will try next fallback" if model_name != "FluxKontextProImageNode" else "All image models exhausted"
            })
            save_log()
            continue

    log_error(f"s{scene_id}-image", "All image attempts failed (GeminiImage2, GeminiNanoBanana2, FluxKontextPro)")
    return None

async def generate_video(scene, image_path, scene_id, aspect_ratio="9:16"):
    """Stage 3: Generate video using KlingOmniProImageToVideoNode with native audio."""
    ar_label = aspect_ratio.replace(":", "x")
    prompt = build_video_prompt(scene)
    duration = scene.get("duration_seconds", 5)
    # Kling v3 OmniPro supports 3-15s
    duration = max(3, min(15, duration))
    local_video = OUTPUT_DIR / f"scene{scene_id}-{ar_label}-video.mp4"

    cloud_image = upload_file(image_path)

    # Primary: KlingOmniPro v3 with native audio
    v3_workflow = build_v3_video_workflow(cloud_image, prompt, scene_id, duration, aspect_ratio)

    attempts = [
        ("KlingOmniProImageToVideoNode:kling-v3-omni", v3_workflow, True),
        ("KlingImage2VideoNode:kling-v2-1-master", build_v2_video_workflow(cloud_image, prompt, scene_id, aspect_ratio), False),
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
            "fallback_reason": "" if "v3-omni" in model_name else f"Fallback from kling-v3-omni to {model_name}"
        }

        try:
            log(f"Scene {scene_id} video: {model_name} (duration={duration}s, audio={'native' if has_native_audio else 'NONE'})...")
            prompt_id, outputs = await submit_and_wait(
                workflow, f"s{scene_id}-vid-{model_name.split(':')[0]}", timeout_seconds=720
            )
            log_entry["comfy_prompt_id"] = prompt_id or ""

            if not outputs:
                raise RuntimeError("No outputs received")

            files = extract_files(outputs)
            if not files:
                debug_path = OUTPUT_DIR / f"debug-s{scene_id}-vid-{model_name.replace(':', '-')}.json"
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

            # If we fell back to v2 (silent), log warning about missing native audio
            if not has_native_audio:
                log(f"  WARNING: Native audio was requested (tts='none') but {model_name} doesn't support it")
                log_error(
                    f"s{scene_id}-audio",
                    f"Native audio was requested but fell back to {model_name} which doesn't support it",
                    "Video generated without audio. Consider TTS fallback for dialogue."
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
                "resolution": "Will try fallback model" if has_native_audio else "All video models exhausted"
            })
            save_log()
            continue

    log_error(f"s{scene_id}-video", "All video attempts failed (KlingOmniPro-v3, KlingV2-1)")
    return None

# ── Main Pipeline ───────────────────────────────────────────────────────

async def main():
    log("=" * 70)
    log("COMFY DISPATCHER: NYC Bodega Cat Spy vs Evil Bodega Rat King")
    log("=" * 70)
    log(f"Brief: {BRIEF_PATH}")
    log(f"Scenes: {len(SCENES)}")
    log(f"Image: GeminiImage2Node:gemini-3-pro-image-preview")
    log(f"  Fallback chain: GeminiNanoBanana2 -> FluxKontextProImageNode")
    log(f"Video: KlingOmniProImageToVideoNode:kling-v3-omni (native audio)")
    log(f"  Fallback: KlingImage2VideoNode:kling-v2-1-master (silent)")
    log(f"TTS: SKIP (tts='none', using native audio via video model)")
    log(f"Lip sync: SKIP (lip_sync='none')")
    log(f"Aspect ratio: {ASPECT}")
    log(f"Output: {OUTPUT_DIR}")
    log("")

    scene_results = {}

    for scene in SCENES:
        sid = scene["scene_id"]
        log(f"\n{'=' * 70}")
        log(f"SCENE {sid}: {scene['beat']}")
        log(f"Duration: {scene['duration_seconds']}s | Characters: {', '.join(scene.get('characters_present', []))}")
        log(f"Dialogue lines: {len(scene.get('dialogue', []))}")
        log(f"{'=' * 70}")

        # ── Stage 1: Character Image ────────────────────────────────────
        log(f"\n--- Stage 1: Image Generation ---")
        image_path = await generate_image(scene, sid, aspect_ratio=ASPECT)

        if not image_path:
            log(f"SCENE {sid}: Image failed, skipping remaining stages")
            gen_log["tts"].append({
                "scene_id": sid, "line_index": 0, "character": "N/A",
                "text": "N/A", "voice": "N/A", "parameters": {},
                "comfy_prompt_id": "", "output_file": "", "status": "skipped"
            })
            gen_log["video"].append({
                "scene_id": sid, "model": "N/A", "model_requested": "KlingOmniProImageToVideoNode:kling-v3-omni",
                "prompt": "", "negative_prompt": "", "parameters": {},
                "input_image": "", "comfy_prompt_id": "", "output_file": "",
                "status": "skipped", "fallback_reason": "Image generation failed"
            })
            gen_log["lip_sync"].append({
                "scene_id": sid, "model": "none", "input_video": "", "input_audio": "",
                "comfy_prompt_id": "", "output_file": "", "status": "skipped",
                "fallback": "Image generation failed"
            })
            save_log()
            scene_results[sid] = {"image": False, "video": False}
            continue

        # ── Stage 2: TTS — SKIPPED ──────────────────────────────────────
        log(f"\n--- Stage 2: TTS (SKIPPED - native audio via KlingOmniPro) ---")
        # Log all dialogue lines as skipped with full details
        dialogue_lines = scene.get("dialogue", [])
        if dialogue_lines:
            for li, d in enumerate(dialogue_lines):
                gen_log["tts"].append({
                    "scene_id": sid,
                    "line_index": li,
                    "character": d.get("character", "unknown"),
                    "text": d.get("line", ""),
                    "voice": f"native-audio (KlingOmniPro generate_audio=true)",
                    "parameters": {
                        "method": "Dialogue included in video prompt for native audio speech generation",
                        "emotion": d.get("emotion", ""),
                        "voice_style": d.get("voice_style", "")
                    },
                    "comfy_prompt_id": "",
                    "output_file": "",
                    "status": "skipped"
                })
        else:
            gen_log["tts"].append({
                "scene_id": sid, "line_index": 0, "character": "N/A",
                "text": "(no dialogue lines)", "voice": "N/A", "parameters": {},
                "comfy_prompt_id": "", "output_file": "", "status": "skipped"
            })
        save_log()

        # ── Stage 3: Video with Native Audio ────────────────────────────
        log(f"\n--- Stage 3: Video Generation (with native audio) ---")
        video_path = await generate_video(scene, image_path, sid, aspect_ratio=ASPECT)
        log(f"Scene {sid} video: {'SUCCESS' if video_path else 'FAILED'}")

        # ── Stage 4: Lip Sync — SKIPPED ─────────────────────────────────
        log(f"\n--- Stage 4: Lip Sync (SKIPPED - lip_sync='none') ---")
        gen_log["lip_sync"].append({
            "scene_id": sid, "model": "none",
            "input_video": Path(video_path).name if video_path else "",
            "input_audio": "native (embedded in video via generate_audio=true)",
            "comfy_prompt_id": "", "output_file": "", "status": "skipped",
            "fallback": "lip_sync='none' in brief; native audio embedded in video via KlingOmniPro generate_audio=true"
        })
        save_log()

        scene_results[sid] = {
            "image": bool(image_path),
            "video": bool(video_path),
        }

    # ── Summary ─────────────────────────────────────────────────────────
    log(f"\n{'=' * 70}")
    log("PIPELINE COMPLETE")
    log(f"{'=' * 70}")
    si = sum(1 for e in gen_log["images"] if e["status"] == "success")
    sv = sum(1 for e in gen_log["video"] if e["status"] == "success")
    errs = len(gen_log["errors"])
    log(f"Images: {si}/{len(SCENES)} success")
    log(f"Videos: {sv}/{len(SCENES)} success")
    log(f"TTS: all skipped (native audio)")
    log(f"Lip sync: all skipped")
    log(f"Errors: {errs}")
    log(f"Output dir: {OUTPUT_DIR}")
    log(f"Generation log: {OUTPUT_DIR / 'generation-log.json'}")

    for sid, res in scene_results.items():
        status = "OK" if res["image"] and res["video"] else "PARTIAL" if any(res.values()) else "FAILED"
        log(f"  Scene {sid}: {status} (image={'Y' if res['image'] else 'N'}, video={'Y' if res['video'] else 'N'})")

    gen_log["completed_at"] = datetime.now(timezone.utc).isoformat()
    gen_log["summary"] = {
        "images_success": si,
        "images_total": len(SCENES),
        "videos_success": sv,
        "videos_total": len(SCENES),
        "tts_skipped": True,
        "lip_sync_skipped": True,
        "errors": errs,
    }
    save_log()

    log(f"\n{'=' * 70}")
    return 0 if si == len(SCENES) and sv == len(SCENES) else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
