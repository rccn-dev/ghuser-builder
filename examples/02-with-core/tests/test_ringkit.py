import math

import pytest

from ringkit import ring_points


def test_every_point_is_on_the_circle():
    for x, y, z in ring_points(2.5, 17, z=1.0):
        assert math.hypot(x, y) == pytest.approx(2.5)
        assert z == 1.0


def test_points_are_evenly_spaced():
    pts = ring_points(1.0, 12)
    gaps = [math.dist(pts[i], pts[(i + 1) % 12]) for i in range(12)]
    assert max(gaps) == pytest.approx(min(gaps))


@pytest.mark.parametrize("radius, count", [(0, 6), (-1, 6), (1, 2)])
def test_rejects_degenerate_rings(radius, count):
    with pytest.raises(ValueError):
        ring_points(radius, count)
