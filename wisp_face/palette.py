"""Wisp colour palette.

Straight from the asset pack README. These are the only colours allowed
anywhere in the renderer.
"""

INK = "#0E1320"        # background, eyes
DUSK = "#161D2E"       # cards, surfaces
GLOW = "#7FE3D6"       # the light, main colour
CORE = "#F4FFFD"       # hot centre, highlights
DEEP_TEAL = "#1F8F86"  # body edge
EMBER = "#FFB86B"      # success moments only


def rgb(hex_colour):
    """'#7FE3D6' -> (127, 227, 214)."""
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


INK_RGB = rgb(INK)
DUSK_RGB = rgb(DUSK)
GLOW_RGB = rgb(GLOW)
CORE_RGB = rgb(CORE)
DEEP_TEAL_RGB = rgb(DEEP_TEAL)
EMBER_RGB = rgb(EMBER)
