"""Round display: artwork, blink, and the framebuffer write path."""

import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
import pygame  # noqa: E402
from PIL import Image  # noqa: E402

from wisp_face import geometry as geo  # noqa: E402
from wisp_face.face import WispFace  # noqa: E402
from wisp_face.round_face import ROUND_STATES, Framebuffer, RoundFace  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _init():
    if not pygame.display.get_init():
        pygame.init()
        pygame.display.set_mode((8, 8))


def _draw(face, state=None, blink=None):
    surf = pygame.Surface((face.size, face.size))
    if state:
        face.set_state(state, immediate=True)
    face.motion.float_phase = 0.0
    face.motion._blink_started = None if blink is None else face.motion.t - blink
    face.draw(surf)
    return np.frombuffer(
        pygame.image.tostring(surf, "RGB"), dtype=np.uint8
    ).reshape(face.size, face.size, 3).astype(int)


def test_open_eyes_match_the_packs_round_render():
    _init()
    got = _draw(RoundFace(), "idle")
    ref = np.asarray(Image.open(
        os.path.join(ROOT, "assets", "png", "round-240", "eyes-open.png")
    ).convert("RGB")).astype(int)
    d = np.abs(ref - got)
    assert d.mean() < 0.1, d.mean()
    assert d.max() <= 4, d.max()


def test_layers_use_the_round_viewbox():
    """A 200x200 layer drawn in the body's 200x240 box comes out 1.2x small.

    That bug is invisible in code review and obvious in a bounding box, so
    pin the box.
    """
    _init()
    face = RoundFace()
    got = _draw(face, "idle")
    bg = got[2, 2]
    mask = np.abs(got - bg).sum(2) > 30
    ys, xs = np.nonzero(mask)
    # Eyes are centred on the panel.
    assert abs((xs.min() + xs.max()) / 2 - 119.5) < 1.5
    assert abs((ys.min() + ys.max()) / 2 - 119.5) < 1.5
    # And the glow spans the panel's width the way the reference does.
    assert xs.max() - xs.min() > 150


def test_blink_closes_to_the_packs_bar_thickness():
    """eyes-blink.svg shuts the eyes to a 10-unit bar; the squash must agree."""
    assert abs(geo.ROUND_BLINK_CLOSED_SCALE * 30.0 * 2.0 - 10.0) < 1e-9
    _init()
    face = RoundFace()
    shut = face.eye_steps[0][0]
    opened = face.eye_steps[-1][0]
    assert shut.get_height() < opened.get_height() * 0.35


def test_every_state_has_round_artwork():
    assert set(ROUND_STATES) == set(geo.STATE_NAMES)
    _init()
    face = RoundFace()
    seen = {}
    for state in geo.STATE_NAMES:
        seen[state] = _draw(face, state).tobytes()
    # happy, sleepy and thinking must not all render as plain idle eyes.
    assert seen["happy"] != seen["idle"]
    assert seen["sleepy"] != seen["idle"]
    assert seen["thinking"] != seen["idle"]


def test_mirroring_keeps_both_screens_in_step():
    _init()
    big = WispFace()
    small = RoundFace(mirror=big)
    assert small.motion is big.motion
    big.set_state("thinking")
    assert small.state == "thinking"
    # Driving the round face routes back through the main one.
    small.set_state("happy", immediate=True)
    assert big.state == "happy"


def test_framebuffer_writes_rgb565():
    """Exercise the real conversion and write, against a file standing in
    for /dev/fb1."""
    _init()
    with tempfile.TemporaryDirectory() as d:
        node = os.path.join(d, "fb1")
        with open(node, "wb") as f:
            f.write(b"\0" * (240 * 240 * 2))

        # _probe is a staticmethod; restore it as one or the next test gets
        # an implicit self.
        real_probe = Framebuffer.__dict__["_probe"]
        Framebuffer._probe = staticmethod(lambda dev: (240, 240, 16))
        try:
            fb = Framebuffer(node)
            surf = pygame.Surface((240, 240))
            surf.fill(geo.palette.GLOW_RGB)
            fb.show(surf)
            fb.close()
        finally:
            Framebuffer._probe = real_probe

        raw = open(node, "rb").read()
        assert len(raw) == 240 * 240 * 2
        px = int.from_bytes(raw[:2], "little")
        r = ((px >> 11) & 0x1F) * 255 // 31
        g = ((px >> 5) & 0x3F) * 255 // 63
        b = (px & 0x1F) * 255 // 31
        want = geo.palette.GLOW_RGB
        assert all(abs(a - c) <= 8 for a, c in zip((r, g, b), want)), (r, g, b)


def test_framebuffer_rejects_a_non_16bpp_panel():
    real_probe = Framebuffer.__dict__["_probe"]
    Framebuffer._probe = staticmethod(lambda dev: (240, 240, 32))
    try:
        Framebuffer("/dev/null")
    except RuntimeError as exc:
        assert "16bpp" in str(exc)
        return
    finally:
        Framebuffer._probe = real_probe
    raise AssertionError("accepted a 32bpp framebuffer")


def test_missing_framebuffer_says_something_useful():
    try:
        Framebuffer("/dev/fb-does-not-exist")
    except RuntimeError as exc:
        assert "gc9a01" in str(exc)
        return
    raise AssertionError("no error for a missing framebuffer")


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
