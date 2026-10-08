"""In-memory station arrays, loaded once per process so requests never hit the database."""
import threading

import numpy as np

from stations.models import Station

from . import geo

_lock = threading.Lock()
_index = None


class StationIndex:
    def __init__(self, rows):
        self.rows = rows  # (opis_id, name, address, city, state)
        self.lat = np.array([r[5] for r in rows], dtype=np.float64)
        self.lng = np.array([r[6] for r in rows], dtype=np.float64)
        self.price = np.array([r[7] for r in rows], dtype=np.float64)

    def __len__(self):
        return len(self.rows)

    def project_onto_route(self, r_lng, r_lat, r_miles, max_offset):
        """Stations within `max_offset` miles of the route -> (station idx, route mile, offset)."""
        if not len(self.rows):
            return np.array([], dtype=int), np.array([]), np.array([])
        lat_pad = max_offset / 69.0
        worst_lat = min(85.0, np.abs(r_lat).max() + lat_pad)
        lng_pad = max_offset / (69.0 * np.cos(np.radians(worst_lat)))
        box = (
            (self.lat >= r_lat.min() - lat_pad)
            & (self.lat <= r_lat.max() + lat_pad)
            & (self.lng >= r_lng.min() - lng_pad)
            & (self.lng <= r_lng.max() + lng_pad)
        )
        ids = np.nonzero(box)[0]
        if not len(ids):
            return ids, np.array([]), np.array([])
        near, dist = geo.nearest_route_point(r_lat, r_lng, self.lat[ids], self.lng[ids])
        ok = dist <= max_offset
        return ids[ok], r_miles[near[ok]], dist[ok]

    def describe(self, i):
        opis_id, name, address, city, state = self.rows[i][:5]
        return {
            "id": opis_id,
            "name": name,
            "address": address,
            "city": city,
            "state": state,
            "lat": float(self.lat[i]),
            "lng": float(self.lng[i]),
        }


def get_station_index():
    global _index
    if _index is None:
        with _lock:
            if _index is None:
                rows = [
                    (s.opis_id, s.name, s.address, s.city, s.state, s.lat, s.lng, float(s.price))
                    for s in Station.objects.all().iterator()
                ]
                _index = StationIndex(rows)
    return _index


def reset_station_index():
    global _index
    _index = None
