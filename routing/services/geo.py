"""Vectorised geometry helpers (numpy only)."""
import numpy as np

EARTH_RADIUS_MILES = 3958.8


def cumulative_miles(lng, lat):
    """Haversine distance along a polyline; returns miles from the start for every vertex."""
    phi = np.radians(lat)
    lam = np.radians(lng)
    dphi = np.diff(phi)
    dlam = np.diff(lam)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi[:-1]) * np.cos(phi[1:]) * np.sin(dlam / 2) ** 2
    seg = 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    return np.concatenate([[0.0], np.cumsum(seg)])


def thin_indices(cum_miles, max_points):
    """Indices of ~evenly spaced (by distance) vertices, always keeping both endpoints."""
    n = len(cum_miles)
    if n <= max_points:
        return np.arange(n)
    targets = np.linspace(0.0, cum_miles[-1], max_points)
    idx = np.clip(np.searchsorted(cum_miles, targets), 0, n - 1)
    return np.unique(np.concatenate([[0], idx, [n - 1]]))


def nearest_route_point(route_lat, route_lng, pt_lat, pt_lng, chunk=256):
    """For each point, the index of the nearest route vertex and the distance to it (miles).

    Uses an equirectangular approximation, which is accurate to well under a percent at
    the tens-of-miles scale we care about. Chunked to keep memory bounded.
    """
    r_lat = np.radians(route_lat)[None, :]
    r_lng = np.radians(route_lng)[None, :]
    p_lat = np.radians(pt_lat)
    p_lng = np.radians(pt_lng)
    n = len(p_lat)
    idx = np.empty(n, dtype=np.int64)
    dist = np.empty(n, dtype=np.float64)
    for s in range(0, n, chunk):
        la = p_lat[s : s + chunk, None]
        lo = p_lng[s : s + chunk, None]
        dy = la - r_lat
        dx = (lo - r_lng) * np.cos(la)
        d2 = dx * dx + dy * dy
        j = d2.argmin(axis=1)
        rows = np.arange(len(j))
        idx[s : s + chunk] = j
        dist[s : s + chunk] = np.sqrt(d2[rows, j]) * EARTH_RADIUS_MILES
    return idx, dist
