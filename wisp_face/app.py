"""The run loop: desktop preview on a Mac, fullscreen on the Pi.

Same code path either way -- the only differences are the window flags and
whether the HUD starts visible. Iterate on the Mac, deploy the same thing.

Keys
    1-6         idle / listening / thinking / speaking / happy / sleepy
    M           fake TTS mouth movement (toggle)
    H           HUD on/off
    F           fullscreen on/off
    B           force a blink
    ESC or Q    quit

With --socket, the face also takes state from the voice assistant, and
forwards RETURN (push to talk) and SPACE (interrupt) back to it -- the face
owns the screen on the Pi, so it has to own those keys too.
"""

import collections
import math
import os
import sys
import time

import pygame

from . import geometry as geo
from . import ipc
from .face import WispFace
from .layers import Layout

STATE_KEYS = {
    pygame.K_1: "idle",
    pygame.K_2: "listening",
    pygame.K_3: "thinking",
    pygame.K_4: "speaking",
    pygame.K_5: "happy",
    pygame.K_6: "sleepy",
}

TARGET_FPS = 30

# "sleepy: no input for 10+ min, or night mode"
IDLE_SLEEP_S = 600.0


def fake_speech_level(t):
    """A plausible TTS volume envelope, for previewing the mouth without audio."""
    syllable = max(0.0, math.sin(t * 11.0))
    phrase = 0.55 + 0.45 * math.sin(t * 1.7 + 0.6)
    breath = 0.0 if math.sin(t * 0.55) < -0.6 else 1.0
    return syllable * phrase * breath


class _Hud:
    """Tiny corner readout. Silently disables itself if no font is available."""

    def __init__(self):
        self.font = None
        try:
            pygame.font.init()
            self.font = pygame.font.SysFont(
                "ibmplexmono,dejavusansmono,monospace", 16
            )
        except Exception:
            self.font = None

    def draw(self, target, lines):
        if self.font is None:
            return
        y = 8
        for line in lines:
            try:
                img = self.font.render(line, True, geo.palette.GLOW_RGB)
            except Exception:
                return
            target.blit(img, (10, y))
            y += img.get_height() + 2


def run(fullscreen=False, size=(800, 480), state="idle", hud=None,
        cache_dir=None, fps=TARGET_FPS, driver=None, max_frames=None,
        socket_path=None, sleep_after=IDLE_SLEEP_S):
    """Run the face until the window is closed.

    ``max_frames`` stops after a fixed number of frames; it exists so the
    loop itself can be smoke-tested headlessly.
    """
    if driver:
        os.environ["SDL_VIDEODRIVER"] = driver
    if hud is None:
        hud = not fullscreen

    pygame.init()
    pygame.display.set_caption("Wisp")
    flags = pygame.FULLSCREEN | pygame.SCALED if fullscreen else 0
    screen = pygame.display.set_mode(size, flags)
    if fullscreen:
        pygame.mouse.set_visible(False)

    layout = Layout(width=size[0], height=size[1])
    if size != (800, 480):
        # Keep Wisp centred and proportional if the window isn't the Pi's panel.
        layout.scale = 1.5 * min(size[0] / 800.0, size[1] / 480.0)
        vw, vh = geo.CANVAS
        layout.origin = (
            (size[0] - vw * layout.scale) / 2.0,
            (size[1] - vh * layout.scale) / 2.0 - 12 * layout.scale / 1.5,
        )

    t0 = time.perf_counter()
    print("Pre-rendering layers...", flush=True)
    face = WispFace(layout=layout, cache_dir=cache_dir, initial_state=state)
    print(
        f"Ready in {time.perf_counter() - t0:.2f}s "
        f"({face.cache.stats['rasterised']} rasterised, "
        f"{face.cache.stats['from_disk']} cached)",
        flush=True,
    )

    # Commands arrive on the server's threads; queue them and apply on the
    # render thread so a state change can't land halfway through a draw.
    inbox = collections.deque()
    server = None
    if socket_path:
        server = ipc.WispServer(
            socket_path,
            on_state=lambda v: inbox.append(("state", v)),
            on_mouth=lambda v: inbox.append(("mouth", v)),
        )
        print(f"Listening for the assistant on {socket_path}", flush=True)

    overlay = _Hud()
    clock = pygame.time.Clock()
    show_hud = hud
    faking = False
    fake_t = 0.0
    frame_ms = 0.0
    idle_for = 0.0
    running = True
    frames = 0

    while running:
        if max_frames is not None and frames >= max_frames:
            break
        frames += 1
        dt = clock.tick(fps) / 1000.0
        dt = min(dt, 0.1)  # don't let a stall throw the animation forward

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key in STATE_KEYS:
                    face.set_state(STATE_KEYS[event.key])
                    idle_for = 0.0
                elif event.key == pygame.K_m:
                    faking = not faking
                    fake_t = 0.0
                    if faking:
                        face.set_state("speaking")
                    else:
                        face.set_mouth_level(0.0)
                        face.set_state("idle")
                elif event.key == pygame.K_h:
                    show_hud = not show_hud
                elif event.key == pygame.K_b:
                    face.motion.blink_now()
                elif event.key == pygame.K_RETURN and server is not None:
                    server.send_key(ipc.KEY_PTT)
                    idle_for = 0.0
                elif event.key == pygame.K_SPACE and server is not None:
                    server.send_key(ipc.KEY_INTERRUPT)
                    idle_for = 0.0
                elif event.key == pygame.K_f:
                    fullscreen = not fullscreen
                    flags = pygame.FULLSCREEN | pygame.SCALED if fullscreen else 0
                    screen = pygame.display.set_mode(size, flags)
                    pygame.mouse.set_visible(not fullscreen)

        while inbox:
            kind, value = inbox.popleft()
            if kind == "state":
                if value in geo.STATES:
                    face.set_state(value)
                    idle_for = 0.0
                else:
                    print(f"[wisp] ignoring unknown state {value!r}", flush=True)
            elif kind == "mouth":
                face.set_mouth_level(value)

        # Doze off after a long silence, and wake on anything at all.
        if sleep_after and face.state == "idle":
            idle_for += dt
            if idle_for >= sleep_after:
                face.set_state("sleepy")
        elif face.state != "sleepy":
            idle_for = 0.0

        if faking:
            fake_t += dt
            face.set_mouth_level(fake_speech_level(fake_t))

        start = time.perf_counter()
        face.render(screen, dt)
        frame_ms = frame_ms * 0.9 + (time.perf_counter() - start) * 1000.0 * 0.1

        if show_hud:
            overlay.draw(screen, [
                f"state  {face.state}{'  ->' if face.transitioning else ''}",
                f"fps    {clock.get_fps():4.1f}   draw {frame_ms:4.2f} ms",
                f"mouth  {face.motion.params(face.state).mouth:.2f}"
                f"{'   [M faking]' if faking else ''}",
                ("link   " + ("agent connected" if server.client_count
                              else "waiting for agent")) if server else
                "1-6 state  M mouth  B blink  H hud  F full  Q quit",
            ])

        pygame.display.flip()

    if server is not None:
        server.close()
    pygame.quit()
    return 0


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(
        description="Run Wisp's face. Windowed by default; --fullscreen on the Pi.",
    )
    ap.add_argument("--fullscreen", action="store_true",
                    help="fullscreen, no cursor (how it runs on the Pi)")
    ap.add_argument("--size", default="800x480",
                    help="window size, e.g. 1200x720 (default 800x480)")
    ap.add_argument("--state", default="idle", choices=list(geo.STATE_NAMES))
    ap.add_argument("--fps", type=int, default=TARGET_FPS)
    ap.add_argument("--hud", dest="hud", action="store_true", default=None)
    ap.add_argument("--no-hud", dest="hud", action="store_false")
    ap.add_argument("--cache-dir", default=None,
                    help="where to keep pre-rendered layers")
    ap.add_argument("--driver", default=None,
                    help="force an SDL video driver (e.g. kmsdrm on a headless Pi)")
    ap.add_argument("--socket", nargs="?", const=ipc.DEFAULT_SOCKET, default=None,
                    help="take state from the voice assistant over this unix "
                         f"socket (default {ipc.DEFAULT_SOCKET})")
    ap.add_argument("--sleep-after", type=float, default=IDLE_SLEEP_S,
                    help="seconds of no input before dozing off (0 disables)")
    args = ap.parse_args(argv)

    try:
        w, h = (int(v) for v in args.size.lower().split("x"))
    except ValueError:
        ap.error(f"bad --size {args.size!r}; expected WIDTHxHEIGHT")

    return run(fullscreen=args.fullscreen, size=(w, h), state=args.state,
               hud=args.hud, cache_dir=args.cache_dir, fps=args.fps,
               driver=args.driver, socket_path=args.socket,
               sleep_after=args.sleep_after)


if __name__ == "__main__":
    sys.exit(main())
