#!/usr/bin/env python3
"""Export each state as a looping sprite sheet plus a GIF preview.

For the iPhone app: every state becomes one PNG strip of frames and one GIF
you can actually look at.

    python export_sprites.py                    # all six states, 2x, to export/
    python export_sprites.py --scale 1 --fps 24
    python export_sprites.py --states idle happy --transparent

Loop lengths come from the motion spec, so each sheet cycles seamlessly: a
state's sheet covers the least common multiple of whatever is moving in it
(the 3 s float, the 0.8 s listening pulse, the 1.2 s thinking dots, and so on).
Blink is left out on purpose -- it's random and every 4-6 s, so baking it into
a short loop would make Wisp twitch on a timer.
"""

import argparse
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402
from PIL import Image  # noqa: E402

from wisp_face import animation as anim  # noqa: E402
from wisp_face import geometry as geo  # noqa: E402
from wisp_face.face import WispFace  # noqa: E402
from wisp_face.layers import Layout  # noqa: E402

# What actually cycles in each state, in seconds. The sheet runs for the least
# common multiple of these and the float, so the last frame joins the first.
STATE_CYCLES = {
    "idle": (),
    "listening": (anim.LISTEN_PULSE_PERIOD_S, anim.RING_PERIOD_S),
    "thinking": (anim.DOT_STEP_S * len(anim.DOT_ORDER),),
    "speaking": (0.6,),        # one mouth cycle of the canned speech envelope
    "happy": (),
    "sleepy": (anim.Z_PERIOD_S,),
}


def _lcm_seconds(periods):
    """Least common multiple of a set of periods, worked in whole ms."""
    out = None
    for p in periods:
        if p <= 0:
            continue
        b = int(round(p * 1000))
        out = b if out is None else (out * b // math.gcd(out, b))
    return (out or 0) / 1000.0


def loop_plan(state, limit=6.0):
    """Pick a loop length for this state, and the float period that closes it.

    Returns ``(seconds, float_period)``.

    Ideally the loop is the least common multiple of everything moving, and
    the float runs at its spec period. For two states that LCM is impractical
    -- listening wants lcm(3 s float, 0.8 s pulse) = 12 s, sleepy wants
    lcm(5 s, 2.4 s) = 60 s. Rather than truncate (which silently produces a
    sheet that doesn't loop), keep the state's own cycles exact and stretch
    the float by a few percent so it closes at the same instant. A 3.0 s float
    becoming 3.2 s is invisible; a sheet that jumps on every repeat is not.
    """
    base = (anim.FLOAT_PERIOD_SLEEPY_S if state == "sleepy"
            else anim.FLOAT_PERIOD_S)
    extras = STATE_CYCLES.get(state, ())
    exact = _lcm_seconds(tuple(extras) + (base,))
    if exact and exact <= limit + 1e-9:
        return exact, base

    step = _lcm_seconds(extras) or base
    best = None
    k = 1
    while step * k <= limit + 1e-9:
        length = step * k
        turns = max(1, round(length / base))
        period = length / turns
        err = abs(period - base) / base
        if best is None or err < best[2] - 1e-12:
            best = (length, period, err)
        k += 1
    if best is None:
        return min(step, limit), base
    return best[0], best[1]


def loop_length(state):
    """Seconds one seamless cycle of this state takes."""
    return loop_plan(state)[0]


def mouth_envelope(t, period=0.6):
    """A tidy, loopable mouth cycle for the speaking sheet."""
    return max(0.0, math.sin(t / period * 2.0 * math.pi)) ** 0.7


def render_frames(state, fps, scale, transparent, cache_dir=None, crop=False):
    """Render one full loop of a state. Returns a list of PIL images.

    ``crop`` trims every frame to the character's bounding box rather than the
    whole 800x480 screen. Same animation, much less empty background -- worth
    it for sheets that get scaled up in a UI.
    """
    layout = Layout(width=int(800 * scale), height=int(480 * scale))
    layout.scale = 1.5 * scale
    layout.origin = (250.0 * scale, 48.0 * scale)

    seconds, float_period = loop_plan(state)
    face = WispFace(
        layout=layout,
        cache_dir=cache_dir,
        initial_state=state,
        background=None if transparent else geo.palette.INK_RGB,
        float_period=float_period,
    )
    # A sprite sheet is a fixed loop, so the random blink stays out of it.
    face.motion._blink_at = float("inf")

    count = max(1, int(round(seconds * fps)))
    dt = seconds / count

    # Happy opens with a one-shot squash. Baked into a loop that would hitch
    # on every repeat, so settle past it first -- the bounce is a live-entry
    # flourish, not part of the cycle.
    if state == "happy":
        settle = 0.0
        while settle < anim.HAPPY_BOUNCE_S:
            face.update(dt)
            settle += dt

    box = None
    if crop:
        r = face.content_rect
        box = (r.left, r.top, r.right, r.bottom)

    flags = pygame.SRCALPHA if transparent else 0
    canvas = pygame.Surface(layout.size, flags)
    frames = []
    for i in range(count):
        if transparent:
            canvas.fill((0, 0, 0, 0))
        if state == "speaking":
            face.set_mouth_level(mouth_envelope(i * dt))
        face.update(dt)
        face.draw(canvas)
        mode = "RGBA" if transparent else "RGB"
        img = Image.frombytes(
            mode, layout.size, pygame.image.tostring(canvas, mode)
        )
        if box is not None:
            img = img.crop(box)
        frames.append(img)
    return frames


def write_sheet(frames, path, columns=None, quality=88):
    """Lay frames out in a grid and save one sheet.

    Format comes from the extension. WebP is a lot kinder to Wisp's gradients
    than PNG -- the listening sheet, whose halo changes on every frame, goes
    from 1.5 MB to a fraction of that.
    """
    w, h = frames[0].size
    columns = columns or min(len(frames), 8)
    rows = math.ceil(len(frames) / columns)
    mode = frames[0].mode
    sheet = Image.new(mode, (w * columns, h * rows),
                      (0, 0, 0, 0) if mode == "RGBA" else (0, 0, 0))
    for i, frame in enumerate(frames):
        sheet.paste(frame, ((i % columns) * w, (i // columns) * h))
    if path.lower().endswith(".webp"):
        sheet.save(path, quality=quality, method=6)
    else:
        sheet.save(path)
    return sheet.size, (columns, rows)


def write_gif(frames, path, fps):
    duration = int(round(1000.0 / fps))
    first, rest = frames[0], frames[1:]
    kwargs = {}
    if first.mode == "RGBA":
        # GIF can't do partial alpha; flatten onto Ink so the preview looks
        # like the screen rather than a checkerboard.
        bg = Image.new("RGBA", first.size, geo.palette.INK_RGB + (255,))
        first = Image.alpha_composite(bg, first).convert("RGB")
        rest = [Image.alpha_composite(bg, f).convert("RGB") for f in rest]
    first.save(path, save_all=True, append_images=rest, loop=0,
               duration=duration, optimize=True, **kwargs)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="export", help="output directory")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--scale", type=float, default=2.0,
                    help="1 = 800x480, 2 = 1600x960 (default)")
    ap.add_argument("--states", nargs="+", default=list(geo.STATE_NAMES),
                    choices=list(geo.STATE_NAMES))
    ap.add_argument("--columns", type=int, default=None,
                    help="frames per sheet row (default: up to 8)")
    ap.add_argument("--transparent", action="store_true",
                    help="no background, for compositing in the app")
    ap.add_argument("--crop", action="store_true",
                    help="trim frames to the character instead of the whole screen")
    ap.add_argument("--format", default="png", choices=["png", "webp"],
                    help="sheet format; webp is much smaller for the gradients")
    ap.add_argument("--quality", type=int, default=88,
                    help="webp quality (ignored for png)")
    ap.add_argument("--no-gif", dest="gif", action="store_false", default=True)
    ap.add_argument("--cache-dir", default=None)
    args = ap.parse_args(argv)

    pygame.init()
    pygame.display.set_mode((8, 8))
    os.makedirs(args.out, exist_ok=True)

    manifest = []
    for state in args.states:
        frames = render_frames(state, args.fps, args.scale, args.transparent,
                               cache_dir=args.cache_dir, crop=args.crop)
        sheet_path = os.path.join(args.out, f"wisp-{state}.{args.format}")
        size, grid = write_sheet(frames, sheet_path, args.columns, args.quality)
        line = (f"{state:10s} {len(frames):3d} frames  "
                f"{frames[0].size[0]}x{frames[0].size[1]}  "
                f"grid {grid[0]}x{grid[1]}  sheet {size[0]}x{size[1]}  "
                f"loop {loop_length(state):.1f}s")
        if args.gif:
            write_gif(frames, os.path.join(args.out, f"wisp-{state}.gif"),
                      args.fps)
            line += "  +gif"
        print(line, flush=True)
        manifest.append({
            "state": state,
            "sheet": os.path.basename(sheet_path),
            "frames": len(frames),
            "frame_size": list(frames[0].size),
            "grid": list(grid),
            "fps": args.fps,
            "loop_seconds": round(loop_length(state), 3),
        })

    import json
    with open(os.path.join(args.out, "sprites.json"), "w") as f:
        json.dump({"fps": args.fps, "states": manifest}, f, indent=2)
    print(f"\nWrote {len(manifest)} states to {args.out}/ "
          f"(+ sprites.json for the app)")
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
