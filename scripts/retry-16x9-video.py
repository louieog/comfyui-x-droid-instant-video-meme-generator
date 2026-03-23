#!/usr/bin/env python3
"""
Retry the 16:9 image-to-video step with a shorter prompt.
The character image was already generated and uploaded as:
  c48beca93b1909cd5fd80bcaf8882b5d8307c313c25626647e3da14aea3c51dc.png
"""

import asyncio
import json
import os
import ssl
import subprocess
import sys
import uuid
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import websockets

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()

PROJECT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT / "output" / "scenes" / "a-cinematic-and-intense-chinese-mini-drama-featuri"

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

UPLOADED_IMAGE = "c48beca93b1909cd5fd80bcaf8882b5d8307c313c25626647e3da14aea3c51dc.png"

# Shortened prompt (under 500 chars) — same visual intent
VIDEO_PROMPT = (
    "Dark war room, holographic map glowing blue-green. Bald eagle in military uniform "
    "slams talon on table, medals jangling, feathers bristling. Chinese dragon in black "
    "suit sits still, slowly reaches for teacup, takes a calm sip, sets it down. Dragon's "
    "golden eyes lock on eagle. Faint smirk crosses dragon's face. Camera pushes in on "
    "dragon's knowing expression. Cinematic 4K, dramatic lighting."
)

print(f"Video prompt length: {len(VIDEO_PROMPT)} chars")


def make_ws_url():
    return f"wss://cloud.comfy.org/ws?clientId={uuid.uuid4()}&token={API_KEY}"


import urllib.request
import urllib.error


def api_post_json(path, payload):
    url = BASE_URL + path
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    })
    with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as resp:
        return json.loads(resp.read())


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
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode == 0 and dest_path.exists() and dest_path.stat().st_size > 0:
        size_kb = dest_path.stat().st_size / 1024
        print(f"  Downloaded {dest_path.name} ({size_kb:.0f} KB)")
        return True
    print(f"  Download error: {result.stderr}")
    return False


async def submit_and_wait(prompt_json, step_name, timeout_seconds=720):
    payload = {
        "prompt": prompt_json,
        "extra_data": {"api_key_comfy_org": API_KEY},
    }
    resp = api_post_json("/api/prompt", payload)
    prompt_id = resp.get("prompt_id") or resp.get("id")
    print(f"  Submitted: prompt_id={prompt_id}")

    outputs = {}
    async with websockets.connect(make_ws_url(), ssl=SSL_CTX) as ws:
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                print("  TIMEOUT")
                return None, None

            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 30))
            except asyncio.TimeoutError:
                print(f"  waiting...")
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
                    print(f"  executing node {node}")
            elif msg_type == "progress":
                print(f"  progress: {msg_data.get('value', 0)}/{msg_data.get('max', 0)}")
            elif msg_type == "executed" and msg_data.get("output"):
                node_id = msg_data.get("node", "?")
                outputs[node_id] = msg_data["output"]
                print(f"  node {node_id} produced output")
            elif msg_type == "execution_success":
                print("  SUCCESS")
                return prompt_id, outputs
            elif msg_type == "execution_error":
                err = msg_data.get("exception_message", "Unknown")
                print(f"  FAILED: {err}")
                return prompt_id, None


def extract_files(outputs):
    files = []
    for node_id, node_out in (outputs or {}).items():
        for key in ("images", "video", "audio", "gifs"):
            for item in node_out.get(key, []):
                if isinstance(item, dict) and "filename" in item:
                    files.append(item)
    return files


async def main():
    workflow = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": UPLOADED_IMAGE},
        },
        "2": {
            "class_type": "KlingImage2VideoNode",
            "inputs": {
                "start_frame": ["1", 0],
                "prompt": VIDEO_PROMPT,
                "negative_prompt": "blurry, distorted, low quality, cartoon, anime, morphing",
                "model_name": "kling-v2-1-master",
                "cfg_scale": 0.8,
                "mode": "pro",
                "aspect_ratio": "16:9",
                "duration": "5",
            },
        },
        "3": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["2", 0],
                "filename_prefix": "video/dragon-eagle-16x9",
                "format": "mp4",
                "codec": "h264",
            },
        },
    }

    print("Submitting 16:9 i2v with shortened prompt...")
    prompt_id, outputs = await submit_and_wait(workflow, "16x9-i2v-retry")

    if not outputs:
        print("FAILED — no outputs")
        sys.exit(1)

    files = extract_files(outputs)
    if not files:
        print(f"No files in outputs: {json.dumps(outputs, indent=2)[:500]}")
        sys.exit(1)

    fi = files[0]
    dest = OUTPUT_DIR / "scene1-16x9-raw-video.mp4"
    if download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), dest):
        print(f"\n✅ 16:9 video saved: {dest}")
        
        # Update the generation log
        log_path = OUTPUT_DIR / "generation-log.json"
        with open(log_path) as f:
            gen_log = json.load(f)
        
        gen_log["assets"]["scene1-16x9"] = {
            "aspect_ratio": "16:9",
            "character_image": "scene1-16x9-character.png",
            "raw_video": "scene1-16x9-raw-video.mp4",
            "final_video": "scene1-16x9-raw-video.mp4",
            "video_model": "kling-v2-1-master",
            "tts_needed": False,
            "lip_sync_needed": False,
        }
        gen_log["steps"].append({
            "step": "scene1-16x9-image-to-video-retry",
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": f"prompt_id={prompt_id} → scene1-16x9-raw-video.mp4 ({dest.stat().st_size // 1024} KB), model=kling-v2-1-master",
        })
        gen_log["scenes_completed"] = 1
        gen_log["summary"]["aspect_ratios_generated"] = 2
        gen_log["completed_at"] = datetime.now(timezone.utc).isoformat()
        
        with open(log_path, "w") as f:
            json.dump(gen_log, f, indent=2)
        print(f"Updated generation-log.json")
    else:
        print("Download failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
