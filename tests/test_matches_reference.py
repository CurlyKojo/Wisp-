"""Wisp must look like the asset pack says he looks.

The pack ships finished 800x480 PNGs. The renderer rebuilds those frames from
the geometry source as separate layers, so this checks the rebuild still lands
on the original artwork -- it's what stops a "small" layer change quietly
redrawing the character.
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_DIR = os.path.join(ROOT, "assets", "png", "screen-800x480")


def _diff(state, face, screen):
    face.draw_rest(screen, state)
    got = np.frombuffer(
        pygame.image.tostring(screen, "RGB"), dtype=np.uint8
    ).reshape(480, 800, 3).astype(int)
    ref = np.asarray(
        Image.open(os.path.join(REF_DIR, f"{state}.png")).convert("RGB")
    ).astype(int)
    return np.abs(ref - got)


def test_every_state_matches_its_reference_render():
    pygame.init()
    screen = pygame.display.set_mode((800, 480))
    face = WispFace()
    for state in geo.STATE_NAMES:
        d = _diff(state, face, screen)
        assert d.mean() < 0.15, f"{state}: mean error {d.mean():.3f}/255"


def test_body_and_face_are_pixel_exact():
    """Everything except the sleepy z's should be indistinguishable.

    The z's are the one deliberate deviation: the source file draws them with
    an SVG <text> element in IBM Plex Mono, and this renderer strokes them as
    a path instead so the Pi doesn't need fonts installed. Same size, same
    place, a hair different in the antialiasing.
    """
    pygame.init()
    screen = pygame.display.set_mode((800, 480))
    face = WispFace()
    for state in geo.STATE_NAMES:
        d = _diff(state, face, screen)
        if state == "sleepy":
            # Check the character itself, ignoring the z's up in the corner.
            d = d[:, :470]
        assert d.max() <= 4, f"{state}: max channel error {d.max()}"


def test_background_is_the_ink_colour():
    pygame.init()
    screen = pygame.display.set_mode((800, 480))
    WispFace().draw_rest(screen, "idle")
    assert screen.get_at((5, 5))[:3] == geo.palette.INK_RGB


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL  {name}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
