"""Easing curves. All take and return 0..1."""

import math


def linear(t):
    return t


def ease_in_out_sine(t):
    return 0.5 * (1.0 - math.cos(math.pi * t))


def ease_out_cubic(t):
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_cubic(t):
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - ((-2.0 * t + 2.0) ** 3) / 2.0


def ease_out_back(t, overshoot=1.70158):
    c3 = overshoot + 1.0
    return 1.0 + c3 * ((t - 1.0) ** 3) + overshoot * ((t - 1.0) ** 2)


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t
