#!/bin/bash
set -euo pipefail

ENGINE_DIR="$HOME/.meme-engine"
REQUESTS_DIR="$ENGINE_DIR/requests"
PROCESSED_DIR="$ENGINE_DIR/requests/processed"

mkdir -p "$PROCESSED_DIR"

echo "Watching $REQUESTS_DIR for new request files..."

# Poll every 30 seconds for new JSON files
while true; do
  for request_file in "$REQUESTS_DIR"/*.json; do
    [ -f "$request_file" ] || continue

    filename=$(basename "$request_file")
    echo "[$(date)] Processing request: $filename"

    # Run the request through droid exec
    droid exec --auto high --cwd "$ENGINE_DIR" \
      "Process custom content request from ./requests/$filename

Read the request JSON and use the content-request workflow:
1. Use the meme-scout subagent to expand the request into a full production brief.
2. Use the workflow-builder subagent to create/verify workflow templates.
3. Use the comfy-dispatcher subagent to generate all assets via ComfyUI Cloud.
4. Use the assembler subagent to produce final videos.

Save output to ./output/custom/" \
      2>&1 | tee "$ENGINE_DIR/output/custom/$filename.log"

    # Move processed request
    mv "$request_file" "$PROCESSED_DIR/$filename"
    echo "[$(date)] Completed: $filename"
  done

  sleep 30
done
