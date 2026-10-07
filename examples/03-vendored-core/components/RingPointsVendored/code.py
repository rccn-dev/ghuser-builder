"""Ring Points (vendored) -- the ringkit core ships inside the .yak, in lib/.

No package registry, no pip: Rhino's Package Manager installs the .yak, and the
few lines below put its lib/ folder on sys.path. ghuser-build fills in
{{version}}, so each component loads the core from its own package version.
"""

import glob
import os
import sys

PACKAGE, VERSION = "rccn-ringkit-vendored", "{{version}}"


def _package_lib():
    # Rhino installs packages to <root>/packages/<rhino version>/<name>/<version>/
    roots = [
        os.path.join(os.environ.get("APPDATA", ""), "McNeel", "Rhinoceros", "packages"),
        os.path.expanduser("~/Library/Application Support/McNeel/Rhinoceros/packages"),
    ]
    for root in roots:
        for lib in sorted(glob.glob(os.path.join(root, "*", PACKAGE, VERSION, "lib")), reverse=True):
            return lib
    raise ImportError(f"{PACKAGE} {VERSION} is not installed; install it with the Package Manager")


_lib = _package_lib()
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import Rhino.Geometry as rg  # noqa: E402
from ghpythonlib.componentbase import executingcomponent as component  # noqa: E402

from ringkit import ring_points  # noqa: E402


class RingPointsVendored(component):
    def RunScript(self, radius, count, z):
        if not radius or not count:
            return None
        pts = ring_points(radius, count, z or 0.0)
        return [rg.Point3d(*p) for p in pts]
