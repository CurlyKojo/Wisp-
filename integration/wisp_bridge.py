"""Drop-in bridge from be-more-agent to Wisp's face.

Copy this next to ``agent.py``. It translates that project's ``BotStates``
into Wisp's six states and pushes them to the face process.

Deliberately forgiving: if the face isn't running, or the wisp package isn't
importable, every call here turns into a no-op. The assistant must never fail
because its face is missing.
"""

import os
import sys
import threading

# The face package normally sits beside this file's repo. Set WISP_HOME if it
# lives somewhere else.
_WISP_HOME = os.environ.get("WISP_HOME")
if _WISP_HOME and _WISP_HOME not in sys.path:
    sys.path.insert(0, _WISP_HOME)

try:
    from wisp_face.ipc import DEFAULT_SOCKET, KEY_INTERRUPT, KEY_PTT, WispLink
    _AVAILABLE = True
except ImportError:  # pragma: no cover - depends on deployment layout
    _AVAILABLE = False
    DEFAULT_SOCKET = None
    KEY_PTT = "ptt"
    KEY_INTERRUPT = "interrupt"
    WispLink = None


# be-more-agent has seven states; Wisp has six. Two of the agent's states have
# no Wisp equivalent, so they borrow the nearest one that reads correctly:
#
#   warmup    -> thinking   models are loading, so Wisp is busy
#   capturing -> listening  camera is up and Wisp is paying attention
#   error     -> idle       Wisp has no error face, and the agent's own status
#                           line already says what broke
#
# Edit this if you'd rather they went somewhere else.
STATE_MAP = {
    "idle": "idle",
    "listening": "listening",
    "thinking": "thinking",
    "speaking": "speaking",
    "warmup": "thinking",
    "capturing": "listening",
    "error": "idle",
}

# Wisp's "happy" is for "task done" (see the pack's state table). The agent
# never emits it, but it does land on IDLE with one of these messages exactly
# when a turn has finished cleanly -- which is the same moment.
HAPPY_ON_IDLE_MESSAGES = {"Ready"}
HAPPY_HOLD_S = 1.4

# Piper streams signed 16-bit audio, so this is full scale for the mouth.
INT16_FULL_SCALE = 32767.0
# Speech rarely peaks at full scale; dividing by this makes normal talking use
# the whole range instead of a thin sliver at the bottom.
MOUTH_HEADROOM = 0.45


class WispBridge:
    """Everything agent.py needs, behind four methods."""

    def __init__(self, socket_path=None, enabled=True, on_key=None):
        self.enabled = bool(enabled) and _AVAILABLE
        self._link = None
        self._happy_timer = None
        self._on_key = on_key
        if not self.enabled:
            if enabled and not _AVAILABLE:
                print("[WISP] wisp_face not importable; face disabled. "
                      "Set WISP_HOME to the wisp checkout.", flush=True)
            return
        self._link = WispLink(socket_path or DEFAULT_SOCKET, on_key=self._key)
        print(f"[WISP] face link on {socket_path or DEFAULT_SOCKET}", flush=True)

    # -- from agent.py -------------------------------------------------

    def set_state(self, bot_state, msg=""):
        """Call from BotGUI.set_state, with the same arguments."""
        if not self.enabled:
            return
        self._cancel_happy()
        if bot_state == "idle" and msg in HAPPY_ON_IDLE_MESSAGES:
            # Grin, then settle back to idle.
            self._link.set_state("happy")
            self._happy_timer = threading.Timer(
                HAPPY_HOLD_S, self._settle
            )
            self._happy_timer.daemon = True
            self._happy_timer.start()
            return
        self._link.set_state(STATE_MAP.get(bot_state, "idle"))

    def set_volume(self, peak_int16):
        """Call from speak(), with the raw int16 peak of the audio chunk."""
        if not self.enabled:
            return
        try:
            level = float(peak_int16) / (INT16_FULL_SCALE * MOUTH_HEADROOM)
        except (TypeError, ValueError):
            return
        self._link.set_mouth_level(min(1.0, max(0.0, level)))

    def close(self):
        self._cancel_happy()
        if self._link is not None:
            self._link.close()
            self._link = None

    # -- internals -----------------------------------------------------

    def _settle(self):
        self._happy_timer = None
        if self._link is not None:
            self._link.set_state("idle")

    def _cancel_happy(self):
        if self._happy_timer is not None:
            self._happy_timer.cancel()
            self._happy_timer = None

    def _key(self, name):
        """Keys forwarded from the face window back to the agent."""
        if self._on_key:
            self._on_key(name)
