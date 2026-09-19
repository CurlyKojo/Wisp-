"""The motion spec, as numbers.

Every constant in here comes straight from the asset pack README. This module
owns *what moves when*; it produces a plain :class:`FrameParams` each tick and
knows nothing about pygame or surfaces.
"""

import math
import random
from dataclasses import dataclass, field

from .easing import clamp, ease_in_out_sine, ease_out_cubic
from .geometry import EXTRA_BASE_ALPHA

# --- motion spec ----------------------------------------------------------

# "Float: 6 px up and down, 3 s ease-in-out loop" -- 6 px above rest and 6 px
# below, so 12 px peak to peak, on a 3 s loop.
FLOAT_AMPLITUDE_PX = 6.0
FLOAT_PERIOD_S = 3.0
FLOAT_PERIOD_SLEEPY_S = 5.0     # "float slows to 5 s"

# "Blink: every 4-6 s (randomize), 120 ms eyes closed"
BLINK_INTERVAL_S = (4.0, 6.0)
BLINK_DURATION_S = 0.12

# "Tip flicker: the side ember drifts +/- 3 px, 1.2 s loop"
FLICKER_AMPLITUDE_PX = 3.0
FLICKER_PERIOD_S = 1.2

# "Listening: glow pulses 100% -> 130%, sound rings fade out every 0.8 s"
LISTEN_PULSE_PERIOD_S = 0.8
RING_PERIOD_S = 0.8
RING_DRIFT_PX = 4.0             # rings ease outward as they fade

# "Thinking: dots light up bottom to top, 0.4 s each, loop"
DOT_STEP_S = 0.4
DOT_ORDER = ("dot1", "dot2", "dot3")   # dot1 is the lowest on screen
DOT_REST_ALPHA = 0.35                  # how far an unlit dot drops back

# "Happy: quick 1-bounce squash and stretch on entry, then idle float"
HAPPY_BOUNCE_S = 0.45
HAPPY_SQUASH = 0.12             # peak deformation, as a fraction

# "Sleepy: z's drift up and fade"
Z_PERIOD_S = 2.4
Z_RISE_PX = 16.0

# "set_state(...) switches states with a ~200 ms eased transition. No hard cuts."
TRANSITION_S = 0.2

# Mouth smoothing. TTS volume is spiky; without this the mouth strobes.
MOUTH_ATTACK = 0.55             # fraction of the gap closed per 30 fps frame
MOUTH_RELEASE = 0.22

# Pivot for the happy squash, in SVG units: the base of the flame, so Wisp
# squashes down onto its own bottom rather than shrinking about its middle.
SQUASH_PIVOT_SVG = (100.0, 204.0)


@dataclass
class FrameParams:
    """Everything the renderer needs to draw one state for one frame."""

    float_dy: float = 0.0
    eye_open: float = 1.0                  # 1 open, 0 fully closed
    flicker_offset: tuple = (0.0, 0.0)
    halo_pulse: float = 0.0                # 0 = 100%, 1 = 130%
    mouth: float = 0.0                     # 0 closed, 1 wide
    squash: tuple = (1.0, 1.0)             # (scale x, scale y) about the pivot
    extra_alpha: dict = field(default_factory=dict)   # name -> 0..1 multiplier
    extra_offset: dict = field(default_factory=dict)  # name -> (dx, dy) px


class Motion:
    """Drives the clock-based parts of the motion spec.

    Float and blink are deliberately global rather than per state: they carry
    straight through a state change, so a transition never resets the bob or
    interrupts a blink.
    """

    def __init__(self, rng=None, float_period=None):
        self.rng = rng or random.Random()
        # Overrides the spec's 3 s / 5 s float. The sprite exporter nudges it
        # by a few percent so a state's float closes at the same instant as
        # its other cycles; nothing else should touch it.
        self.float_period = float_period
        self.t = 0.0                 # global clock
        self.float_phase = 0.0       # integrated, so period changes don't jump
        self.state_t = 0.0           # time since the current state was entered
        self._blink_at = self.rng.uniform(*BLINK_INTERVAL_S)
        self._blink_started = None
        self._mouth = 0.0
        self._mouth_target = 0.0

    # -- input -------------------------------------------------------------

    def set_mouth_level(self, level):
        self._mouth_target = clamp(float(level))

    def state_changed(self):
        self.state_t = 0.0

    def blink_now(self):
        """Force a blink, e.g. on waking up."""
        if self._blink_started is None:
            self._blink_started = self.t

    # -- clock -------------------------------------------------------------

    def tick(self, dt, state):
        self.t += dt
        self.state_t += dt

        period = self.float_period or (
            FLOAT_PERIOD_SLEEPY_S if state == "sleepy" else FLOAT_PERIOD_S
        )
        self.float_phase = (self.float_phase + dt / period) % 1.0

        # Blink scheduling.
        if self._blink_started is None:
            if self.t >= self._blink_at:
                self._blink_started = self.t
        if self._blink_started is not None:
            if self.t - self._blink_started >= BLINK_DURATION_S:
                self._blink_started = None
                self._blink_at = self.t + self.rng.uniform(*BLINK_INTERVAL_S)

        # Mouth smoothing, frame-rate independent.
        gap = self._mouth_target - self._mouth
        rate = MOUTH_ATTACK if gap > 0 else MOUTH_RELEASE
        # rate is tuned for 30 fps; rescale so other frame rates match.
        k = 1.0 - (1.0 - rate) ** max(0.0, dt * 30.0)
        self._mouth += gap * k

    # -- derived values ----------------------------------------------------

    @property
    def eye_open(self):
        """1.0 open, 0.0 closed. A blink eases shut and back over its window."""
        if self._blink_started is None:
            return 1.0
        p = clamp((self.t - self._blink_started) / BLINK_DURATION_S)
        # Triangle through full closure at the midpoint, eased so it doesn't
        # look mechanical.
        tri = 1.0 - abs(p * 2.0 - 1.0)
        return 1.0 - ease_in_out_sine(tri)

    def float_dy(self, px=1.0):
        # Sine gives the ease-in-out at the top and bottom of the travel.
        return -math.sin(self.float_phase * 2.0 * math.pi) * FLOAT_AMPLITUDE_PX * px

    def flicker_offset(self, px=1.0):
        a = self.t / FLICKER_PERIOD_S * 2.0 * math.pi
        # Vertical drift is the main motion; a half-period horizontal wobble
        # keeps it alive without breaking the 1.2 s loop.
        return (
            math.sin(a * 2.0 + 1.1) * (FLICKER_AMPLITUDE_PX * 0.33) * px,
            math.sin(a) * FLICKER_AMPLITUDE_PX * px,
        )

    def params(self, state, px=1.0, state_t=None):
        """Build this frame's parameters for ``state``.

        ``px`` scales every pixel-denominated motion value, so the same spec
        holds at 800x480, on the round display, and in 2x sprite exports.
        Alphas in ``extra_alpha`` are final, not multipliers.

        ``state_t`` overrides the time-in-state, which the cross-fade needs so
        the outgoing state keeps animating on its own timeline.
        """
        if state_t is None:
            state_t = self.state_t
        p = FrameParams()
        p.float_dy = self.float_dy(px)
        p.eye_open = self.eye_open
        p.flicker_offset = self.flicker_offset(px)
        p.mouth = self._mouth
        base = EXTRA_BASE_ALPHA

        if state == "listening":
            # One heartbeat drives both the glow and the rings.
            ph = (self.t % LISTEN_PULSE_PERIOD_S) / LISTEN_PULSE_PERIOD_S
            p.halo_pulse = math.sin(ph * math.pi) ** 2
            for i, name in enumerate(("ring1", "ring2")):
                rp = ((self.t + i * RING_PERIOD_S * 0.5) % RING_PERIOD_S) / RING_PERIOD_S
                # Fade close to linearly so a ring is actually readable for
                # most of its 0.8 s life; the outward drift decelerates.
                p.extra_alpha[name] = base[name] * ((1.0 - rp) ** 1.2)
                p.extra_offset[name] = (RING_DRIFT_PX * ease_out_cubic(rp) * px, 0.0)

        elif state == "thinking":
            cycle = DOT_STEP_S * len(DOT_ORDER)
            for i, name in enumerate(DOT_ORDER):
                ph = (self.t - i * DOT_STEP_S) % cycle
                if ph < DOT_STEP_S:
                    # Bright for this dot's slot, then decay to the resting level.
                    lit = 1.0 - ease_out_cubic(ph / DOT_STEP_S)
                    p.extra_alpha[name] = clamp(DOT_REST_ALPHA + (1.0 - DOT_REST_ALPHA) * lit)
                else:
                    p.extra_alpha[name] = DOT_REST_ALPHA

        elif state == "sleepy":
            for i, name in enumerate(("z1", "z2")):
                zp = ((self.t + i * Z_PERIOD_S * 0.5) % Z_PERIOD_S) / Z_PERIOD_S
                p.extra_alpha[name] = base[name] * (math.sin(zp * math.pi) ** 0.7)
                p.extra_offset[name] = (0.0, -Z_RISE_PX * zp * px)

        elif state == "happy":
            p.squash = self._happy_squash(state_t)

        return p

    def _happy_squash(self, state_t):
        """One quick squash-and-stretch bounce on entering happy."""
        if state_t >= HAPPY_BOUNCE_S:
            return (1.0, 1.0)
        t = state_t / HAPPY_BOUNCE_S
        # Squash down first, overshoot tall, settle. Decaying sine does all
        # three in one expression.
        # Squash down first (wider, shorter), overshoot tall, then settle. A
        # decaying sine does all three in one expression. The decay is gentle
        # on purpose: a steeper one damps the stretch half away entirely and
        # you just get a squash.
        amount = math.sin(t * math.pi * 2.0) * HAPPY_SQUASH * (1.0 - t) ** 0.5
        return (1.0 + amount, 1.0 - amount)
