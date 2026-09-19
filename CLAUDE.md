# Wisp — Animation Build

## What this is
Wisp is my AI companion character. It's a glowing teal flame with two eyes. The design is final. Everything visual is in this folder. **Your job is to make it move.**

It runs on my BMO build: Raspberry Pi 5 (16GB), 5" DSI touchscreen at 800x480, running an offline voice assistant (wake word -> STT -> local LLM -> TTS). The face needs to react to what the assistant is doing.

## Source of truth
- `source/wisp_geometry.py` has the exact SVG geometry for the body, eyes, flicker, halo, all 6 expressions, and the turnaround. **Use this, don't redraw Wisp.**
- `png/` and `svg/` are static reference renders. Match them.
- `README.md` has the palette, the state table, and the motion spec.

## Main thing: animate from layers, not baked frames
The PNGs have the eyes baked in, so you can't blink with them. Split Wisp into layers from the geometry file (halo, body, side flicker, eyes, mouth, extras like sound rings and z's). Pre-render each layer once at startup, then animate transforms and alpha every frame.

## Build this, in this order

1. **Desktop preview mode first.** Run it windowed on my Mac so I can iterate without the Pi. Keys 1-6 switch states. `M` fakes TTS mouth movement.
2. **The face renderer** (`wisp_face/`), using pygame:
   - 800x480 fullscreen on the Pi, 30 fps
   - States: idle, listening, thinking, speaking, happy, sleepy
   - `face.set_state("listening")` switches states with a ~200 ms eased transition. No hard cuts.
   - `face.set_mouth_level(0.0-1.0)` drives the mouth from TTS volume
3. **Motion spec. Hit these exactly:**
   - Float: 6 px up/down, 3 s ease-in-out loop (every state)
   - Blink: every 4-6 s (randomize), eyes closed 120 ms (scale eyes Y to ~0.1, don't swap images)
   - Tip flicker: side ember drifts +/-3 px, 1.2 s loop
   - Listening: glow pulses 100% -> 130%, sound rings fade out every 0.8 s
   - Thinking: 3 dots light bottom to top, 0.4 s each, loop
   - Speaking: mouth open/close from `set_mouth_level`
   - Happy: quick 1-bounce squash and stretch on entry, then idle float
   - Sleepy: body at 60% brightness, float slows to 5 s, z's drift up and fade
4. **Hook it into the assistant.** The voice stack is based on the open-source `brenpoly/be-more-agent` repo. Read that code, find where it changes state (wake word, listening, generating, speaking), and call `set_state` there. **Don't guess the API. Read the repo first** and tell me where you're hooking in before editing it.
5. **Round display renderer** for the 1.28" GC9A01 (240x240, SPI). Eyes-only mode, same blink and state logic. Check which Python driver actually supports GC9A01 on the Pi 5 before picking one.
6. **Sprite sheet exporter** (`export_sprites.py`): renders each state as a looping PNG sprite sheet plus a GIF preview, for the iPhone app later.

## Constraints
- Must run well on a Pi 5. Target 30 fps, under ~15% of one CPU core. Pre-render everything you can.
- Fully offline. No network calls.
- Keep dependencies small: pygame, cairosvg, Pillow. Ask before adding anything else.
- Colors come from the README palette only.

## Done means
- Preview mode runs on Mac, all 6 states look right and match the static renders
- Runs fullscreen on the Pi at 30 fps
- Wisp reacts live to a real voice interaction
- A short README section on how to run it and how to add a new state
