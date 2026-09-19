"""Build every surface a state needs, once, at startup.

Each state owns a small bundle of pre-rendered layers plus the pre-computed
variants the motion spec needs: blink steps for the eyes, mouth openings for
speech, and halo sizes for the listening pulse. Nothing here runs per frame.
"""

from dataclasses import dataclass, field


from . import geometry as geo
from .render import LayerCache, scaled


@dataclass
class Layout:
    """Where the 200x240 artwork lands on the display.

    The defaults reproduce the asset pack's own 800x480 renders: the 200x240
    viewBox is drawn at ``scale`` with its (0,0) corner at ``origin``. These
    were fitted against png/screen-800x480/*.png -- see
    tools/calibrate_layout.py.
    """

    width: int = 800
    height: int = 480
    scale: float = 1.5
    origin: tuple = (250.0, 48.0)

    @property
    def canvas_px(self):
        vw, vh = geo.CANVAS
        return (round(vw * self.scale), round(vh * self.scale))

    @property
    def size(self):
        return (self.width, self.height)

    def place(self, offset):
        """Layer crop offset -> screen position."""
        return (self.origin[0] + offset[0], self.origin[1] + offset[1])


@dataclass
class StateLayers:
    """Every surface one state needs, keyed for cheap per-frame lookup."""

    name: str
    halo: tuple = None            # (surface, offset) at 100%
    halo_steps: list = field(default_factory=list)  # (surface, offset) per pulse step
    body: tuple = None
    flicker: tuple = None
    eye_steps: list = field(default_factory=list)   # index 0 closed -> last open
    eye_centre_y: float = 0.0
    mouth_steps: list = field(default_factory=list)  # index 0 closed -> last open
    extras: dict = field(default_factory=dict)

    @property
    def has_eyes(self):
        return bool(self.eye_steps)


def _lerp(a, b, t):
    return a + (b - a) * t


def build_state(cache, name, layout):
    """Pre-render one state's layers and variants."""
    spec = geo.STATES[name]
    sl = StateLayers(name=name)

    if spec["halo"] is not None:
        colour, opacity = spec["halo"]
        sl.halo = cache.layer(geo.halo_svg(colour, opacity))
        # Listening pulses the glow 100% -> 130%. Scaling a soft radial
        # gradient bitmap is visually identical to re-rasterising it and far
        # cheaper, so the steps are smoothscaled copies.
        surf, off = sl.halo
        for i in range(geo.HALO_STEPS):
            t = i / (geo.HALO_STEPS - 1)
            factor = _lerp(1.0, geo.HALO_PULSE_MAX, t)
            s, shift = scaled(surf, factor)
            sl.halo_steps.append((s, (off[0] + shift[0], off[1] + shift[1])))

    body = spec["body"]
    sl.body = cache.layer(geo.body_svg(body["mid"], body["core"], body["edge"]))

    if spec["flicker"] is not None:
        sl.flicker = cache.layer(geo.flicker_svg(spec["flicker"]))

    eyes = spec["eyes"]
    if eyes is not None:
        sl.eye_centre_y = eyes["y"]
        # Blink squashes the eyes vertically. Each step is re-rasterised from
        # SVG rather than downscaled from the open-eye bitmap, so a nearly
        # closed eye stays a crisp sliver.
        for i in range(geo.BLINK_STEPS):
            t = i / (geo.BLINK_STEPS - 1)
            ys = _lerp(geo.BLINK_CLOSED_SCALE, 1.0, t)
            sl.eye_steps.append(cache.layer(geo.eyes_svg(yscale=ys, **eyes)))

    for extra in spec["extras"]:
        if extra == "mouth":
            for i in range(geo.MOUTH_STEPS):
                t = i / (geo.MOUTH_STEPS - 1)
                ry = _lerp(geo.MOUTH_MIN_RY, geo.MOUTH_MAX_RY, t)
                sl.mouth_steps.append(cache.layer(geo.mouth_svg(ry)))
        else:
            sl.extras[extra] = cache.layer(geo.EXTRAS[extra]())

    return sl


def build_all(layout, cache_dir=None, use_disk=True, states=None):
    """Pre-render every state. Returns ``(dict_of_StateLayers, cache)``."""
    cache = LayerCache(layout.canvas_px, cache_dir=cache_dir, use_disk=use_disk)
    names = states or geo.STATE_NAMES
    return {n: build_state(cache, n, layout) for n in names}, cache


def pick(steps, t):
    """Nearest pre-rendered step for a 0..1 parameter."""
    if not steps:
        return None
    idx = int(round(max(0.0, min(1.0, t)) * (len(steps) - 1)))
    return steps[idx]


def blit_layer(target, layer, layout, alpha=255, offset=(0.0, 0.0)):
    """Blit a ``(surface, crop_offset)`` layer, with optional alpha and shift."""
    if layer is None:
        return
    surf, crop = layer
    x, y = layout.place(crop)
    x += offset[0]
    y += offset[1]
    if alpha >= 255:
        target.blit(surf, (round(x), round(y)))
    else:
        if alpha <= 0:
            return
        tmp = surf.copy()
        tmp.set_alpha(int(alpha))
        target.blit(tmp, (round(x), round(y)))


class AlphaPool:
    """Reusable alpha-adjusted copies, so fading layers don't allocate per frame."""

    def __init__(self):
        self._pool = {}

    def get(self, key, surface, alpha):
        entry = self._pool.get(key)
        if entry is None or entry[0] is not surface:
            entry = (surface, surface.copy())
            self._pool[key] = entry
        copy = entry[1]
        copy.set_alpha(int(max(0, min(255, alpha))))
        return copy


def blit_pooled(target, pool, key, layer, layout, alpha=255, offset=(0.0, 0.0)):
    """Like :func:`blit_layer` but reuses a cached copy for alpha blending."""
    if layer is None or alpha <= 0:
        return
    surf, crop = layer
    x, y = layout.place(crop)
    x += offset[0]
    y += offset[1]
    if alpha >= 255:
        target.blit(surf, (round(x), round(y)))
    else:
        target.blit(pool.get(key, surf, alpha), (round(x), round(y)))
