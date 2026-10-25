"""Interval maths (standard library only)."""
from __future__ import annotations

import math


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval for k successes out of n. Returns (0, 0) for n == 0."""
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    lo = 0.0 if k == 0 else max(0.0, centre - half)
    hi = 1.0 if k == n else min(1.0, centre + half)
    return (lo, hi)


def summarize(k: int, n: int) -> dict:
    """Rate and Wilson interval; with no denominator there is no data (rate/ci95 are None, not 0%)."""
    if n <= 0:
        return {"k": k, "n": 0, "rate": None, "ci95": None, "no_data": True}
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": k / n, "ci95": [round(lo, 4), round(hi, 4)], "no_data": False}
