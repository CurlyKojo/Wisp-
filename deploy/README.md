# Running Wisp on the Pi

```bash
git clone https://github.com/CurlyKojo/Wisp-.git ~/wisp
cd ~/wisp
./deploy/install.sh --round --enable-gc9a01
sudo systemctl start wisp-face
```

Drop `--round` if you're not using the 1.28" LCD, and `--enable-gc9a01` if
you'd rather edit `config.txt` yourself. `--dry-run` prints every change first.

## What it does

1. Installs `libcairo2` (for cairosvg, startup only) and the SDL2 libraries
   that let pygame drive the DSI panel with no desktop running.
2. Makes a venv at `.venv` and installs this checkout into it.
3. **Pre-renders the layer cache.** Without this the first boot spends its
   first second rasterising ~70 layers before anything shows up.
4. Writes `wisp-face.service` (and `wisp-round.service`), enables them, and
   points both at the same socket.

The units run as your user, not root, with `Restart=always`. The socket lives
in `/run/wisp`, created by systemd's `RuntimeDirectory`.

## Display

`wisp-face.service` sets `SDL_VIDEODRIVER=kmsdrm`, which draws straight to the
DSI panel from the console — no X, no Wayland, no desktop session. If you *do*
boot to a desktop, delete that line from the unit and let SDL pick.

The round display needs group `video` to write `/dev/fb1`; the installer adds
you, but group changes only apply after a fresh login.

## Checking it

```bash
systemctl status wisp-face
journalctl -u wisp-face -f       # startup prints the cache stats
```

`Ready in 0.05s (0 rasterised, 71 cached)` means the cache is warm. If it says
`71 rasterised` every boot the cache directory isn't writable.

## Connecting the assistant

```bash
export WISP_HOME=~/wisp
export WISP_SOCKET=/run/wisp/wisp-face.sock
```

Then patch `agent.py` per [`../integration/README.md`](../integration/README.md).
`WISP=0` disables the face without unpatching.

## Uninstalling

```bash
sudo systemctl disable --now wisp-face wisp-round
sudo rm /etc/systemd/system/wisp-{face,round}.service
sudo systemctl daemon-reload
```

`config.txt` is backed up to `config.txt.wisp-backup.*` before the overlay is
added, if you used `--enable-gc9a01`.
