# src/highs/model.py
"""
HiGHS (highspy) implementation of the aircraft scheduling model.

Two model builders:

    build_and_solve_model(...)              -> fleet assignment only
    build_and_solve_maintenance_model(...)  -> fleet assignment + maintenance

Both return (h, x, y, z):
    x : dict {(flight, aircraft): variable}  (always populated)
    y : dict {(day, aircraft): variable}     (maintenance only)
    z : dict {(flight, aircraft): variable}  (maintenance only)
"""

import bisect
import random
from collections import defaultdict
from itertools import groupby
from math import fsum

import highspy


def build_and_solve(
    nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
    aircraft_init, airports, m_airports, Days, data, maintenance=True,
    *, initial_maintenance_days=None,
):
    if maintenance:
        return build_and_solve_maintenance_model(
            nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
            aircraft_init, airports, m_airports, Days, data,
            initial_maintenance_days=initial_maintenance_days,
        )
    return build_and_solve_model(
        nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
        aircraft_init, airports, m_airports, Days, data,
    )


def build_and_solve_model(
    nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
    aircraft_init, airports, m_airports, Days, data,
):
    """
    Build one continuous route per aircraft using binary flight assignments.

    `cap_maintenance`, `horizon`, `m_costs`, `m_airports`, `Days` are accepted
    for signature compatibility with the maintenance model but not used.

    Returns:
        (h, x, y, z) with y = {} and z = {}.
    """
    h, x, _ = _build_fleet_model(nb_flights, flights, costs, aircraft_init, data)
    return h, x, {}, {}


def _build_fleet_model(nb_flights, flights, costs, aircraft_init, data):
    aircraft = range(len(aircraft_init))
    flight_ids = range(1, nb_flights + 1)
    reachable = _reachable_flights(flights, aircraft_init.values())
    tail_flights = {t: reachable[aircraft_init[t]] for t in aircraft}

    h = highspy.Highs()
    x = h.addVariables(
        flight_ids,
        aircraft,
        ub=[float(i in tail_flights[t]) for i in flight_ids for t in aircraft],
        obj=[costs[i - 1][t] for i in flight_ids for t in aircraft],
        type=highspy.HighsVarType.kInteger,
        out_array=False,
    )
    for i in flight_ids:
        columns = [x[i, t].index for t in aircraft if i in tail_flights[t]]
        h.addRow(1.0, 1.0, len(columns), columns, [1.0] * len(columns))

    # A nonempty route must leave its initial base at least once.
    for t in aircraft:
        base_departures = data["departures_sorted"].get(aircraft_init[t], [])
        columns = [x[i, t].index for i in base_departures]
        h.addRow(1.0, highspy.kHighsInf, len(columns), columns, [1.0] * len(columns))

    _add_fleet_flow_constraints(h, aircraft_init, data, tail_flights, x)
    return h, x, tail_flights


def _reachable_flights(flights, bases):
    """Find flights each base can reach when one aircraft travels on its own."""
    if any(flight["arrival"] <= flight["departure"] for flight in flights):
        raise ValueError("Fleet assignment requires each flight to arrive after it departs.")

    by_departure = sorted(flights, key=lambda flight: flight["departure"])
    reachable = {}
    for base in dict.fromkeys(bases):
        earliest_arrival = {base: float("-inf")}
        flights_from_base = set()
        for flight in by_departure:
            if earliest_arrival.get(flight["origin"], float("inf")) <= flight["departure"]:
                flights_from_base.add(flight["id"])
                dest = flight["dest"]
                earliest_arrival[dest] = min(
                    flight["arrival"], earliest_arrival.get(dest, float("inf"))
                )
        reachable[base] = flights_from_base
    return reachable


def _add_fleet_flow_constraints(h, aircraft_init, data, tail_flights, x):
    """Bound cumulative departures by cumulative arrivals plus initial stock."""
    for airport, departures in data["departures_sorted"].items():
        arrivals = data["arrivals_sorted"].get(airport, [])
        departure_times = [data["flight_departure_time"][i] for i in departures]
        arrival_times = [data["flight_arrival_time"][i] for i in arrivals]

        end = 0
        while end < len(departures):
            # Arrivals at the same instant are available for the departures.
            arrived = bisect.bisect_right(arrival_times, departure_times[end])
            # Between consecutive arrivals, the last departure balance implies
            # the earlier balances because the departure count only increases.
            end = (bisect.bisect_left(departure_times, arrival_times[arrived], lo=end)
                   if arrived < len(arrivals) else len(departures))

            departed_ids = set(departures[:end])
            arrived_ids = set(arrivals[:arrived])
            outgoing = sorted(departed_ids - arrived_ids)
            incoming = sorted(arrived_ids - departed_ids)
            for t, base in aircraft_init.items():
                reachable = tail_flights[t]
                dep_cols = [x[i, t].index for i in outgoing if i in reachable]
                if not dep_cols:
                    continue
                arr_cols = [x[i, t].index for i in incoming if i in reachable]
                columns = dep_cols + arr_cols
                coefficients = [1.0] * len(dep_cols) + [-1.0] * len(arr_cols)
                h.addRow(-highspy.kHighsInf, float(base == airport),
                         len(columns), columns, coefficients)


def build_and_solve_maintenance_model(
    nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
    aircraft_init, airports, m_airports, Days, data, *, initial_maintenance_days=None,
):
    """Build fleet assignment with maintenance at eligible end-of-day arrivals.

    initial_maintenance_days maps each aircraft to its last maintenance day.
    When omitted, use a reproducible draw from the pre-schedule days.
    """
    if horizon <= 0:
        raise ValueError("The maintenance horizon must be positive.")

    aircraft = range(len(aircraft_init))
    days = sorted(set(Days))
    first_day = days[0] if days else 1
    history = range(first_day - horizon, first_day)
    if initial_maintenance_days is None:
        rng = random.Random(0)
        initial_maintenance_days = {t: rng.choice(history) for t in aircraft}
    if (set(initial_maintenance_days) != set(aircraft)
            or any(day not in history for day in initial_maintenance_days.values())):
        raise ValueError(f"Supply one initial maintenance day in {list(history)} per aircraft.")

    h, x, tail_flights = _build_fleet_model(nb_flights, flights, costs, aircraft_init, data)
    flight_ids = range(1, nb_flights + 1)
    all_days = [*history, *days]
    day_set = set(days)
    airport_index = {airport: index for index, airport in enumerate(m_airports)}

    flights_by_day = defaultdict(list)
    maintenance_by_station = defaultdict(list)
    maintenance_station = {}
    for flight in flights:
        i, day, destination = flight["id"], flight["day"], flight["dest"]
        if day in day_set:
            flights_by_day[day].append(flight)
            if destination in airport_index:
                maintenance_by_station[destination, day].append(i)
                maintenance_station[i] = airport_index[destination]

    eligible = {}
    for t in aircraft:
        eligible[t] = tail_flights[t].intersection(maintenance_station)
    y = h.addVariables(
        all_days,
        aircraft,
        lb=[float(d == initial_maintenance_days[t]) for d in all_days for t in aircraft],
        ub=[float(d in day_set or d == initial_maintenance_days[t])
            for d in all_days for t in aircraft],
        type=highspy.HighsVarType.kInteger,
        out_array=False,
    )
    z = h.addVariables(
        flight_ids,
        aircraft,
        ub=[float(i in eligible[t]) for i in flight_ids for t in aircraft],
        obj=[m_costs[t][maintenance_station[i]] if i in eligible[t] else 0.0
             for i in flight_ids for t in aircraft],
        type=highspy.HighsVarType.kInteger,
        out_array=False,
    )

    for i, t in z:
        if i in eligible[t]:
            h.addRow(-highspy.kHighsInf, 0.0, 2, [z[i, t].index, x[i, t].index], [1.0, -1.0])

    for (station, day), ids in maintenance_by_station.items():
        columns = [z[i, t].index for i in ids for t in aircraft if i in eligible[t]]
        h.addRow(-highspy.kHighsInf, cap_maintenance, len(columns), columns, [1.0] * len(columns))

    _add_maintenance_day_constraints(h, days, flights_by_day, eligible, x, y, z)
    if days:
        _add_maintenance_windows(h, days, horizon, initial_maintenance_days, y)

    return h, x, y, z


def _add_maintenance_day_constraints(h, days, flights_by_day, eligible, x, y, z):
    for day in days:
        by_departure = sorted(flights_by_day[day], key=lambda f: f["departure"])
        departure_groups = [
            [f["id"] for f in group]
            for _, group in groupby(by_departure, key=lambda f: f["departure"])
        ]
        for t, candidates in eligible.items():
            previous_maintenance = []
            for group in departure_groups:
                if previous_maintenance:
                    # A tail can depart at most once at this time, and only
                    # if it has not taken its maintenance flight earlier today.
                    columns = [x[i, t].index for i in group] + previous_maintenance
                    h.addRow(-highspy.kHighsInf, 1.0, len(columns), columns, [1.0] * len(columns))
                previous_maintenance.extend(z[i, t].index for i in group if i in candidates)

            columns = previous_maintenance + [y[day, t].index]
            coefficients = [1.0] * len(previous_maintenance) + [-1.0]
            h.addRow(0.0, 0.0, len(columns), columns, coefficients)


def _add_maintenance_windows(h, days, horizon, initial_maintenance_days, y):
    for t, previous_day in initial_maintenance_days.items():
        # Earlier windows already contain the fixed historical maintenance.
        for end in range(previous_day + horizon, days[-1] + 1):
            columns = [y[d, t].index for d in days if end - horizon < d <= end]
            h.addRow(1.0, highspy.kHighsInf, len(columns), columns, [1.0] * len(columns))


def minimize_maintenance_visits(h, x, y, days, time_limit):
    """Re-solve with fixed flights and return the refined plan's operating cost."""
    if (time_limit <= 0
            or h.getInfo().primal_solution_status != highspy.SolutionStatus.kSolutionStatusFeasible):
        return None

    incumbent = h.getSolution()
    costs = h.getLp().col_cost_
    flight_columns = [var.index for var in x.values()]
    flight_column_set = set(flight_columns)
    assignments = [float(incumbent.col_value[col] > 0.5) for col in flight_columns]
    flight_cost = fsum(costs[col] for col, assigned in zip(flight_columns, assignments) if assigned)
    h.changeColsBounds(len(flight_columns), flight_columns, assignments, assignments)

    # Flight costs are constant once the assignments have been fixed.
    cost_columns = [col for col, cost in enumerate(costs) if cost and col not in flight_column_set]
    if cost_columns:
        cost_limit = fsum(costs[col] for col in cost_columns if incumbent.col_value[col] > 0.5)
        h.addRow(-highspy.kHighsInf, cost_limit, len(cost_columns),
                 cost_columns, [costs[col] for col in cost_columns])

    planning_days = set(days)
    visit_costs = [0.0] * len(costs)
    for (day, _), var in y.items():
        if day in planning_days:
            visit_costs[var.index] = 1.0
    h.changeColsCost(len(costs), list(range(len(costs))), visit_costs)
    h.setSolution(incumbent)
    h.setOptionValue("mip_rel_gap", 0.0)
    h.setOptionValue("time_limit", time_limit)
    h.run()

    if h.getInfo().primal_solution_status == highspy.SolutionStatus.kSolutionStatusFeasible:
        solution = h.getSolution()
        maintenance_cost = fsum(costs[col] for col in cost_columns if solution.col_value[col] > 0.5)
        return flight_cost + maintenance_cost
    return None
