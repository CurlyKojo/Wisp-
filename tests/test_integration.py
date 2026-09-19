"""End-to-end check of the agent <-> face link.

Runs the real socket, the real bridge and a real WispFace -- no mocks -- so it
catches the things that actually break in deployment: threading, reconnects,
and the state name mismatch between the two projects.
"""

import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "integration"))

import pygame  # noqa: E402

from wisp_face import geometry as geo  # noqa: E402
from wisp_face import ipc  # noqa: E402
from wisp_face.face import WispFace  # noqa: E402
from wisp_bridge import STATE_MAP, WispBridge  # noqa: E402

SOCK = "/tmp/wisp-test-%d.sock" % os.getpid()


def _settle(pred, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_state_map_covers_every_bot_state():
    """The seven BotStates in agent.py must all land somewhere real."""
    bot_states = {"idle", "listening", "thinking", "speaking",
                  "error", "capturing", "warmup"}
    assert set(STATE_MAP) == bot_states, set(STATE_MAP) ^ bot_states
    for target in STATE_MAP.values():
        assert target in geo.STATES, target


def test_agent_states_reach_the_face():
    seen = []
    server = ipc.WispServer(SOCK, on_state=seen.append, on_mouth=lambda v: None)
    bridge = WispBridge(socket_path=SOCK)
    try:
        assert _settle(lambda: server.client_count == 1), "bridge never connected"
        for bot_state in ("listening", "thinking", "speaking", "capturing",
                          "warmup", "error"):
            bridge.set_state(bot_state, "")
        assert _settle(lambda: len(seen) == 6), seen
        assert seen == ["listening", "thinking", "speaking",
                        "listening", "thinking", "idle"], seen
    finally:
        bridge.close()
        server.close()


def test_finished_turn_shows_happy_then_settles():
    """Wisp's 'happy' is for task done; the agent signals that as IDLE/Ready."""
    seen = []
    server = ipc.WispServer(SOCK, on_state=seen.append, on_mouth=lambda v: None)
    bridge = WispBridge(socket_path=SOCK)
    try:
        assert _settle(lambda: server.client_count == 1)
        import wisp_bridge
        wisp_bridge.HAPPY_HOLD_S = 0.15
        bridge.set_state("idle", "Ready")
        assert _settle(lambda: seen == ["happy"]), seen
        assert _settle(lambda: seen == ["happy", "idle"], timeout=2.0), seen
        # A plain idle (not a finished turn) must not grin.
        seen.clear()
        bridge.set_state("idle", "Interrupted.")
        assert _settle(lambda: seen == ["idle"]), seen
    finally:
        bridge.close()
        server.close()


def test_tts_volume_drives_the_mouth():
    levels = []
    server = ipc.WispServer(SOCK, on_state=lambda v: None, on_mouth=levels.append)
    bridge = WispBridge(socket_path=SOCK)
    try:
        assert _settle(lambda: server.client_count == 1)
        bridge.set_volume(0)
        bridge.set_volume(32767)       # full scale
        bridge.set_volume(4000)        # quiet speech
        assert _settle(lambda: len(levels) == 3), levels
        assert levels[0] == 0.0
        assert levels[1] == 1.0
        assert 0.0 < levels[2] < 1.0
        # Normal speech shouldn't be stuck near the bottom of the range.
        assert levels[2] > 0.15, levels[2]
    finally:
        bridge.close()
        server.close()


def test_repeated_volume_is_not_resent():
    """speak() calls this per audio chunk; identical values shouldn't spam."""
    levels = []
    server = ipc.WispServer(SOCK, on_state=lambda v: None, on_mouth=levels.append)
    bridge = WispBridge(socket_path=SOCK)
    try:
        assert _settle(lambda: server.client_count == 1)
        for _ in range(50):
            bridge.set_volume(8000)
        bridge.set_volume(0)
        assert _settle(lambda: len(levels) == 2, timeout=1.5), levels
    finally:
        bridge.close()
        server.close()


def test_keys_travel_back_from_the_face():
    """The face owns the screen on the Pi, so PTT has to come back to us."""
    got = []
    server = ipc.WispServer(SOCK)
    bridge = WispBridge(socket_path=SOCK, on_key=got.append)
    try:
        assert _settle(lambda: server.client_count == 1)
        server.send_key(ipc.KEY_PTT)
        server.send_key(ipc.KEY_INTERRUPT)
        assert _settle(lambda: got == [ipc.KEY_PTT, ipc.KEY_INTERRUPT]), got
    finally:
        bridge.close()
        server.close()


def test_bridge_survives_a_missing_face():
    """The assistant must keep working when the face isn't running."""
    bridge = WispBridge(socket_path="/tmp/wisp-definitely-not-here.sock")
    try:
        for _ in range(20):
            bridge.set_state("listening", "")
            bridge.set_volume(12345)
        assert not bridge._link.connected
    finally:
        bridge.close()


def test_bridge_reconnects_when_the_face_comes_back():
    bridge = WispBridge(socket_path=SOCK)
    seen = []
    try:
        # Face starts late, as it would if the agent booted first.
        time.sleep(0.1)
        server = ipc.WispServer(SOCK, on_state=seen.append)
        try:
            assert _settle(lambda: server.client_count == 1, timeout=6.0), \
                "bridge never reconnected"
            bridge.set_state("thinking", "")
            assert _settle(lambda: seen == ["thinking"]), seen
        finally:
            server.close()
    finally:
        bridge.close()


def test_face_applies_states_from_the_link():
    """The whole chain: bridge -> socket -> queue -> WispFace."""
    import collections
    pygame.init()
    screen = pygame.display.set_mode((800, 480))
    face = WispFace()
    inbox = collections.deque()
    server = ipc.WispServer(
        SOCK,
        on_state=lambda v: inbox.append(("state", v)),
        on_mouth=lambda v: inbox.append(("mouth", v)),
    )
    bridge = WispBridge(socket_path=SOCK)
    try:
        assert _settle(lambda: server.client_count == 1)
        bridge.set_state("listening", "")
        bridge.set_volume(20000)
        assert _settle(lambda: len(inbox) >= 2), list(inbox)
        while inbox:
            kind, value = inbox.popleft()
            if kind == "state":
                face.set_state(value)
            else:
                face.set_mouth_level(value)
        for _ in range(10):
            face.render(screen, 1 / 30)
        assert face.state == "listening"
        assert face.motion.params("listening").mouth > 0.5
    finally:
        bridge.close()
        server.close()


def test_a_second_face_refuses_the_same_socket():
    server = ipc.WispServer(SOCK)
    try:
        try:
            ipc.WispServer(SOCK)
        except RuntimeError:
            return
        raise AssertionError("two faces bound the same socket")
    finally:
        server.close()


def test_stale_socket_file_is_cleared():
    path = SOCK + ".stale"
    open(path, "w").close()          # leftover from a crash
    server = ipc.WispServer(path)
    try:
        assert ipc.wait_for(path, timeout=2.0)
    finally:
        server.close()


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
    for leftover in (SOCK, SOCK + ".stale"):
        try:
            os.unlink(leftover)
        except OSError:
            pass
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
