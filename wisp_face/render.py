"""Turn layer SVG into pygame surfaces, once, at startup.

Rasterising SVG is far too slow to do per frame on a Pi. Everything here runs
during ``WispFace`` construction and then never again: each layer (and each
pre-computed variant of it -- blink steps, mouth openings, halo pulse sizes)
becomes a plain surface that the render loop only has to blit.

Results are cached to disk as cropped PNGs, so the second startup skips
cairosvg entirely.
"""

import glob
import hashlib
import io
import os
import re

import pygame

_CAIRO_ERROR = (
    "cairosvg is required to pre-render Wisp's layers.\n"
    "  pip install cairosvg\n"
    "On Raspberry Pi OS you may also need: sudo apt install libcairo2"
)


def _cairosvg():
    try:
        import cairosvg
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(f"{_CAIRO_ERROR}\n\n(import failed: {exc})") from exc
    return cairosvg


def default_cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    return os.path.join(base, "wisp_face")


class LayerCache:
    """Rasterise SVG to cropped pygame surfaces, memoised on disk and in RAM.

    A layer is drawn on the full 200x240 canvas so every layer shares one
    coordinate system, then cropped to its opaque bounding box. The crop offset
    comes back with the surface, so compositing is just
    ``blit(surface, origin + offset)`` -- no per-layer coordinate maths and no
    wasted blitting of transparent pixels.
    """

    def __init__(self, canvas_px, cache_dir=None, use_disk=True, convert=True,
                 view=None):
        self.canvas_px = canvas_px
        # SVG user-space box this canvas represents. It must match the artwork
        # or cairosvg letterboxes it: the round display's 200x200 eyes drawn
        # into the body's 200x240 box come out 1.2x small and off-centre.
        self.view = view
        self.cache_dir = cache_dir or default_cache_dir()
        self.use_disk = use_disk
        self.convert = convert
        self._mem = {}
        self._rendered = 0
        self._from_disk = 0
        if self.use_disk:
            try:
                os.makedirs(self.cache_dir, exist_ok=True)
            except OSError:
                self.use_disk = False

    # -- stats -------------------------------------------------------------

    @property
    def stats(self):
        return {"rasterised": self._rendered, "from_disk": self._from_disk}

    # -- internals ---------------------------------------------------------

    def _key(self, svg):
        w, h = self.canvas_px
        vw, vh = self.view or (0, 0)
        digest = hashlib.sha1(
            f"{w}x{h}|{vw}x{vh}|{svg}".encode("utf-8")
        ).hexdigest()[:20]
        return digest

    def _disk_lookup(self, key):
        pattern = os.path.join(self.cache_dir, f"{key}_*.png")
        for path in glob.glob(pattern):
            m = re.search(r"_(-?\d+)_(-?\d+)\.png$", path)
            if not m:
                continue
            try:
                surf = pygame.image.load(path)
            except pygame.error:
                continue
            return surf, (int(m.group(1)), int(m.group(2)))
        return None

    def _disk_store(self, key, surface, offset):
        path = os.path.join(self.cache_dir, f"{key}_{offset[0]}_{offset[1]}.png")
        tmp = path + f".{os.getpid()}.tmp"
        try:
            pygame.image.save(surface, tmp)
            os.replace(tmp, path)
        except (pygame.error, OSError):
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def _rasterise(self, svg_inner):
        from .geometry import svg_doc

        w, h = self.canvas_px
        doc = svg_doc(svg_inner, w, h, view=self.view)
        png = _cairosvg().svg2png(
            bytestring=doc.encode("utf-8"), output_width=w, output_height=h
        )
        surf = pygame.image.load(io.BytesIO(png), "layer.png")
        return surf.convert_alpha() if _display_ready() else surf

    # -- public ------------------------------------------------------------

    def layer(self, svg_inner):
        """Return ``(surface, (offset_x, offset_y))`` for this layer markup."""
        key = self._key(svg_inner)
        hit = self._mem.get(key)
        if hit is not None:
            return hit

        got = self._disk_lookup(key) if self.use_disk else None
        if got is not None:
            surf, offset = got
            self._from_disk += 1
        else:
            full = self._rasterise(svg_inner)
            surf, offset = crop_to_content(full)
            self._rendered += 1
            if self.use_disk:
                self._disk_store(key, surf, offset)

        if self.convert and _display_ready():
            surf = surf.convert_alpha()
        self._mem[key] = (surf, offset)
        return surf, offset


def _display_ready():
    try:
        return pygame.display.get_init() and pygame.display.get_surface() is not None
    except pygame.error:
        return False


def crop_to_content(surface):
    """Crop to the opaque bounding box, returning the crop offset."""
    rect = surface.get_bounding_rect(min_alpha=1)
    if rect.width == 0 or rect.height == 0:
        # Fully transparent layer; keep a 1x1 stub so callers stay simple.
        stub = pygame.Surface((1, 1), pygame.SRCALPHA)
        return stub, (0, 0)
    cropped = pygame.Surface(rect.size, pygame.SRCALPHA)
    cropped.blit(surface, (0, 0), rect)
    return cropped, (rect.x, rect.y)


def scaled(surface, factor):
    """Smoothly scale a surface about its centre, returning surface + shift.

    The shift is how far the top-left corner moves, so the caller can keep the
    layer centred on the same point.
    """
    if factor == 1.0:
        return surface, (0, 0)
    w, h = surface.get_size()
    nw, nh = max(1, round(w * factor)), max(1, round(h * factor))
    out = pygame.transform.smoothscale(surface, (nw, nh))
    return out, ((w - nw) / 2.0, (h - nh) / 2.0)


def tinted(surface, alpha):
    """Copy with a per-surface alpha applied (0-255)."""
    out = surface.copy()
    out.set_alpha(int(max(0, min(255, alpha))))
    return out
