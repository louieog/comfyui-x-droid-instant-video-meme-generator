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
- Native audio video models: Veo3VideoGenerationNode (all variants: veo-3.0, veo-3.1, veo-3.1-fast), Veo3FirstLastFrameNode, KlingTextToVideoWithAudio, KlingImageToVideoWithAudio, KlingOmniProTextToVideoNode, KlingOmniProImageToVideoNode, WanSoundImageToVideo
- For Veo 3 nodes: set generate_audio=true. Veo3VideoGenerationNode supports optional image input for I2V. Model options: veo-3.1-generate, veo-3.1-fast-generate, veo-3.0-generate-001. Duration is fixed at 8s. Include dialogue in the prompt for speech generation.
- For Google image models: GeminiImageNode (model: gemini-2.5-flash-image), GeminiImage2Node (model: gemini-3-pro-image-preview), GeminiNanoBanana2 (model: 'Nano Banana 2 (Gemini 3.1 Flash Image)'), GoogleImagenNode (model: imagen-4.0-generate-preview-06-06 or imagen-3.0-generate-002)
- For Kling v3 OmniPro nodes (KlingOmniProTextToVideoNode, KlingOmniProImageToVideoNode): use model_name 'kling-v3-omni' and set optional generate_audio=true. These support duration 3-15s, aspect_ratio 16:9/9:16/1:1, resolution 1080p/720p. Include dialogue in the prompt text so the model generates speech audio.
- For KlingTextToVideoWithAudio / KlingImageToVideoWithAudio: use model_name 'kling-v2-6', mode 'pro', generate_audio=true. Include dialogue in the prompt.
- The video model value may contain a colon separator like 'KlingOmniProImageToVideoNode:kling-v3-omni' meaning node_type:model_name. Parse accordingly.
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

CRITICAL: Write a DETAILED generation-log.json to ./output/scenes/${SLUG}/generation-log.json with this structure:
{
  \"images\": [{\"scene_id\": N, \"model\": \"actual model\", \"prompt\": \"exact prompt sent\", \"negative_prompt\": \"...\", \"parameters\": {...}, \"comfy_prompt_id\": \"uuid\", \"output_file\": \"filename\", \"status\": \"success/failed\", \"error\": \"if any\"}],
  \"tts\": [{\"scene_id\": N, \"line_index\": 0, \"character\": \"name\", \"text\": \"exact dialogue\", \"voice\": \"voice label\", \"parameters\": {\"speed\": ..., \"stability\": ..., \"similarity_boost\": ...}, \"comfy_prompt_id\": \"uuid\", \"output_file\": \"filename\", \"status\": \"success/failed/skipped\"}],
  \"video\": [{\"scene_id\": N, \"model\": \"actual model\", \"model_requested\": \"original\", \"prompt\": \"exact prompt\", \"negative_prompt\": \"...\", \"parameters\": {...}, \"input_image\": \"filename\", \"comfy_prompt_id\": \"uuid\", \"output_file\": \"filename\", \"status\": \"success/failed\", \"fallback_reason\": \"if model changed\"}],
  \"lip_sync\": [{\"scene_id\": N, \"model\": \"...\", \"input_video\": \"...\", \"input_audio\": \"...\", \"comfy_prompt_id\": \"uuid\", \"output_file\": \"filename\", \"status\": \"success/failed/skipped\", \"fallback\": \"description if fallback used\"}],
  \"errors\": [{\"stage\": \"...\", \"error\": \"...\", \"resolution\": \"...\"}]
}
Every prompt_id, every prompt string, every parameter must be logged. This is essential for manual re-runs." 2>&1 | tee "./requests/${REQUEST_ID}.comfy-dispatcher.log"

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
9. IMPORTANT: The metadata.json MUST include a 'pipeline_log' object with the following structure:

{
  ...existing metadata fields...,
  \"pipeline_log\": {
    \"request_id\": \"${REQUEST_ID}\",
    \"generated_at\": \"ISO timestamp\",
    \"errors\": [
      {\"stage\": \"stage_name\", \"error\": \"description\", \"resolution\": \"what happened\"}
    ],
    \"stages\": {
      \"images\": {
        \"model_used\": \"actual model name used\",
        \"model_requested\": \"what was requested\",
        \"per_scene\": [
          {
            \"scene_id\": 1,
            \"prompt_input\": \"the exact prompt text sent to the image model\",
            \"negative_prompt\": \"if any\",
            \"parameters\": {\"aspect_ratio\": \"...\", \"seed\": ..., \"other_params\": \"...\"},
            \"output_file\": \"filename.png\",
            \"comfy_prompt_id\": \"the prompt_id returned by ComfyUI\",
            \"status\": \"success or failed\",
            \"error\": \"if failed\"
          }
        ]
      },
      \"tts\": {
        \"model_used\": \"ElevenLabs eleven_v3 or none\",
        \"voice\": \"voice name used\",
        \"skipped\": true/false,
        \"per_line\": [
          {
            \"scene_id\": 1,
            \"character\": \"char name\",
            \"text_input\": \"the exact dialogue text\",
            \"voice_style\": \"description from brief\",
            \"emotion\": \"emotion tag\",
            \"parameters\": {\"speed\": ..., \"stability\": ..., \"similarity_boost\": ...},
            \"output_file\": \"filename.mp3\",
            \"comfy_prompt_id\": \"...\",
            \"status\": \"success or failed or skipped\"
          }
        ]
      },
      \"video\": {
        \"model_used\": \"actual model name\",
        \"model_requested\": \"what was requested\",
        \"fallback_reason\": \"why a different model was used, if applicable\",
        \"per_scene\": [
          {
            \"scene_id\": 1,
            \"prompt_input\": \"exact prompt sent to video model\",
            \"negative_prompt\": \"if any\",
            \"parameters\": {\"duration\": \"...\", \"mode\": \"...\", \"aspect_ratio\": \"...\", \"cfg_scale\": ...},
            \"input_image\": \"source image filename\",
            \"output_file\": \"filename.mp4\",
            \"comfy_prompt_id\": \"...\",
            \"status\": \"success or failed\"
          }
        ]
      },
      \"lip_sync\": {
        \"model_used\": \"model name or none\",
        \"skipped\": true/false,
        \"per_scene\": [
          {
            \"scene_id\": 1,
            \"input_video\": \"source video filename\",
            \"input_audio\": \"source audio filename\",
            \"output_file\": \"filename.mp4\",
            \"comfy_prompt_id\": \"...\",
            \"status\": \"success or failed or skipped\",
            \"fallback\": \"ffmpeg audio overlay if lip sync failed\"
          }
        ]
      },
      \"assembly\": {
        \"ffmpeg_commands\": [\"the actual ffmpeg commands run\"],
        \"output_files\": {\"16x9\": \"filename\", \"9x16\": \"filename\", \"thumbnail\": \"filename\"}
      }
    },
    \"characters\": [
      {
        \"id\": \"character id from brief\",
        \"description\": \"full character description from brief\",
        \"reference_image\": \"filename if generated\"
      }
    ],
    \"scene_briefs\": [
      {
        \"scene_id\": 1,
        \"beat\": \"HOOK\",
        \"visual_description\": \"full visual description from brief\",
        \"dialogue\": [{\"character\": \"...\", \"line\": \"...\", \"emotion\": \"...\"}],
        \"text_overlay\": \"...\",
        \"camera\": \"...\",
        \"duration_target\": 5,
        \"duration_actual\": 4.8
      }
    ]
  }
}

Read the comfy-dispatcher generation-log.json from ./output/scenes/${SLUG}/ for the prompt_ids and per-asset details.
Also read the brief at ./output/briefs/${SLUG}-brief.json for the scene descriptions and character info.
Include ALL errors encountered during generation and how they were resolved.

Output to ./output/$(date +%Y-%m-%d)/${SLUG}-16x9.mp4 and 9x16.
Create the thumbnails/ subdirectory too." 2>&1 | tee "./requests/${REQUEST_ID}.assembler.log"

update_status "complete" "done" "Video assembled"
echo ""
echo "[4/4] Pipeline complete!"

# Auto-copy to Desktop
DESKTOP_DIR="$HOME/Desktop/Meme Engine Outputs/$(date +%Y-%m-%d) - ${SLUG}"
OUTPUT_DIR="./output/$(date +%Y-%m-%d)"
if [ -d "$OUTPUT_DIR" ]; then
  mkdir -p "$DESKTOP_DIR"
  cp -R "$OUTPUT_DIR"/* "$DESKTOP_DIR"/ 2>/dev/null
  echo "Copied to: $DESKTOP_DIR"
fi

echo "Output: $OUTPUT_DIR"
