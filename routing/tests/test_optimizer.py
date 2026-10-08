import unittest

from routing.services.optimizer import Candidate, InfeasibleRoute, plan_fuel_stops


def C(mile, price):
    return Candidate(float(mile), float(price), ref=f"{mile}@{price}")


class OptimizerTests(unittest.TestCase):
    def test_short_route_needs_no_stop(self):
        plan = plan_fuel_stops([C(100, 3.0)], total_miles=400)
        self.assertEqual(plan.purchases, [])
        self.assertEqual(plan.total_cost, 0.0)

    def test_buys_only_enough_to_reach_cheaper_station_then_finishes(self):
        # 1000-mile trip. Free 500 mi at start -> arrive at mile 400 with 100 mi left.
        # Cheaper station at 800 is 400 away: buy 300 mi (30 gal) at $3.50, then
        # 200 mi (20 gal) at $3.00 to finish.
        plan = plan_fuel_stops([C(400, 3.5), C(800, 3.0)], total_miles=1000)
        self.assertEqual([p.candidate.mile for p in plan.purchases], [400, 800])
        self.assertAlmostEqual(plan.purchases[0].gallons, 30.0)
        self.assertAlmostEqual(plan.purchases[1].gallons, 20.0)
        self.assertAlmostEqual(plan.total_cost, 30 * 3.5 + 20 * 3.0)

    def test_cheap_station_just_out_of_range_is_not_counted_on(self):
        # B ($2.00 @ 700) is 600 mi from A, out of range; must stage through C.
        plan = plan_fuel_stops([C(100, 4.0), C(450, 4.2), C(700, 2.0)], total_miles=1000)
        self.assertEqual([p.candidate.mile for p in plan.purchases], [100, 450, 700])
        self.assertAlmostEqual(plan.total_gallons, 10 + 10 + 30)
        self.assertAlmostEqual(plan.total_cost, 10 * 4.0 + 10 * 4.2 + 30 * 2.0)

    def test_fills_up_at_cheapest_station_when_nothing_cheaper_ahead(self):
        # A is cheapest; everything after is pricier. Fill the tank at A.
        plan = plan_fuel_stops([C(300, 3.0), C(600, 3.5), C(900, 3.6)], total_miles=1200)
        first = plan.purchases[0]
        self.assertEqual(first.candidate.mile, 300)
        # arrived with 200 mi, filled to 500 -> bought 300 mi = 30 gal
        self.assertAlmostEqual(first.gallons, 30.0)

    def test_skips_stations_that_do_not_help(self):
        # Expensive stop before a cheap one within range of the initial tank: no purchase.
        plan = plan_fuel_stops([C(100, 5.0), C(450, 2.0)], total_miles=900)
        self.assertNotIn(100, [p.candidate.mile for p in plan.purchases])

    def test_gap_larger_than_range_is_infeasible(self):
        with self.assertRaises(InfeasibleRoute):
            plan_fuel_stops([C(100, 3.0), C(700, 3.0)], total_miles=1000)

    def test_no_station_within_initial_range_is_infeasible(self):
        with self.assertRaises(InfeasibleRoute):
            plan_fuel_stops([C(600, 3.0)], total_miles=1000)

    def test_never_runs_dry_and_never_overfills(self):
        # Randomised invariant check against a simulation of the returned plan.
        import random

        rng = random.Random(7)
        for _ in range(200):
            total = rng.uniform(501, 3000)
            stations = [C(rng.uniform(0, total), rng.uniform(2.5, 5.0)) for _ in range(rng.randint(15, 80))]
            try:
                plan = plan_fuel_stops(stations, total)
            except InfeasibleRoute:
                continue
            fuel, pos = 500.0, 0.0
            for p in plan.purchases:
                fuel -= p.candidate.mile - pos
                pos = p.candidate.mile
                self.assertGreaterEqual(fuel, -1e-6, "ran dry before a stop")
                fuel += p.gallons * 10
                self.assertLessEqual(fuel, 500.0 + 1e-6, "overfilled the tank")
            self.assertGreaterEqual(fuel - (total - pos), -1e-6, "ran dry before the destination")


if __name__ == "__main__":
    unittest.main()
