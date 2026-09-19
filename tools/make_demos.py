#!/usr/bin/env python3
"""Render the demo GIFs in docs/.

    python tools/make_demos.py

Three things:

* ``docs/demo.gif``        a scripted tour of all six states, with transitions
* ``docs/demo-round.gif``  the same tour on the 1.28" round display
* ``docs/states/*.gif``    one seamless loop per state

The per-state loops come from ``export_sprites.render_frames``, so what you see
here is exactly what the sprite sheets contain -- if a loop hitches in the GIF,
it hitches in the app.
"""

import argparse
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402
from PIL import Image  # noqa: E402

import export_sprites as ex  # noqa: E402
from wisp_face import geometry as geo  # noqa: E402
from wisp_face.app import fake_speech_level  # noqa: E402
from wisp_face.face import WispFace  # noqa: E402
from wisp_face.round_face import RoundFace  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")

# The tour, as (state, seconds, drive_the_mouth).
TOUR = [
    ("idle", 2.0, False),
    ("listening", 2.2, False),
    ("thinking", 2.4, False),
    ("speaking", 3.0, True),
    ("happy", 2.0, False),
    ("sleepy", 3.0, False),
    ("idle", 1.5, False),
]


def save_gif(frames, path, fps):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frames[0].save(path, save_all=True, append_images=frames[1:], loop=0,
                   duration=int(round(1000.0 / fps)), optimize=True)
    return os.path.getsize(path)


def grab(surface, size, out_size):
    img = Image.frombytes("RGB", size, pygame.image.tostring(surface, "RGB"))
    return img.resize(out_size, Image.LANCZOS) if out_size != size else img


def tour(face, surface, size, out_size, fps):
    """Walk the six states, letting each transition play."""
    dt = 1.0 / fps
    frames = []
    for state, seconds, talking in TOUR:
        face.set_state(state)
        t = 0.0
        for _ in range(int(seconds * fps)):
            face.set_mouth_level(fake_speech_level(t) if talking else 0.0)
            face.render(surface, dt)
            frames.append(grab(surface, size, out_size))
            t += dt
    return frames


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--width", type=int, default=480,
                    help="width of the big-screen GIFs (aspect kept)")
    ap.add_argument("--out", default=DOCS)
    args = ap.parse_args(argv)

    pygame.init()
    pygame.display.set_mode((800, 480))
    big = (args.width, round(args.width * 480 / 800))
    total = 0

    # 1. the tour
    face = WispFace()
    screen = pygame.Surface((800, 480))
    size = save_gif(tour(face, screen, (800, 480), big, args.fps),
                    os.path.join(args.out, "demo.gif"), args.fps)
    print(f"  demo.gif             {big[0]}x{big[1]}  {size // 1024:5d} KB")
    total += size

    # 2. the same tour on the round display
    rface = RoundFace()
    rsurf = pygame.Surface((rface.size, rface.size))
    size = save_gif(
        tour(rface, rsurf, (rface.size, rface.size), (rface.size, rface.size),
             args.fps),
        os.path.join(args.out, "demo-round.gif"), args.fps)
    print(f"  demo-round.gif       240x240  {size // 1024:5d} KB")
    total += size

    # 3. one seamless loop per state, straight from the sprite exporter
    for state in geo.STATE_NAMES:
        frames = ex.render_frames(state, args.fps, 1.0, transparent=False)
        frames = [f.resize(big, Image.LANCZOS) for f in frames]
        path = os.path.join(args.out, "states", f"{state}.gif")
        size = save_gif(frames, path, args.fps)
        print(f"  states/{state + '.gif':17s} {len(frames):3d} frames  "
              f"{size // 1024:5d} KB  loop {ex.loop_length(state):.1f}s")
        total += size

    print(f"\n  {total // 1024} KB total")
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
