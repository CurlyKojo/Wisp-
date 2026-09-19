"""The motion spec, as assertions.

Every number checked here is quoted from the asset pack README. If someone
changes a constant, this is what catches it.
"""

import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from wisp_face import animation as anim  # noqa: E402
from wisp_face import geometry as geo  # noqa: E402
from wisp_face.animation import Motion  # noqa: E402
from wisp_face.face import WispFace  # noqa: E402

DT = 1.0 / 30.0


def _screen():
    if not pygame.display.get_init():
        pygame.init()
    surf = pygame.display.get_surface()
    return surf or pygame.display.set_mode((800, 480))


def _sample(seconds, state="idle", dt=DT):
    """Run the clock and yield (t, Motion) at each frame."""
    m = Motion(rng=random.Random(7))
    n = int(seconds / dt)
    for _ in range(n):
        m.tick(dt, state)
        yield m


# -- float -----------------------------------------------------------------

def test_float_amplitude_is_6px_peak():
    ys = [m.float_dy() for m in _sample(6.0)]
    assert abs(max(ys) - 6.0) < 0.1, max(ys)
    assert abs(min(ys) + 6.0) < 0.1, min(ys)


def test_float_period_is_3s():
    m = Motion(rng=random.Random(1))
    for _ in range(int(3.0 / DT)):
        m.tick(DT, "idle")
    # One full 3 s loop returns the phase to where it started.
    assert m.float_phase < 1e-9 or m.float_phase > 1.0 - 1e-9, m.float_phase


def test_sleepy_float_slows_to_5s():
    m = Motion(rng=random.Random(1))
    for _ in range(int(5.0 / DT)):
        m.tick(DT, "sleepy")
    assert m.float_phase < 1e-9 or m.float_phase > 1.0 - 1e-9, m.float_phase


def test_float_scales_with_render_scale():
    m = next(iter(_sample(0.75)))
    assert abs(m.float_dy(2.0) - 2.0 * m.float_dy(1.0)) < 1e-9


# -- blink -----------------------------------------------------------------

def test_blink_closes_fully_and_lasts_120ms():
    m = Motion(rng=random.Random(3))
    m.blink_now()
    closed = []
    t = 0.0
    while m.eye_open < 1.0 or t == 0.0:
        closed.append(m.eye_open)
        m.tick(DT, "idle")
        t += DT
        if t > 1.0:
            break
    assert min(closed) < 0.05, f"blink never fully closed: {min(closed)}"
    assert abs(anim.BLINK_DURATION_S - 0.12) < 1e-9


def test_blink_interval_is_4_to_6s_and_randomised():
    m = Motion(rng=random.Random(11))
    gaps = []
    last = 0.0
    t = 0.0
    was_open = True
    while t < 60.0:
        m.tick(DT, "idle")
        t += DT
        closing = m.eye_open < 1.0
        if closing and was_open:
            gaps.append(t - last)
            last = t
        was_open = not closing
    assert len(gaps) >= 8, len(gaps)
    for g in gaps[1:]:
        assert 4.0 <= g <= 6.0 + DT, g
    assert len(set(round(g, 3) for g in gaps[1:])) > 1, "intervals not randomised"


def test_blink_is_a_scale_not_an_image_swap():
    """The eyes must be their own layer, squashed -- not a swapped frame.

    This is the whole reason the renderer doesn't use the baked PNGs.
    """
    sl = WispFace(initial_state="idle").states["idle"]
    assert len(sl.eye_steps) == geo.BLINK_STEPS
    open_h = sl.eye_steps[-1][0].get_height()
    shut_h = sl.eye_steps[0][0].get_height()
    assert shut_h < open_h * 0.3, (shut_h, open_h)


def test_blink_leaves_the_body_untouched():
    """Closing the eyes must not disturb a single body pixel."""
    face = WispFace(initial_state="idle")
    screen = _screen()

    face.draw(screen)
    opened = pygame.image.tostring(screen, "RGB")
    # Put the blink at its midpoint without advancing the clock, so the float
    # and the tip flicker are guaranteed to be in the same place both times.
    face.motion._blink_started = face.motion.t - anim.BLINK_DURATION_S / 2.0
    assert face.motion.eye_open < 0.05
    face.draw(screen)
    shut = pygame.image.tostring(screen, "RGB")

    assert opened != shut, "blink had no visible effect"
    # The flame tip, well clear of the eyes, must be byte-identical.
    w = 800
    for y in range(90, 150):
        row = slice((y * w + 360) * 3, (y * w + 440) * 3)
        assert opened[row] == shut[row], f"body changed at y={y}"


# -- tip flicker -----------------------------------------------------------

def test_tip_flicker_is_3px_on_a_1_2s_loop():
    ys = [m.flicker_offset()[1] for m in _sample(2.4)]
    assert abs(max(ys) - 3.0) < 0.05, max(ys)
    assert abs(min(ys) + 3.0) < 0.05, min(ys)
    m = Motion(rng=random.Random(5))
    first = m.flicker_offset()
    for _ in range(int(anim.FLICKER_PERIOD_S / DT)):
        m.tick(DT, "idle")
    later = m.flicker_offset()
    assert abs(first[0] - later[0]) < 1e-6 and abs(first[1] - later[1]) < 1e-6


# -- listening -------------------------------------------------------------

def test_glow_pulses_100_to_130_percent():
    assert abs(geo.HALO_PULSE_MAX - 1.3) < 1e-9
    pulses = [m.params("listening").halo_pulse for m in _sample(1.6, "listening")]
    assert abs(max(pulses) - 1.0) < 0.02, max(pulses)
    assert min(pulses) < 0.02, min(pulses)
    sl = WispFace(initial_state="listening").states["listening"]
    small = sl.halo_steps[0][0].get_width()
    big = sl.halo_steps[-1][0].get_width()
    assert abs(big / small - 1.3) < 0.02, (small, big)


def test_sound_rings_fade_out_every_0_8s():
    assert abs(anim.RING_PERIOD_S - 0.8) < 1e-9
    seen = []
    for m in _sample(0.8, "listening"):
        seen.append(m.params("listening").extra_alpha["ring1"])
    # Ring 1 starts at full strength and fades to nothing across the cycle.
    assert seen[0] > 0.9, seen[0]
    assert seen[-1] < 0.1, seen[-1]
    assert all(b <= a + 1e-6 for a, b in zip(seen, seen[1:])), "ring did not fade monotonically"


def test_rings_stay_readable_for_most_of_the_cycle():
    """Guards against an ease that makes the rings vanish instantly."""
    vals = [m.params("listening").extra_alpha["ring1"] for m in _sample(0.8, "listening")]
    visible = sum(1 for v in vals if v > 0.25)
    assert visible > len(vals) * 0.5, f"only {visible}/{len(vals)} frames readable"


# -- thinking --------------------------------------------------------------

def test_dots_light_bottom_to_top_0_4s_each():
    assert abs(anim.DOT_STEP_S - 0.4) < 1e-9
    # dot1 is lowest on screen (cy=80), dot3 highest (cy=46). Evaluate at
    # explicit times rather than by ticking, so the cycle boundary can't hide
    # a peak that lands exactly at t=0.
    m = Motion(rng=random.Random(9))
    cycle = anim.DOT_STEP_S * 3
    peaks = {}
    for k in range(240):
        m.t = k * cycle / 240.0
        for name, a in m.params("thinking").extra_alpha.items():
            if name not in peaks or a > peaks[name][0]:
                peaks[name] = (a, m.t)
    order = sorted(peaks, key=lambda n: peaks[n][1])
    assert order == ["dot1", "dot2", "dot3"], order
    assert abs((peaks["dot2"][1] - peaks["dot1"][1]) - 0.4) < 0.02
    assert abs((peaks["dot3"][1] - peaks["dot2"][1]) - 0.4) < 0.02
    # and the lit one really is brighter than the others at its own peak
    m.t = peaks["dot2"][1]
    a = m.params("thinking").extra_alpha
    assert a["dot2"] > a["dot1"] and a["dot2"] > a["dot3"]


# -- speaking --------------------------------------------------------------

def test_mouth_level_drives_the_mouth():
    m = Motion(rng=random.Random(2))
    m.set_mouth_level(1.0)
    for _ in range(30):
        m.tick(DT, "speaking")
    assert m.params("speaking").mouth > 0.95
    m.set_mouth_level(0.0)
    for _ in range(30):
        m.tick(DT, "speaking")
    assert m.params("speaking").mouth < 0.05


def test_mouth_level_is_clamped():
    m = Motion(rng=random.Random(2))
    m.set_mouth_level(5.0)
    m.tick(DT, "speaking")
    assert m.params("speaking").mouth <= 1.0
    m.set_mouth_level(-3.0)
    for _ in range(60):
        m.tick(DT, "speaking")
    assert m.params("speaking").mouth >= 0.0


def test_mouth_steps_cover_closed_to_open():
    sl = WispFace(initial_state="speaking").states["speaking"]
    assert len(sl.mouth_steps) == geo.MOUTH_STEPS
    assert sl.mouth_steps[0][0].get_height() < sl.mouth_steps[-1][0].get_height()


# -- happy -----------------------------------------------------------------

def test_happy_squashes_then_stretches_then_settles():
    m = Motion(rng=random.Random(4))
    m.state_changed()
    sx = []
    for _ in range(int(anim.HAPPY_BOUNCE_S / DT) + 4):
        m.tick(DT, "happy")
        sx.append(m.params("happy").squash[0])
    assert max(sx) > 1.05, f"never squashed wider: {max(sx)}"
    assert min(sx) < 0.96, f"never stretched taller: {min(sx)}"
    assert abs(sx[-1] - 1.0) < 1e-6, f"did not settle: {sx[-1]}"
    # Squash (wide) comes before stretch (tall).
    assert sx.index(max(sx)) < sx.index(min(sx))


def test_squash_preserves_volume_roughly():
    m = Motion(rng=random.Random(4))
    m.state_changed()
    for _ in range(6):
        m.tick(DT, "happy")
        sx, sy = m.params("happy").squash
        assert abs(sx * sy - 1.0) < 0.02, (sx, sy)


# -- sleepy ----------------------------------------------------------------

def test_zs_drift_up_and_fade():
    ups, alphas = [], []
    for m in _sample(anim.Z_PERIOD_S, "sleepy"):
        p = m.params("sleepy")
        ups.append(p.extra_offset["z1"][1])
        alphas.append(p.extra_alpha["z1"])
    assert min(ups) < -10.0, f"z never rose: {min(ups)}"
    assert all(u <= 0.0 for u in ups), "z drifted downward"
    assert min(alphas) < 0.1 and max(alphas) > 0.5


def test_sleepy_palette_is_about_60_percent_brightness():
    """The spec's 'body at 60% brightness' is the source file's sleepy palette."""
    awake = geo.STATES["idle"]["body"]
    dozing = geo.STATES["sleepy"]["body"]
    ratios = []
    for key in ("mid", "core", "edge"):
        a = sum(geo.palette.rgb(awake[key]))
        b = sum(geo.palette.rgb(dozing[key]))
        ratios.append(b / a)
    avg = sum(ratios) / len(ratios)
    assert 0.55 <= avg <= 0.70, avg


# -- transitions -----------------------------------------------------------

def test_state_change_cross_fades_over_200ms():
    assert abs(anim.TRANSITION_S - 0.2) < 1e-9
    face = WispFace(initial_state="idle")
    face.set_state("listening")
    assert face.state == "listening"
    assert face.transitioning
    elapsed = 0.0
    while face.transitioning and elapsed < 1.0:
        face.update(DT)
        elapsed += DT
    assert abs(elapsed - 0.2) < DT + 1e-6, elapsed


def test_transition_has_no_hard_cut():
    """Frame-to-frame change must stay gradual across a state switch."""
    face = WispFace(initial_state="listening")
    screen = _screen()
    face.draw(screen)
    prev = pygame.image.tostring(screen, "RGB")

    deltas = []
    for i in range(12):
        if i == 1:
            face.set_state("sleepy")
        face.render(screen, DT)
        cur = pygame.image.tostring(screen, "RGB")
        deltas.append(sum(abs(a - b) for a, b in zip(prev, cur)) / len(cur))
        prev = cur
    # No single frame may carry most of the change.
    assert max(deltas) < sum(deltas) * 0.5, deltas


def test_immediate_skips_the_transition():
    face = WispFace(initial_state="idle")
    face.set_state("happy", immediate=True)
    assert not face.transitioning
    assert face.state == "happy"


def test_unknown_state_is_rejected():
    face = WispFace()
    for bad in ("angry", "", None, "IDLE"):
        try:
            face.set_state(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted bad state {bad!r}")


def test_all_six_states_render():
    face = WispFace()
    screen = _screen()
    assert set(geo.STATE_NAMES) == {
        "idle", "listening", "thinking", "speaking", "happy", "sleepy"
    }
    for name in geo.STATE_NAMES:
        face.set_state(name, immediate=True)
        face.render(screen, DT)


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
