"""Ring Points -- Grasshopper adapter for ringkit.ring_points. Thin on purpose."""
# r: ringkit=={{version}}

import Rhino.Geometry as rg
from ghpythonlib.componentbase import executingcomponent as component

from ringkit import ring_points


class RingPoints(component):
    def RunScript(self, radius, count, z):
        if not radius or not count:
            return None
        pts = ring_points(radius, count, z or 0.0)
        return [rg.Point3d(*p) for p in pts]
