"""Spiral -- points on an Archimedean spiral.

Self-contained: needs nothing but Rhino, so the .ghuser alone is the whole tool.
Built by ghuser-builder, version {{version}}.
"""

import math

import Rhino.Geometry as rg
from ghpythonlib.componentbase import executingcomponent as component


class Spiral(component):
    def RunScript(self, turns, count, pitch):
        turns = turns or 3.0
        count = count or 60
        pitch = pitch if pitch is not None else 1.0
        if count < 2:
            return []
        points = []
        for i in range(count):
            t = turns * 2 * math.pi * i / (count - 1)
            r = pitch * t / (2 * math.pi)
            points.append(rg.Point3d(r * math.cos(t), r * math.sin(t), 0.0))
        return points
