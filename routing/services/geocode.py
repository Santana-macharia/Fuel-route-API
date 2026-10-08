"""Turn the caller's start/finish into coordinates (free-text via Nominatim, or "lat,lng")."""
import hashlib
import re
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

from .errors import RoutingError

COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
# Contiguous USA. OSRM can't drive to AK/HI from the mainland anyway.
US_BOUNDS = {"min_lat": 24.3, "max_lat": 49.6, "min_lng": -125.1, "max_lng": -66.8}

_session = requests.Session()


@dataclass(frozen=True)
class Location:
    query: str
    lat: float
    lng: float
    label: str
    from_api: bool = False


def normalize_query(text):
    m = COORD_RE.match(text)
    if m:
        return f"{float(m.group(1)):.5f},{float(m.group(2)):.5f}"
    return " ".join(text.lower().split())


def _check_us(lat, lng, text):
    b = US_BOUNDS
    if not (b["min_lat"] <= lat <= b["max_lat"] and b["min_lng"] <= lng <= b["max_lng"]):
        raise RoutingError(f"'{text}' is outside the contiguous USA.", 400)


def resolve_location(text):
    text = text.strip()
    m = COORD_RE.match(text)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        _check_us(lat, lng, text)
        return Location(text, lat, lng, f"{lat:.5f}, {lng:.5f}")

    key = "geocode:" + hashlib.sha1(normalize_query(text).encode()).hexdigest()
    hit = cache.get(key)
    if hit:
        return Location(from_api=False, **hit)

    try:
        resp = _session.get(
            settings.NOMINATIM_URL,
            params={"q": text, "format": "jsonv2", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": settings.NOMINATIM_USER_AGENT},
            timeout=settings.NOMINATIM_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json()
    except (requests.RequestException, ValueError):
        raise RoutingError("Geocoding service is unavailable; try again or pass 'lat,lng'.", 502)
    if not results:
        raise RoutingError(f"Could not find '{text}' in the USA.", 400)

    lat, lng = float(results[0]["lat"]), float(results[0]["lon"])
    _check_us(lat, lng, text)
    data = {"query": text, "lat": lat, "lng": lng, "label": results[0].get("display_name", text)}
    cache.set(key, data, settings.ROUTE_CACHE_TTL * 30)
    return Location(from_api=True, **data)
