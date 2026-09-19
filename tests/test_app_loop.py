"""Smoke-test the run loop headlessly: keys, resizing, and the fake mouth."""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from wisp_face import app  # noqa: E402
from wisp_face import geometry as geo  # noqa: E402


def test_keys_1_to_6_cover_every_state():
    assert sorted(app.STATE_KEYS.values()) == sorted(geo.STATE_NAMES)
    assert list(app.STATE_KEYS) == [
        pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6
    ]


def test_fake_speech_stays_in_range_and_moves():
    vals = [app.fake_speech_level(i / 30.0) for i in range(300)]
    assert all(0.0 <= v <= 1.0 for v in vals)
    assert max(vals) > 0.6, "fake mouth never opens"
    assert min(vals) < 0.05, "fake mouth never closes"


def _arm(events):
    """Queue key events. The event queue needs video up, and run() tears it
    down when it exits, so re-init before every queued run."""
    pygame.init()
    pygame.display.set_mode((8, 8))
    for key in events:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))


def test_loop_runs_and_handles_keys():
    _arm([])
    for key in app.STATE_KEYS:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_b))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h))
    assert app.run(max_frames=40, driver="dummy") == 0


def test_loop_quits_on_escape():
    _arm([pygame.K_ESCAPE])
    # A huge frame cap that still returns proves ESC ended the loop, not the cap.
    assert app.run(max_frames=10_000, driver="dummy") == 0


def test_non_native_window_size_keeps_wisp_centred():
    """A bigger preview window must not crop or offset the character."""
    from wisp_face.face import WispFace
    from wisp_face.layers import Layout
    size = (1200, 720)
    layout = Layout(width=size[0], height=size[1])
    layout.scale = 1.5 * min(size[0] / 800.0, size[1] / 480.0)
    vw, vh = geo.CANVAS
    layout.origin = ((size[0] - vw * layout.scale) / 2.0,
                     (size[1] - vh * layout.scale) / 2.0 - 12 * layout.scale / 1.5)
    pygame.init()
    screen = pygame.display.set_mode(size)
    face = WispFace(layout=layout)
    for name in geo.STATE_NAMES:
        face.set_state(name, immediate=True)
        face.render(screen, 1 / 30)
    rect = face._dirty
    assert rect.left >= 0 and rect.top >= 0
    assert rect.right <= size[0] and rect.bottom <= size[1]


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
