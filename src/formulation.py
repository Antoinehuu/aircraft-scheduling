"""Solver-independent rows and eligibility for tail assignment."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from itertools import groupby
from math import inf
from random import Random


def initial_fleet_assignment(flights, costs, aircraft_init, *, seed=None):
    """Return a deterministic starting tail for each flight in a feasible fleet schedule."""
    ready = {tail: (aircraft_init[tail], -inf) for tail in sorted(aircraft_init)}
    assigned = {}
    used = set()
    rng = Random(seed) if seed is not None else None
    for flight in sorted(flights, key=lambda f: (f["departure"], f["id"])):
        i = flight["id"]
        available = (
            tail for tail, (airport, time) in ready.items()
            if airport == flight["origin"] and time <= flight["departure"]
        )
        # Every tail must fly, so prefer one that has not left its base yet.
        tail = min(available,
                   key=lambda t: (t in used, rng.random() if rng is not None else costs[i - 1][t], t),
                   default=None)
        if tail is None:
            return None
        assigned[i] = tail
        used.add(tail)
        ready[tail] = (flight["dest"], flight["arrival"])
    return assigned if len(used) == len(aircraft_init) else None


def tail_reachability(flights, aircraft_init):
    """Find flights each tail could reach from its base before assignment."""
    if any(flight["arrival"] <= flight["departure"] for flight in flights):
        raise ValueError("Fleet assignment requires each flight to arrive after it departs.")

    by_departure = sorted(flights, key=lambda flight: flight["departure"])
    reachable = {}
    for base in dict.fromkeys(aircraft_init.values()):
        earliest = {base: float("-inf")}
        flight_ids = set()
        for flight in by_departure:
            if earliest.get(flight["origin"], float("inf")) <= flight["departure"]:
                flight_ids.add(flight["id"])
                dest = flight["dest"]
                earliest[dest] = min(flight["arrival"], earliest.get(dest, float("inf")))
        reachable[base] = flight_ids
    return {t: reachable[base] for t, base in aircraft_init.items()}


def fleet_rows(flight_ids, aircraft_init, data, reachable, x):
    """Yield (positive terms, negative terms, sense, RHS) for fleet assignment."""
    for i in flight_ids:
        yield [x[i, t] for t in aircraft_init if i in reachable[t]], [], "=", 1

    for t, base in aircraft_init.items():
        yield [x[i, t] for i in data["departures_sorted"].get(base, [])], [], ">=", 1

    for airport, departures in data["departures_sorted"].items():
        arrivals = data["arrivals_sorted"].get(airport, [])
        departure_times = [data["flight_departure_time"][i] for i in departures]
        arrival_times = [data["flight_arrival_time"][i] for i in arrivals]
        end = 0
        while end < len(departures):
            arrived = bisect_right(arrival_times, departure_times[end])
            # The last departure before the next arrival implies earlier balances.
            end = (bisect_left(departure_times, arrival_times[arrived], lo=end)
                   if arrived < len(arrivals) else len(departures))
            departed_ids = set(departures[:end])
            arrived_ids = set(arrivals[:arrived])
            outgoing = sorted(departed_ids - arrived_ids)
            incoming = sorted(arrived_ids - departed_ids)
            for t, base in aircraft_init.items():
                positive = [x[i, t] for i in outgoing if i in reachable[t]]
                if positive:
                    negative = [x[i, t] for i in incoming if i in reachable[t]]
                    yield positive, negative, "<=", int(base == airport)


class Maintenance:
    """Prepare maintenance bounds and rows using the instance's flight day labels."""

    def __init__(self, flights, days, horizon, m_airports, reachable, initial_days):
        if horizon <= 0:
            raise ValueError("The maintenance horizon must be positive.")
        self.days = sorted(set(days))
        self.day_set = set(self.days)
        self.horizon = horizon
        first_day = self.days[0] if self.days else 1
        history = range(first_day - horizon, first_day)
        if initial_days is None:
            rng = Random(0)
            initial_days = {t: rng.choice(history) for t in sorted(reachable)}
        if (set(initial_days) != set(reachable)
                or any(day not in history for day in initial_days.values())):
            raise ValueError(f"Supply one initial maintenance day in {list(history)} per aircraft.")

        self.initial_days = initial_days
        self.all_days = [*history, *self.days]
        airport_index = {airport: index for index, airport in enumerate(m_airports)}
        self.station_index = {}
        self.by_station_day = defaultdict(list)
        by_day = defaultdict(list)
        for flight in flights:
            i, day, dest = flight["id"], flight["day"], flight["dest"]
            if day in self.day_set:
                by_day[day].append(flight)
                if dest in airport_index:
                    self.by_station_day[dest, day].append(i)
                    self.station_index[i] = airport_index[dest]
        self.eligible = {t: flights.intersection(self.station_index) for t, flights in reachable.items()}
        self.departure_groups = {
            day: [[f["id"] for f in group] for _, group in groupby(
                sorted(by_day[day], key=lambda f: f["departure"]),
                key=lambda f: f["departure"],
            )]
            for day in self.days
        }

    def day_bounds(self, day, tail):
        historical = int(day == self.initial_days[tail])
        return historical, max(historical, int(day in self.day_set))

    def rows(self, capacity, x, y, z):
        for t, candidates in self.eligible.items():
            for i in sorted(candidates):
                yield [z[i, t]], [x[i, t]], "<=", 0

        for ids in self.by_station_day.values():
            yield [z[i, t] for i in ids for t in self.eligible if i in self.eligible[t]], [], "<=", capacity

        for day, groups in self.departure_groups.items():
            for t, candidates in self.eligible.items():
                previous = []
                for group in groups:
                    if previous:
                        yield [x[i, t] for i in group] + previous, [], "<=", 1
                    previous.extend(z[i, t] for i in group if i in candidates)
                yield previous, [y[day, t]], "=", 0

        if self.days:
            for t, previous in self.initial_days.items():
                for end in range(previous + self.horizon, self.days[-1] + 1):
                    yield [y[d, t] for d in self.days if end - self.horizon < d <= end], [], ">=", 1

    def cost_terms(self, m_costs, z):
        for t, candidates in self.eligible.items():
            for i in sorted(candidates):
                yield m_costs[t][self.station_index[i]], z[i, t]
