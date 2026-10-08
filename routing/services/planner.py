import hashlib
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from django.conf import settings
from django.core.cache import cache

from . import geo, osrm
from .errors import RoutingError
from .geocode import normalize_query, resolve_location
from .optimizer import Candidate, InfeasibleRoute, plan_fuel_stops
from .station_index import get_station_index

CACHE_PREFIX = "route:"


def route_id(start_text, finish_text):
    raw = f"{normalize_query(start_text)}|{normalize_query(finish_text)}"
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def get_cached_route(map_id):
    return cache.get(CACHE_PREFIX + map_id)


def plan_route(start_text, finish_text):
    t0 = time.perf_counter()
    rid = route_id(start_text, finish_text)

    cached = cache.get(CACHE_PREFIX + rid)
    if cached is not None:
        cached["meta"] = {**cached["meta"], "cached": True, "external_api_calls": 0,
                          "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1)}
        return cached

    # Geocode both ends concurrently (0-2 calls; none for "lat,lng" input or cached places).
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_start = pool.submit(resolve_location, start_text)
        f_finish = pool.submit(resolve_location, finish_text)
        start, finish = f_start.result(), f_finish.result()
    api_calls = int(start.from_api) + int(finish.from_api)

    route = osrm.fetch_route(start, finish)  # the single routing call
    api_calls += 1

    cum = geo.cumulative_miles(route.lng, route.lat)
    keep = geo.thin_indices(cum, settings.ROUTE_MAX_POINTS)
    r_lng, r_lat = route.lng[keep], route.lat[keep]
    scale = route.distance_miles / cum[-1] if cum[-1] > 0 else 1.0
    r_miles = cum[keep] * scale  # mile markers calibrated to OSRM's driven distance
    total = route.distance_miles

    index = get_station_index()
    widths = settings.CORRIDOR_MILES
    ids, miles, offsets = index.project_onto_route(r_lng, r_lat, r_miles, max(widths))

    plan, used_width, candidates_used = None, None, 0
    for width in widths:  # narrowest corridor first; widen only if undrivable
        sel = offsets <= width
        cands = [Candidate(float(m), float(index.price[i]), (int(i), float(o)))
                 for i, m, o in zip(ids[sel], miles[sel], offsets[sel])]
        try:
            plan = plan_fuel_stops(cands, total, settings.FUEL_MAX_RANGE_MILES, settings.FUEL_MPG,
                                   settings.FUEL_INITIAL_RANGE_MILES)
            used_width, candidates_used = width, len(cands)
            break
        except InfeasibleRoute:
            continue
    if plan is None:
        raise RoutingError(
            f"No fuel stations within {max(widths):.0f} miles of the route make this trip drivable "
            f"on a {settings.FUEL_MAX_RANGE_MILES:.0f}-mile range.", 422)

    stops = []
    for p in plan.purchases:
        i, offset = p.candidate.ref
        stops.append({
            **index.describe(i),
            "route_mile": round(p.candidate.mile, 1),
            "offset_miles": round(offset, 1),
            "price_per_gallon": round(p.candidate.price, 3),
            "gallons_on_arrival": round(p.gallons_on_arrival, 2),
            "gallons_purchased": round(p.gallons, 2),
            "cost": round(p.cost, 2),
        })

    result = {
        "start": {"query": start.query, "label": start.label, "lat": start.lat, "lng": start.lng},
        "finish": {"query": finish.query, "label": finish.label, "lat": finish.lat, "lng": finish.lng},
        "distance_miles": round(total, 1),
        "duration_hours": round(route.duration_hours, 2),
        "total_fuel_cost": round(plan.total_cost, 2),
        "total_gallons_purchased": round(plan.total_gallons, 2),
        "gallons_needed_for_trip": round(total / settings.FUEL_MPG, 2),
        "fuel_stops": stops,
        "route": {"type": "LineString", "coordinates": np.column_stack([r_lng, r_lat]).round(5).tolist()},
        "assumptions": {
            "max_range_miles": settings.FUEL_MAX_RANGE_MILES,
            "miles_per_gallon": settings.FUEL_MPG,
            "initial_range_miles": settings.FUEL_INITIAL_RANGE_MILES,
            "initial_fuel_counted_as_spend": False,
            "station_corridor_miles": used_width,
        },
        "map_id": rid,
        "meta": {"cached": False, "external_api_calls": api_calls, "candidate_stations": candidates_used,
                 "elapsed_ms": 0},
    }
    cache.set(CACHE_PREFIX + rid, result, settings.ROUTE_CACHE_TTL)
    result["meta"]["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return result
