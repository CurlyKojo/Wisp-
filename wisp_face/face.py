"""WispFace -- the animated 800x480 face.

Public API, and all the voice stack needs:

    face = WispFace()
    face.set_state("listening")     # ~200 ms eased transition, never a cut
    face.set_mouth_level(0.0..1.0)  # drive the mouth from TTS volume
    face.render(screen, dt)         # update + draw

Everything expensive happens in ``__init__``. The per-frame path is a fill and
a handful of blits of pre-rendered surfaces.
"""

import random

import pygame

from . import animation as anim
from . import geometry as geo
from .animation import Motion
from .easing import clamp, ease_in_out_cubic
from .layers import AlphaPool, Layout, build_all, pick

# Layers that belong to the character itself and so deform with the happy
# squash. The halo and the floating extras (rings, dots, z's) do not.
_FACE_EXTRAS = frozenset({"brows", "blush", "sleepy_eyes"})

# Distinguishes "caller said nothing" from "caller asked for no background".
_DEFAULT_BG = object()


class WispFace:
    """Renders Wisp, in one of six states, onto any pygame surface."""

    def __init__(self, layout=None, cache_dir=None, use_disk_cache=True,
                 rng=None, initial_state="idle", background=_DEFAULT_BG,
                 float_period=None):
        if initial_state not in geo.STATES:
            raise ValueError(f"unknown state {initial_state!r}")

        self.layout = layout or Layout()
        # background=None draws onto whatever is already there, which is how
        # the sprite exporter gets transparent frames.
        self.background = (geo.palette.INK_RGB if background is _DEFAULT_BG
                           else background)
        self.motion = Motion(rng=rng or random.Random(), float_period=float_period)

        self.states, self.cache = build_all(
            self.layout, cache_dir=cache_dir, use_disk=use_disk_cache
        )

        self._state = initial_state
        self._prev_state = None
        self._transition = 0.0          # seconds remaining
        self._prev_state_t = 0.0

        self._pool = AlphaPool()
        self._pivot = (
            self.layout.origin[0] + anim.SQUASH_PIVOT_SVG[0] * self.layout.scale,
            self.layout.origin[1] + anim.SQUASH_PIVOT_SVG[1] * self.layout.scale,
        )
        # Pixel motion values in the spec are quoted for the 800x480 screen,
        # which is scale 1.5. Everything scales off that so the same numbers
        # hold on the round display and in 2x sprite exports.
        self._px = self.layout.scale / 1.5

        self._dirty = self._character_rect()
        self._buf_a = None
        self._buf_b = None

    # -- public API --------------------------------------------------------

    @property
    def state(self):
        return self._state

    @property
    def transitioning(self):
        return self._transition > 0.0

    @property
    def content_rect(self):
        """Bounding box of everything any state can draw, with motion headroom.

        Useful for cropping exports down to the character instead of shipping
        a screenful of empty background.
        """
        return pygame.Rect(self._dirty)

    def set_state(self, state, immediate=False):
        """Switch state. Cross-fades over ~200 ms unless ``immediate``."""
        if state not in geo.STATES:
            raise ValueError(
                f"unknown state {state!r}; expected one of {list(geo.STATE_NAMES)}"
            )
        if state == self._state and not self.transitioning:
            return
        self._prev_state = None if immediate else self._state
        self._prev_state_t = self.motion.state_t
        self._transition = 0.0 if immediate else anim.TRANSITION_S
        self._state = state
        self.motion.state_changed()

    def set_mouth_level(self, level):
        """0.0 closed to 1.0 wide open. Drive this from TTS output volume."""
        self.motion.set_mouth_level(level)

    def update(self, dt):
        self.motion.tick(dt, self._state)
        if self._transition > 0.0:
            self._transition = max(0.0, self._transition - dt)
            self._prev_state_t += dt
            if self._transition == 0.0:
                self._prev_state = None

    def draw(self, target):
        if self.background is not None:
            target.fill(self.background)

        cur = self.states[self._state]
        p_cur = self.motion.params(self._state, px=self._px)

        if self._prev_state is None:
            self._draw_state(target, cur, p_cur)
            return

        # Cross-dissolve, composited so the background never shows through
        # mid-transition.
        #
        # Blitting the outgoing frame at (1-t) and the incoming one at t would
        # leave (1-t)*t of the background visible underneath -- a grey dip at
        # the halfway point. Instead the outgoing frame goes down opaque and
        # only the incoming one is faded in, which lerps exactly where the two
        # overlap. Layers the incoming state does not draw at all (rings when
        # leaving listening, dots when leaving thinking) would then pop at the
        # end, so those are faded out individually inside the outgoing frame.
        t = ease_in_out_cubic(1.0 - self._transition / anim.TRANSITION_S)
        a, b = self._buffers()
        prev = self.states[self._prev_state]
        p_prev = self.motion.params(
            self._prev_state, px=self._px, state_t=self._prev_state_t
        )
        shift = self._dirty.topleft
        shared = self._slots(prev) & self._slots(cur)

        a.fill((0, 0, 0, 0))
        b.fill((0, 0, 0, 0))
        self._draw_state(a, prev, p_prev, origin_shift=shift,
                         keep=shared, fade=1.0 - t)
        self._draw_state(b, cur, p_cur, origin_shift=shift)
        a.set_alpha(255)
        b.set_alpha(int(255 * t))
        target.blit(a, shift)
        target.blit(b, shift)

    def render(self, target, dt):
        """Convenience: update then draw."""
        self.update(dt)
        self.draw(target)

    def draw_rest(self, target, state=None):
        """Draw a state with every animation at rest.

        This is the pose the asset pack's static PNGs show, so it is what the
        reference-match test compares against. It goes through the same
        compositing path as the live render -- nothing here is a second
        implementation that could drift.
        """
        state = state or self._state
        if state not in geo.STATES:
            raise ValueError(f"unknown state {state!r}")
        if self.background is not None:
            target.fill(self.background)
        p = anim.FrameParams(mouth=geo.REST_MOUTH)
        self._draw_state(target, self.states[state], p)

    # -- internals ---------------------------------------------------------

    def _buffers(self):
        if self._buf_a is None:
            size = self._dirty.size
            self._buf_a = pygame.Surface(size, pygame.SRCALPHA)
            self._buf_b = pygame.Surface(size, pygame.SRCALPHA)
        return self._buf_a, self._buf_b

    @staticmethod
    def _slots(sl):
        """Which drawable slots a state uses, for working out what cross-fades."""
        s = {"body"}
        if sl.halo is not None:
            s.add("halo")
        if sl.flicker is not None:
            s.add("flicker")
        if sl.eye_steps:
            s.add("eyes")
        if sl.mouth_steps:
            s.add("mouth")
        s.update(sl.extras)
        return s

    def _character_rect(self):
        """Union of everything any state can draw, with room for the motion.

        Used to keep the cross-fade buffers small -- there is no point
        compositing 800x480 of mostly empty background twice per frame.
        """
        rect = None
        for sl in self.states.values():
            layers = [sl.body, sl.flicker]
            layers += sl.halo_steps or ([sl.halo] if sl.halo else [])
            layers += sl.eye_steps + sl.mouth_steps
            layers += list(sl.extras.values())
            for layer in layers:
                if layer is None:
                    continue
                surf, crop = layer
                x, y = self.layout.place(crop)
                r = pygame.Rect(int(x), int(y), *surf.get_size())
                rect = r if rect is None else rect.union(r)
        if rect is None:  # pragma: no cover - always has layers in practice
            return pygame.Rect(0, 0, *self.layout.size)
        # Headroom for the float, the squash, ring drift and rising z's.
        pad = int(max(
            anim.FLOAT_AMPLITUDE_PX, anim.Z_RISE_PX, anim.RING_DRIFT_PX
        ) * self._px) + int(rect.height * anim.HAPPY_SQUASH) + 8
        rect = rect.inflate(pad * 2, pad * 2)
        return rect.clip(pygame.Rect(0, 0, *self.layout.size))

    def _place(self, layer, p, dx=0.0, dy=0.0, squash=False):
        """Resolve a layer to ``(surface, (x, y))`` for this frame."""
        surf, crop = layer
        x, y = self.layout.place(crop)
        if squash:
            sx, sy = p.squash
            if sx != 1.0 or sy != 1.0:
                w, h = surf.get_size()
                surf = pygame.transform.smoothscale(
                    surf, (max(1, round(w * sx)), max(1, round(h * sy)))
                )
                px, py = self._pivot
                x = px + (x - px) * sx
                y = py + (y - py) * sy
        # Float is applied after the squash so the bob isn't scaled by it.
        return surf, (x + dx, y + dy + p.float_dy)

    def _blit(self, target, key, layer, p, alpha=1.0, dx=0.0, dy=0.0,
              squash=False, shift=(0, 0)):
        if layer is None or alpha <= 0.0:
            return
        surf, (x, y) = self._place(layer, p, dx, dy, squash)
        pos = (round(x - shift[0]), round(y - shift[1]))
        a = int(clamp(alpha) * 255)
        if a >= 255:
            target.blit(surf, pos)
        else:
            target.blit(self._pool.get(key, surf, a), pos)

    def _draw_state(self, target, sl, p, origin_shift=(0, 0), keep=None,
                    fade=1.0):
        """Composite one state.

        ``keep`` is the set of slots the *other* state also draws during a
        transition; anything outside it is multiplied by ``fade`` so it can
        disappear smoothly instead of popping.
        """
        blit = self._blit
        n = sl.name

        def mul(slot):
            return 1.0 if keep is None or slot in keep else fade

        if sl.halo_steps:
            blit(target, f"{n}.halo", pick(sl.halo_steps, p.halo_pulse), p,
                 alpha=mul("halo"), shift=origin_shift)

        blit(target, f"{n}.body", sl.body, p, alpha=mul("body"), squash=True,
             shift=origin_shift)

        if sl.flicker is not None:
            fx, fy = p.flicker_offset
            blit(target, f"{n}.flicker", sl.flicker, p, alpha=mul("flicker"),
                 dx=fx, dy=fy, squash=True, shift=origin_shift)

        if sl.eye_steps:
            blit(target, f"{n}.eyes", pick(sl.eye_steps, p.eye_open), p,
                 alpha=mul("eyes"), squash=True, shift=origin_shift)

        if sl.mouth_steps:
            blit(target, f"{n}.mouth", pick(sl.mouth_steps, p.mouth), p,
                 alpha=mul("mouth"), squash=True, shift=origin_shift)

        base = geo.EXTRA_BASE_ALPHA
        for name, layer in sl.extras.items():
            alpha = p.extra_alpha.get(name, base.get(name, 1.0)) * mul(name)
            ox, oy = p.extra_offset.get(name, (0.0, 0.0))
            blit(target, f"{n}.{name}", layer, p, alpha=alpha, dx=ox, dy=oy,
                 squash=name in _FACE_EXTRAS, shift=origin_shift)
