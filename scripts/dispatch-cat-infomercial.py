#!/usr/bin/env python3
"""
comfy-dispatcher pipeline for: cat-doing-an-infomercial
Submits ComfyUI Cloud jobs via HTTP, listens for outputs via WebSocket.
Downloads all assets to ./output/scenes/cat-doing-an-infomercial/
"""

import asyncio
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

import websockets

# ── SSL context ────────────────────────────────────────────────────────
try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()

# ── Paths ──────────────────────────────────────────────────────────────
PROJECT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT / "output" / "scenes" / "cat-doing-an-infomercial"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Load API key ───────────────────────────────────────────────────────
def load_env():
    env_path = PROJECT / ".env"
    if not env_path.exists():
        print("ERROR: .env not found at", env_path)
        sys.exit(1)
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                val = val.strip().strip("'").strip('"')
                os.environ[key.strip()] = val

load_env()
API_KEY = os.environ.get("COMFY_CLOUD_API_KEY", "")
if not API_KEY:
    print("ERROR: COMFY_CLOUD_API_KEY not set in .env")
    sys.exit(1)

BASE_URL = "https://cloud.comfy.org"
def make_ws_url():
    """Generate a fresh WebSocket URL with unique clientId per connection."""
    return f"wss://cloud.comfy.org/ws?clientId={uuid.uuid4()}&token={API_KEY}"

# ── Generation log accumulator ─────────────────────────────────────────
generation_log = {
    "brief": "cat-doing-an-infomercial",
    "started_at": datetime.now(timezone.utc).isoformat(),
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
    print(f"[{status.upper()}] {name}" + (f" — {details}" if details else ""))

# ── HTTP helpers ───────────────────────────────────────────────────────
def api_post_json(path, payload):
    """POST JSON to ComfyUI Cloud, return parsed response."""
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
    """Upload a file via POST /api/upload/image (works for image, video, audio)."""
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
    """Download a generated file from ComfyUI Cloud via redirect."""
    params = urllib.parse.urlencode({
        "filename": filename,
        "subfolder": subfolder or "",
        "type": file_type or "output",
    })
    url = f"{BASE_URL}/api/view?{params}"

    # Use curl with -L to follow redirects (the 302 → signed URL pattern)
    result = subprocess.run(
        ["curl", "-s", "-L", "-o", str(dest_path),
         "-H", f"X-API-Key: {API_KEY}",
         url],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode == 0 and dest_path.exists() and dest_path.stat().st_size > 0:
        print(f"  Downloaded {dest_path.name} ({dest_path.stat().st_size} bytes)")
        return True
    print(f"  Download error for {filename}: {result.stderr}")
    return False

# ── WebSocket-based job execution ──────────────────────────────────────
async def submit_and_wait(prompt_json, step_name, timeout_seconds=600):
    """Submit a workflow via HTTP, then listen on WebSocket for outputs."""

    # Submit via HTTP
    payload = {
        "prompt": prompt_json,
        "extra_data": {
            "api_key_comfy_org": API_KEY
        }
    }
    log_step(step_name, "submitting")
    resp = api_post_json("/api/prompt", payload)
    prompt_id = resp.get("prompt_id") or resp.get("id")
    if not prompt_id:
        raise RuntimeError(f"No prompt_id in response: {json.dumps(resp)}")
    log_step(step_name, "submitted", f"prompt_id={prompt_id}")

    # Listen on WebSocket for this specific prompt_id
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
                    print(f"  [{step_name}] waiting...")
                    continue

                # Skip binary frames (preview images)
                if isinstance(raw, bytes):
                    continue

                msg = json.loads(raw)
                msg_type = msg.get("type", "")
                msg_data = msg.get("data", {})

                # Filter to our job
                if msg_data.get("prompt_id") != prompt_id:
                    continue

                if msg_type == "executing":
                    node = msg_data.get("node")
                    if node:
                        print(f"  [{step_name}] executing node {node}")
                    else:
                        print(f"  [{step_name}] execution finishing...")

                elif msg_type == "progress":
                    val = msg_data.get("value", 0)
                    mx = msg_data.get("max", 0)
                    print(f"  [{step_name}] progress: {val}/{mx}")

                elif msg_type == "executed" and msg_data.get("output"):
                    node_id = msg_data.get("node", "unknown")
                    outputs[node_id] = msg_data["output"]
                    print(f"  [{step_name}] node {node_id} produced output")

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

def extract_files_from_outputs(outputs):
    """Extract file info dicts from WebSocket outputs."""
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


# ══════════════════════════════════════════════════════════════════════
# SCENE 1 DATA
# ══════════════════════════════════════════════════════════════════════

CHARACTER_PROMPT = (
    "A calico cat with wide, unnervingly enthusiastic amber eyes and a tiny "
    "clip-on microphone on her collar. She wears a bright teal polo shirt with "
    "a small embroidered paw logo on the chest. Sitting upright on a white "
    "countertop in front of a tacky infomercial set — bright studio lighting, "
    "a kitchen backdrop with deliberately cheap shelving. Behind her, a tacky "
    "banner reads 'PAWPUSH PRO 3000' in bold yellow text on a blue background. "
    "On the counter: a glass of water, a TV remote, and a small potted plant — "
    "all precariously close to the edge. Her paw rests on a small red button "
    "labeled 'PUSH'. Unblinking sincerity. Bright flat infomercial lighting, "
    "classic 2AM QVC style, slightly over-saturated."
)

DIALOGUE_TEXT = "Tired of knocking things off tables... manually?"

VIDEO_MOTION_PROMPT = (
    "The calico cat in a teal polo shirt sits on a white countertop delivering "
    "an infomercial pitch, looking directly into camera with unblinking enthusiasm. "
    "At the 3.5-second mark, her paw presses a red button labeled 'PUSH'. A glass "
    "of water, a TV remote, and a small potted plant sweep off the counter edge in "
    "a satisfying cascade. The cat doesn't break eye contact. Bright flat studio "
    "lighting, over-saturated infomercial aesthetic, smooth camera hold, medium-close "
    "framing. Cinematic 4K."
)

NEGATIVE_PROMPT = "blurry, distorted, low quality, cartoon, anime, morphing, deformed, ugly"


# ══════════════════════════════════════════════════════════════════════
# PIPELINE STEPS
# ══════════════════════════════════════════════════════════════════════

async def generate_character_image():
    """Generate Mitzi character image using FluxKontextProImageNode."""
    prompt_json = {
        "1": {
            "class_type": "FluxKontextProImageNode",
            "inputs": {
                "prompt": CHARACTER_PROMPT,
                "aspect_ratio": "9:16",
                "guidance": 3.5,
                "steps": 28,
                "seed": 1001,
                "prompt_upsampling": False
            }
        },
        "2": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["1", 0],
                "filename_prefix": "mitzi-infomercial"
            }
        }
    }

    prompt_id, outputs = await submit_and_wait(prompt_json, "scene1-character-image")
    if not outputs:
        return None

    files = extract_files_from_outputs(outputs)
    if not files:
        log_step("scene1-character-image", "error", "No output files in WebSocket response")
        # Debug dump
        with open(OUTPUT_DIR / "debug-ws-outputs-image.json", "w") as f:
            json.dump(outputs, f, indent=2)
        return None

    fi = files[0]
    dest = OUTPUT_DIR / "scene1-mitzi-character.png"
    if download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), dest):
        generation_log["assets"]["character_image"] = str(dest)
        return dest
    return None


async def generate_tts_dialogue():
    """Generate dialogue audio using ElevenLabs via ComfyUI Cloud."""
    prompt_json = {
        "1": {
            "class_type": "ElevenLabsVoiceSelector",
            "inputs": {
                "voice": "Bella (female, american)"
            }
        },
        "2": {
            "class_type": "ElevenLabsTextToSpeech",
            "inputs": {
                "voice": ["1", 0],
                "text": DIALOGUE_TEXT,
                "stability": 0.35,
                "apply_text_normalization": "auto",
                "model": "eleven_v3",
                "model.speed": 0.85,
                "model.similarity_boost": 0.8,
                "language_code": "en",
                "seed": 2001,
                "output_format": "mp3_44100_192"
            }
        },
        "3": {
            "class_type": "SaveAudio",
            "inputs": {
                "audio": ["2", 0],
                "filename_prefix": "audio/mitzi-dialogue"
            }
        }
    }

    prompt_id, outputs = await submit_and_wait(prompt_json, "scene1-tts-dialogue")
    if not outputs:
        return None

    files = extract_files_from_outputs(outputs)
    if not files:
        log_step("scene1-tts-dialogue", "error", "No output files in WebSocket response")
        with open(OUTPUT_DIR / "debug-ws-outputs-tts.json", "w") as f:
            json.dump(outputs, f, indent=2)
        return None

    fi = files[0]
    dest = OUTPUT_DIR / "scene1-dialogue.mp3"
    if download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), dest):
        generation_log["assets"]["dialogue_audio"] = str(dest)
        return dest
    return None


async def generate_video(character_image_path):
    """Upload character image, then generate video with KlingImage2VideoNode."""
    log_step("scene1-upload-image", "uploading", str(character_image_path))
    uploaded_name = upload_file(str(character_image_path))
    if not uploaded_name:
        log_step("scene1-upload-image", "failed", "Upload returned no filename")
        return None
    log_step("scene1-upload-image", "success", f"uploaded as {uploaded_name}")

    prompt_json = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {
                "image": uploaded_name
            }
        },
        "2": {
            "class_type": "KlingImage2VideoNode",
            "inputs": {
                "start_frame": ["1", 0],
                "prompt": VIDEO_MOTION_PROMPT,
                "negative_prompt": NEGATIVE_PROMPT,
                "model_name": "kling-v2-master",
                "cfg_scale": 0.8,
                "mode": "std",
                "aspect_ratio": "9:16",
                "duration": "5"
            }
        },
        "3": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["2", 0],
                "filename_prefix": "video/mitzi-scene1",
                "format": "mp4",
                "codec": "h264"
            }
        }
    }

    prompt_id, outputs = await submit_and_wait(prompt_json, "scene1-image-to-video", timeout_seconds=720)
    if not outputs:
        return None

    files = extract_files_from_outputs(outputs)
    if not files:
        log_step("scene1-image-to-video", "error", "No output files")
        with open(OUTPUT_DIR / "debug-ws-outputs-video.json", "w") as f:
            json.dump(outputs, f, indent=2)
        return None

    fi = files[0]
    dest = OUTPUT_DIR / "scene1-raw-video.mp4"
    if download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), dest):
        generation_log["assets"]["raw_video"] = str(dest)
        return dest
    return None


async def generate_lip_sync(video_path, audio_path):
    """Upload video + audio, then lip-sync. Fallback to ffmpeg overlay."""

    # Upload video
    log_step("scene1-upload-video", "uploading", str(video_path))
    video_uploaded = upload_file(str(video_path))
    if not video_uploaded:
        log_step("scene1-upload-video", "failed", "Upload returned no filename")
        return ffmpeg_fallback(video_path, audio_path)
    log_step("scene1-upload-video", "success", f"uploaded as {video_uploaded}")

    # Upload audio
    log_step("scene1-upload-audio", "uploading", str(audio_path))
    audio_uploaded = upload_file(str(audio_path))
    if not audio_uploaded:
        log_step("scene1-upload-audio", "failed", "Upload returned no filename")
        return ffmpeg_fallback(video_path, audio_path)
    log_step("scene1-upload-audio", "success", f"uploaded as {audio_uploaded}")

    prompt_json = {
        "1": {
            "class_type": "LoadVideo",
            "inputs": {
                "file": video_uploaded
            }
        },
        "2": {
            "class_type": "LoadAudio",
            "inputs": {
                "audio": audio_uploaded
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
                "filename_prefix": "video/mitzi-lipsync",
                "format": "mp4",
                "codec": "h264"
            }
        }
    }

    prompt_id, outputs = await submit_and_wait(prompt_json, "scene1-lip-sync", timeout_seconds=720)

    if outputs:
        files = extract_files_from_outputs(outputs)
        if files:
            fi = files[0]
            dest = OUTPUT_DIR / "scene1-lipsync-video.mp4"
            if download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), dest):
                generation_log["assets"]["lipsync_video"] = str(dest)
                return dest

    # Lip-sync failed — fallback to ffmpeg
    log_step("scene1-lip-sync", "fallback", "Lip-sync failed (cat face geometry), using ffmpeg audio overlay")
    return ffmpeg_fallback(video_path, audio_path)


def ffmpeg_fallback(video_path, audio_path):
    """Overlay audio onto video using ffmpeg as lip-sync fallback."""
    dest = OUTPUT_DIR / "scene1-final-video.mp4"
    log_step("scene1-ffmpeg-fallback", "running")

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
        str(dest)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        log_step("scene1-ffmpeg-fallback", "success", f"Output: {dest}")
        generation_log["assets"]["final_video_ffmpeg"] = str(dest)
        return dest
    else:
        error_tail = result.stderr[-500:] if result.stderr else "unknown error"
        log_step("scene1-ffmpeg-fallback", "failed", error_tail)
        generation_log["errors"].append({"step": "scene1-ffmpeg-fallback", "error": error_tail})
        return None


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════
async def main():
    print("=" * 60)
    print("COMFY-DISPATCHER: cat-doing-an-infomercial")
    print("=" * 60)
    print(f"Output → {OUTPUT_DIR}")
    print()

    # Step 1 & 2 can run in parallel (independent)
    print("\n── STEP 1 & 2: Character Image + TTS Dialogue (parallel) ──")
    img_task = asyncio.create_task(generate_character_image())
    tts_task = asyncio.create_task(generate_tts_dialogue())

    character_image, dialogue_audio = await asyncio.gather(img_task, tts_task)

    if not character_image:
        print("FATAL: Character image generation failed. Cannot proceed.")
        write_log()
        sys.exit(1)

    if not dialogue_audio:
        print("FATAL: TTS dialogue generation failed. Cannot proceed.")
        write_log()
        sys.exit(1)

    # Step 3: Image → Video (depends on step 1)
    print("\n── STEP 3: Image-to-Video Generation ──")
    raw_video = await generate_video(character_image)
    if not raw_video:
        print("FATAL: Video generation failed. Cannot proceed.")
        write_log()
        sys.exit(1)

    # Step 4: Lip-Sync (depends on steps 2 & 3)
    print("\n── STEP 4: Lip-Sync (with ffmpeg fallback) ──")
    final_video = await generate_lip_sync(raw_video, dialogue_audio)
    if not final_video:
        print("WARNING: Both lip-sync and ffmpeg fallback failed.")
        generation_log["errors"].append({"step": "pipeline", "error": "No final video produced"})
    else:
        print(f"\n✓ Final video: {final_video}")

    write_log()
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)


def write_log():
    generation_log["completed_at"] = datetime.now(timezone.utc).isoformat()
    log_path = OUTPUT_DIR / "generation-log.json"
    with open(log_path, "w") as f:
        json.dump(generation_log, f, indent=2)
    print(f"\nGeneration log → {log_path}")


if __name__ == "__main__":
    asyncio.run(main())
