#!/usr/bin/env python3
"""
comfy-dispatcher pipeline for:
  STRAIT OF PATIENCE — Dragon vs Eagle war room mini-drama
  1 scene × 2 aspect ratios, no dialogue, no lip-sync.
  Steps per aspect: character image → upload → image-to-video → download
  Uses WebSocket to receive output filenames from ComfyUI Cloud.
"""

import asyncio
import json
import os
import ssl
import subprocess
import sys
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
OUTPUT_DIR = PROJECT / "output" / "scenes" / "a-cinematic-and-intense-chinese-mini-drama-featuri"
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

# Video model preference order (brief asks for kling-v3; fall back to known-working models)
VIDEO_MODELS = ["kling-v3", "kling-v2-1-master", "kling-v2-master"]


def make_ws_url():
    return f"wss://cloud.comfy.org/ws?clientId={uuid.uuid4()}&token={API_KEY}"


# ── Generation log ──────────────────────────────────────────────────────
generation_log = {
    "brief": "a-cinematic-and-intense-chinese-mini-drama-featuri",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "scenes_total": 1,
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
    detail_str = f" — {details[:200]}" if details else ""
    print(f"  {tag} {name}{detail_str}")


def write_log():
    generation_log["completed_at"] = datetime.now(timezone.utc).isoformat()
    log_path = OUTPUT_DIR / "generation-log.json"
    with open(log_path, "w") as f:
        json.dump(generation_log, f, indent=2)
    print(f"\n  Generation log → {log_path}")


# ── HTTP helpers ────────────────────────────────────────────────────────
import urllib.error
import urllib.parse
import urllib.request


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
    """Upload file via curl (supports image, video, audio despite endpoint name)."""
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{BASE_URL}/api/upload/image",
         "-H", f"X-API-Key: {API_KEY}",
         "-F", f"image=@{filepath}",
         "-F", "type=input",
         "-F", "overwrite=true"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Upload failed: {result.stderr}")
    resp = json.loads(result.stdout)
    return resp.get("name") or resp.get("filename")


def download_file(filename, subfolder, file_type, dest_path):
    """Download output file from ComfyUI Cloud."""
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
        print(f"    Downloaded {dest_path.name} ({size_kb:.0f} KB)")
        return True
    print(f"    Download error for {filename}: {result.stderr}")
    return False


# ── WebSocket submit + wait ─────────────────────────────────────────────
async def submit_and_wait(prompt_json, step_name, timeout_seconds=600):
    """Submit workflow via HTTP, listen on WebSocket for outputs."""
    payload = {
        "prompt": prompt_json,
        "extra_data": {"api_key_comfy_org": API_KEY},
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
    """Pull downloadable file info from WebSocket output messages."""
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


# ── Prompts ─────────────────────────────────────────────────────────────

IMAGE_PROMPT_16x9 = (
    "A dark, cinematic war room lit only by a massive holographic strategic map glowing "
    "blue-green on the table between two characters. The map shows the Strait of Hormuz "
    "region pulsing red. On the left side: an anthropomorphic bald eagle with stark white "
    "head feathers, fierce amber eyes, and a powerful hooked beak, wearing a dark navy US "
    "military dress uniform with rows of medals, epaulettes, and a stars-and-stripes lapel "
    "pin, leaning forward aggressively, one talon slamming the table edge, feathers bristling "
    "and slightly ruffled from stress, beak open mid-shout, jabbing a wing toward the glowing "
    "strait. On the right side: an anthropomorphic Chinese dragon with deep crimson scales, "
    "sharp golden eyes, and elegant antler-like horns, wearing a perfectly tailored black "
    "Zhongshan suit (Mao suit) with subtle gold thread embroidery on the collar and cuffs, "
    "sitting upright in a high-backed obsidian chair, claws steepled in front of him, a small "
    "white porcelain teacup within reach, expression of ancient amused patience — the faintest "
    "knowing smirk. Dramatic uplighting from the holographic map casts eerie blue-green shadows "
    "upward onto both faces. Medium shot, slight dutch angle. Photorealistic, cinematic, 4K, "
    "highly detailed, dramatic contrast between the eagle's agitation and the dragon's calm."
)

IMAGE_PROMPT_9x16 = (
    "A dark, cinematic war room, vertical composition. Dramatic holographic strategic map "
    "glowing blue-green in the center. On the left foreground: an anthropomorphic bald eagle "
    "in dark navy US military dress uniform with medals, leaning forward aggressively, talon "
    "slamming the table, feathers bristling, beak open mid-shout, amber eyes fierce. On the "
    "right, slightly further back: an anthropomorphic Chinese dragon with deep crimson scales, "
    "sharp golden eyes, antler-like horns, wearing a black Zhongshan suit with gold embroidery, "
    "sitting perfectly still in a high-backed obsidian chair, claws steepled, faint knowing "
    "smirk, white porcelain teacup within reach. The holographic map between them shows the "
    "Strait of Hormuz pulsing red. Eerie blue-green uplighting. Vertical framing, slight low "
    "angle. Photorealistic, cinematic, 4K, highly detailed."
)

VIDEO_PROMPT_16x9 = (
    "Dark cinematic war room scene. The bald eagle in military uniform on the left slams his "
    "talon on the metal table aggressively — medals jangling, feathers bristling, beak open. "
    "The Chinese dragon in black Zhongshan suit on the right sits perfectly still, then slowly, "
    "deliberately reaches his right claw for a white porcelain teacup. He lifts it with "
    "unhurried grace, takes a single calm sip, and sets it down with a soft clink. His golden "
    "eyes never leave the eagle. A faint smirk slowly crosses the dragon's face. Camera slowly "
    "pushes in toward the dragon's knowing expression. Holographic map glows and pulses between "
    "them. Dramatic blue-green uplighting, cinematic 4K."
)

VIDEO_PROMPT_9x16 = (
    "Vertical composition, dark cinematic war room. The bald eagle in military uniform slams "
    "the table aggressively, medals jangling. The Chinese dragon in a black suit sits perfectly "
    "still, then with deliberate calm reaches for a white porcelain teacup, lifts it, takes a "
    "graceful sip, and sets it down. The dragon's golden eyes never waver. A faint knowing "
    "smirk crosses his face. Camera slowly pushes in on the dragon. Holographic map pulses "
    "between them. Dramatic blue-green uplighting, cinematic 4K."
)


# ── Workflow builders ───────────────────────────────────────────────────
def build_character_image(prompt_text, aspect_ratio, filename_prefix, seed=42):
    return {
        "1": {
            "class_type": "FluxKontextProImageNode",
            "inputs": {
                "prompt": prompt_text,
                "aspect_ratio": aspect_ratio,
                "guidance": 3.5,
                "steps": 28,
                "seed": seed,
                "prompt_upsampling": False,
            },
        },
        "2": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["1", 0],
                "filename_prefix": filename_prefix,
            },
        },
    }


def build_i2v(uploaded_image, motion_prompt, aspect_ratio, model_name, filename_prefix, duration="5"):
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {
                "image": uploaded_image,
            },
        },
        "2": {
            "class_type": "KlingImage2VideoNode",
            "inputs": {
                "start_frame": ["1", 0],
                "prompt": motion_prompt,
                "negative_prompt": "blurry, distorted, low quality, cartoon, anime, morphing face, text artifacts",
                "model_name": model_name,
                "cfg_scale": 0.8,
                "mode": "pro",
                "aspect_ratio": aspect_ratio,
                "duration": duration,
            },
        },
        "3": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["2", 0],
                "filename_prefix": filename_prefix,
                "format": "mp4",
                "codec": "h264",
            },
        },
    }


# ── Per-aspect pipeline ────────────────────────────────────────────────
async def run_aspect(aspect_ratio, ar_label, image_prompt, video_prompt, seed_offset=0):
    """Run full pipeline for one aspect ratio: image → upload → video → download."""
    prefix = f"scene1-{ar_label}"
    assets = {"aspect_ratio": aspect_ratio}

    # ── Step 1: Character image ──
    step = f"{prefix}-character-image"
    print(f"\n{'─'*60}")
    print(f"  {step} ({aspect_ratio})")
    print(f"{'─'*60}")

    prompt_id, outputs = await submit_and_wait(
        build_character_image(image_prompt, aspect_ratio, f"dragon-eagle-{ar_label}", seed=42 + seed_offset),
        step,
    )
    if not outputs:
        raise RuntimeError(f"Character image generation failed ({ar_label})")

    files = extract_files(outputs)
    if not files:
        debug_path = OUTPUT_DIR / f"debug-ws-{prefix}-image.json"
        with open(debug_path, "w") as f:
            json.dump(outputs, f, indent=2)
        raise RuntimeError(f"No image output files ({ar_label})")

    fi = files[0]
    local_img = OUTPUT_DIR / f"{prefix}-character.png"
    if not download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), local_img):
        raise RuntimeError(f"Failed to download character image ({ar_label})")
    assets["character_image"] = f"{prefix}-character.png"
    size_kb = local_img.stat().st_size // 1024
    log_step(step, "downloaded", f"{prefix}-character.png ({size_kb} KB)")

    # ── Step 2: Upload image ──
    step = f"{prefix}-upload-image"
    log_step(step, "uploading", str(local_img))
    uploaded_name = upload_file(str(local_img))
    if not uploaded_name:
        raise RuntimeError(f"Image upload failed ({ar_label})")
    log_step(step, "success", f"uploaded as {uploaded_name}")

    # ── Step 3: Image-to-video (try models in preference order) ──
    step = f"{prefix}-image-to-video"
    print(f"\n{'─'*60}")
    print(f"  {step} ({aspect_ratio})")
    print(f"{'─'*60}")

    prompt_id = None
    vid_outputs = None
    chosen_model = None

    for model in VIDEO_MODELS:
        print(f"  Trying video model: {model}")
        try:
            prompt_id, vid_outputs = await submit_and_wait(
                build_i2v(uploaded_name, video_prompt, aspect_ratio, model, f"video/dragon-eagle-{ar_label}", "5"),
                f"{step}-{model}",
                timeout_seconds=720,
            )
            if vid_outputs:
                chosen_model = model
                break
            else:
                print(f"  Model {model} failed, trying next...")
        except RuntimeError as e:
            err_str = str(e)
            if "400" in err_str or "422" in err_str:
                print(f"  Model {model} rejected, trying next...")
                continue
            raise

    if not vid_outputs:
        raise RuntimeError(f"All video models failed ({ar_label})")

    files = extract_files(vid_outputs)
    if not files:
        debug_path = OUTPUT_DIR / f"debug-ws-{prefix}-video.json"
        with open(debug_path, "w") as f:
            json.dump(vid_outputs, f, indent=2)
        raise RuntimeError(f"No video output files ({ar_label})")

    fi = files[0]
    local_vid = OUTPUT_DIR / f"{prefix}-raw-video.mp4"
    if not download_file(fi["filename"], fi.get("subfolder", ""), fi.get("type", "output"), local_vid):
        raise RuntimeError(f"Failed to download video ({ar_label})")
    assets["raw_video"] = f"{prefix}-raw-video.mp4"
    assets["video_model"] = chosen_model
    size_kb = local_vid.stat().st_size // 1024
    log_step(step, "downloaded", f"{prefix}-raw-video.mp4 ({size_kb} KB), model={chosen_model}")

    # No TTS or lip-sync needed for this brief
    # The raw video IS the final video
    assets["final_video"] = assets["raw_video"]
    assets["tts_needed"] = False
    assets["lip_sync_needed"] = False

    return assets


# ── Main ────────────────────────────────────────────────────────────────
async def main():
    print(f"\n{'='*60}")
    print("  COMFY-DISPATCHER: STRAIT OF PATIENCE")
    print("  Dragon vs Eagle war room — 1 scene × 2 aspects")
    print(f"  Output → {OUTPUT_DIR}")
    print(f"{'='*60}\n")

    all_assets = {}

    # ── 16:9 (landscape, primary for this two-character scene) ──
    try:
        assets_16x9 = await run_aspect("16:9", "16x9", IMAGE_PROMPT_16x9, VIDEO_PROMPT_16x9, seed_offset=0)
        all_assets["scene1-16x9"] = assets_16x9
        print(f"\n  ✅ 16:9 complete — {len(assets_16x9)} assets")
    except Exception as e:
        err_msg = str(e)
        print(f"\n  ❌ 16:9 FAILED: {err_msg}")
        generation_log["errors"].append({"step": "scene1-16x9", "error": err_msg})
        log_step("scene1-16x9", "failed", err_msg)

    # ── 9:16 (vertical for TikTok / Reels) ──
    try:
        assets_9x16 = await run_aspect("9:16", "9x16", IMAGE_PROMPT_9x16, VIDEO_PROMPT_9x16, seed_offset=100)
        all_assets["scene1-9x16"] = assets_9x16
        print(f"\n  ✅ 9:16 complete — {len(assets_9x16)} assets")
    except Exception as e:
        err_msg = str(e)
        print(f"\n  ❌ 9:16 FAILED: {err_msg}")
        generation_log["errors"].append({"step": "scene1-9x16", "error": err_msg})
        log_step("scene1-9x16", "failed", err_msg)

    # ── Summarize ──
    completed = len(all_assets)
    generation_log["scenes_completed"] = 1 if completed > 0 else 0
    generation_log["assets"] = all_assets
    generation_log["summary"] = {
        "total_scenes": 1,
        "aspect_ratios_requested": 2,
        "aspect_ratios_generated": completed,
        "tts_needed": False,
        "lip_sync_needed": False,
        "text_overlay": "你越急，我越稳。\nThe more you panic… the calmer I become.",
        "note": (
            "Single-scene mini-drama with no dialogue. "
            "Two anthropomorphic characters (Chinese dragon in Zhongshan suit vs "
            "American bald eagle in military dress) in a dark war room. "
            f"Generated {completed}/2 aspect ratio variants. "
            "Text overlay to be added by assembler droid."
        ),
    }
    write_log()

    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE — {completed}/2 variants generated")
    print(f"  Assets in: {OUTPUT_DIR}")
    print(f"{'='*60}\n")

    return 0 if completed > 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
