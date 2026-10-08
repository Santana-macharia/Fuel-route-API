import unittest

import numpy as np

from routing.services import geo


class GeoTests(unittest.TestCase):
    def test_one_degree_of_latitude_is_about_69_miles(self):
        cum = geo.cumulative_miles(np.array([-100.0, -100.0]), np.array([40.0, 41.0]))
        self.assertAlmostEqual(cum[-1], 69.09, delta=0.1)

    def test_thinning_keeps_endpoints_and_caps_size(self):
        lat = np.linspace(30, 40, 20000)
        lng = np.full_like(lat, -90.0)
        cum = geo.cumulative_miles(lng, lat)
        idx = geo.thin_indices(cum, 1000)
        self.assertLessEqual(len(idx), 1002)
        self.assertEqual(idx[0], 0)
        self.assertEqual(idx[-1], len(lat) - 1)

    def test_nearest_route_point_and_offset(self):
        lat = np.linspace(40.0, 41.0, 200)
        lng = np.full_like(lat, -100.0)
        # Station ~0.1 degrees of longitude east (~5.3 mi at 40.5N), halfway along.
        idx, dist = geo.nearest_route_point(lat, lng, np.array([40.5]), np.array([-99.9]))
        self.assertAlmostEqual(lat[idx[0]], 40.5, delta=0.01)
        self.assertAlmostEqual(dist[0], 5.25, delta=0.3)


if __name__ == "__main__":
    unittest.main()
