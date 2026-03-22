#!/usr/bin/env python3
"""
Finish scene 4 of the cat infomercial pipeline.
Scene 4 character image + dialogue already exist.
Needs: image-to-video → ffmpeg overlay → update generation-log.json
"""

import asyncio
import json
import os
import ssl
import subprocess
import sys
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

PROJECT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT / "output" / "scenes" / "cat-doing-an-infomercial-for-an-amazon-pet-product"

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
BASE_URL = "https://cloud.comfy.org"

def make_ws_url():
    return f"wss://cloud.comfy.org/ws?clientId={uuid.uuid4()}&token={API_KEY}"

# Load existing generation log
log_path = OUTPUT_DIR / "generation-log.json"
with open(log_path) as f:
    generation_log = json.load(f)

def log_step(name, status, details=None):
    entry = {"step": name, "status": status, "timestamp": datetime.now(timezone.utc).isoformat()}
    if details:
        entry["details"] = details
    generation_log["steps"].append(entry)
    print(f"  [{status.upper():>12}] {name}" + (f" — {details[:140]}" if details else ""))

def api_post_json(path, payload):
    url = BASE_URL + path
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    })
    with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as resp:
        return json.loads(resp.read())

def upload_file(filepath):
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{BASE_URL}/api/upload/image",
         "-H", f"X-API-Key: {API_KEY}",
         "-F", f"image=@{filepath}",
         "-F", "type=input",
         "-F", "overwrite=true"],
        capture_output=True, text=True, timeout=120
    )
    resp = json.loads(result.stdout)
    return resp.get("name") or resp.get("filename")

def download_file(filename, subfolder, file_type, dest_path):
    params = urllib.parse.urlencode({
        "filename": filename, "subfolder": subfolder or "", "type": file_type or "output"
    })
    url = f"{BASE_URL}/api/view?{params}"
    result = subprocess.run(
        ["curl", "-s", "-L", "-o", str(dest_path), "-H", f"X-API-Key: {API_KEY}", url],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode == 0 and dest_path.exists() and dest_path.stat().st_size > 0:
        print(f"    Downloaded {dest_path.name} ({dest_path.stat().st_size // 1024} KB)")
        return True
    return False

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

async def submit_and_wait(prompt_json, step_name, timeout_seconds=600):
    payload = {"prompt": prompt_json, "extra_data": {"api_key_comfy_org": API_KEY}}
    log_step(step_name, "submitting")
    resp = api_post_json("/api/prompt", payload)
    prompt_id = resp.get("prompt_id") or resp.get("id")
    log_step(step_name, "submitted", f"prompt_id={prompt_id}")

    outputs = {}
    async with websockets.connect(make_ws_url(), ssl=SSL_CTX) as ws:
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"Job timed out after {timeout_seconds}s")
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
                print(f"    [{step_name}] progress: {msg_data.get('value')}/{msg_data.get('max')}")
            elif msg_type == "executed" and msg_data.get("output"):
                outputs[msg_data.get("node", "unknown")] = msg_data["output"]
            elif msg_type == "execution_success":
                log_step(step_name, "success", f"prompt_id={prompt_id}")
                return prompt_id, outputs
            elif msg_type == "execution_error":
                err_msg = msg_data.get("exception_message", "Unknown error")
                raise RuntimeError(err_msg)

async def main():
    print("\n── Finishing Scene 4: PAYOFF — PRODUCT IN ACTION + CTA ──")

    local_img = OUTPUT_DIR / "scene4-character.png"
    local_audio = OUTPUT_DIR / "scene4-dialogue.mp3"

    # Verify existing assets
    assert local_img.exists(), f"Missing: {local_img}"
    assert local_audio.exists(), f"Missing: {local_audio}"
    print(f"  ✓ Character image exists: {local_img.stat().st_size // 1024} KB")
    print(f"  ✓ Dialogue audio exists: {local_audio.stat().st_size // 1024} KB")

    # Upload image → image-to-video
    log_step("scene4-upload-image", "uploading", str(local_img))
    uploaded_img = upload_file(str(local_img))
    log_step("scene4-upload-image", "success", f"uploaded as {uploaded_img}")

    video_prompt = (
        "Close-up of a tuxedo cat rubbing its cheek against a wall-mounted brush with pure "
        "bliss. The cat's eyes slowly close to half-mast, its body vibrates with a deep purr "
        "of satisfaction. It leans harder into the brush. Camera slowly pushes in on the "
        "cat's ecstatic face. Warm over-saturated lighting. The cat looks like it has achieved "
        "enlightenment. Cinematic 4K."
    )

    i2v_workflow = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": uploaded_img}
        },
        "2": {
            "class_type": "KlingImage2VideoNode",
            "inputs": {
                "start_frame": ["1", 0],
                "prompt": video_prompt,
                "negative_prompt": "blurry, distorted, low quality, cartoon, anime, morphing, text artifacts",
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
                "filename_prefix": "video/scene4-raw",
                "format": "mp4",
                "codec": "h264"
            }
        }
    }

    prompt_id, outputs = await submit_and_wait(i2v_workflow, "scene4-image-to-video", timeout_seconds=720)
    files = extract_files(outputs)
    if not files:
        raise RuntimeError("No video output for scene 4")

    fi = files[0]
    local_video = OUTPUT_DIR / "scene4-raw-video.mp4"
    if not download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), local_video):
        raise RuntimeError("Failed to download scene 4 raw video")
    log_step("scene4-download-video", "success", str(local_video))

    # ffmpeg overlay (voiceover scene)
    local_final = OUTPUT_DIR / "scene4-final-video.mp4"
    log_step("scene4-ffmpeg-overlay", "running", "Voiceover scene — ffmpeg audio overlay")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(local_video), "-i", str(local_audio),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-map", "0:v:0", "-map", "1:a:0",
        str(local_final)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[:300]}")
    log_step("scene4-ffmpeg-overlay", "success", f"Output: {local_final}")

    # Update generation log
    generation_log["assets"]["scene4"] = {
        "character_image": str(local_img),
        "dialogue_audio": str(local_audio),
        "raw_video": str(local_video),
        "final_video": str(local_final),
        "lip_sync_method": "voiceover-ffmpeg-overlay"
    }
    generation_log["scenes_completed"] = 4
    generation_log["completed_at"] = datetime.now(timezone.utc).isoformat()

    with open(log_path, "w") as f:
        json.dump(generation_log, f, indent=2)

    print(f"\n  ✅ Scene 4 complete")
    print(f"  Generation log updated → {log_path}")
    print(f"\n{'='*60}")
    print(f"  ALL 4 SCENES COMPLETE")
    print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())
