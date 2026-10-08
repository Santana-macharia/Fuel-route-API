import csv
import time
import urllib.request
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from stations import importing
from stations.models import Station

DEFAULT_CSV = settings.BASE_DIR / "data" / "fuel-prices-for-be-assessment.csv"
GEOCODED_CSV = settings.BASE_DIR / "data" / "stations_geocoded.csv"
GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_place_national.zip"
)
FIELDS = ["opis_id", "name", "address", "city", "state", "price", "lat", "lng"]


class Command(BaseCommand):
    help = (
        "Load fuel stations into the database. Cleans the CSV (US only, one row per OPIS id, "
        "cheapest price) and geocodes each unique city/state ONCE, offline from the request path."
    )

    def add_arguments(self, parser):
        parser.add_argument("--csv", default=str(DEFAULT_CSV), help="Fuel price CSV.")
        parser.add_argument("--gazetteer", default=GAZETTEER_URL,
                            help="URL or local path of a Census 'places' gazetteer (.zip or .txt).")
        parser.add_argument("--nominatim-fallback", action="store_true",
                            help="Geocode cities missing from the gazetteer via Nominatim (1 req/sec).")
        parser.add_argument("--from-geocoded", action="store_true",
                            help=f"Skip geocoding; load the committed {GEOCODED_CSV.name} directly.")

    def handle(self, *args, **opts):
        if opts["from_geocoded"]:
            rows = self._read_geocoded()
        else:
            rows = self._geocode(opts)
            self._write_geocoded(rows)
        with transaction.atomic():
            Station.objects.all().delete()
            Station.objects.bulk_create([Station(**r) for r in rows], batch_size=1000)
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} stations."))

    # -- geocoding -------------------------------------------------------------------
    def _geocode(self, opts):
        stations, stats = importing.read_us_stations(opts["csv"])
        self.stdout.write(f"CSV: {stats['rows']} rows -> dropped {stats['dropped_non_us']} non-US, "
                          f"{stats['unique_us_stations']} unique US stations.")
        primary, secondary = importing.parse_gazetteer(*self._load_gazetteer(opts["gazetteer"]))
        self.stdout.write(f"Gazetteer: {len(primary)} places.")

        coords, missing = {}, set()
        for s in stations:
            key = (s["state"], s["city"])
            if key in coords or key in missing:
                continue
            hit = importing.match_city(primary, secondary, *key)
            if hit:
                coords[key] = hit
            else:
                missing.add(key)
        self.stdout.write(f"Matched {len(coords)} cities; {len(missing)} unmatched.")

        if missing and opts["nominatim_fallback"]:
            for n, key in enumerate(sorted(missing), 1):
                hit = self._nominatim(*key)
                if hit:
                    coords[key] = hit
                if n % 25 == 0:
                    self.stdout.write(f"  nominatim {n}/{len(missing)}")
                time.sleep(1.05)  # Nominatim usage policy: max 1 request/second
            missing = {k for k in missing if k not in coords}

        if missing:
            self.stdout.write(self.style.WARNING(
                f"{len(missing)} cities could not be geocoded; their stations are skipped "
                f"(re-run with --nominatim-fallback to try them)."))
        rows = []
        for s in stations:
            hit = coords.get((s["state"], s["city"]))
            if hit:
                rows.append({**s, "lat": hit[0], "lng": hit[1]})
        return rows

    def _load_gazetteer(self, src):
        if src.startswith(("http://", "https://")):
            cache_dir = settings.BASE_DIR / "data" / "gazetteer"
            cache_dir.mkdir(parents=True, exist_ok=True)
            path = cache_dir / src.rsplit("/", 1)[-1]
            if not path.exists():
                self.stdout.write(f"Downloading {src} ...")
                req = urllib.request.Request(src, headers={"User-Agent": settings.NOMINATIM_USER_AGENT})
                try:
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        path.write_bytes(resp.read())
                except OSError as exc:
                    raise CommandError(f"Could not download gazetteer ({exc}). Download it manually from "
                                       "census.gov/geographies/reference-files and pass --gazetteer PATH.")
        else:
            path = Path(src)
        return path.read_bytes(), path.name

    def _nominatim(self, state, city):
        try:
            r = requests.get(
                settings.NOMINATIM_URL,
                params={"q": f"{city}, {state}, USA", "format": "jsonv2", "limit": 1, "countrycodes": "us"},
                headers={"User-Agent": settings.NOMINATIM_USER_AGENT}, timeout=10)
            r.raise_for_status()
            res = r.json()
            return (float(res[0]["lat"]), float(res[0]["lon"])) if res else None
        except (requests.RequestException, ValueError, KeyError):
            return None

    # -- geocoded snapshot -----------------------------------------------------------
    def _write_geocoded(self, rows):
        with open(GEOCODED_CSV, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        self.stdout.write(f"Wrote {GEOCODED_CSV.relative_to(settings.BASE_DIR)} (commit it so reviewers can "
                          f"run with --from-geocoded and no network).")

    def _read_geocoded(self):
        try:
            with open(GEOCODED_CSV, newline="") as fh:
                return [{**r, "opis_id": int(r["opis_id"]), "price": float(r["price"]),
                         "lat": float(r["lat"]), "lng": float(r["lng"])} for r in csv.DictReader(fh)]
        except FileNotFoundError:
            raise CommandError(f"{GEOCODED_CSV} not found; run without --from-geocoded first.")
