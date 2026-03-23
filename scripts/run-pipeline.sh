#!/bin/bash
# Runs the full meme-engine pipeline for a given request ID
# Usage: ./scripts/run-pipeline.sh <request-id>

cd "$(dirname "$0")/.."

# Trap errors to update status on failure
trap 'update_status "failed" "$CURRENT_STAGE" "Unexpected error in pipeline"' ERR

REQUEST_ID="$1"
if [ -z "$REQUEST_ID" ]; then
  echo "Usage: $0 <request-id>"
  exit 1
fi

REQUEST_FILE="./requests/$REQUEST_ID.json"
if [ ! -f "$REQUEST_FILE" ]; then
  echo "Request file not found: $REQUEST_FILE"
  exit 1
fi

CONCEPT=$(python3 -c "import json; print(json.load(open('$REQUEST_FILE'))['concept'])")
FORMAT=$(python3 -c "import json; print(json.load(open('$REQUEST_FILE')).get('format','skit'))")
STYLE=$(python3 -c "import json; print(json.load(open('$REQUEST_FILE')).get('style','dark-humor'))")
DURATION=$(python3 -c "import json; print(json.load(open('$REQUEST_FILE')).get('duration_target_seconds',15))")
MODEL_OVERRIDES=$(python3 -c "import json; print(json.dumps(json.load(open('$REQUEST_FILE')).get('model_overrides',{})))")

SLUG=$(echo "$CONCEPT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//' | head -c 50)
STATUS_FILE="./requests/$REQUEST_ID.status.json"

update_status() {
  python3 -c "
import json, sys
status = '$1'
stage = '$2'
detail = '$3'
data = {'request_id': '$REQUEST_ID', 'slug': '$SLUG', 'status': status, 'stage': stage, 'detail': detail}
try:
    existing = json.load(open('$STATUS_FILE'))
    existing.update(data)
    data = existing
except: pass
json.dump(data, open('$STATUS_FILE', 'w'), indent=2)
"
}

echo "=== Meme Engine Pipeline ==="
echo "Request: $REQUEST_ID"
echo "Concept: $CONCEPT"
echo "Format: $FORMAT | Style: $STYLE | Duration: ${DURATION}s"
echo ""

# Stage 1: Meme Scout - Generate Brief
CURRENT_STAGE="meme-scout"
update_status "generating" "meme-scout" "Generating production brief..."
echo "[1/4] Running meme-scout..."
droid exec \
  --cwd "$(pwd)" \
  --skip-permissions-unsafe \
  "You are the meme-scout droid. Generate a production brief for this request:

Concept: $CONCEPT
Format: $FORMAT
Style: $STYLE
Target Duration: ${DURATION}s
Model Overrides: $MODEL_OVERRIDES

Read ./seed-list.json for context. Research current trends related to the concept.
Write the brief to ./output/briefs/${SLUG}-brief.json following the schema in your droid instructions.
Also write it to ./requests/${REQUEST_ID}.brief.json for the web UI." 2>&1 | tee "./requests/${REQUEST_ID}.meme-scout.log"

if [ ! -f "./output/briefs/${SLUG}-brief.json" ] && [ ! -f "./requests/${REQUEST_ID}.brief.json" ]; then
  update_status "failed" "meme-scout" "Failed to generate brief"
  echo "FAILED: No brief generated"
  exit 1
fi

# Copy brief if only one location has it
[ -f "./output/briefs/${SLUG}-brief.json" ] && [ ! -f "./requests/${REQUEST_ID}.brief.json" ] && \
  cp "./output/briefs/${SLUG}-brief.json" "./requests/${REQUEST_ID}.brief.json"
[ ! -f "./output/briefs/${SLUG}-brief.json" ] && [ -f "./requests/${REQUEST_ID}.brief.json" ] && \
  mkdir -p "./output/briefs" && cp "./requests/${REQUEST_ID}.brief.json" "./output/briefs/${SLUG}-brief.json"

update_status "brief_ready" "meme-scout" "Brief generated"
echo "[1/4] Brief generated."
echo ""

# Stage 2: Comfy Dispatcher - Generate Assets
CURRENT_STAGE="comfy-dispatcher"
update_status "generating" "comfy-dispatcher" "Generating scene assets..."
echo "[2/4] Running comfy-dispatcher..."
droid exec \
  --cwd "$(pwd)" \
  --skip-permissions-unsafe \
  "You are the comfy-dispatcher droid. Execute the production pipeline for this brief.

Read the brief at ./output/briefs/${SLUG}-brief.json (or ./requests/${REQUEST_ID}.brief.json).
Read the workflow templates in ./workflows/ for the correct API schemas.
Source .env for the API key.

For each scene, execute these stages in order:
1. Generate character images using the character-image workflow template
2. Generate TTS dialogue using the tts-dialogue workflow template (SKIP if model_overrides.tts is 'none')
3. Generate video clips using the image-to-video workflow template
4. Generate lip-sync using the lip-sync workflow template (SKIP if model_overrides.lip_sync is 'none', fallback to raw video + audio overlay via ffmpeg if lip sync fails)

CRITICAL - AUDIO HANDLING:
- Check model_overrides in the request JSON for tts and lip_sync settings
- If tts is 'none' AND the video model supports native audio (like Veo3, KlingTextToVideoWithAudio, WanSoundImageToVideo), include the dialogue text directly in the video generation prompt so the model generates audio
- If tts is 'none' BUT the video model does NOT support native audio (like kling-v2-master, kling-v2-1-master, kling-v2-5-turbo, RunwayGen4, Luma, Vidu, etc.), OVERRIDE the tts setting and generate TTS audio anyway using ElevenLabs with voice 'George (male, british)'. Log a warning that native audio was requested but the video model doesn't support it.
- Native audio video models: Veo3VideoGenerationNode, KlingTextToVideoWithAudio, KlingImageToVideoWithAudio, WanSoundImageToVideo
- All other video models are SILENT and need separate TTS

IMPORTANT schema notes (from previous successful runs):
- ElevenLabs voice needs full label format: 'George (male, british)' not just 'George'
- ElevenLabs model sub-inputs use dot-notation: 'model.speed', 'model.similarity_boost'  
- SaveVideo format must be 'mp4' not 'video/h264-mp4'
- SaveAudio uses filename_prefix
- ComfyUI Cloud job status is 'success' not 'completed'
- Always include extra_data.api_key_comfy_org in prompt submissions
- Upload files via POST /api/upload/image (works for images, video, and audio despite the name)
- If a model name doesn't exist on ComfyUI Cloud (e.g. kling-v3), query /api/object_info to find the closest available model and use that instead. Log the fallback.

Save all assets to ./output/scenes/${SLUG}/
Write a generation-log.json summarizing results." 2>&1 | tee "./requests/${REQUEST_ID}.comfy-dispatcher.log"

update_status "generating" "assembler" "Assembling final video..."
echo "[2/4] Assets generated."
echo ""

# Stage 3: Assembler - Final video
CURRENT_STAGE="assembler"
echo "[3/4] Running assembler..."
droid exec \
  --cwd "$(pwd)" \
  --skip-permissions-unsafe \
  "You are the assembler droid. Assemble the final video from generated assets.

Read the brief at ./output/briefs/${SLUG}-brief.json.
Scene assets are in ./output/scenes/${SLUG}/.

Follow the assembly pipeline:
1. For each scene, pick the best clip (lip-sync > video > image)
2. Concatenate audio per scene if multiple dialogue lines
3. Add text overlay chyrons from the brief
4. Normalize all clips to same resolution
5. Concatenate all scenes
6. Export 16:9 and 9:16 versions
7. Generate thumbnail from punchline scene
8. Write metadata.json with suggested caption and hashtags

Output to ./output/$(date +%Y-%m-%d)/${SLUG}-16x9.mp4 and 9x16.
Create the thumbnails/ subdirectory too." 2>&1 | tee "./requests/${REQUEST_ID}.assembler.log"

update_status "complete" "done" "Video assembled"
echo ""
echo "[4/4] Pipeline complete!"
echo "Output: ./output/$(date +%Y-%m-%d)/"
