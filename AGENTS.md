# Meme Engine - Agent Instructions

## Project Overview
Automated viral meme video content engine. Generates 2 videos daily in unique formats using ComfyUI Cloud for all media generation (image, video, audio, lip-sync via partner nodes).

## Architecture
4 droids in a pipeline, orchestrated by Missions:
1. **meme-scout** — trend research + creative direction → production brief
2. **workflow-builder** — discovers ComfyUI nodes, constructs workflow JSON, uploads to cloud
3. **comfy-dispatcher** — parameterizes templates, submits to ComfyUI Cloud, polls, downloads
4. **assembler** — ffmpeg post-production, multi-format export (9:16 + 16:9)

## Key Paths
- `./workflows/` — ComfyUI API-format workflow templates (JSON)
- `./requests/` — Watched folder for custom content requests (JSON)
- `./output/YYYY-MM-DD/` — Daily auto-generated outputs
- `./output/custom/` — Custom request outputs
- `./characters/` — Reusable character reference images
- `./formats/` — Format definition files
- `./seed-list.json` — Weekly curated topics/trends
- `./scripts/` — Automation scripts (cron, watchers)

## API Configuration
All API keys live in `.env` (never committed):
- `COMFY_CLOUD_API_KEY` — ComfyUI Cloud (used for both X-API-Key header and extra_data.api_key_comfy_org for partner nodes)

## ComfyUI Cloud API
- Base URL: `https://cloud.comfy.org`
- Submit workflow: `POST /api/prompt` with `{"prompt": <workflow_json>}`
- Partner nodes require: `"extra_data": {"api_key_comfy_org": "$COMFY_CLOUD_API_KEY"}`
- Poll status: `GET /api/job/{prompt_id}/status`
- Download: `GET /api/view?filename=X` (follow 302 redirect)
- Upload input: `POST /api/upload/image`
- Discover nodes: `GET /api/object_info`
- Save workflow to cloud UI: `POST /api/userdata/workflows/{name}.json`
- List workflows: `GET /api/userdata?dir=workflows`

## Production Brief Schema
Every content request (auto or custom) produces a production brief JSON with:
- `concept` — one-line description
- `format` — mini-drama | text-meme | reaction | custom
- `style` — visual/humor style
- `duration_target_seconds`
- `aspect_ratios` — ["9:16", "16:9"]
- `scenes[]` — beat, duration, visual prompt, camera, dialogue, audio, text_overlay
- `generation_requirements` — character_consistency, lip_sync_needed, preferred models

## Conventions
- All inter-droid communication uses JSON files in the project directory
- Workflow templates use ComfyUI API format (node IDs as keys)
- ffmpeg is the only local dependency for post-production
- Never commit API keys or .env files
- Output filenames: `{concept-slug}-{format}-{aspect}.mp4`

## Input Modes
1. **Daily auto** — Cron triggers `scripts/daily-run.sh` → Mission via droid exec
2. **Chat** — User types request in Droid session → content-request skill → Mission
3. **Watched folder** — Drop JSON in `./requests/` → `scripts/watch-requests.sh` → droid exec

## Testing Workflows
To test a workflow template manually:
```bash
source .env
curl -X POST "https://cloud.comfy.org/api/prompt" \
  -H "X-API-Key: $COMFY_CLOUD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": '"$(cat workflows/template.json)"', "extra_data": {"api_key_comfy_org": "'$COMFY_CLOUD_API_KEY'"}}'
```
