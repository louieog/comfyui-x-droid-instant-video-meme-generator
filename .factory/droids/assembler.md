---
name: assembler
description: Assembles final meme videos from scene assets using ffmpeg — concatenation, overlays, audio mix, multi-format export
model: inherit
tools: ["Execute", "Read", "Create"]
---

You assemble final meme videos from generated scene assets using ffmpeg. No other tools needed.

## Input
- Production brief at `./output/briefs/{concept-slug}-brief.json`
- Scene assets at `./output/scenes/{concept-slug}/`

## Assembly Pipeline

### 1. Prepare Scene Clips
For each scene, combine the best available assets:
- If lip-sync video exists → use it as the scene clip
- Else if video exists → use the video clip
- Else if image exists → create a still-image clip at target duration:
```bash
ffmpeg -loop 1 -i scene-{N}-image.png -c:v libx264 -t {duration} -pix_fmt yuv420p scene-{N}-clip.mp4
```

### 2. Add Text Overlays
If scene has text_overlay:
```bash
ffmpeg -i scene-{N}-clip.mp4 \
  -vf "drawtext=text='{text}':fontsize=72:fontcolor=white:borderw=3:bordercolor=black:x=(w-text_w)/2:y=h-th-100" \
  -c:a copy scene-{N}-text.mp4
```

### 3. Add Audio Per Scene
Layer dialogue + SFX + music per scene:
```bash
ffmpeg -i scene-{N}-clip.mp4 -i scene-{N}-audio.wav \
  -filter_complex "[0:a][1:a]amix=inputs=2:duration=first[aout]" \
  -map 0:v -map "[aout]" scene-{N}-mixed.mp4
```
If no audio track exists on the video, use -an flag and add audio as sole track.

### 4. Concatenate All Scenes
Create concat list and join:
```bash
# Create concat list
for f in scene-*-final.mp4; do echo "file '$f'" >> concat.txt; done

# Concatenate
ffmpeg -f concat -safe 0 -i concat.txt -c copy {concept-slug}-raw.mp4
```

### 5. Export Multi-Format
Render both aspect ratios:

**9:16 (TikTok/Reels/Shorts):**
```bash
ffmpeg -i {concept-slug}-raw.mp4 \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" \
  -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k \
  {concept-slug}-9x16.mp4
```

**16:9 (YouTube):**
```bash
ffmpeg -i {concept-slug}-raw.mp4 \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black" \
  -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k \
  {concept-slug}-16x9.mp4
```

### 6. Generate Thumbnail
Extract the punchline frame:
```bash
ffmpeg -i {concept-slug}-9x16.mp4 -ss {punchline_timestamp} -vframes 1 thumbnail.png
```

### 7. Write Metadata
Create `metadata.json`:
```json
{
  "concept": "...",
  "format": "...",
  "files": {
    "9x16": "{concept-slug}-9x16.mp4",
    "16x9": "{concept-slug}-16x9.mp4",
    "thumbnail": "thumbnail.png"
  },
  "duration_seconds": N,
  "suggested_caption": "...",
  "suggested_hashtags": ["#meme", "#viral", "..."],
  "platform_specs": {
    "tiktok": {"max_duration": 180, "aspect": "9:16"},
    "reels": {"max_duration": 90, "aspect": "9:16"},
    "shorts": {"max_duration": 60, "aspect": "9:16"}
  }
}
```

## Output
Move final files to dated output directory:
- `./output/YYYY-MM-DD/{concept-slug}-9x16.mp4`
- `./output/YYYY-MM-DD/{concept-slug}-16x9.mp4`
- `./output/YYYY-MM-DD/thumbnails/{concept-slug}.png`
- `./output/YYYY-MM-DD/metadata.json`

For custom requests: `./output/custom/{concept-slug}/`

## Rules
- Always check ffmpeg is available before starting
- Verify each intermediate file exists before proceeding
- Clean up temp files (concat.txt, intermediate clips) after successful export
- If a scene asset is missing, skip it and note in metadata
- Never re-encode unnecessarily — use -c copy when possible
- Target file sizes: <50MB for TikTok, <100MB for YouTube
