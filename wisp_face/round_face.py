"""Eyes-only face for the 1.28" GC9A01 round LCD (240x240, SPI).

Driver note -- this is why there's no SPI code in here
------------------------------------------------------
On a Pi 5 the usual userspace GC9A01 libraries are dead ends:

* ``luma.lcd`` doesn't support GC9A01 at all (ST7735/ST7789/ILI9341 and
  friends only).
* Anything built on ``RPi.GPIO`` cannot work on a Pi 5 -- the RP1 southbridge
  needs different kernel drivers, and RPi.GPIO was never ported.
* The MicroPython GC9A01 drivers that turn up in searches don't run on CPython.

What does work, and is the maintained path, is the kernel's own
``mipi-dbi-spi`` DRM driver via the ``gc9a01`` device-tree overlay. It brings
the panel up as an ordinary framebuffer at ``/dev/fb1``, so this module just
writes RGB565 pixels to it -- no SPI library, no GPIO library, and nothing
added to the dependency list. Setup lives in ``docs/round-display.md``.

Everything shares the main face's clock, so if both screens are running they
blink at the same moment.
"""

import os

import pygame

from . import animation as anim
from . import geometry as geo
from .animation import Motion
from .easing import ease_in_out_cubic
from .render import LayerCache

# How each state reads when all you have is a pair of eyes.
ROUND_STATES = {
    "idle":      {"art": "eyes"},
    "listening": {"art": "eyes", "pulse": True},
    # Eyes drift up and to the side, same as the thinking face on the big screen.
    "thinking":  {"art": "eyes", "look": (6.0, -8.0), "scale": 0.92},
    "speaking":  {"art": "eyes", "mouth": True},
    "happy":     {"art": "happy"},
    "sleepy":    {"art": "sleepy"},
}

# Listening pulse is gentler here: the eyes already fill the panel, so a full
# 30% would run off the edge.
ROUND_PULSE = 1.12
# How much the eyes widen with TTS volume while speaking.
ROUND_MOUTH_STRETCH = 0.10


class RoundFace:
    """Renders Wisp's eyes to a 240x240 surface.

    Pass ``mirror=<WispFace>`` to share that face's clock and state, so the two
    displays stay in lockstep. On its own it keeps its own ``Motion``.
    """

    def __init__(self, size=geo.ROUND_SIZE, cache_dir=None, use_disk_cache=True,
                 rng=None, initial_state="idle", mirror=None):
        self.size = size
        self.mirror = mirror
        self.scale = size / geo.ROUND_CANVAS[0]
        self.motion = mirror.motion if mirror is not None else Motion(rng=rng)
        self._px = self.scale / 1.5

        canvas = (round(geo.ROUND_CANVAS[0] * self.scale),
                  round(geo.ROUND_CANVAS[1] * self.scale))
        self.cache = LayerCache(canvas, cache_dir=cache_dir,
                                use_disk=use_disk_cache, view=geo.ROUND_CANVAS)

        # Blink squashes the eyes; each step is its own rasterisation.
        self.eye_steps = []
        for i in range(geo.BLINK_STEPS):
            t = i / (geo.BLINK_STEPS - 1)
            ys = geo.ROUND_BLINK_CLOSED_SCALE + (1.0 - geo.ROUND_BLINK_CLOSED_SCALE) * t
            self.eye_steps.append(self.cache.layer(geo.round_eyes_svg(yscale=ys)))
        self.art = {
            "happy": self.cache.layer(geo.round_happy_svg()),
            "sleepy": self.cache.layer(geo.round_sleepy_svg()),
        }

        self.background = geo.palette.rgb(geo.ROUND_BG)
        self._state = initial_state if mirror is None else mirror.state
        self._prev_state = None
        self._transition = 0.0
        self._buf_a = None
        self._buf_b = None

    # -- public API --------------------------------------------------------

    @property
    def state(self):
        return self.mirror.state if self.mirror is not None else self._state

    def set_state(self, state, immediate=False):
        if self.mirror is not None:
            self.mirror.set_state(state, immediate=immediate)
            return
        if state not in ROUND_STATES:
            raise ValueError(f"unknown state {state!r}")
        if state == self._state and self._transition <= 0.0:
            return
        self._prev_state = None if immediate else self._state
        self._transition = 0.0 if immediate else anim.TRANSITION_S
        self._state = state
        self.motion.state_changed()

    def set_mouth_level(self, level):
        self.motion.set_mouth_level(level)

    def update(self, dt):
        if self.mirror is not None:
            # The main face owns the clock; just follow its transition.
            self._prev_state = self.mirror._prev_state
            self._transition = self.mirror._transition
            return
        self.motion.tick(dt, self._state)
        if self._transition > 0.0:
            self._transition = max(0.0, self._transition - dt)
            if self._transition == 0.0:
                self._prev_state = None

    def draw(self, target):
        target.fill(self.background)
        cur = self.state
        if not self._prev_state or self._prev_state == cur:
            self._draw_state(target, cur)
            return
        # Same trick as the big face: outgoing frame opaque, incoming faded in,
        # so the background never shows through the middle of a switch.
        t = ease_in_out_cubic(1.0 - self._transition / anim.TRANSITION_S)
        a, b = self._buffers()
        a.fill((0, 0, 0, 0))
        b.fill((0, 0, 0, 0))
        self._draw_state(a, self._prev_state)
        self._draw_state(b, cur)
        a.set_alpha(255)
        b.set_alpha(int(255 * t))
        target.blit(a, (0, 0))
        target.blit(b, (0, 0))

    def render(self, target, dt):
        self.update(dt)
        self.draw(target)

    # -- internals ---------------------------------------------------------

    def _buffers(self):
        if self._buf_a is None:
            self._buf_a = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
            self._buf_b = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
        return self._buf_a, self._buf_b

    def _draw_state(self, target, state):
        spec = ROUND_STATES.get(state, ROUND_STATES["idle"])
        p = self.motion.params(state, px=self._px)

        if spec["art"] == "eyes":
            surf, crop = self.eye_steps[
                int(round(max(0.0, min(1.0, p.eye_open)) * (len(self.eye_steps) - 1)))
            ]
        else:
            surf, crop = self.art[spec["art"]]

        scale = spec.get("scale", 1.0)
        if spec.get("pulse"):
            scale *= 1.0 + (ROUND_PULSE - 1.0) * p.halo_pulse
        if spec.get("mouth"):
            scale *= 1.0 + ROUND_MOUTH_STRETCH * p.mouth

        x, y = crop
        if scale != 1.0:
            w, h = surf.get_size()
            nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
            surf = pygame.transform.smoothscale(surf, (nw, nh))
            x += (w - nw) / 2.0
            y += (h - nh) / 2.0

        look = spec.get("look", (0.0, 0.0))
        x += look[0] * self.scale
        y += look[1] * self.scale + p.float_dy
        target.blit(surf, (round(x), round(y)))


class Framebuffer:
    """Writes 240x240 RGB565 straight to ``/dev/fbN``.

    The gc9a01 overlay exposes the panel as a normal Linux framebuffer, so
    there is nothing clever to do: convert once into a 16-bit surface (pygame
    hands back native RGB565) and write the bytes.
    """

    def __init__(self, device="/dev/fb1"):
        self.device = device
        self.width, self.height, self.bpp = self._probe(device)
        if self.bpp != 16:
            raise RuntimeError(
                f"{device} is {self.bpp}bpp; this writes RGB565 (16bpp). "
                "Check the gc9a01 overlay in /boot/firmware/config.txt."
            )
        self._fb = open(device, "r+b", buffering=0)
        self._conv = pygame.Surface((self.width, self.height), 0, 16)

    @staticmethod
    def _probe(device):
        node = os.path.basename(device)
        base = f"/sys/class/graphics/{node}"
        try:
            with open(f"{base}/virtual_size") as f:
                w, h = (int(v) for v in f.read().strip().split(","))
            with open(f"{base}/bits_per_pixel") as f:
                bpp = int(f.read().strip())
            return w, h, bpp
        except OSError as exc:
            raise RuntimeError(
                f"can't read framebuffer geometry for {device} ({exc}). "
                "Is dtoverlay=gc9a01 set and the panel wired up?"
            ) from exc

    def show(self, surface):
        if surface.get_size() != (self.width, self.height):
            surface = pygame.transform.smoothscale(
                surface, (self.width, self.height)
            )
        self._conv.blit(surface, (0, 0))
        self._fb.seek(0)
        self._fb.write(self._conv.get_buffer().raw)

    def close(self):
        try:
            self._fb.close()
        except OSError:
            pass


def run(device="/dev/fb1", socket_path=None, fps=30, cache_dir=None,
        max_frames=None, sleep_after=None):
    """Drive the round display on its own, taking state from the assistant."""
    import collections

    from . import ipc

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1, 1))

    face = RoundFace(cache_dir=cache_dir)
    surface = pygame.Surface((face.size, face.size))
    fb = Framebuffer(device)

    inbox = collections.deque()
    server = None
    if socket_path:
        server = ipc.WispServer(
            socket_path,
            on_state=lambda v: inbox.append(("state", v)),
            on_mouth=lambda v: inbox.append(("mouth", v)),
        )
        print(f"Round display listening on {socket_path}", flush=True)

    clock = pygame.time.Clock()
    idle_for = 0.0
    frames = 0
    try:
        while max_frames is None or frames < max_frames:
            frames += 1
            dt = min(clock.tick(fps) / 1000.0, 0.1)
            while inbox:
                kind, value = inbox.popleft()
                if kind == "state" and value in ROUND_STATES:
                    face.set_state(value)
                    idle_for = 0.0
                elif kind == "mouth":
                    face.set_mouth_level(value)
            if sleep_after and face.state == "idle":
                idle_for += dt
                if idle_for >= sleep_after:
                    face.set_state("sleepy")
            face.render(surface, dt)
            fb.show(surface)
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.close()
        fb.close()
        pygame.quit()
    return 0


def main(argv=None):
    import argparse

    from . import ipc

    ap = argparse.ArgumentParser(description="Wisp on the 1.28\" round GC9A01 LCD.")
    ap.add_argument("--device", default="/dev/fb1",
                    help="framebuffer node created by the gc9a01 overlay")
    ap.add_argument("--socket", nargs="?", const=ipc.DEFAULT_SOCKET, default=None,
                    help="take state from the voice assistant")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--sleep-after", type=float, default=None,
                    help="seconds of no input before dozing off")
    ap.add_argument("--cache-dir", default=None)
    args = ap.parse_args(argv)
    return run(device=args.device, socket_path=args.socket, fps=args.fps,
               cache_dir=args.cache_dir, sleep_after=args.sleep_after)


if __name__ == "__main__":
    raise SystemExit(main())
