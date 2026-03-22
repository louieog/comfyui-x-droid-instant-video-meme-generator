#!/usr/bin/env python3
"""Assembler: Final video assembly for cat-doing-an-infomercial-for-an-amazon-pet-product.

Pipeline:
1. Select best clip per scene (final-video > raw-video > image)
2. Add text overlay chyrons from the brief
3. Extend scene 4 with freeze-frame for CTA readability
4. Normalize all clips to same resolution
5. Concatenate all scenes
6. Export 16:9 (1920x1080) with blurred background + 9:16 (1080x1920)
7. Generate thumbnail from punchline scene
8. Write metadata.json
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

# ── Paths ──────────────────────────────────────────────────────────────
SCENES_DIR = "/Users/orlando/.meme-engine/output/scenes/cat-doing-an-infomercial-for-an-amazon-pet-product"
BRIEF_PATH = "/Users/orlando/.meme-engine/output/briefs/cat-doing-an-infomercial-for-an-amazon-pet-product-brief.json"
OUTPUT_DIR = "/Users/orlando/.meme-engine/output/2026-03-20"
SLUG = "cat-doing-an-infomercial-for-an-amazon-pet-product"

FONT_REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_BLACK = "/System/Library/Fonts/Supplemental/Arial Black.ttf"


def run_ff(cmd, desc=""):
    """Run an ffmpeg/ffprobe command, raise on failure."""
    print(f"\n{'─'*60}")
    print(f"▶ {desc}")
    print(f"  {' '.join(cmd[:6])}{'...' if len(cmd)>6 else ''}")
    print(f"{'─'*60}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"STDERR:\n{result.stderr[:2000]}")
        raise RuntimeError(f"FAILED: {desc}\n{result.stderr[:500]}")
    return result


def probe_duration(path):
    """Get duration of a media file in seconds."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True
    )
    return float(r.stdout.strip())


def escape_dt(text):
    """Escape text for ffmpeg drawtext filter option."""
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "'\\\\\\''")
    return text


def main():
    # ── Load brief ─────────────────────────────────────────────────────
    with open(BRIEF_PATH) as f:
        brief = json.load(f)

    scenes = brief["scenes"]

    # ── Create directories ─────────────────────────────────────────────
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "thumbnails"), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="meme-asm-")
    print(f"Temp dir: {tmp}")

    # ── Step 1: Select best clip per scene ─────────────────────────────
    # Priority: final-video (lip-sync/fallback) > raw-video > image
    scene_info = []
    for sc in scenes:
        sid = sc["scene_id"]
        final = os.path.join(SCENES_DIR, f"scene{sid}-final-video.mp4")
        raw = os.path.join(SCENES_DIR, f"scene{sid}-raw-video.mp4")
        img = os.path.join(SCENES_DIR, f"scene{sid}-character.png")

        if os.path.exists(final):
            clip_type, clip_path = "final-video", final
        elif os.path.exists(raw):
            clip_type, clip_path = "raw-video", raw
        else:
            clip_type, clip_path = "image", img

        scene_info.append({
            "scene_id": sid,
            "clip_type": clip_type,
            "clip_path": clip_path,
            "text_overlay": sc.get("text_overlay"),
            "beat": sc["beat"],
            "target_duration": sc["duration_seconds"],
        })
        print(f"  Scene {sid}: {clip_type} → {os.path.basename(clip_path)}")

    # ── Step 2 & 3: Process each scene (overlays + extend scene 4) ─────
    processed = []
    for si in scene_info:
        sid = si["scene_id"]
        inp = si["clip_path"]
        out = os.path.join(tmp, f"scene{sid}-proc.mp4")
        overlay = si["text_overlay"]

        vf_parts = []
        af_parts = []

        # Text overlay filters
        if overlay is None:
            pass  # no overlay
        elif overlay == "ACTUAL FOOTAGE":
            # Bottom-left, white bold, documentary style
            txt = escape_dt("ACTUAL FOOTAGE")
            vf_parts.append(
                f"drawtext=fontfile='{FONT_BOLD}'"
                f":text='{txt}'"
                f":fontsize=28:fontcolor=white"
                f":x=20:y=h-th-30"
                f":borderw=2:bordercolor=black"
            )
        elif overlay == "NEW!":
            # Top-right, yellow on red box — infomercial starburst
            txt = escape_dt("NEW!")
            vf_parts.append(
                f"drawtext=fontfile='{FONT_BLACK}'"
                f":text='{txt}'"
                f":fontsize=52:fontcolor=yellow"
                f":x=w-tw-30:y=30"
                f":borderw=3:bordercolor=red"
                f":box=1:boxcolor=red@0.75:boxborderw=12"
            )
        else:
            # Scene 4 CTA — multi-line lower-third
            # Split into headline + sub-line for readability
            l1 = escape_dt("CALL 1-800-FUR-BLISS")
            l2 = escape_dt("ONLY $19.99")
            l3 = escape_dt("Humans not included.")
            vf_parts.append(
                f"drawtext=fontfile='{FONT_BOLD}'"
                f":text='{l1}'"
                f":fontsize=32:fontcolor=yellow"
                f":x=(w-tw)/2:y=h-180"
                f":box=1:boxcolor=red@0.85:boxborderw=10"
            )
            vf_parts.append(
                f"drawtext=fontfile='{FONT_BOLD}'"
                f":text='{l2}'"
                f":fontsize=32:fontcolor=yellow"
                f":x=(w-tw)/2:y=h-130"
                f":box=1:boxcolor=red@0.85:boxborderw=10"
            )
            vf_parts.append(
                f"drawtext=fontfile='{FONT_REGULAR}'"
                f":text='{l3}'"
                f":fontsize=18:fontcolor=white"
                f":x=(w-tw)/2:y=h-80"
                f":borderw=1:bordercolor=black"
            )

        # For scene 4: extend with 2s freeze-frame for CTA readability
        if sid == 4:
            vf_parts.insert(0, "tpad=stop_mode=clone:stop_duration=2")
            af_parts.append("apad=pad_dur=2")

        # Build ffmpeg command
        vf_str = ",".join(vf_parts) if vf_parts else "null"
        af_str = ",".join(af_parts) if af_parts else "anull"

        run_ff([
            "ffmpeg", "-y", "-i", inp,
            "-vf", vf_str,
            "-af", af_str,
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-r", "24",
            out
        ], f"Scene {sid}: overlay + process")

        processed.append(out)

    # ── Verify intermediate clips ──────────────────────────────────────
    durations = []
    for p in processed:
        d = probe_duration(p)
        durations.append(d)
        print(f"  {os.path.basename(p)}: {d:.2f}s")
    total_dur = sum(durations)
    print(f"  Total duration: {total_dur:.2f}s")

    # ── Step 4: Concatenate via concat demuxer ─────────────────────────
    concat_list = os.path.join(tmp, "concat.txt")
    with open(concat_list, "w") as f:
        for p in processed:
            f.write(f"file '{p}'\n")

    concat_native = os.path.join(tmp, "concat-native.mp4")
    run_ff([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "128k",
        concat_native
    ], "Concatenate all scenes (native res)")

    # ── Step 5: Export 9:16 (1080×1920) ────────────────────────────────
    out_9x16 = os.path.join(OUTPUT_DIR, f"{SLUG}-9x16.mp4")
    # Source 704×1304 → scale to fit 1080×1920, pad with black
    vf_9x16 = (
        "scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1"
    )
    run_ff([
        "ffmpeg", "-y", "-i", concat_native,
        "-vf", vf_9x16,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        out_9x16
    ], "Export 9:16 (1080×1920)")

    # ── Step 6: Export 16:9 (1920×1080) with blurred BG ────────────────
    out_16x9 = os.path.join(OUTPUT_DIR, f"{SLUG}-16x9.mp4")
    # Portrait source → blurred fill background + sharp center overlay
    fc_16x9 = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1920:1080:force_original_aspect_ratio=increase:flags=fast_bilinear,"
        "crop=1920:1080,gblur=sigma=40[bgblur];"
        "[fg]scale=-2:1080:flags=lanczos[fgscale];"
        "[bgblur][fgscale]overlay=(W-w)/2:(H-h)/2[vout]"
    )
    run_ff([
        "ffmpeg", "-y", "-i", concat_native,
        "-filter_complex", fc_16x9,
        "-map", "[vout]", "-map", "0:a",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        out_16x9
    ], "Export 16:9 (1920×1080) — blurred BG")

    # ── Step 7: Thumbnails from punchline scene (scene 4) ──────────────
    scene4_start = sum(durations[:3])
    thumb_time = scene4_start + 0.5  # half-second into scene 4

    thumb_16x9 = os.path.join(OUTPUT_DIR, "thumbnails", f"{SLUG}-thumb-16x9.jpg")
    thumb_9x16 = os.path.join(OUTPUT_DIR, "thumbnails", f"{SLUG}-thumb-9x16.jpg")

    # 16:9 thumbnail with blurred BG
    fc_thumb = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1280:720:force_original_aspect_ratio=increase:flags=fast_bilinear,"
        "crop=1280:720,gblur=sigma=30[bgblur];"
        "[fg]scale=-2:720:flags=lanczos[fgscale];"
        "[bgblur][fgscale]overlay=(W-w)/2:(H-h)/2[vout]"
    )
    run_ff([
        "ffmpeg", "-y", "-i", concat_native,
        "-ss", str(thumb_time),
        "-vframes", "1",
        "-filter_complex", fc_thumb,
        "-map", "[vout]",
        "-q:v", "2",
        thumb_16x9
    ], f"Thumbnail 16:9 at t={thumb_time:.2f}s")

    # 9:16 thumbnail
    run_ff([
        "ffmpeg", "-y", "-i", concat_native,
        "-ss", str(thumb_time),
        "-vframes", "1",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1",
        "-q:v", "2",
        thumb_9x16
    ], f"Thumbnail 9:16 at t={thumb_time:.2f}s")

    # ── Step 8: metadata.json ──────────────────────────────────────────
    size_16x9 = os.path.getsize(out_16x9)
    size_9x16 = os.path.getsize(out_9x16)

    metadata = {
        "concept": brief["concept"],
        "slug": SLUG,
        "format": brief["format"],
        "style": brief["style"],
        "duration_seconds": round(total_dur, 2),
        "outputs": {
            "16x9": {
                "file": f"{SLUG}-16x9.mp4",
                "resolution": "1920x1080",
                "size_bytes": size_16x9,
            },
            "9x16": {
                "file": f"{SLUG}-9x16.mp4",
                "resolution": "1080x1920",
                "size_bytes": size_9x16,
            },
        },
        "thumbnails": {
            "16x9": f"thumbnails/{SLUG}-thumb-16x9.jpg",
            "9x16": f"thumbnails/{SLUG}-thumb-9x16.jpg",
        },
        "suggested_caption": (
            "Have you ever wanted to be petted… but your human… is asleep? 😿 "
            "Introducing the FurBliss Pro 9000. Order now. You deserve this. 🐱✨"
        ),
        "suggested_hashtags": [
            "#CatInfomercial",
            "#FurBlissPro9000",
            "#CatsOfTikTok",
            "#AIGeneratedCats",
            "#AsSeenOnTV",
            "#CatMemes",
            "#PetProducts",
            "#InfomercialParody",
            "#SirReginald",
            "#FunnyAnimals",
            "#AIVideo",
        ],
        "scenes": [
            {
                "scene_id": si["scene_id"],
                "beat": si["beat"],
                "asset_used": si["clip_type"],
                "duration_actual": round(durations[i], 2),
                "text_overlay": si["text_overlay"],
            }
            for i, si in enumerate(scene_info)
        ],
        "assembly_notes": {
            "lip_sync": "All lip-sync attempts failed (720px min, source 704px). All scenes use ffmpeg audio-overlay fallback.",
            "scene4_extended": "Added 2s freeze-frame for CTA readability.",
            "16x9_method": "Blurred background fill + sharp center overlay (source is portrait 704×1304).",
            "9x16_method": "Scale to fit with minimal letterboxing.",
        },
    }

    meta_path = os.path.join(OUTPUT_DIR, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    # ── Summary ────────────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print("✅ ASSEMBLY COMPLETE")
    print(f"{'═'*60}")
    print(f"  9:16  → {out_9x16}  ({size_9x16/1024:.0f} KB)")
    print(f"  16:9  → {out_16x9}  ({size_16x9/1024:.0f} KB)")
    print(f"  Thumb → {thumb_16x9}")
    print(f"  Thumb → {thumb_9x16}")
    print(f"  Meta  → {meta_path}")
    print(f"  Duration: {total_dur:.2f}s")
    print(f"{'═'*60}")

    # Cleanup
    shutil.rmtree(tmp)
    print(f"  Cleaned up {tmp}")


if __name__ == "__main__":
    main()
