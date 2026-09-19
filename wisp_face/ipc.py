"""A tiny local link between the voice assistant and the face.

Standard library only, on purpose: the agent side of this gets imported into
be-more-agent's ``agent.py``, which must not grow a dependency on pygame or
cairosvg just to say "I'm listening now".

Why a socket at all: ``agent.py`` is a Tkinter app that owns a fullscreen
800x480 window, and Wisp is pygame. Two toolkits cannot share one window, and
running the face inside Tk means re-uploading an 800x480 PhotoImage every
frame, which will not hold 30 fps on a Pi. So the face runs as its own process
and the agent pushes state to it.

The link is duplex. State and mouth level go agent -> face; key presses go
face -> agent, so the face can own the screen and the keyboard while the
agent keeps its push-to-talk and interrupt bindings working.

Protocol: newline-delimited JSON over a unix domain socket. No network, ever.

    {"t": "state", "v": "listening"}
    {"t": "mouth", "v": 0.73}
    {"t": "key",   "v": "ptt"}
"""

import json
import os
import socket
import threading
import time

DEFAULT_SOCKET = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "wisp-face.sock"
)

# Keys the face can forward back to the agent.
KEY_PTT = "ptt"
KEY_INTERRUPT = "interrupt"
KEY_QUIT = "quit"


def _send_line(sock, obj):
    sock.sendall((json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8"))


class _LineReader:
    """Buffers a socket into complete JSON lines."""

    def __init__(self):
        self.buf = b""

    def feed(self, chunk):
        self.buf += chunk
        out = []
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line.decode("utf-8")))
            except (ValueError, UnicodeDecodeError):
                continue  # ignore junk rather than kill the link
        return out


class WispLink:
    """Agent side. Fire-and-forget; never blocks and never raises.

    If the face isn't running yet, or dies, calls quietly no-op and the link
    reconnects in the background. Losing the face must never take down the
    assistant.
    """

    def __init__(self, path=DEFAULT_SOCKET, on_key=None, retry_s=2.0):
        self.path = path
        self.on_key = on_key
        self.retry_s = retry_s
        self._sock = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._last_mouth = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # -- public --------------------------------------------------------

    @property
    def connected(self):
        return self._sock is not None

    def set_state(self, state):
        self._send({"t": "state", "v": str(state)})

    def set_mouth_level(self, level):
        try:
            level = round(float(level), 3)
        except (TypeError, ValueError):
            return
        level = 0.0 if level < 0.0 else 1.0 if level > 1.0 else level
        # The TTS loop calls this per audio chunk; skip no-op traffic.
        if level == self._last_mouth:
            return
        self._last_mouth = level
        self._send({"t": "mouth", "v": level})

    def close(self):
        self._stop.set()
        self._drop()

    # -- internals -----------------------------------------------------

    def _send(self, obj):
        with self._lock:
            sock = self._sock
            if sock is None:
                return
            try:
                _send_line(sock, obj)
            except OSError:
                self._drop_locked()

    def _drop(self):
        with self._lock:
            self._drop_locked()

    def _drop_locked(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
            self._last_mouth = None

    def _run(self):
        reader = _LineReader()
        while not self._stop.is_set():
            if self._sock is None:
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.settimeout(1.0)
                    s.connect(self.path)
                    with self._lock:
                        self._sock = s
                    reader = _LineReader()
                except OSError:
                    self._stop.wait(self.retry_s)
                    continue
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    self._drop()
                    self._stop.wait(self.retry_s)
                    continue
                for msg in reader.feed(chunk):
                    if msg.get("t") == "key" and self.on_key:
                        try:
                            self.on_key(msg.get("v"))
                        except Exception:
                            pass
            except socket.timeout:
                continue
            except OSError:
                self._drop()
                self._stop.wait(self.retry_s)


class WispServer:
    """Face side. Accepts agent connections and dispatches their messages.

    Callbacks fire on the server thread, so they must be cheap and thread
    safe; ``WispFace.set_state``/``set_mouth_level`` only assign, which is
    fine under CPython.
    """

    def __init__(self, path=DEFAULT_SOCKET, on_state=None, on_mouth=None):
        self.path = path
        self.on_state = on_state
        self.on_mouth = on_mouth
        self._clients = []
        self._lock = threading.Lock()
        self._stop = threading.Event()

        if os.path.exists(path):
            # A stale socket from a crashed run would block bind().
            try:
                probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                probe.settimeout(0.2)
                probe.connect(path)
                probe.close()
                raise RuntimeError(f"another Wisp face is already using {path}")
            except (ConnectionRefusedError, socket.timeout, FileNotFoundError):
                os.unlink(path)
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(path)
        self._srv.listen(4)
        self._srv.settimeout(0.5)
        os.chmod(path, 0o600)

        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    @property
    def client_count(self):
        with self._lock:
            return len(self._clients)

    def send_key(self, name):
        """Forward a key press to every connected agent."""
        dead = []
        with self._lock:
            clients = list(self._clients)
        for sock in clients:
            try:
                _send_line(sock, {"t": "key", "v": name})
            except OSError:
                dead.append(sock)
        if dead:
            with self._lock:
                for sock in dead:
                    if sock in self._clients:
                        self._clients.remove(sock)

    def close(self):
        self._stop.set()
        try:
            self._srv.close()
        except OSError:
            pass
        with self._lock:
            for sock in self._clients:
                try:
                    sock.close()
                except OSError:
                    pass
            self._clients = []
        try:
            os.unlink(self.path)
        except OSError:
            pass

    # -- internals -----------------------------------------------------

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                sock, _ = self._srv.accept()
            except (socket.timeout, OSError):
                continue
            sock.settimeout(0.5)
            with self._lock:
                self._clients.append(sock)
            threading.Thread(
                target=self._client_loop, args=(sock,), daemon=True
            ).start()

    def _client_loop(self, sock):
        reader = _LineReader()
        try:
            while not self._stop.is_set():
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                for msg in reader.feed(chunk):
                    kind, value = msg.get("t"), msg.get("v")
                    try:
                        if kind == "state" and self.on_state:
                            self.on_state(value)
                        elif kind == "mouth" and self.on_mouth:
                            self.on_mouth(value)
                    except Exception:
                        pass  # a bad message must not kill the face
        finally:
            with self._lock:
                if sock in self._clients:
                    self._clients.remove(sock)
            try:
                sock.close()
            except OSError:
                pass


def wait_for(path=DEFAULT_SOCKET, timeout=5.0):
    """Block until a face is listening on ``path``. Returns True if it is."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.2)
            s.connect(path)
            s.close()
            return True
        except OSError:
            time.sleep(0.05)
    return False
