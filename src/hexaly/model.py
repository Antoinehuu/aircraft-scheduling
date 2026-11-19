"""Hexaly implementation of the Gurobi tail-assignment formulation."""

import random
from bisect import bisect_left, bisect_right
from collections import defaultdict

from hexaly.optimizer import HexalyOptimizer, HxSolutionStatus


def build_and_solve(nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
                    aircraft_init, airports, m_airports, Days, data,
                    is_maintenance_instance):
    """Build an open model and return (optimizer, x, y, z)."""
    builder = build_and_solve_model
    if is_maintenance_instance:
        builder = build_and_solve_maintenance_model
    return builder(nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
                   aircraft_init, airports, m_airports, Days, data)


def build_and_solve_model(nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
                          aircraft_init, airports, m_airports, Days, data):
    """Build the fleet-only model, with empty maintenance decision dictionaries."""
    optimizer = HexalyOptimizer()
    model = optimizer.model
    flight_ids = range(1, nb_flights + 1)
    aircraft = range(len(aircraft_init))
    x = _add_assignment(model, flight_ids, aircraft, flights, aircraft_init, data)
    model.minimize(model.sum(costs[i - 1][t] * var for (i, t), var in x.items()))
    return optimizer, x, {}, {}


def build_and_solve_maintenance_model(nb_flights, cap_maintenance, horizon, flights,
                                      costs, m_costs, aircraft_init, airports,
                                      m_airports, Days, data):
    """Build the fleet-assignment model with overnight maintenance."""
    optimizer = HexalyOptimizer()
    model = optimizer.model
    flight_ids = range(1, nb_flights + 1)
    aircraft = range(len(aircraft_init))
    fictive_days = list(range(1 - horizon, 1))
    all_days = fictive_days + list(Days)

    x = _add_assignment(model, flight_ids, aircraft, flights, aircraft_init, data)
    y = {(d, t): model.bool() for d in all_days for t in aircraft}
    z = {(i, t): model.bool() for i in flight_ids for t in aircraft}
    _add_maintenance(model, aircraft, Days, fictive_days, all_days, horizon,
                     flights, m_airports, cap_maintenance, x, y, z)
    total_cost = model.sum(costs[i - 1][t] * var for (i, t), var in x.items())
    airport_index = {airport: idx for idx, airport in enumerate(m_airports)}
    for (i, t), var in z.items():
        destination = data["flight_destination"][i]
        if destination in airport_index:
            total_cost.add_operand(m_costs[t][airport_index[destination]] * var)
    model.minimize(total_cost)
    return optimizer, x, y, z


def _add_assignment(model, flight_ids, aircraft, flights, aircraft_init, data):
    x = {(i, t): model.bool() for i in flight_ids for t in aircraft}
    for i in flight_ids:
        model.constraint(model.sum(x[i, t] for t in aircraft) == 1)

    for airport, departures in data["departures_sorted"].items():
        arrivals = data["arrivals_sorted"].get(airport, [])
        arrival_times = [data["flight_arrival_time"][i] for i in arrivals]
        departure_times = [data["flight_departure_time"][i] for i in departures]
        for i, departure in zip(departures, departure_times):
            arrival_count = bisect_right(arrival_times, departure)
            departure_count = bisect_left(departure_times, departure)
            for t in aircraft:
                arrived = model.sum(x[j, t] for j in arrivals[:arrival_count])
                departed = model.sum(x[j, t] for j in departures[:departure_count])
                initial = int(aircraft_init.get(t) == airport)
                model.constraint(initial + arrived - departed >= x[i, t])

    first_flight = {}
    for flight in flights:
        key = (flight["departure"], flight["arrival"], flight["origin"], flight["dest"])
        i = flight["id"]
        j = first_flight.setdefault(key, i)
        if j != i:
            for t in aircraft:
                model.constraint(x[i, t] + x[j, t] <= 1)
    return x


def _add_maintenance(model, aircraft, days, fictive_days, all_days, horizon,
                     flights, m_airports, capacity, x, y, z):
    day_set = set(all_days)
    windows = [
        [d for d in range(start + 1, start + horizon + 1) if d in day_set]
        for start in all_days if start + horizon in day_set
    ]
    flights_by_day = defaultdict(list)
    maintenance_flights = defaultdict(list)
    for flight in flights:
        day = flight["day"]
        origin = flight["origin"]
        flights_by_day[day].append(flight)
        # Match the Gurobi formulation, which links maintenance by origin.
        if origin in m_airports:
            maintenance_flights[origin, day].append(flight["id"])

    later_flights = [
        (i["id"], j["id"])
        for d in days for i in flights_by_day[d] for j in flights_by_day[d]
        if j["departure"] > i["arrival"]
    ]
    for t in aircraft:
        last_maintenance = random.choice(fictive_days)
        for d in fictive_days:
            model.constraint(y[d, t] == int(d == last_maintenance))
        for window in windows:
            model.constraint(model.sum(y[d, t] for d in window) >= 1)
        for flight in flights:
            i = flight["id"]
            model.constraint(z[i, t] <= x[i, t])
        for i, j in later_flights:
            model.constraint(z[i, t] + x[j, t] <= 1)
        for d in days:
            linked = model.sum(z[i, t] for airport in m_airports
                               for i in maintenance_flights[airport, d])
            model.constraint(linked == y[d, t])

    for airport in m_airports:
        for d in days:
            model.constraint(model.sum(z[i, t] for i in maintenance_flights[airport, d]
                                       for t in aircraft) <= capacity)


def build_and_solve_model_2(nb_flights, flights, costs, m_costs,
                            aircraft_init, m_airports, Days, data, optimizer, x, y, z):
    """Prepare phase two, minimizing maintenance days at the incumbent cost."""
    if optimizer.solution.status not in (HxSolutionStatus.FEASIBLE, HxSolutionStatus.OPTIMAL):
        raise ValueError("Phase two requires a feasible phase-one solution.")

    model = optimizer.model
    total_cost = model.get_objective(0)
    best_cost = total_cost.value
    assigned = [var for var in x.values() if var.value]
    aircraft = range(len(aircraft_init))
    model.open()
    for var in assigned:
        model.constraint(var == 1)
    model.constraint(total_cost <= best_cost)
    model.remove_objective(0)
    model.minimize(model.sum(y[d, t] for d in Days for t in aircraft))
    model.close()
    return optimizer, x, y, z
