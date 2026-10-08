"""One call to the public OSRM server returns the whole route geometry and distance."""
from dataclasses import dataclass

import numpy as np
import requests
from django.conf import settings

from .errors import RoutingError

METERS_PER_MILE = 1609.344
_session = requests.Session()


@dataclass(frozen=True)
class Route:
    lng: np.ndarray
    lat: np.ndarray
    distance_miles: float
    duration_hours: float


def fetch_route(start, finish):
    coords = f"{start.lng:.6f},{start.lat:.6f};{finish.lng:.6f},{finish.lat:.6f}"
    url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{coords}"
    try:
        resp = _session.get(
            url,
            params={"overview": "full", "geometries": "geojson", "steps": "false", "alternatives": "false"},
            timeout=settings.OSRM_TIMEOUT,
        )
        data = resp.json()
    except (requests.RequestException, ValueError):
        raise RoutingError("Routing service is unavailable; try again shortly.", 502)

    code = data.get("code")
    if code == "NoRoute":
        raise RoutingError("No drivable route between those locations.", 422)
    if code != "Ok" or not data.get("routes"):
        raise RoutingError(f"Routing service error: {data.get('message', code)}", 502)

    r = data["routes"][0]
    pts = np.asarray(r["geometry"]["coordinates"], dtype=np.float64)
    return Route(pts[:, 0], pts[:, 1], r["distance"] / METERS_PER_MILE, r["duration"] / 3600.0)
