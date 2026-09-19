# Hooking Wisp into be-more-agent

Target: [`brenpoly/be-more-agent`](https://github.com/brenpoly/be-more-agent)
at commit `5fb7558` (2026-04-10). All line numbers below are from that commit's
`agent.py`.

## What I read first

`agent.py` is a single 1081-line Tkinter app. The face is already there: a
`tk.Label` filled with PNG frames from `faces/<state>/*.png`, cycled by
`update_animation()` on a `master.after()` timer — 500 ms per frame normally,
50 ms while speaking.

The state machine is clean and there is exactly one choke point:

| What | Where | Notes |
|---|---|---|
| `class BotStates` | line 159 | Seven states: idle, listening, thinking, speaking, error, capturing, warmup |
| `BotGUI.set_state(state, msg, cam_path)` | line 402 | **Every** state change goes through here |
| `self.current_volume = np.max(np.abs(audio_chunk))` | line 1004 | Inside `speak()`, per audio chunk, int16 peak straight off Piper |
| `load_animations()` / `update_animation()` | lines 364, 383 | The built-in PNG face |
| `handle_ptt_toggle` / `handle_speaking_interrupt` | lines 338, 353 | Bound to `<Return>` and `<space>` on the Tk root |
| `safe_exit()` | line 293 | Shutdown |

## The one real problem

`agent.py` owns a **fullscreen Tkinter window** at 800x480. Wisp is pygame.
Two toolkits cannot share one window, and there's no good way around it:

- Rendering Wisp into the existing `tk.Label` means building an 800x480
  `ImageTk.PhotoImage` every frame. That's ~10-20 ms each on a Pi — 30-60% of
  a core at 30 fps, against a 15% budget. (It's why the built-in face only runs
  at 2 fps.)
- Embedding via `SDL_WINDOWID` is X11-only and fragile.

So **Wisp runs as its own process** and the agent pushes state to it over a
unix socket. That also means the face keeps 30 fps while the agent is blocked
in Ollama or Piper, which the in-process approach could never do.

The catch: if Wisp owns the screen, the Tk window loses focus, and PTT
(`<Return>`) and interrupt (`<space>`) are Tk key bindings. So the link is
**duplex** — state and mouth level go agent → face, key presses come back
face → agent. Nothing is lost.

```
agent.py ──{"t":"state","v":"listening"}──▶  wisp_face
         ──{"t":"mouth","v":0.73}────────▶  (owns the screen)
         ◀─{"t":"key","v":"ptt"}─────────
```

Wake-word detection is audio on a background thread, so it never cared about
window focus and keeps working regardless.

## Where the hooks go

Six edits, 34 added lines, all in `agent.py`. See `be-more-agent.patch`.

1. **line 47** — `from wisp_bridge import WispBridge`, plus a `WISP` env switch.
2. **line 278** — create the bridge; when it's live, withdraw the Tk window and
   skip `load_animations()`/`update_animation()` entirely.
3. **line 353** — `_wisp_key()`, which bounces forwarded keys back onto the Tk
   thread via `master.after(0, ...)`.
4. **line 402** — `set_state()` calls `self.wisp.set_state(state, msg)` *before*
   the `master.after` block, so the face reacts immediately rather than
   whenever Tk next gets a slice.
5. **line 1004** — `speak()` pushes `current_volume` to `set_volume()`, plus the
   two places it resets to 0.
6. **line 293** — `safe_exit()` closes the link.

## State mapping

Seven agent states, six Wisp states. Two have to borrow:

| BotStates | Wisp | Why |
|---|---|---|
| `idle` | idle | |
| `listening` | listening | |
| `thinking` | thinking | |
| `speaking` | speaking | |
| `warmup` | thinking | Models are loading; Wisp is busy |
| `capturing` | listening | Camera is up, Wisp is paying attention |
| `error` | idle | Wisp has no error face, and the agent's own status line already says what broke |

Edit `STATE_MAP` in `wisp_bridge.py` if you'd rather they went elsewhere.

### The two states the agent never sends

The asset pack's state table wants `happy` on "task done" and `sleepy` after
"no input for 10+ min". Neither needed a change to `agent.py`:

- **happy** — the agent lands on `set_state(IDLE, "Ready")` exactly when a turn
  finishes cleanly (its other idle messages are "Interrupted.", "Heard
  nothing.", "Memory Wiped", "Resetting..."). The bridge grins for 1.4 s on
  that one message, then settles. It's a string match, which is why it's a
  named constant — `HAPPY_ON_IDLE_MESSAGES`.
- **sleepy** — the face times its own silence. `--sleep-after` (default 600 s).
  Anything at all wakes it.

## Mouth level

Piper streams signed 16-bit PCM, so `current_volume` is a 0–32767 peak. Speech
rarely peaks at full scale, so the bridge divides by `32767 * 0.45` and clamps —
otherwise normal talking only ever uses the bottom third of the mouth's range.
`MOUTH_HEADROOM` is the knob.

Identical consecutive values aren't resent; `speak()` calls this on every 4096
byte chunk.

## Installing

```bash
cd /path/to/be-more-agent
patch -p1 < /path/to/wisp/integration/be-more-agent.patch
cp /path/to/wisp/integration/wisp_bridge.py .
export WISP_HOME=/path/to/wisp        # so wisp_bridge can import wisp_face
```

Then run the face first, the agent second (order doesn't actually matter — the
bridge reconnects):

```bash
python /path/to/wisp/run_face.py --fullscreen --socket &
python agent.py
```

To back out, `WISP=0 python agent.py` restores the original PNG face without
reverting the patch.

## If it isn't working

- `[WISP] wisp_face not importable` — set `WISP_HOME`.
- Face stays idle — check the agent is connected; the face's HUD (`H`) shows
  `link  agent connected`.
- Face doesn't start: `another Wisp face is already using ...` means a previous
  run is still up.
- Mouth barely moves — lower `MOUTH_HEADROOM` in `wisp_bridge.py`.
- PTT does nothing — the Wisp window needs focus, since it's the one on screen.
