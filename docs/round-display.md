# The 1.28" round display (GC9A01, 240x240)

## Which driver, and why

Short version: **don't use a Python SPI library.** Use the kernel's device-tree
overlay and write to the framebuffer.

The obvious candidates all fail on a Pi 5:

| Option | Verdict |
|---|---|
| `luma.lcd` | Doesn't support GC9A01 at all — it covers PCD8544, HD44780, HT1621, ST7735, ST7789, ST7567, UC1701X and ILI9341. |
| Anything on `RPi.GPIO` | `RPi.GPIO` does not work on a Pi 5. The RP1 southbridge needs different kernel drivers and RPi.GPIO was never ported. |
| `gpiozero` + `lgpio` | These *do* work on a Pi 5 (with the lgpio pin factory, `/dev/gpiochip4`), but there's still no GC9A01 panel driver on top of them. |
| MicroPython GC9A01 drivers | Most search results are these. They don't run on CPython. |
| **`gc9a01` dtoverlay** | **Works.** Kernel `mipi-dbi-spi` DRM driver, panel shows up as `/dev/fb1`. |

So `wisp_face/round_face.py` contains no SPI or GPIO code at all. It renders to
a 240x240 surface, converts to RGB565 (pygame hands that back natively from a
16-bit surface) and writes the bytes to `/dev/fb1`. No new dependencies.

## Wiring

The overlay expects SPI0 plus three control pins:

| Signal | GPIO | Header pin |
|---|---|---|
| DIN / MOSI | 10 | 19 |
| CLK | 11 | 23 |
| CS | 8 | 24 |
| DC | 25 | 22 |
| RST | 27 | 13 |
| BL (backlight) | 18 | 12 |

## Setup

Add to `/boot/firmware/config.txt`:

```
dtparam=spi=on
dtoverlay=gc9a01
```

Parameters the overlay accepts: `speed`, `rotate` (0/90/180/270), `width`,
`height`, `fps`, `debug`. If Wisp comes up rotated, fix it here rather than in
the renderer:

```
dtoverlay=gc9a01,rotate=180,speed=40000000
```

Reboot, then check it came up:

```bash
ls /dev/fb1
cat /sys/class/graphics/fb1/virtual_size     # 240,240
cat /sys/class/graphics/fb1/bits_per_pixel   # 16
cat /dev/urandom > /dev/fb1                  # should fill with noise
```

If `/dev/fb1` doesn't exist, the overlay didn't load — check SPI is enabled and
that your kernel ships the overlay (`ls /boot/firmware/overlays/gc9a01.dtbo`).

## Running

```bash
python -m wisp_face.round_face --socket          # takes state from the agent
python -m wisp_face.round_face --device /dev/fb2 # if it landed elsewhere
```

Writing to `/dev/fb1` normally needs group `video`:

```bash
sudo usermod -aG video $USER    # log out and back in
```

## Running both screens together

Both the 5" panel and the round LCD can run off one state machine, so they
blink at the same instant:

```python
from wisp_face.face import WispFace
from wisp_face.round_face import RoundFace, Framebuffer

big = WispFace()
small = RoundFace(mirror=big)     # shares big's clock and state
```

`small.set_state(...)` routes back through `big`, so there's still only one
place state lives.
