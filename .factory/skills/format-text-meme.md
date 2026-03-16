---
name: format-text-meme
description: Text meme clip format rules for meme-scout scene planning
invoke: manual
---

## Text Meme Clip Format (5-15 seconds)

### Structure
- **Single visual** with text overlay
- Optional: slight camera motion (slow zoom or pan)
- Optional: reveal/transition (text appears beat by beat)

### Scene Count
1 scene. That's the whole point — dead simple.

### Visual Rules
- The image IS the joke setup, the text IS the punchline (or vice versa)
- High contrast between text and background
- Image should be absurd, surreal, or hyperspecific
- No characters needed (but can use one)

### Text Rules
- Top text: setup (optional, max 10 words)
- Bottom text: punchline (max 8 words)
- Bold, white, black outline — the classic meme font style
- Text must be readable at phone size

### Audio
- Background music loop (trending sound or classic meme music)
- No dialogue, no SFX needed

### Generation Requirements
- character_consistency: false
- lip_sync_needed: false
- Preferred image model: Ideogram V3 (best text rendering) or Flux
- Video: just a still image converted to video with slight motion via ffmpeg
