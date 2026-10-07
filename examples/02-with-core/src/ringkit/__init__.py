"""ringkit -- the pure-Python core behind the Ring Points component.

No Rhino imports: it runs and is tested anywhere, and Grasshopper only ever
receives its results. Must stay compatible with Python 3.9 (Rhino 8's CPython).
"""

import math
from typing import List, Tuple

__all__ = ["ring_points"]

Point = Tuple[float, float, float]


def ring_points(radius: float, count: int, z: float = 0.0) -> List[Point]:
    """``count`` points evenly spaced on a circle of ``radius`` at height ``z``."""
    if radius <= 0:
        raise ValueError("radius must be positive")
    if count < 3:
        raise ValueError("a ring needs at least 3 points")
    step = 2 * math.pi / count
    return [(radius * math.cos(i * step), radius * math.sin(i * step), z) for i in range(count)]
