"""Wisp, split into animatable layers.

The character is NOT redrawn here. Every path, colour and coordinate comes
from ``assets/source/wisp_geometry.py``, which the asset pack calls the source
of truth. This module loads that file and re-composes the same primitives into
separate layers so each one can be transformed independently at runtime.

The baked PNGs can't blink -- the eyes are burned into the body. Splitting the
character into ``halo / body / flicker / eyes / mouth / extras`` is what makes
the motion spec possible.

Everything is expressed in the asset pack's 200x240 SVG user-unit space. A
layer is rendered onto a full 200x240 canvas (so all layers share one
coordinate system and line up exactly), then cropped to its opaque bounding box
at load time so blits stay cheap.
"""

import importlib.util
import os

from . import palette

CANVAS = (200, 240)  # the asset pack's viewBox, shared by every layer

_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "source", "wisp_geometry.py",
)


def _load_source():
    """Import the asset pack's geometry file as a module."""
    if not os.path.exists(_SRC):
        raise FileNotFoundError(
            f"Wisp geometry source not found at {_SRC}. "
            "The asset pack's source/wisp_geometry.py is required."
        )
    spec = importlib.util.spec_from_file_location("wisp_geometry_src", _SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


g = _load_source()

# Pulled straight out of the source file so there is exactly one definition.
BODY = g.BODY
FLICK = g.FLICK
SIDE = g.SIDE
INK = g.INK
GLOW = g.GLOW
CORE = g.CORE
DEEP = g.DEEP
EMBER = g.EMBER


def svg_doc(inner, width, height, view=None):
    """Wrap layer markup in a standalone SVG on the shared canvas."""
    vw, vh = view or CANVAS
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {vw} {vh}" width="{width}" height="{height}">'
        f"{inner}</svg>"
    )


# --------------------------------------------------------------------------
# State definitions
#
# These mirror wisp_geometry.expr() exactly -- same colours, same coordinates.
# They are restated as data so the renderer can build one layer at a time
# instead of one flat SVG per state.
# --------------------------------------------------------------------------

_DEFAULT_BODY = {"mid": GLOW, "core": CORE, "edge": DEEP}

STATES = {
    "idle": {
        "halo": (GLOW, 0.4),
        "body": _DEFAULT_BODY,
        "flicker": GLOW,
        "eyes": {"y": 146, "rx": 7, "ry": 11, "dx": 0, "hl": True},
        "extras": (),
    },
    "listening": {
        "halo": (GLOW, 0.55),
        "body": {"mid": "#8FF0E2", "core": "#FFFFFF", "edge": DEEP},
        "flicker": "#8FF0E2",
        "eyes": {"y": 144, "rx": 9, "ry": 14, "dx": 0, "hl": True},
        "extras": ("ring1", "ring2"),
    },
    "thinking": {
        "halo": (GLOW, 0.4),
        "body": _DEFAULT_BODY,
        "flicker": GLOW,
        "eyes": {"y": 138, "rx": 6, "ry": 9, "dx": 6, "hl": False},
        "extras": ("dot1", "dot2", "dot3"),
    },
    "speaking": {
        "halo": (GLOW, 0.4),
        "body": _DEFAULT_BODY,
        "flicker": GLOW,
        "eyes": {"y": 142, "rx": 7, "ry": 11, "dx": 0, "hl": True},
        "extras": ("mouth",),
    },
    "happy": {
        "halo": (EMBER, 0.28),
        "body": _DEFAULT_BODY,
        "flicker": GLOW,
        "eyes": None,
        "extras": ("brows", "blush"),
    },
    "sleepy": {
        # No halo, no side ember -- the sleepy palette from the source file is
        # itself the "60% brightness" the motion spec asks for (its channels
        # land at ~0.6x of the waking palette), which is why the static sleepy
        # render is dimmer without any extra dimming applied on top.
        "halo": None,
        "body": {"mid": "#4E9C95", "core": "#BFD9D6", "edge": "#1D4F4B"},
        "flicker": None,
        "eyes": None,
        "extras": ("sleepy_eyes", "z1", "z2"),
    },
}

STATE_NAMES = ("idle", "listening", "thinking", "speaking", "happy", "sleepy")

# Mouth opening, in SVG units of ellipse ry. The static speaking render uses
# ry=7 and lands exactly on a step; 1.0 reads as a closed line and 9 as a wide open mouth.
MOUTH_MIN_RY = 1.0
MOUTH_MAX_RY = 9.0
MOUTH_STEPS = 17
# Where the static speaking render sits on that range (ry=7).
REST_MOUTH = (7.0 - MOUTH_MIN_RY) / (MOUTH_MAX_RY - MOUTH_MIN_RY)

# Blink is a Y-scale on the eye layer, never an image swap.
BLINK_CLOSED_SCALE = 0.1
BLINK_STEPS = 9

# Listening glow pulse, as a scale on the halo layer.
HALO_PULSE_MAX = 1.3
HALO_STEPS = 13


# --------------------------------------------------------------------------
# Layer markup builders
# --------------------------------------------------------------------------

def halo_svg(colour, opacity, uid="h"):
    """The soft radial glow behind Wisp."""
    return (
        f'<defs><radialGradient id="{uid}" cx="50%" cy="58%" r="50%">'
        f'<stop offset="0%" stop-color="{colour}" stop-opacity="{opacity}"/>'
        f'<stop offset="100%" stop-color="{colour}" stop-opacity="0"/>'
        "</radialGradient></defs>"
        f'<circle cx="100" cy="140" r="100" fill="url(#{uid})"/>'
    )


def body_svg(mid, core, edge, uid="b"):
    """The flame body with its three-stop gradient."""
    return (
        f'<defs><radialGradient id="{uid}" cx="50%" cy="68%" r="62%">'
        f'<stop offset="0%" stop-color="{core}"/>'
        f'<stop offset="50%" stop-color="{mid}"/>'
        f'<stop offset="100%" stop-color="{edge}"/>'
        "</radialGradient></defs>"
        f'<path d="{BODY}" fill="url(#{uid})"/>'
    )


def flicker_svg(colour):
    """The little ember off Wisp's right shoulder."""
    return f'<path d="{FLICK}" fill="{colour}" opacity="0.7"/>'


def eyes_svg(y=146, rx=7, ry=11, dx=0, hl=True, yscale=1.0):
    """Both eyes, optionally squashed vertically about their own centre.

    ``yscale`` is the blink: 1.0 open, ~0.1 closed. The squash is applied as an
    SVG transform and re-rasterised, so closed eyes stay crisp instead of
    turning into a blurry downscale of an open-eye bitmap.
    """
    inner = g.eyes(y=y, rx=rx, ry=ry, dx=dx, hl=hl)
    if yscale == 1.0:
        return inner
    return (
        f'<g transform="translate(0 {y}) scale(1 {yscale}) translate(0 {-y})">'
        f"{inner}</g>"
    )


def mouth_svg(ry=7.0):
    """Speaking mouth. ry is driven by TTS volume."""
    return f'<ellipse cx="100" cy="172" rx="10" ry="{ry}" fill="{INK}"/>'


def _ring(d, opacity):
    return (
        f'<path d="{d}" stroke="{GLOW}" stroke-width="5" fill="none" '
        f'stroke-linecap="round" opacity="{opacity}"/>'
    )


def _dot(cx, cy, r):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{GLOW}"/>'


def _z(x, y, size):
    """A 'z' drawn as a stroked path.

    The source file sets these with an SVG <text> element in IBM Plex Mono.
    Stroking the glyph instead keeps the renderer working on a Pi with no fonts
    installed, which matters because the whole thing has to run offline.
    """
    # Ratios fitted to the glyph metrics in png/screen-800x480/sleepy.png so
    # the path version sits exactly where the text version did.
    w = size * 0.467
    h = size * 0.533
    sw = size * 0.08
    return (
        f'<path d="M{x} {y - h} H{x + w} L{x} {y} H{x + w}" fill="none" '
        f'stroke="{GLOW}" stroke-width="{sw}" stroke-linecap="butt" '
        'stroke-linejoin="bevel"/>'
    )


# Extras are rendered at full strength; per-frame alpha does the animating.
EXTRAS = {
    "ring1": lambda: _ring("M170 124 q 10 20 0 40", 1.0),
    "ring2": lambda: _ring("M184 112 q 12 32 0 64", 1.0),
    "dot1": lambda: _dot(160, 80, 4),
    "dot2": lambda: _dot(172, 64, 5),
    "dot3": lambda: _dot(184, 46, 6),
    "brows": lambda: (
        f'<path d="M73 152 q 9 -16 18 0" stroke="{INK}" stroke-width="6" '
        'fill="none" stroke-linecap="round"/>'
        f'<path d="M109 152 q 9 -16 18 0" stroke="{INK}" stroke-width="6" '
        'fill="none" stroke-linecap="round"/>'
    ),
    "blush": lambda: (
        f'<circle cx="68" cy="166" r="7" fill="{EMBER}" opacity="0.6"/>'
        f'<circle cx="132" cy="166" r="7" fill="{EMBER}" opacity="0.6"/>'
    ),
    "sleepy_eyes": lambda: (
        f'<path d="M74 150 h16" stroke="{INK}" stroke-width="5" '
        'stroke-linecap="round"/>'
        f'<path d="M110 150 h16" stroke="{INK}" stroke-width="5" '
        'stroke-linecap="round"/>'
    ),
    "z1": lambda: _z(150, 86, 22),
    "z2": lambda: _z(166, 60, 30),
}

# Resting opacity of the thinking dots, from the source file. The animation
# brightens one at a time from this floor.
DOT_BASE_ALPHA = {"dot1": 0.5, "dot2": 0.75, "dot3": 1.0}

# Eyes-only artwork for the 1.28" round display.
def eyes_only_svg(uid="r", yscale=1.0):
    inner = g.eyes_only(uid)
    if yscale != 1.0:
        inner = (
            f'<g transform="translate(0 100) scale(1 {yscale}) '
            f'translate(0 -100)">{inner}</g>'
        )
    return inner


__all__ = [
    "CANVAS", "STATES", "STATE_NAMES", "EXTRAS", "DOT_BASE_ALPHA",
    "BODY", "FLICK", "SIDE", "INK", "GLOW", "CORE", "DEEP", "EMBER",
    "svg_doc", "halo_svg", "body_svg", "flicker_svg", "eyes_svg",
    "mouth_svg", "eyes_only_svg",
    "MOUTH_MIN_RY", "MOUTH_MAX_RY", "MOUTH_STEPS",
    "BLINK_CLOSED_SCALE", "BLINK_STEPS", "HALO_PULSE_MAX", "HALO_STEPS",
    "palette",
]


# Resting opacity of every extra, matching the source file's own values. The
# animations modulate around these.
EXTRA_BASE_ALPHA = {
    "ring1": 1.0, "ring2": 0.6,
    "dot1": 0.5, "dot2": 0.75, "dot3": 1.0,
    "z1": 0.6, "z2": 1.0,
    "brows": 1.0, "blush": 1.0, "sleepy_eyes": 1.0,
}


# --------------------------------------------------------------------------
# 1.28" round display (GC9A01, 240x240)
#
# The pack's eyes-only artwork lives in a 200x200 viewBox rendered at 240x240,
# so the round display runs at scale 1.2.
# --------------------------------------------------------------------------

ROUND_CANVAS = (200, 200)
ROUND_SIZE = 240
ROUND_SCALE = ROUND_SIZE / ROUND_CANVAS[0]

# Background from the pack's own svg/eyes-only.svg -- a touch deeper than Ink,
# because on a self-lit round LCD in the dark, Ink reads as grey.
ROUND_BG = "#05070C"

# The pack's eyes-blink.svg closes the round eyes to a 10-unit bar. Squashing
# the 30-unit-tall eye by this lands on exactly that, so blink stays a scale
# rather than an image swap here too.
ROUND_BLINK_CLOSED_SCALE = 10.0 / (30.0 * 2.0)

# Eye extents, matching eyes-blink.svg's bars.
_ROUND_EYE_SPANS = ((50, 86), (114, 150))
_ROUND_EYE_CY = 100


def round_eyes_svg(yscale=1.0):
    """The open eyes, optionally squashed for a blink."""
    return eyes_only_svg("eo", yscale=yscale)


def round_happy_svg():
    """Closed, curved-up eyes, in the same weight as the pack's blink bars."""
    parts = []
    for x0, x1 in _ROUND_EYE_SPANS:
        parts.append(
            f'<path d="M{x0} {_ROUND_EYE_CY + 8} q {(x1 - x0) / 2} -22 {x1 - x0} 0" '
            f'stroke="{GLOW}" stroke-width="10" fill="none" stroke-linecap="round"/>'
        )
    return "".join(parts)


def round_sleepy_svg():
    """Flat bars -- the pack's eyes-blink.svg shape, dimmed like the sleepy body."""
    dim = STATES["sleepy"]["body"]["mid"]
    return (
        f'<path d="M50 100 H 86 M114 100 H 150" stroke="{dim}" '
        'stroke-width="10" stroke-linecap="round"/>'
    )
