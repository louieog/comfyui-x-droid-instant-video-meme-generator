#!/bin/bash
set -euo pipefail

ENGINE_DIR="$HOME/.meme-engine"
DATE=$(date +%Y-%m-%d)
OUTPUT_DIR="$ENGINE_DIR/output/$DATE"
LOG_FILE="$ENGINE_DIR/output/$DATE-run.log"

mkdir -p "$OUTPUT_DIR"

echo "[$DATE] Starting daily meme engine run..." | tee "$LOG_FILE"

# Run as a Mission via droid exec
droid exec --auto high --cwd "$ENGINE_DIR" \
  "Run /enter-mission to generate today's 2 viral meme videos.

Mission plan:
1. Use the meme-scout subagent to research trends, cross-reference with seed-list.json, and produce 2 production briefs. Auto-select top 2 concepts.
2. Use the workflow-builder subagent to create/verify ComfyUI workflow templates for each brief.
3. Use the comfy-dispatcher subagent to execute workflows on ComfyUI Cloud and download all scene assets.
4. Use the assembler subagent to produce final videos in 9:16 and 16:9 formats.

Save all output to ./output/$DATE/
Log generation details to ./output/$DATE/generation-log.json" \
  2>&1 | tee -a "$LOG_FILE"

echo "[$DATE] Daily run complete. Output: $OUTPUT_DIR" | tee -a "$LOG_FILE"
