# The site

Deployed to <https://wisp-two-tau.vercel.app> from this directory. The Vercel
project is linked to the repo, so **pushing to `main` deploys it** — there's no
build step, Vercel just serves these files.

## What it is

A sprite-sheet player, not a video. It reads `sprites/sprites.json` and steps
`background-position` across each sheet — the same way the phone app will
consume them. So the page is also a check on the export: if a loop hitches
here, it hitches there.

## Regenerating the sprites

These aren't the same sheets as `export_sprites.py` produces by default. The
web ones are cropped to the character, smaller, and WebP:

```bash
python export_sprites.py \
    --out web/sprites \
    --scale 0.62 --fps 20 \
    --transparent --crop \
    --format webp --no-gif
```

Why each flag:

| | |
|---|---|
| `--crop` | trims to the character. Uncropped frames are the whole 800x480 screen, so Wisp ends up tiny in a sea of empty background. |
| `--transparent` | lets the page's own background show through. |
| `--format webp` | the gradients compress badly as PNG — the listening sheet is 1.5 MB as PNG and 278 KB as WebP. |
| `--scale 0.62` | big enough to stay crisp when the hero scales it up, small enough to keep the whole set around 2 MB. |
| `--fps 20` | 30 would be smoother and half again as heavy; 20 reads fine for a loop. |

The player re-reads `frame_size`, `grid`, `frames` and `fps` from the manifest,
so changing any of those flags needs no edit to `index.html`.

`demo-round.gif` is copied from `docs/`, which `tools/make_demos.py` renders.

## Caching

`vercel.json` marks `/sprites/*` immutable for a year. The filenames don't
carry a hash, so if you regenerate the sheets and the old ones seem stuck,
that's why — hard-reload, or rename them.
