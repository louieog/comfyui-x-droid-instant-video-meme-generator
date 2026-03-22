#!/usr/bin/env python3
"""
comfy-dispatcher pipeline for:
  CAT INFOMERCIAL — Sir Reginald, tuxedo cat, FurBliss Pro 9000
  4 scenes, character image → TTS → image-to-video → lip-sync/fallback
  Uses WebSocket to receive output filenames from ComfyUI Cloud.
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
OUTPUT_DIR = PROJECT / "output" / "scenes" / "cat-doing-an-infomercial-for-an-amazon-pet-product"
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

def make_ws_url():
    return f"wss://cloud.comfy.org/ws?clientId={uuid.uuid4()}&token={API_KEY}"

# ── Generation log ──────────────────────────────────────────────────────
generation_log = {
    "brief": "cat-doing-an-infomercial-for-an-amazon-pet-product",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "scenes_total": 4,
    "scenes_completed": 0,
    "steps": [],
    "assets": {},
    "errors": [],
    "completed_at": None,
}

def log_step(name, status, details=None):
    entry = {"step": name, "status": status, "timestamp": datetime.now(timezone.utc).isoformat()}
    if details:
        entry["details"] = details
    generation_log["steps"].append(entry)
    tag = f"[{status.upper():>12}]"
    detail_str = f" — {details[:140]}" if details else ""
    print(f"  {tag} {name}{detail_str}")

def write_log():
    generation_log["completed_at"] = datetime.now(timezone.utc).isoformat()
    log_path = OUTPUT_DIR / "generation-log.json"
    with open(log_path, "w") as f:
        json.dump(generation_log, f, indent=2)
    print(f"\n  Generation log → {log_path}")

# ── HTTP helpers ────────────────────────────────────────────────────────
def api_post_json(path, payload):
    url = BASE_URL + path
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    })
    try:
        with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"POST {path} → {e.code}: {body}")

def upload_file(filepath):
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{BASE_URL}/api/upload/image",
         "-H", f"X-API-Key: {API_KEY}",
         "-F", f"image=@{filepath}",
         "-F", "type=input",
         "-F", "overwrite=true"],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"Upload failed: {result.stderr}")
    resp = json.loads(result.stdout)
    return resp.get("name") or resp.get("filename")

def download_file(filename, subfolder, file_type, dest_path):
    params = urllib.parse.urlencode({
        "filename": filename,
        "subfolder": subfolder or "",
        "type": file_type or "output",
    })
    url = f"{BASE_URL}/api/view?{params}"
    result = subprocess.run(
        ["curl", "-s", "-L", "-o", str(dest_path),
         "-H", f"X-API-Key: {API_KEY}",
         url],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode == 0 and dest_path.exists() and dest_path.stat().st_size > 0:
        size_kb = dest_path.stat().st_size / 1024
        print(f"    Downloaded {dest_path.name} ({size_kb:.0f} KB)")
        return True
    print(f"    Download error for {filename}: {result.stderr}")
    return False

# ── WebSocket submit + wait ─────────────────────────────────────────────
async def submit_and_wait(prompt_json, step_name, timeout_seconds=600):
    """Submit workflow via HTTP, listen on WebSocket for outputs."""
    payload = {
        "prompt": prompt_json,
        "extra_data": {"api_key_comfy_org": API_KEY}
    }
    log_step(step_name, "submitting")
    resp = api_post_json("/api/prompt", payload)
    prompt_id = resp.get("prompt_id") or resp.get("id")
    if not prompt_id:
        raise RuntimeError(f"No prompt_id in response: {json.dumps(resp)}")
    log_step(step_name, "submitted", f"prompt_id={prompt_id}")

    outputs = {}
    try:
        async with websockets.connect(make_ws_url(), ssl=SSL_CTX) as ws:
            deadline = asyncio.get_event_loop().time() + timeout_seconds
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    log_step(step_name, "timeout", f"Exceeded {timeout_seconds}s")
                    generation_log["errors"].append({"step": step_name, "error": "timeout"})
                    return None, None

                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 30))
                except asyncio.TimeoutError:
                    print(f"    [{step_name}] waiting...")
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
                        print(f"    [{step_name}] executing node {node}")

                elif msg_type == "progress":
                    val = msg_data.get("value", 0)
                    mx = msg_data.get("max", 0)
                    print(f"    [{step_name}] progress: {val}/{mx}")

                elif msg_type == "executed" and msg_data.get("output"):
                    node_id = msg_data.get("node", "unknown")
                    outputs[node_id] = msg_data["output"]
                    print(f"    [{step_name}] node {node_id} produced output")

                elif msg_type == "execution_success":
                    log_step(step_name, "success", f"prompt_id={prompt_id}")
                    return prompt_id, outputs

                elif msg_type == "execution_error":
                    err_msg = msg_data.get("exception_message", "Unknown error")
                    log_step(step_name, "failed", err_msg)
                    generation_log["errors"].append({"step": step_name, "error": err_msg})
                    return prompt_id, None

    except Exception as e:
        log_step(step_name, "error", str(e))
        generation_log["errors"].append({"step": step_name, "error": str(e)})
        return None, None

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

# ── Scene data ──────────────────────────────────────────────────────────
SCENES = [
    {
        "scene_id": 1,
        "beat": "HOOK — THE PROBLEM",
        "image_prompt": (
            "A tuxedo cat with piercing green eyes and immaculate black-and-white fur, "
            "wearing a tiny crimson bow tie clipped to a miniature shirt collar, sitting upright "
            "with regal poise on a white countertop. Behind him: a cheap blue curtain backdrop "
            "with gold trim and a small gold banner reading 'AS SEEN ON TV'. Bright, flat, "
            "slightly over-saturated infomercial studio lighting — the 2AM QVC aesthetic. "
            "Classic medium-close infomercial host shot. The cat stares directly into the camera "
            "with absolute gravitas. One paw rests authoritatively on the countertop."
        ),
        "video_prompt": (
            "The tuxedo cat sits perfectly still on the countertop, staring directly into the "
            "camera with solemn intensity. Minimal movement — only a very slight ear twitch and "
            "slow blink. Bright flat infomercial studio lighting. Static camera, dead center. "
            "The cat's mouth opens slightly as if speaking with measured authority. Cinematic 4K."
        ),
        "dialogue": "Have you ever wanted to be petted... but your human... is asleep?",
        "tts_speed": 0.85,
        "tts_stability": 0.35,
        "tts_similarity": 0.85,
        "lip_sync": True,
        "aspect_ratio": "9:16",
        "duration": "5",
        "seed_offset": 0,
    },
    {
        "scene_id": 2,
        "beat": "TRAGEDY — B&W STRUGGLE FOOTAGE",
        "image_prompt": (
            "A sad disheveled tuxedo cat with big glistening green eyes sits on a dark couch "
            "next to a sleeping human whose face is buried in a pillow. No bow tie. The cat "
            "has one paw gently placed on the human's arm. Dark, moody, noir-grade lighting — "
            "deliberate manufactured tragedy. Shot in grayscale / black and white. "
            "Wide-medium faux-documentary framing. The entire image radiates sadness and neglect. "
            "Bold white text 'ACTUAL FOOTAGE' in cheap sans-serif font in the bottom-left corner."
        ),
        "video_prompt": (
            "Black and white grayscale footage. A sad tuxedo cat lifts a paw and places it gently "
            "on a sleeping human's arm. Nothing happens. The cat slowly turns to look back at the "
            "camera with enormous glistening sad eyes. Slight handheld camera shake. Dark moody "
            "noir lighting. Faux-documentary style. Manufactured tragedy. Cinematic 4K."
        ),
        "dialogue": "Every year... millions of cats go unpetted.",
        "tts_speed": 0.80,
        "tts_stability": 0.30,
        "tts_similarity": 0.85,
        "lip_sync": False,
        "aspect_ratio": "9:16",
        "duration": "5",
        "seed_offset": 10,
    },
    {
        "scene_id": 3,
        "beat": "THE REVEAL — PRODUCT INTRODUCTION",
        "image_prompt": (
            "A tuxedo cat with piercing green eyes wearing a tiny crimson bow tie stands on a "
            "white countertop next to a wall-mounted cat self-groomer brush (an arch-shaped "
            "bristle brush on a white base). A comically large spotlight illuminates the product. "
            "Hyper-saturated colors — even brighter than a normal infomercial. Lens flare sparkles "
            "around the product. Behind them, a bold banner reads 'FURBLISS PRO 9000' in bright "
            "yellow text on electric blue background. Medium shot, slight low angle making the "
            "product look monumental. The cat extends one paw toward the product in a sweeping "
            "presentation gesture."
        ),
        "video_prompt": (
            "The tuxedo cat in a crimson bow tie makes a slow, deliberate sweeping paw gesture "
            "toward the cat self-groomer brush product beside it, like unveiling a treasure. "
            "Lens flare sparkles animate around the product. Hyper-saturated infomercial colors. "
            "Slight low angle. The cat's expression is one of reverent awe. Dramatic lighting. "
            "The cat's mouth opens as if announcing something of great importance. Cinematic 4K."
        ),
        "dialogue": "Introducing... the FurBliss Pro 9000.",
        "tts_speed": 0.85,
        "tts_stability": 0.40,
        "tts_similarity": 0.80,
        "lip_sync": True,
        "aspect_ratio": "9:16",
        "duration": "5",
        "seed_offset": 20,
    },
    {
        "scene_id": 4,
        "beat": "PAYOFF — PRODUCT IN ACTION + CTA",
        "image_prompt": (
            "Close-up of a tuxedo cat with a tiny crimson bow tie rubbing its cheek against a "
            "wall-mounted arch-shaped cat self-groomer brush with an expression of transcendent "
            "bliss — eyes half-closed, mouth slightly open, pure feline ecstasy. The cat leans "
            "into the brush with its whole body vibrating with satisfaction. Bright, warm, "
            "over-saturated infomercial lighting. The background is slightly blurred, focus on "
            "the cat's blissful face. Close-up shot with slow push-in framing."
        ),
        "video_prompt": (
            "Close-up of a tuxedo cat rubbing its cheek against a wall-mounted brush with pure "
            "bliss. The cat's eyes slowly close to half-mast, its body vibrates with a deep purr "
            "of satisfaction. It leans harder into the brush. Camera slowly pushes in on the "
            "cat's ecstatic face. Warm over-saturated lighting. The cat looks like it has achieved "
            "enlightenment. Cinematic 4K."
        ),
        "dialogue": "Order now. You deserve this.",
        "tts_speed": 0.90,
        "tts_stability": 0.45,
        "tts_similarity": 0.80,
        "lip_sync": False,
        "aspect_ratio": "9:16",
        "duration": "5",
        "seed_offset": 30,
    },
]

# ── Workflow builders ───────────────────────────────────────────────────
def build_character_image(scene):
    return {
        "1": {
            "class_type": "FluxKontextProImageNode",
            "inputs": {
                "prompt": scene["image_prompt"],
                "aspect_ratio": scene["aspect_ratio"],
                "guidance": 3.5,
                "steps": 28,
                "seed": 42 + scene["seed_offset"],
                "prompt_upsampling": False
            }
        },
        "2": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["1", 0],
                "filename_prefix": f"sir-reginald-scene{scene['scene_id']}"
            }
        }
    }

def build_tts(scene):
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
                "text": scene["dialogue"],
                "stability": scene["tts_stability"],
                "apply_text_normalization": "auto",
                "model": "eleven_v3",
                "model.speed": scene["tts_speed"],
                "model.similarity_boost": scene["tts_similarity"],
                "language_code": "en",
                "seed": 100 + scene["seed_offset"],
                "output_format": "mp3_44100_192"
            }
        },
        "3": {
            "class_type": "SaveAudio",
            "inputs": {
                "audio": ["2", 0],
                "filename_prefix": f"audio/scene{scene['scene_id']}-dialogue"
            }
        }
    }

def build_image_to_video(scene, uploaded_image_name):
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {
                "image": uploaded_image_name
            }
        },
        "2": {
            "class_type": "KlingImage2VideoNode",
            "inputs": {
                "start_frame": ["1", 0],
                "prompt": scene["video_prompt"],
                "negative_prompt": "blurry, distorted, low quality, cartoon, anime, morphing, text artifacts",
                "model_name": "kling-v2-master",
                "cfg_scale": 0.8,
                "mode": "std",
                "aspect_ratio": scene["aspect_ratio"],
                "duration": scene["duration"]
            }
        },
        "3": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["2", 0],
                "filename_prefix": f"video/scene{scene['scene_id']}-raw",
                "format": "mp4",
                "codec": "h264"
            }
        }
    }

def build_lip_sync(uploaded_video, uploaded_audio, scene_id):
    return {
        "1": {
            "class_type": "LoadVideo",
            "inputs": {
                "file": uploaded_video
            }
        },
        "2": {
            "class_type": "LoadAudio",
            "inputs": {
                "audio": uploaded_audio
            }
        },
        "3": {
            "class_type": "KlingLipSyncAudioToVideoNode",
            "inputs": {
                "video": ["1", 0],
                "audio": ["2", 0],
                "voice_language": "en"
            }
        },
        "4": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["3", 0],
                "filename_prefix": f"video/scene{scene_id}-lipsync",
                "format": "mp4",
                "codec": "h264"
            }
        }
    }

# ── ffmpeg helpers ──────────────────────────────────────────────────────
def ffmpeg_overlay(video_path, audio_path, output_path):
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-map", "0:v:0",
        "-map", "1:a:0",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[:500]}")
    return output_path

# ── Per-scene pipeline ──────────────────────────────────────────────────
async def process_scene(scene):
    sid = scene["scene_id"]
    prefix = f"scene{sid}"
    scene_assets = {}

    # ── Step 1: Character image ──
    step = f"{prefix}-character-image"
    prompt_id, outputs = await submit_and_wait(build_character_image(scene), step)
    if not outputs:
        raise RuntimeError(f"Character image generation failed for scene {sid}")

    files = extract_files(outputs)
    if not files:
        # Dump debug info
        debug_path = OUTPUT_DIR / f"debug-ws-{prefix}-image.json"
        with open(debug_path, "w") as f:
            json.dump(outputs, f, indent=2)
        raise RuntimeError(f"No image output files for scene {sid}")

    fi = files[0]
    local_img = OUTPUT_DIR / f"{prefix}-character.png"
    if not download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), local_img):
        raise RuntimeError(f"Failed to download character image for scene {sid}")
    scene_assets["character_image"] = str(local_img)
    log_step(f"{prefix}-download-image", "success", str(local_img))

    # ── Step 2: TTS dialogue ──
    step = f"{prefix}-tts-dialogue"
    prompt_id, outputs = await submit_and_wait(build_tts(scene), step)
    if not outputs:
        raise RuntimeError(f"TTS generation failed for scene {sid}")

    files = extract_files(outputs)
    if not files:
        debug_path = OUTPUT_DIR / f"debug-ws-{prefix}-tts.json"
        with open(debug_path, "w") as f:
            json.dump(outputs, f, indent=2)
        raise RuntimeError(f"No audio output for scene {sid}")

    fi = files[0]
    local_audio = OUTPUT_DIR / f"{prefix}-dialogue.mp3"
    if not download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), local_audio):
        raise RuntimeError(f"Failed to download dialogue audio for scene {sid}")
    scene_assets["dialogue_audio"] = str(local_audio)
    log_step(f"{prefix}-download-audio", "success", str(local_audio))

    # ── Step 3: Upload image → image-to-video ──
    log_step(f"{prefix}-upload-image", "uploading", str(local_img))
    uploaded_img = upload_file(str(local_img))
    if not uploaded_img:
        raise RuntimeError(f"Image upload failed for scene {sid}")
    log_step(f"{prefix}-upload-image", "success", f"uploaded as {uploaded_img}")

    step = f"{prefix}-image-to-video"
    prompt_id, outputs = await submit_and_wait(
        build_image_to_video(scene, uploaded_img), step, timeout_seconds=720
    )
    if not outputs:
        raise RuntimeError(f"Image-to-video failed for scene {sid}")

    files = extract_files(outputs)
    if not files:
        debug_path = OUTPUT_DIR / f"debug-ws-{prefix}-video.json"
        with open(debug_path, "w") as f:
            json.dump(outputs, f, indent=2)
        raise RuntimeError(f"No video output for scene {sid}")

    fi = files[0]
    local_video = OUTPUT_DIR / f"{prefix}-raw-video.mp4"
    if not download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), local_video):
        raise RuntimeError(f"Failed to download raw video for scene {sid}")
    scene_assets["raw_video"] = str(local_video)
    log_step(f"{prefix}-download-video", "success", str(local_video))

    # ── Step 4: Lip-sync or ffmpeg overlay ──
    local_final = OUTPUT_DIR / f"{prefix}-final-video.mp4"

    if scene["lip_sync"]:
        # Upload video + audio
        log_step(f"{prefix}-upload-video", "uploading", str(local_video))
        uploaded_vid = upload_file(str(local_video))
        log_step(f"{prefix}-upload-video", "success", f"uploaded as {uploaded_vid}")

        log_step(f"{prefix}-upload-audio", "uploading", str(local_audio))
        uploaded_aud = upload_file(str(local_audio))
        log_step(f"{prefix}-upload-audio", "success", f"uploaded as {uploaded_aud}")

        step = f"{prefix}-lip-sync"
        try:
            prompt_id, outputs = await submit_and_wait(
                build_lip_sync(uploaded_vid, uploaded_aud, sid), step, timeout_seconds=720
            )
            if outputs:
                files = extract_files(outputs)
                if files:
                    fi = files[0]
                    if download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), local_final):
                        scene_assets["final_video"] = str(local_final)
                        scene_assets["lip_sync_method"] = "KlingLipSyncAudioToVideoNode"
                        log_step(f"{prefix}-download-lipsync", "success", str(local_final))
                        return scene_assets

            # If we get here, lip-sync didn't produce a downloadable file
            raise RuntimeError("Lip-sync produced no downloadable output")

        except Exception as e:
            err_msg = str(e)
            log_step(step, "fallback", f"Lip-sync failed ({err_msg}), using ffmpeg audio overlay")
            generation_log["errors"].append({"step": step, "error": err_msg})

            # ffmpeg fallback
            log_step(f"{prefix}-ffmpeg-fallback", "running")
            ffmpeg_overlay(local_video, local_audio, local_final)
            scene_assets["final_video"] = str(local_final)
            scene_assets["lip_sync_method"] = "ffmpeg-fallback"
            log_step(f"{prefix}-ffmpeg-fallback", "success", f"Output: {local_final}")
    else:
        # Voiceover scene — just overlay audio
        step = f"{prefix}-ffmpeg-overlay"
        log_step(step, "running", "Voiceover scene — ffmpeg audio overlay")
        ffmpeg_overlay(local_video, local_audio, local_final)
        scene_assets["final_video"] = str(local_final)
        scene_assets["lip_sync_method"] = "voiceover-ffmpeg-overlay"
        log_step(step, "success", f"Output: {local_final}")

    return scene_assets


# ── Main ────────────────────────────────────────────────────────────────
async def main():
    print(f"\n{'='*60}")
    print("  COMFY-DISPATCHER: Sir Reginald's FurBliss Pro 9000 Infomercial")
    print(f"  Output → {OUTPUT_DIR}")
    print(f"  Scenes: {len(SCENES)}")
    print(f"{'='*60}\n")

    all_assets = {}

    for scene in SCENES:
        sid = scene["scene_id"]
        print(f"\n{'─'*60}")
        print(f"  SCENE {sid}: {scene['beat']}")
        print(f"  Lip-sync: {'YES (direct-to-camera)' if scene['lip_sync'] else 'NO (voiceover → ffmpeg)'}")
        print(f"{'─'*60}")

        try:
            scene_assets = await process_scene(scene)
            all_assets[f"scene{sid}"] = scene_assets
            print(f"\n  ✅ Scene {sid} complete — {len(scene_assets)} assets")
        except Exception as e:
            err_msg = str(e)
            print(f"\n  ❌ Scene {sid} FAILED: {err_msg}")
            generation_log["errors"].append({"step": f"scene{sid}", "error": err_msg})
            log_step(f"scene{sid}", "failed", err_msg)

    generation_log["scenes_completed"] = len(all_assets)
    generation_log["assets"] = all_assets
    write_log()

    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE")
    print(f"  Scenes: {len(all_assets)}/{len(SCENES)} succeeded")
    print(f"  Errors: {len(generation_log['errors'])}")
    print(f"{'='*60}\n")

    sys.exit(0 if len(all_assets) == len(SCENES) else 1)


if __name__ == "__main__":
    asyncio.run(main())
