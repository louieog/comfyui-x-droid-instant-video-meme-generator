---
name: content-request
description: Handles custom meme video requests from chat or watched folder, structures them into production briefs
invoke: auto
---

Activate when the user requests a meme video, content generation, or mentions making a video/meme/clip in chat.

## From Chat
When the user describes a video they want:
1. Extract: concept, format preference (if any), style (if any), duration preference, constraints
2. If format not specified, recommend one based on the concept:
   - Dialogue-heavy or character-driven → mini-drama
   - Single joke or punchline → text-meme
   - Commentary on existing content → reaction
3. Confirm the plan with the user, then invoke the meme-scout droid with the request to produce a full production brief
4. Once the brief is ready, start a Mission with 3 milestones:
   - Milestone 1: workflow-builder creates/verifies templates
   - Milestone 2: comfy-dispatcher generates all scene assets
   - Milestone 3: assembler produces final videos

## From Watched Folder
When processing a JSON file from ./requests/:
1. Validate the JSON has at minimum: concept, format
2. Pass it to meme-scout to expand into a full production brief
3. Execute the same 3-milestone pipeline

## User Interaction
- Show the production brief summary before starting generation
- Report progress after each milestone
- On completion, report output file paths and total generation time
