"""End-to-end API tests with the external services mocked (no network needed)."""
from unittest import mock

import numpy as np
from django.core.cache import cache
from django.test import TestCase, override_settings

from routing.services import geocode, osrm
from routing.services.station_index import reset_station_index
from stations.models import Station

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def fake_route(start, finish):
    # Straight west-east line ~1,000 miles long along lat 40 (about 14.5 degrees of longitude)
    lng = np.linspace(-100.0, -85.5, 400)
    lat = np.full_like(lng, 40.0)
    return osrm.Route(lng, lat, 1000.0, 15.0)


@override_settings(CACHES=LOCMEM)
class RouteApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Stations along the line; (lng, price). 500-mile range -> needs stops.
        for i, (lng, price) in enumerate([(-97.0, 3.9), (-93.0, 3.2), (-89.0, 3.6), (-86.0, 3.0)]):
            Station.objects.create(opis_id=i + 1, name=f"Stop {i}", address="I-1", city="Town",
                                   state="MO", price=price, lat=40.0, lng=lng)

    def setUp(self):
        cache.clear()
        reset_station_index()
        self.addCleanup(reset_station_index)

    def post(self, start="40.0,-100.0", finish="40.0,-85.5"):
        return self.client.post("/api/route/", {"start": start, "finish": finish}, content_type="application/json")

    def test_returns_stops_cost_route_and_map_url(self):
        with mock.patch.object(osrm, "fetch_route", side_effect=fake_route) as m:
            resp = self.post()
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(m.call_count, 1)  # exactly one routing call
        self.assertEqual(body["meta"]["external_api_calls"], 1)  # coordinates need no geocoding
        self.assertTrue(body["fuel_stops"])
        self.assertAlmostEqual(body["total_fuel_cost"], sum(s["cost"] for s in body["fuel_stops"]), delta=0.05)
        self.assertEqual(body["route"]["type"], "LineString")
        self.assertIn("/api/map/", body["map_url"])
        # 1,000 mi at 10 mpg needs 100 gal; 50 come from the starting tank.
        self.assertAlmostEqual(body["total_gallons_purchased"], 50.0, delta=0.1)

    def test_second_identical_request_makes_no_external_calls(self):
        with mock.patch.object(osrm, "fetch_route", side_effect=fake_route) as m:
            self.post()
            second = self.post().json()
        self.assertEqual(m.call_count, 1)
        self.assertTrue(second["meta"]["cached"])
        self.assertEqual(second["meta"]["external_api_calls"], 0)

    def test_map_page_renders(self):
        with mock.patch.object(osrm, "fetch_route", side_effect=fake_route):
            url = self.post().json()["map_url"]
        resp = self.client.get(url[url.index("/api/"):])
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "leaflet")

    def test_unknown_map_id_is_404(self):
        self.assertEqual(self.client.get("/api/map/doesnotexist/").status_code, 404)

    def test_missing_fields_is_400(self):
        resp = self.client.post("/api/route/", {"start": "x"}, content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_coordinates_outside_usa_rejected(self):
        resp = self.post(start="48.85,2.35")  # Paris
        self.assertEqual(resp.status_code, 400)
        self.assertIn("outside", resp.json()["error"])

    def test_free_text_is_geocoded_with_one_call_each(self):
        class Resp:
            def __init__(self, lat, lon): self._d = [{"lat": str(lat), "lon": str(lon), "display_name": "X"}]
            def raise_for_status(self): pass
            def json(self): return self._d

        calls = iter([Resp(40.0, -100.0), Resp(40.0, -85.5)])
        with mock.patch.object(geocode._session, "get", side_effect=lambda *a, **k: next(calls)), \
                mock.patch.object(osrm, "fetch_route", side_effect=fake_route):
            body = self.post(start="Place A, NE", finish="Place B, IN").json()
        self.assertEqual(body["meta"]["external_api_calls"], 3)  # 2 geocodes + 1 route

    def test_undrivable_when_no_stations_in_corridor(self):
        Station.objects.all().delete()
        reset_station_index()
        with mock.patch.object(osrm, "fetch_route", side_effect=fake_route):
            resp = self.post()
        self.assertEqual(resp.status_code, 422)
