#!/usr/bin/env bash
#
# Set Wisp up on a Raspberry Pi so the face comes back on its own after a
# power cut.
#
#   ./deploy/install.sh                 # face only
#   ./deploy/install.sh --round         # also the 1.28" round LCD
#   ./deploy/install.sh --enable-gc9a01 # also add the overlay to config.txt
#   ./deploy/install.sh --dry-run       # print what it would do
#
# Nothing here reaches the network except pip. The one change made outside
# this checkout is the systemd units (and config.txt, only with
# --enable-gc9a01, and only after backing it up).

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO/.venv"
RUN_USER="${SUDO_USER:-$USER}"
SOCKET="/run/wisp/wisp-face.sock"
WANT_ROUND=0
WANT_OVERLAY=0
DRY=0

for arg in "$@"; do
  case "$arg" in
    --round)          WANT_ROUND=1 ;;
    --enable-gc9a01)  WANT_OVERLAY=1 ;;
    --dry-run)        DRY=1 ;;
    -h|--help)        sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1m==>\033[0m %s\n' "$*"; }
run()  { if [ "$DRY" = 1 ]; then printf '   would run: %s\n' "$*"; else "$@"; fi; }
sudo_() { if [ "$(id -u)" = 0 ]; then run "$@"; else run sudo "$@"; fi; }

# --- sanity ---------------------------------------------------------------

if [ ! -f "$REPO/assets/source/wisp_geometry.py" ]; then
  echo "Can't find assets/source/wisp_geometry.py -- run this from the checkout." >&2
  exit 1
fi

if ! grep -qi 'raspberry pi' /proc/device-tree/model 2>/dev/null; then
  echo "Note: this doesn't look like a Raspberry Pi. Continuing anyway."
fi

# --- dependencies ---------------------------------------------------------

say "Installing system packages"
sudo_ apt-get update
# libcairo2 is for cairosvg (startup only). The SDL packages let pygame open
# the DSI panel straight from the console, with no desktop running.
sudo_ apt-get install -y python3-venv python3-dev libcairo2 \
    libsdl2-2.0-0 libsdl2-image-2.0-0 libsdl2-ttf-2.0-0

say "Creating the virtualenv at $VENV"
run python3 -m venv "$VENV"
run "$VENV/bin/pip" install --upgrade pip
run "$VENV/bin/pip" install -e "$REPO"

say "Pre-rendering the layer cache"
# Otherwise the first boot pays for ~70 rasterisations before anything appears.
if [ "$DRY" = 0 ]; then
  SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
    "$VENV/bin/python" -c "
import pygame; pygame.init(); pygame.display.set_mode((8, 8))
from wisp_face.face import WispFace
from wisp_face.round_face import RoundFace
print('  face :', WispFace().cache.stats)
print('  round:', RoundFace().cache.stats)
"
fi

# --- framebuffer access for the round display -----------------------------

if [ "$WANT_ROUND" = 1 ]; then
  say "Adding $RUN_USER to the video group (needed to write /dev/fb1)"
  sudo_ usermod -aG video "$RUN_USER"
fi

if [ "$WANT_OVERLAY" = 1 ]; then
  CONFIG=/boot/firmware/config.txt
  [ -f "$CONFIG" ] || CONFIG=/boot/config.txt
  say "Enabling the gc9a01 overlay in $CONFIG"
  if grep -q '^dtoverlay=gc9a01' "$CONFIG" 2>/dev/null; then
    echo "   already there, leaving it alone"
  else
    sudo_ cp "$CONFIG" "$CONFIG.wisp-backup.$(date +%s)"
    echo "   backed up to $CONFIG.wisp-backup.*"
    if [ "$DRY" = 0 ]; then
      printf '\n# Wisp: 1.28" round GC9A01 LCD -> /dev/fb1\ndtparam=spi=on\ndtoverlay=gc9a01\n' \
        | sudo tee -a "$CONFIG" >/dev/null
    else
      echo "   would append dtparam=spi=on + dtoverlay=gc9a01"
    fi
    echo "   takes effect after a reboot"
  fi
fi

# --- systemd --------------------------------------------------------------

say "Writing systemd units"

write_unit() {
  local name="$1" desc="$2" exec="$3" extra="$4"
  local unit="/etc/systemd/system/$name"
  local body
  body=$(cat <<UNIT
[Unit]
Description=$desc
After=multi-user.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$REPO
RuntimeDirectory=wisp
RuntimeDirectoryMode=0755
Environment=WISP_ASSETS=$REPO/assets
Environment=SDL_AUDIODRIVER=dummy
$extra
ExecStart=$exec
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT
)
  if [ "$DRY" = 1 ]; then
    printf '   would write %s:\n%s\n' "$unit" "$body"
  else
    printf '%s\n' "$body" | sudo tee "$unit" >/dev/null
    echo "   wrote $unit"
  fi
}

# kmsdrm draws straight to the DSI panel with no desktop session. If you do
# run a desktop, drop this line and the unit will use the default driver.
write_unit wisp-face.service "Wisp animated face" \
  "$VENV/bin/wisp-face --fullscreen --socket $SOCKET" \
  "Environment=SDL_VIDEODRIVER=kmsdrm"

if [ "$WANT_ROUND" = 1 ]; then
  write_unit wisp-round.service "Wisp round display (GC9A01)" \
    "$VENV/bin/wisp-round --socket $SOCKET --device /dev/fb1" \
    "SupplementaryGroups=video"
fi

sudo_ systemctl daemon-reload
sudo_ systemctl enable wisp-face.service
[ "$WANT_ROUND" = 1 ] && sudo_ systemctl enable wisp-round.service

say "Done"
cat <<EOF

  Start it now:      sudo systemctl start wisp-face
  Watch the logs:    journalctl -u wisp-face -f
  Stop it:           sudo systemctl stop wisp-face

  The assistant talks to it on $SOCKET. Point the bridge at the same path:

      export WISP_HOME=$REPO
      export WISP_SOCKET=$SOCKET

  See integration/README.md for patching agent.py.
EOF

if [ "$WANT_ROUND" = 1 ]; then
  echo "  Group change needs a fresh login (or a reboot) to take effect."
fi
if [ "$WANT_OVERLAY" = 1 ]; then
  echo "  Reboot for the gc9a01 overlay, then check: ls /dev/fb1"
fi
