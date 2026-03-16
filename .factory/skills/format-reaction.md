---
name: format-reaction
description: Reaction video format rules for meme-scout scene planning
invoke: manual
---

## Reaction Video Format (15-45 seconds)

### Structure
- **SOURCE** (0-5s): Show the thing being reacted to (image or short clip)
- **REACTION** (5-30s): Character reacts. Exaggerated emotion. 2-3 escalating reactions.
- **PUNCHLINE** (30-45s): Final over-the-top reaction or commentary

### Layout
Split screen or picture-in-picture:
- Main content: 70% of frame
- Reactor: 30% inset (bottom-right or side-by-side)

### Scene Count
2-4 scenes. Source material + reaction shots.

### Character Rules
- 1 reactor character (consistent across all reaction shots)
- Reactor must have expressive, exaggerated features
- Each reaction shot increases in intensity

### Audio
- Source audio (if any) plays during SOURCE
- Reactor makes sounds/commentary during REACTION
- Trending sound or meme music sting on punchline

### Generation Requirements
- character_consistency: true (reactor must look same across shots)
- lip_sync_needed: true if reactor speaks, false if just expressions
- Preferred image model: Flux Kontext (consistent reactor)
- Preferred video model: Kling (good facial expressions)
- Assembly note: assembler handles split-screen compositing via ffmpeg
