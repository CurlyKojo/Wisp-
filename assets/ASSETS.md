# Wisp — Asset Pack v1

A small light that knows your stuff. Wake word: "Hey Wisp".

## What's in here

- `svg/wisp.svg` — master character (idle), transparent background, 200x240 viewBox
- `svg/expressions/` — all 6 states as SVG
- `svg/turnaround/` — front, three-quarter, side, back
- `svg/eyes-only.svg`, `svg/eyes-blink.svg` — for the 1.28" round GC9A01 display
- `svg/app-icon.svg` — square, no rounding (iOS rounds it for you)
- `png/screen-800x480/` — drop-in face frames for the BMO 5" screen
- `png/transparent/` — 1000x1200 renders for docs, stickers, slides
- `png/round-240/` — 240x240 frames for the round LCD
- `png/app-icon/` — 1024 (App Store) and 180 (home screen)

## States -> voice pipeline

| State | Trigger |
|---|---|
| idle | default |
| listening | wake word detected / button press |
| thinking | STT done, LLM generating |
| speaking | TTS playing (drive mouth open/closed from audio volume) |
| happy | task done, timer finished, macro goal hit |
| sleepy | no input for 10+ min, or night mode |

## Palette

| Name | Hex | Use |
|---|---|---|
| Ink | #0E1320 | background, eyes |
| Dusk | #161D2E | cards, surfaces |
| Glow | #7FE3D6 | the light, main color |
| Core | #F4FFFD | hot center, highlights |
| Deep teal | #1F8F86 | body edge |
| Ember | #FFB86B | success moments only |

## Fonts

- Display: Bricolage Grotesque
- Body: IBM Plex Sans
- System / status text: IBM Plex Mono

## Motion spec

- Float: 6 px up and down, 3 s ease-in-out loop
- Blink: every 4-6 s (randomize), 120 ms eyes closed
- Tip flicker: the side ember drifts +/- 3 px, 1.2 s loop
- Listening: glow pulses 100% -> 130%, sound rings fade out every 0.8 s
- Thinking: dots light up bottom to top, 0.4 s each, loop
- Sleepy: body at 60% brightness, float slows to 5 s
