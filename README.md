# Wisp

A small light that knows your stuff. This repo makes it move.

![Wisp cycling through all six states](docs/demo.gif)

Wisp is the face for a Raspberry Pi 5 voice assistant: a glowing teal flame
with two eyes, six states, running fullscreen on a 5" 800x480 DSI panel at
30 fps. The character design is finished and lives in `assets/` — everything
here is animation.

```
python run_face.py                    # windowed preview
python run_face.py --fullscreen       # how it runs on the Pi
```

| key | |
|---|---|
| `1`–`6` | idle / listening / thinking / speaking / happy / sleepy |
| `M` | fake TTS mouth movement |
| `B` | force a blink |
| `H` | HUD |
| `F` | fullscreen |
| `Q` | quit |

## Install

```bash
pip install -r requirements.txt
```

Three dependencies: pygame, cairosvg (startup only), Pillow (sprite export
only). On Raspberry Pi OS you may also need `sudo apt install libcairo2`.

## How it works

The asset pack ships finished PNG frames, but **the eyes are baked into the
body**, so you can't blink with them. Instead Wisp is split into layers built
from `assets/source/wisp_geometry.py` — the character is never redrawn, just
re-composed:

```
halo → body → tip flicker → eyes → mouth → extras (rings, dots, z's, brows, blush)
```

Each layer is rasterised **once at startup**, cropped to its opaque bounding
box, and cached to disk. The per-frame path is a fill and about eight blits of
pre-rendered surfaces. Anything that would need re-rasterising — the nine blink
steps, seventeen mouth openings, thirteen halo pulse sizes — is pre-computed
too.

Measured on a dev box: **0.44 ms/frame** steady state, 3.3 ms while
cross-fading. Startup is 0.74 s cold, and near-instant once the disk cache is
warm.

### It still matches the artwork

`tests/test_matches_reference.py` composites each state and diffs it against
the pack's own `png/screen-800x480/*.png`. Five of six states come back with a
**max channel error of 2** — antialiasing noise, nothing more.

The sixth is sleepy, and the difference is deliberate: the source file draws
the z's with an SVG `<text>` element in IBM Plex Mono. This renderer strokes
them as a path instead, so the Pi doesn't need fonts installed. Same size, same
position, slightly different edges.

The layout (scale 1.5, origin 250,48) was fitted to those renders rather than
guessed — see `tools/calibrate_layout.py`.

## The motion spec

Every number in `wisp_face/animation.py` is quoted from the pack's README, and
`tests/test_motion_spec.py` asserts it:

| | |
|---|---|
| Float | 6 px up and down, 3 s ease-in-out loop |
| Blink | every 4–6 s (randomised), 120 ms, eyes scaled to 0.1 — never an image swap |
| Tip flicker | ±3 px, 1.2 s loop |
| Listening | glow pulses 100% → 130%, rings fade out every 0.8 s |
| Thinking | 3 dots light bottom to top, 0.4 s each |
| Speaking | mouth driven by `set_mouth_level()` |
| Happy | one squash-and-stretch bounce on entry, then idle float |
| Sleepy | dimmer palette, float slows to 5 s, z's drift up and fade |
| Transitions | ~200 ms eased cross-fade, no hard cuts |

Two notes on judgement calls:

- **"Body at 60% brightness" for sleepy** is already in the source file's sleepy
  palette — its channels land at ~0.6× the waking ones, which is why the static
  sleepy render is dimmer. Nothing is dimmed on top of it.
- **The cross-fade** puts the outgoing frame down opaque and fades only the
  incoming one in. Fading both at `(1-t)` and `t` leaves `(1-t)·t` of the
  background showing through — a visible grey dip halfway through every switch.
  Layers the incoming state doesn't draw at all (rings, dots) are faded out
  individually so they don't pop at the end.

## Using it

```python
from wisp_face.face import WispFace

face = WispFace()
face.set_state("listening")      # cross-fades over ~200 ms
face.set_mouth_level(0.7)        # 0..1, drive from TTS volume
face.render(screen, dt)
```

## Wiring it to the voice assistant

See **[`integration/README.md`](integration/README.md)** — where the hooks go in
`brenpoly/be-more-agent`, why the face runs as its own process, and how the
seven `BotStates` map onto Wisp's six.

```bash
python run_face.py --fullscreen --socket &
python agent.py                  # patched; see integration/
```

## The round display

The 1.28" GC9A01 runs eyes-only off the same clock, so both screens blink
together. The driver situation on a Pi 5 is a minefield (`luma.lcd` doesn't
support GC9A01; anything on `RPi.GPIO` can't work on a Pi 5 at all) — the
answer is the kernel `gc9a01` overlay and a plain framebuffer write, which
needs no extra dependency. Setup: **[`docs/round-display.md`](docs/round-display.md)**.

```bash
python -m wisp_face.round_face --socket
```

## Sprite sheets

```bash
python export_sprites.py                      # 2x PNG sheets + GIFs to export/
python export_sprites.py --transparent --scale 1
```

Each sheet is a genuine loop: the length is the least common multiple of
everything moving in that state. Two states can't fit that in a sensible sheet
(listening wants 12 s, sleepy 60 s), so their float is stretched by 4–7% to
close the loop instead — invisible, where a sheet that jumps every repeat is
not. Blink is left out: it's random every 4–6 s, and baking it into a 3 s loop
would turn it into a tic. `sprites.json` carries the grid and frame counts.

## Adding a new state

1. **Describe it** in `STATES` in `wisp_face/geometry.py` — halo colour and
   opacity, body gradient, flicker colour, eye geometry, and which extras it
   draws. Use the primitives already there (`eyes_svg`, `mouth_svg`, `EXTRAS`)
   rather than new paths, so it stays the same character.
2. **Add any new extra** to `EXTRAS` and give it a resting opacity in
   `EXTRA_BASE_ALPHA`.
3. **Animate it** in `Motion.params()` in `wisp_face/animation.py`: add a branch
   that fills `extra_alpha` / `extra_offset`, with the timings as named
   constants at the top of the file.
4. **Add it to `STATE_NAMES`**, and to `ROUND_STATES` in `round_face.py` if it
   should appear on the round display.
5. **Give it a key** in `STATE_KEYS` in `wisp_face/app.py`.
6. **Say how it loops** in `STATE_CYCLES` in `export_sprites.py` — list the
   period of anything cyclic you added.

If it's a face layer that should deform with the happy squash, add its name to
`_FACE_EXTRAS` in `face.py`.

Then `python tests/run_all.py`. The reference-match test only covers the six
shipped states, so a new one won't break it — but the motion tests will catch a
timing constant that doesn't do what it claims.

## Tests

```bash
python tests/run_all.py
```

60 tests: the motion spec as assertions, the reference-render match, the
agent↔face link end to end (real sockets, no mocks), the round display, and
sprite-sheet seamlessness.

## Layout

```
wisp_face/
  geometry.py     states as layer data, built on assets/source/wisp_geometry.py
  render.py       SVG → cropped pygame surfaces, disk-cached
  layers.py       per-state surfaces + pre-computed variants
  animation.py    the motion spec as constants; emits per-frame params
  face.py         the 800x480 renderer
  round_face.py   240x240 eyes-only + framebuffer writer
  app.py          run loop, preview keys, IPC server
  ipc.py          stdlib-only duplex link to the assistant
integration/      patch + bridge for be-more-agent
tools/            layout calibration against the reference renders
assets/           the asset pack, unmodified
```
