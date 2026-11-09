# src/model.py
"""
OR-Tools (CP-SAT) port of the aircraft scheduling optimization model.

Mirrors build_and_solve_model / build_and_solve_model_2 from the Gurobi version:
  - x[f,t] : flight f is assigned to aircraft t
  - y[d,t] : aircraft t has a maintenance on day d (d may be fictitious, < 0)
  - z[f,t] : flight f is the last flight of the day that positions aircraft t
             at a maintenance airport (i.e. triggers maintenance)
"""

import bisect
import random
from ortools.sat.python import cp_model


def _int_cost(c):
    """CP-SAT needs integer costs. Scale floats to integers safely."""
    return int(round(c * 1000))


def build_and_solve_model_ortools(
    nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
    aircraft_init, airports, m_airports, Days, data,
    time_limit_seconds=300.0, num_workers=8, log_search_progress=True,
):
    """
    Builds the CP-SAT model.

    Returns:
        (model, x, y, z, solver, vars_dict)
        vars_dict holds helper structures needed by the second phase.
    """
    nb_aircrafts = len(aircraft_init)
    Aircraft = list(range(nb_aircrafts))
    Flights_id = list(range(1, nb_flights + 1))

    m_Flights_id = {f['id']: f['dest'] for f in flights if f['dest'] in m_airports}
    flight_day = {i['id']: i['day'] for i in flights}

    flights_by_day = {
        d: [i for i in Flights_id if flight_day[i] == d]
        for d in Days
    }
    flights_by_origin_day = {
        (k, d): [j for j in flights if j["origin"] == k and j["day"] == d]
        for k in m_airports
        for d in Days
    }

    Days_fictive = list(range(-horizon + 1, 1))
    tot_days = Days_fictive + Days

    ap_to_id = {ap: idx for idx, ap in enumerate(m_airports)}
    airports_set = set(data['departures_sorted'].keys())

    # --- model -------------------------------------------------------------
    model = cp_model.CpModel()

    x = {}
    for i in Flights_id:
        for t in Aircraft:
            x[i, t] = model.NewBoolVar(f"x_{i}_{t}")

    y = {}
    for d in tot_days:
        for t in Aircraft:
            y[d, t] = model.NewBoolVar(f"y_{d}_{t}")

    z = {}
    for i in Flights_id:
        for t in Aircraft:
            z[i, t] = model.NewBoolVar(f"z_{i}_{t}")

    # --- C1 coverage -------------------------------------------------------
    for i in Flights_id:
        model.AddExactlyOne(x[i, t] for t in Aircraft)

    # --- C2 flow (excluding base) ------------------------------------------
    _add_flow_constraints(model, Aircraft, aircraft_init, data, x, airports_set)

    # --- C3 flow (base) ----------------------------------------------------
    _add_base_constraints(model, Aircraft, aircraft_init, data, x)

    # --- C4 duplicates -----------------------------------------------------
    _add_duplicate_constraints(model, Aircraft, flights, x)

    # --- maintenance constraints -------------------------------------------
    _add_maintenance_constraints(
        model, Aircraft, Days, Days_fictive, tot_days, horizon,
        Flights_id, flights, flights_by_day, flights_by_origin_day,
        m_airports, cap_maintenance, x, y, z,
    )

    # --- objective ---------------------------------------------------------
    cost_it = {
        (i, t): m_costs[t][ap_to_id[data['flight_destination'][i]]]
        for i in m_Flights_id for t in Aircraft
    }

    obj_terms = []
    for i in Flights_id:
        for t in Aircraft:
            obj_terms.append(_int_cost(costs[i - 1][t]) * x[i, t])
    for i in m_Flights_id:
        for t in Aircraft:
            obj_terms.append(_int_cost(cost_it[i, t]) * z[i, t])
    model.Minimize(sum(obj_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = num_workers
    solver.parameters.log_search_progress = log_search_progress

    return model, x, y, z, solver


# ---------------------------------------------------------------------------
# Constraint helpers (1:1 with the Gurobi version)
# ---------------------------------------------------------------------------

def _add_flow_constraints(model, Aircraft, aircraft_init, data, x, airports_set):
    """C2 — flow constraints excluding the base airport."""
    for t in Aircraft:
        for airport in airports_set:
            if airport == aircraft_init.get(t):
                continue

            departures = data['departures_sorted'].get(airport, [])
            departure_times = [data['flight_departure_time'][fid] for fid in departures]
            arrivals = data['arrivals_sorted'].get(airport, [])
            arrival_times = [data['flight_arrival_time'][fid] for fid in arrivals]

            for target_fid in departures:
                target_time = data['flight_departure_time'][target_fid]

                idx_arrivals = bisect.bisect_right(arrival_times, target_time)
                arrivals_fids = arrivals[:idx_arrivals]

                idx_departures = bisect.bisect_left(departure_times, target_time)
                departures_fids = departures[:idx_departures]

                # sum_arrivals - sum_departures >= x[target]
                # <=> sum_arrivals - sum_departures - x[target] >= 0
                expr = (
                    sum(x[f, t] for f in arrivals_fids)
                    - sum(x[f, t] for f in departures_fids)
                    - x[target_fid, t]
                )
                model.Add(expr >= 0)


def _add_base_constraints(model, Aircraft, aircraft_init, data, x):
    """C3 — flow constraints for the base airport (allows -1 offset)."""
    for t in Aircraft:
        airport = aircraft_init.get(t)
        departures = data['departures_sorted'].get(airport, [])
        departure_times = [data['flight_departure_time'][fid] for fid in departures]
        arrivals = data['arrivals_sorted'].get(airport, [])
        arrival_times = [data['flight_arrival_time'][fid] for fid in arrivals]

        for target_fid in departures:
            target_time = data['flight_departure_time'][target_fid]

            idx_arrivals = bisect.bisect_right(arrival_times, target_time)
            arrivals_fids = arrivals[:idx_arrivals]

            idx_departures = bisect.bisect_left(departure_times, target_time)
            departures_fids = departures[:idx_departures]

            # sum_arrivals - sum_departures >= x[target] - 1
            expr = (
                sum(x[f, t] for f in arrivals_fids)
                - sum(x[f, t] for f in departures_fids)
                - x[target_fid, t]
            )
            model.Add(expr >= -1)


def _add_duplicate_constraints(model, Aircraft, flights, x):
    """C4 — at most one of two duplicate flights per aircraft."""
    seen = {}
    Doublons = []
    for fi in flights:
        key = (fi['departure'], fi['arrival'], fi['origin'], fi['dest'])
        if key in seen:
            Doublons.append((seen[key], fi['id']))
        else:
            seen[key] = fi['id']

    for t in Aircraft:
        for (i, j) in Doublons:
            model.Add(x[i, t] + x[j, t] <= 1)


def _add_maintenance_constraints(
    model, Aircraft, Days, Days_fictive, tot_days, horizon,
    Flights_id, flights, flights_by_day, flights_by_origin_day,
    m_airports, cap_maintenance, x, y, z,
):
    flight_departure = {i['id']: i['departure'] for i in flights}
    flight_arrival = {i['id']: i['arrival'] for i in flights}

    # Initial maintenance day (one random fictitious day per aircraft)
    d_m = [random.choice(Days_fictive) for _ in Aircraft]
    for t in Aircraft:
        for d in Days_fictive:
            model.Add(y[d, t] == (1 if d == d_m[t] else 0))

    # At least one maintenance every `horizon` days
    for t in Aircraft:
        for d0 in tot_days:
            if d0 + horizon in tot_days:
                window = [d for d in range(d0 + 1, d0 + horizon + 1) if d in tot_days]
                if window:
                    model.Add(sum(y[d, t] for d in window) >= 1)

    # z implies x
    for i in Flights_id:
        for t in Aircraft:
            model.Add(x[i, t] >= z[i, t])

    # The last flight of the day matches the maintenance airport
    for t in Aircraft:
        for d in Days:
            for i in flights_by_day[d]:
                for j in flights_by_day[d]:
                    if flight_departure[j] > flight_arrival[i]:
                        model.Add(z[i, t] + x[j, t] <= 1)

    # If an aircraft is sent for maintenance, there is a flight for it
    for t in Aircraft:
        for d in Days:
            trigger = [
                z[j["id"], t]
                for k in m_airports
                for j in flights_by_origin_day.get((k, d), [])
            ]
            model.Add(sum(trigger) == y[d, t])

    # Maintenance capacity per (airport, day)
    for k in m_airports:
        for d in Days:
            trigger = [
                z[i["id"], t]
                for t in Aircraft
                for i in flights_by_origin_day.get((k, d), [])
            ]
            model.Add(sum(trigger) <= cap_maintenance)


# ---------------------------------------------------------------------------
# Phase 2 — locally remove excess maintenances
# ---------------------------------------------------------------------------

def build_and_solve_model_ortools_2(
    nb_flights, flights, costs, m_costs,
    aircraft_init, m_airports, Days, data,
    first_solution_x, first_obj,
):
    """
    Phase 2: fix the flight→aircraft assignment from phase 1, then minimize
    the number of maintenance days (same spirit as the Gurobi version).

    `first_solution_x` is a dict {(i,t): 0/1} extracted from the CP-SAT solver.
    """
    nb_aircrafts = len(aircraft_init)
    Aircraft = list(range(nb_aircrafts))
    Flights_id = list(range(1, nb_flights + 1))

    m_Flights_id = {f['id']: f['dest'] for f in flights if f['dest'] in m_airports}
    ap_to_id = {ap: idx for idx, ap in enumerate(m_airports)}

    model = cp_model.CpModel()

    # Re-declare variables
    x = {}
    for i in Flights_id:
        for t in Aircraft:
            x[i, t] = model.NewBoolVar(f"x_{i}_{t}")

    flight_day = {i['id']: i['day'] for i in flights}
    flights_by_day = {d: [i for i in Flights_id if flight_day[i] == d] for d in Days}
    flights_by_origin_day = {
        (k, d): [j for j in flights if j["origin"] == k and j["day"] == d]
        for k in m_airports for d in Days
    }

    Days_fictive = list(range(-len(Days) - 1, 1))  # enough room
    # We don't know `horizon` here; caller passes it implicitly through Days.
    # For phase 2 we only need y over real Days (fictitious days are frozen).
    y_real = {}
    for d in Days:
        for t in Aircraft:
            y_real[d, t] = model.NewBoolVar(f"y_{d}_{t}")

    z = {}
    for i in Flights_id:
        for t in Aircraft:
            z[i, t] = model.NewBoolVar(f"z_{i}_{t}")

    # Fix x from phase 1
    for i in Flights_id:
        for t in Aircraft:
            model.Add(x[i, t] == first_solution_x.get((i, t), 0))

    # z <= x  (redundant with fixed x but keeps z defined)
    for i in Flights_id:
        for t in Aircraft:
            model.Add(x[i, t] >= z[i, t])

    # last-flight logic (same as phase 1, restricted to real days)
    flight_departure = {i['id']: i['departure'] for i in flights}
    flight_arrival = {i['id']: i['arrival'] for i in flights}
    for t in Aircraft:
        for d in Days:
            for i in flights_by_day[d]:
                for j in flights_by_day[d]:
                    if flight_departure[j] > flight_arrival[i]:
                        model.Add(z[i, t] + x[j, t] <= 1)

    # link y ↔ z on real days
    for t in Aircraft:
        for d in Days:
            trigger = [
                z[j["id"], t]
                for k in m_airports
                for j in flights_by_origin_day.get((k, d), [])
            ]
            model.Add(sum(trigger) == y_real[d, t])

    # Objective: minimize number of maintenance days on real days
    model.Minimize(sum(y_real[d, t] for d in Days for t in Aircraft))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 120.0
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = True

    return model, x, y_real, z, solver