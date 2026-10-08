# Fuel Route API

Django API that takes a start and finish location in the USA and returns the driving route,
the cost-optimal fuel stops along it (500-mile range), and the total fuel spend at 10 MPG.

* **Django 6.1** (current stable), plain Django views, no DRF needed for two JSON endpoints.
* **Routing:** public [OSRM](https://project-osrm.org/) server, no API key.
* **Geocoding of the request:** Nominatim (OpenStreetMap), or pass `lat,lng` and skip it.
* **Fuel prices:** the supplied OPIS CSV, cleaned and geocoded once, offline (see below).

## Quick start

python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py test
python manage.py migrate
python manage.py import_stations
python manage.py runserver

`import_stations` writes `data/stations_geocoded.csv`. Once that file is committed, anyone can skip the
download with `python manage.py import_stations --from-geocoded`.
Set `NOMINATIM_USER_AGENT="my-app (me@example.com)"` per Nominatim's usage policy.

Run the tests: `python manage.py test`

## API

`POST /api/route/` (or `GET /api/route/?start=...&finish=...`)

```json
{ "start": "New York, NY", "finish": "Los Angeles, CA" }
```

`start` / `finish` accept a free-text place or `"lat,lng"` (e.g. `"41.8781,-87.6298"`).
Both must be in the contiguous USA.

Response (abridged):

```json
{
  "distance_miles": 2790.4,
  "duration_hours": 41.2,
  "total_fuel_cost": 612.35,
  "total_gallons_purchased": 229.0,
  "gallons_needed_for_trip": 279.04,
  "fuel_stops": [
    { "name": "...", "city": "...", "state": "..", "lat": 0, "lng": 0,
      "route_mile": 412.6, "offset_miles": 1.8, "price_per_gallon": 3.049,
      "gallons_on_arrival": 1.7, "gallons_purchased": 41.2, "cost": 125.62 }
  ],
  "route": { "type": "LineString", "coordinates": [[-74.0, 40.7], "..."] },
  "map_url": "http://127.0.0.1:8000/api/map/<id>/",
  "assumptions": { "max_range_miles": 500, "miles_per_gallon": 10, "initial_range_miles": 500, "...": "..." },
  "meta": { "cached": false, "external_api_calls": 3, "candidate_stations": 812, "elapsed_ms": 640.2 }
}
```

`map_url` opens a Leaflet page with the route, numbered fuel stops and totals. The `route`
GeoJSON works in any map client. Errors are `{"error": "..."}` with 400 (bad input),
422 (no drivable route or no usable stations), or 502 (upstream service down).

## External API calls per request

| Case | Calls |
|---|---|
| Free-text start and finish, cold cache | 3 (2 Nominatim geocodes, run concurrently, + **1 OSRM route**) |
| `lat,lng` start and finish | **1** (OSRM only) |
| Previously seen place names | geocodes served from cache |
| Repeat of an identical request | **0** (full result cached 24 h) |

Fuel stations are never geocoded at request time.

## How it stays fast

1. **Offline geocoding.** `import_stations` geocodes each unique city/state once (3,813 of them) using the free
   Census places gazetteer, so request time has no station lookups.
2. **In-memory station arrays.** Loaded once per process into numpy; no DB query per request.
3. **Thinned route.** The route (often 20k+ vertices) is resampled to <=3,000 points by distance (~1 mile
   apart on a cross-country trip) for projection and the response.
4. **Vectorised projection.** A bounding-box prefilter, then chunked numpy nearest-vertex search assigns each
   nearby station a route mile marker and an off-route distance.
5. **Greedy optimizer, O(n*w).** About 2 ms.
6. **Caching** of results (and geocodes) in a file-based Django cache shared across workers.

On a synthetic 2,456-mile route with 6,600 stations, projection plus optimization measured about 70 ms,
so latency is dominated by the one OSRM call.

## Optimizer

Stations within 10 miles of the route are candidates (the corridor widens to 25, then 50 miles only if
the trip is otherwise undrivable; no extra API calls). Fuel can be bought in any amount. At each station:

* if a cheaper station, or the destination, is reachable on a full tank, buy **just enough to get there**;
* otherwise this is the cheapest option nearby: **fill up**, then drive to the cheapest station in range.

This is the classic gas-station greedy. I verified it against an exact dynamic-programming solver on 400
random instances (0 mismatches), and the unit tests also check that the plan never runs dry or overfills.

## Assumptions 

* **Starting tank is full (500 miles) and is not counted as spend.** Only fuel bought en route is charged,
  so a trip under 500 miles returns no stops and `$0`. Change with `FUEL_INITIAL_RANGE_MILES`.
* Fuel can be purchased in fractional gallons; the vehicle ends the trip near empty.
* **Station position is city-level.** The CSV has no coordinates and gives highway-style addresses
  (`I-44, EXIT 283 & US-69`), so stations are placed at their city's Census centroid. That is why the corridor
  is 10 miles. Cities missing from the gazetteer can be filled with `--nominatim-fallback`.
* Detours are not priced: a station's `offset_miles` from the route is reported but not added to cost.
* Data cleaning: 620 Canadian rows dropped; 8,151 rows collapse to 6,626 US stations by OPIS id,
  keeping the **lowest** posted price per station.
* The OSRM demo server is for light use. Point `OSRM_BASE_URL` at your own instance for production.

## Layout

```
config/                 settings, urls
stations/               Station model, import_stations command, CSV/geocode helpers
routing/services/       geo.py, optimizer.py (pure), osrm.py, geocode.py, planner.py, station_index.py
routing/views.py        /api/route/ and /api/map/<id>/
routing/tests/          optimizer + geometry unit tests, API tests (external calls mocked)
postman/                Postman collection with assertions
data/                   source CSV (and stations_geocoded.csv after import)
```


