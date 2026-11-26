"""Construct the same maintenance warm start for every solver."""

from collections import Counter

from src.formulation import Maintenance, initial_fleet_assignment, tail_reachability


def complete_maintenance_start(instance, fleet_assignment):
    """Return flight assignments and selected (day, tail) and (flight, tail) pairs."""
    _, capacity, horizon, flights, costs, _, aircraft, _, stations, days = instance
    rules = Maintenance(flights, days, horizon, stations, tail_reachability(flights, aircraft), None)
    # Try the cost-based fleet start first, then a few repeatable route alternatives.
    assignment = fleet_assignment
    for seed in range(9):
        if seed:
            assignment = initial_fleet_assignment(flights, costs, aircraft, seed=seed)
        if assignment is None:
            continue
        visits = _schedule_visits(rules, capacity, assignment)
        if visits is not None:
            maintenance_days = set(visits) | {(day, tail) for tail, day in rules.initial_days.items()}
            maintenance_flights = {(flight, tail) for (_, tail), flight in visits.items()}
            return assignment, (maintenance_days, maintenance_flights)
    return fleet_assignment, None


def _schedule_visits(rules, capacity, assignment):
    if not rules.days:
        return {}
    last_day = rules.days[-1]
    options = {tail: [] for tail in rules.initial_days}
    for day, groups in rules.departure_groups.items():
        last_flight = {assignment[i]: i for group in groups for i in group}
        for tail, i in last_flight.items():
            if i in rules.eligible[tail]:
                options[tail].append((day, rules.station_index[i], i))

    # Drop visits that cannot reach the end of the horizon even with free capacity.
    for tail, candidates in options.items():
        viable = []
        for visit in reversed(candidates):
            due = visit[0] + rules.horizon
            if due > last_day or (viable and viable[-1][0] <= due):
                viable.append(visit)
        options[tail] = viable

    pending = [(rules.initial_days, Counter(), {})]
    # A bounded search keeps preparation predictable and independent of solver speed.
    for _ in range(2_000):
        if not pending:
            break
        previous_days, slots_used, visits = pending.pop()
        choices = []
        for tail, previous in previous_days.items():
            due = previous + rules.horizon
            if due <= last_day:
                available = [(day, station, i) for day, station, i in options[tail]
                             if previous < day <= due and slots_used[day, station] < capacity]
                choices.append((len(available), due, tail, available))
        if not choices:
            return visits

        # Branch on the tail with the fewest options, trying its latest visit first.
        _, _, tail, available = min(choices)
        for day, station, i in reversed(available):
            next_slots = slots_used.copy()
            next_slots[day, station] += 1
            pending.append((previous_days | {tail: day}, next_slots, visits | {(day, tail): i}))
    return None
