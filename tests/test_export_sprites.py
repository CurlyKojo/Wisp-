"""Sprite sheets have to loop. Anything else shows up as a hitch in the app."""

import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
import pygame  # noqa: E402

import export_sprites as ex  # noqa: E402
from wisp_face import animation as anim  # noqa: E402
from wisp_face import geometry as geo  # noqa: E402

FPS = 10


def _init():
    if not pygame.display.get_init():
        pygame.init()
        pygame.display.set_mode((8, 8))


def _arr(img):
    return np.asarray(img.convert("RGB")).astype(int)


def test_loop_covers_a_whole_number_of_every_cycle():
    """A loop that isn't a whole number of cycles jumps on every repeat."""
    for state in geo.STATE_NAMES:
        loop, float_period = ex.loop_plan(state)
        for period in (float_period,) + tuple(ex.STATE_CYCLES.get(state, ())):
            n = loop / period
            assert abs(n - round(n)) < 1e-6, (state, period, loop)


def test_float_period_is_never_stretched_far():
    """Closing the loop must not visibly change the float's speed."""
    for state in geo.STATE_NAMES:
        _, float_period = ex.loop_plan(state)
        base = (anim.FLOAT_PERIOD_SLEEPY_S if state == "sleepy"
                else anim.FLOAT_PERIOD_S)
        assert abs(float_period - base) / base < 0.10, (state, float_period)


def test_loops_stay_a_reasonable_length():
    for state in geo.STATE_NAMES:
        assert 1.0 <= ex.loop_length(state) <= 6.0, state


def test_every_sheet_loops_seamlessly():
    """Last frame must hand over to the first without a jump."""
    _init()
    for state in geo.STATE_NAMES:
        frames = ex.render_frames(state, FPS, 0.5, transparent=False)
        assert len(frames) > 1, state
        first, last = _arr(frames[0]), _arr(frames[-1])
        # Frame-to-frame change inside the loop sets the scale for "smooth".
        steps = [np.abs(_arr(a) - _arr(b)).mean()
                 for a, b in zip(frames, frames[1:])]
        typical = max(np.mean(steps), 0.01)
        wrap = np.abs(last - first).mean()
        assert wrap < typical * 4.0, (
            f"{state}: wrap-around jump {wrap:.3f} vs typical step {typical:.3f}"
        )


def test_blink_is_not_baked_into_the_sheets():
    """Blink is random every 4-6 s; a short loop would make it a tic."""
    _init()
    frames = ex.render_frames("idle", 30, 0.5, transparent=False)
    heights = []
    for f in frames:
        a = _arr(f)
        # Count dark eye pixels in the eye band.
        band = a[130:190, 180:260]
        heights.append(int((band.sum(2) < 120).sum()))
    assert max(heights) - min(heights) < max(1, max(heights) * 0.2), \
        "the eyes change shape across an idle loop -- a blink got baked in"


def test_transparent_export_has_no_background():
    _init()
    frames = ex.render_frames("idle", 4, 0.5, transparent=True)
    assert frames[0].mode == "RGBA"
    alpha = np.asarray(frames[0])[:, :, 3]
    assert alpha[2, 2] == 0, "corner should be fully transparent"
    assert alpha.max() == 255, "nothing was drawn"


def test_sheet_and_manifest_are_written():
    _init()
    with tempfile.TemporaryDirectory() as d:
        rc = ex.main(["--out", d, "--states", "idle", "--fps", "5",
                      "--scale", "0.5", "--no-gif"])
        assert rc == 0
        assert os.path.exists(os.path.join(d, "wisp-idle.png"))
        import json
        with open(os.path.join(d, "sprites.json")) as f:
            man = json.load(f)
        entry = man["states"][0]
        assert entry["state"] == "idle"
        assert entry["frames"] == len(
            ex.render_frames("idle", 5, 0.5, transparent=False)
        )
        assert entry["grid"][0] * entry["grid"][1] >= entry["frames"]


def test_speaking_mouth_envelope_loops():
    vals = [ex.mouth_envelope(i / 60.0) for i in range(60)]
    assert min(vals) < 0.05 and max(vals) > 0.95
    assert abs(ex.mouth_envelope(0.0) - ex.mouth_envelope(0.6)) < 1e-9


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
