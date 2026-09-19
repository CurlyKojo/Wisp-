"""Fit the display layout to the asset pack's own 800x480 renders.

The pack ships finished PNG frames. This sweeps scale and origin until a
freshly composited rest pose lines up with them, which is how the defaults in
Layout were chosen (scale 1.5, origin 250,48 -- a mean error of 0.03/255).
Re-run it if the artwork ever changes.

    python tools/calibrate_layout.py
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
import pygame  # noqa: E402
from PIL import Image  # noqa: E402

from wisp_face import geometry as geo  # noqa: E402
from wisp_face.face import WispFace  # noqa: E402
from wisp_face.layers import Layout  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_DIR = os.path.join(ROOT, "assets", "png", "screen-800x480")


def error(face, screen, refs):
    """Mean absolute error across every state, in 0-255 units."""
    total = 0.0
    for state, ref in refs.items():
        face.draw_rest(screen, state)
        got = np.frombuffer(
            pygame.image.tostring(screen, "RGB"), dtype=np.uint8
        ).reshape(480, 800, 3).astype(int)
        total += np.abs(ref - got).mean()
    return total / len(refs)


def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 480))
    refs = {
        s: np.asarray(
            Image.open(os.path.join(REF_DIR, f"{s}.png")).convert("RGB")
        ).astype(int)
        for s in geo.STATE_NAMES
    }

    best = None
    for scale in (1.470 + i * 0.0025 for i in range(15)):
        layout = Layout(scale=scale)
        # Rebuilding the face per scale is the slow part; origin is free.
        face = WispFace(layout=layout, use_disk_cache=False)
        for ox in (248 + i * 0.5 for i in range(10)):
            for oy in (46 + i * 0.5 for i in range(10)):
                layout.origin = (ox, oy)
                e = error(face, screen, refs)
                if best is None or e < best[0]:
                    best = (e, scale, ox, oy)
        print(f"  scale={scale:.4f}  best so far err={best[0]:.4f} "
              f"scale={best[1]:.4f} origin=({best[2]}, {best[3]})", flush=True)

    e, scale, ox, oy = best
    print(f"\nBEST  scale={scale:.4f}  origin=({ox}, {oy})  "
          f"mean abs error {e:.4f}/255\n")
    face = WispFace(layout=Layout(scale=scale, origin=(ox, oy)),
                    use_disk_cache=False)
    for state in geo.STATE_NAMES:
        print(f"  {state:10s} {error(face, screen, {state: refs[state]}):.4f}")


if __name__ == "__main__":
    main()
