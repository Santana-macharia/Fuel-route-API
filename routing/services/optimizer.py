"""Fuel-stop optimizer: pure Python, no Django, no I/O.

Classic "gas station" greedy on a line, with a tank that holds `max_range` miles of fuel
and fuel that can be bought in any quantity:

  * At a station, if a cheaper station (or the destination) is reachable on a full tank,
    buy only enough to get there.
  * Otherwise this station is the cheapest around: fill the tank, then drive to the
    cheapest station within range.

Runs in O(n * w) for n stations and w stations per range window, i.e. negligible.
"""
from dataclasses import dataclass
from typing import Any, List, Sequence

EPS = 1e-9


class InfeasibleRoute(Exception):
    def __init__(self, at_mile):
        super().__init__(f"No reachable fuel station after mile {at_mile:.1f}")
        self.at_mile = at_mile


@dataclass(frozen=True)
class Candidate:
    mile: float  # distance along the route
    price: float  # USD per gallon
    ref: Any = None  # caller's handle for this station


@dataclass(frozen=True)
class Purchase:
    candidate: Candidate
    gallons: float
    cost: float
    gallons_on_arrival: float


@dataclass(frozen=True)
class FuelPlan:
    purchases: List[Purchase]
    total_gallons: float
    total_cost: float


def plan_fuel_stops(
    stations: Sequence[Candidate],
    total_miles: float,
    max_range: float = 500.0,
    mpg: float = 10.0,
    initial_range: float = None,
) -> FuelPlan:
    if initial_range is None:
        initial_range = max_range
    initial_range = min(initial_range, max_range)

    if total_miles <= initial_range + EPS:
        return FuelPlan([], 0.0, 0.0)

    st = sorted((s for s in stations if 0 <= s.mile <= total_miles), key=lambda s: (s.mile, s.price))
    # The destination behaves like a free station, so "cheaper station in range" covers it.
    st.append(Candidate(total_miles, 0.0, None))
    last = len(st) - 1

    # Nothing can be bought at mile 0, so the first move is to reach the nearest station
    # on the initial tank; the greedy rule then decides how much to buy there.
    if st[0].mile > initial_range + EPS or last == 0:
        raise InfeasibleRoute(0.0)
    i = 0
    fuel = initial_range - st[0].mile  # miles of fuel in the tank
    purchases = []

    while i < last:
        cur = st[i]
        limit = cur.mile + max_range + EPS
        k = i + 1
        cheaper = None
        while k <= last and st[k].mile <= limit:
            if st[k].price < cur.price - EPS:
                cheaper = k
                break
            k += 1

        if cheaper is not None:
            buy = max(0.0, (st[cheaper].mile - cur.mile) - fuel)
            nxt = cheaper
        else:
            if k == i + 1:  # nothing within range at all
                raise InfeasibleRoute(cur.mile)
            buy = max(0.0, max_range - fuel)
            nxt = min(range(i + 1, k), key=lambda x: (st[x].price, -st[x].mile))

        if buy > EPS:
            gallons = buy / mpg
            purchases.append(Purchase(cur, gallons, gallons * cur.price, fuel / mpg))
            fuel += buy
        fuel -= st[nxt].mile - cur.mile
        i = nxt

    total_gallons = sum(p.gallons for p in purchases)
    total_cost = sum(p.cost for p in purchases)
    return FuelPlan(purchases, total_gallons, total_cost)
