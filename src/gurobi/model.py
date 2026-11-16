# src/gurobi/model.py
"""
Gurobi implementation of the aircraft scheduling model.

Public entry points:
    build_and_solve(...)                    -> dispatcher
    build_and_solve_model(...)              -> fleet assignment only (no maintenance)
    build_and_solve_maintenance_model(...)  -> fleet assignment + maintenance
    build_and_solve_model_2(...)            -> phase 2 (maintenance model only)

All model builders return (model, x, y, z):
    x : tupledict {(flight, aircraft): var}   (always populated)
    y : tupledict {(day,    aircraft): var}   (empty in the no-maintenance model)
    z : tupledict {(flight, aircraft): var}   (empty in the no-maintenance model)
"""

import bisect
import random
from gurobipy import Model, GRB, quicksum


# ===========================================================================
# Dispatcher
# ===========================================================================

def build_and_solve(nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
                    aircraft_init, airports, m_airports, Days, data,
                    is_maintenance_instance):
    """
    Dispatch to the maintenance or no-maintenance model.

    Args:
        is_maintenance_instance: True -> maintenance model, False -> fleet only.
    """
    if is_maintenance_instance:
        return build_and_solve_maintenance_model(
            nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
            aircraft_init, airports, m_airports, Days, data,
        )
    return build_and_solve_model(
        nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
        aircraft_init, airports, m_airports, Days, data,
    )


# ===========================================================================
# No-maintenance model (pure fleet assignment)
# ===========================================================================

def build_and_solve_model(nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
                          aircraft_init, airports, m_airports, Days, data):
    """
    Fleet-assignment model WITHOUT maintenance.

    `cap_maintenance`, `horizon`, `m_costs`, `m_airports`, `Days` are accepted
    for signature compatibility with the maintenance model but not used.

    Returns:
        (model, x, y, z) with y = {} and z = {}.
    """
    nb_aircrafts = len(aircraft_init)
    Aircraft = range(nb_aircrafts)
    Flights_id = range(1, nb_flights + 1)

    airports_set = set(data['departures_sorted'].keys())

    model = Model("aircraft_scheduling")

    # ---- variables: x only ----------------------------------------------
    x = model.addVars(Flights_id, Aircraft, vtype=GRB.BINARY, name="x")
    y = {}
    z = {}

    # ---- shared constraints ---------------------------------------------
    _add_coverage_constraints(model, Aircraft, Flights_id, x)
    _add_flow_constraints(model, Aircraft, aircraft_init, data, x, airports_set)
    _add_base_constraints(model, Aircraft, aircraft_init, data, x)
    _add_duplicate_constraints(model, Aircraft, flights, x)

    # ---- objective: flight costs only ------------------------------------
    model.setObjective(
        quicksum(costs[i - 1][t] * x[i, t] for i in Flights_id for t in Aircraft),
        GRB.MINIMIZE,
    )

    return model, x, y, z


# ===========================================================================
# Maintenance model
# ===========================================================================

def build_and_solve_maintenance_model(nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
                                      aircraft_init, airports, m_airports, Days, data):
    """
    Fleet-assignment model WITH maintenance constraints.

    Returns:
        (model, x, y, z) — all three variable dicts populated.
    """
    nb_aircrafts = len(aircraft_init)
    Aircraft = range(nb_aircrafts)
    Flights_id = range(1, nb_flights + 1)

    # ---- mappings --------------------------------------------------------
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

    # ---- model -----------------------------------------------------------
    model = Model("aircraft_scheduling")

    # ---- variables -------------------------------------------------------
    x = model.addVars(Flights_id, Aircraft, vtype=GRB.BINARY, name="x")
    y = model.addVars(tot_days, Aircraft, vtype=GRB.BINARY, name="y")
    z = model.addVars(Flights_id, Aircraft, vtype=GRB.BINARY, name="z")

    # ---- shared constraints ---------------------------------------------
    _add_coverage_constraints(model, Aircraft, Flights_id, x)
    _add_flow_constraints(model, Aircraft, aircraft_init, data, x, airports_set)
    _add_base_constraints(model, Aircraft, aircraft_init, data, x)
    _add_duplicate_constraints(model, Aircraft, flights, x)

    # ---- maintenance constraints ----------------------------------------
    _add_maintenance_constraints(
        model, Aircraft, Days, Days_fictive, tot_days, horizon,
        Flights_id, flights, flights_by_day, flights_by_origin_day,
        m_airports, cap_maintenance, x, y, z,
    )

    # ---- objective: flight costs + maintenance positioning costs --------
    cost_it = {
        (i, t): m_costs[t][ap_to_id[data['flight_destination'][i]]]
        for i in m_Flights_id for t in Aircraft
    }

    model.setObjective(
        quicksum(costs[i - 1][t] * x[i, t] for i in Flights_id for t in Aircraft)
        + quicksum(z[i, t] * cost_it[i, t] for i in m_Flights_id for t in Aircraft),
        GRB.MINIMIZE,
    )

    return model, x, y, z


# ===========================================================================
# Shared constraint helpers
# ===========================================================================

def _add_coverage_constraints(model, Aircraft, Flights_id, x):
    """C1 — every flight is assigned exactly once."""
    model.addConstrs(
        (quicksum(x[i, t] for t in Aircraft) == 1 for i in Flights_id),
        name="coverage",
    )


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

                sum_arrivals = quicksum(x[f, t] for f in arrivals_fids)
                sum_departures = quicksum(x[f, t] for f in departures_fids)

                model.addConstr(
                    sum_arrivals - sum_departures >= x[target_fid, t],
                    f"flow_{t}_{airport}_{target_fid}",
                )


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

            sum_arrivals = quicksum(x[f, t] for f in arrivals_fids)
            sum_departures = quicksum(x[f, t] for f in departures_fids)

            model.addConstr(
                sum_arrivals - sum_departures >= x[target_fid, t] - 1,
                f"base_{t}_{airport}_{target_fid}",
            )


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

    if Doublons:
        model.addConstrs(
            (x[i, t] + x[j, t] <= 1 for t in Aircraft for (i, j) in Doublons),
            name="duplicates",
        )


def _add_maintenance_constraints(model, Aircraft, Days, Days_fictive, tot_days, horizon,
                                 Flights_id, flights, flights_by_day, flights_by_origin_day,
                                 m_airports, cap_maintenance, x, y, z):
    """Adds maintenance constraints."""

    flight_departure = {i['id']: i['departure'] for i in flights}
    flight_arrival = {i['id']: i['arrival'] for i in flights}

    # Initial maintenance condition
    d_m = [random.choice(Days_fictive) for _ in Aircraft]

    model.addConstrs(
        (y[d, t] == (1 if d == d_m[t] else 0) for t in Aircraft for d in Days_fictive),
        name="initial_maintenance",
    )

    # At least one maintenance every horizon days
    model.addConstrs(
        (quicksum(y[d, t] for d in range(d0 + 1, d0 + horizon + 1) if d in tot_days) >= 1
         for t in Aircraft for d0 in tot_days if d0 + horizon in tot_days),
        name="maintenance_window",
    )

    # The aircraft arrives at the destination for maintenance
    model.addConstrs(
        (x[i, t] >= z[i, t] for i in Flights_id for t in Aircraft),
        name="arrival_for_maintenance",
    )

    # The last flight of the day matches the maintenance airport
    model.addConstrs(
        (
            z[i, t] + x[j, t] <= 1
            for t in Aircraft
            for d in Days
            for i in flights_by_day[d]
            for j in flights_by_day[d]
            if flight_departure[j] > flight_arrival[i]
        ),
        name="last_flight_logic",
    )

    # If an aircraft is sent for maintenance, then there is a flight to carry it out
    model.addConstrs(
        (quicksum(z[j["id"], t] for k in m_airports
                  for j in flights_by_origin_day.get((k, d), [])) == y[d, t]
         for t in Aircraft for d in Days),
        name="maintenance_flight_link",
    )

    # Maintenance capacity constraint
    model.addConstrs(
        (quicksum(z[i["id"], t] for t in Aircraft
                  for i in flights_by_origin_day.get((k, d), [])) <= cap_maintenance
         for k in m_airports for d in Days),
        name="maintenance_capacity",
    )


# ===========================================================================
# Phase 2 — locally reduce excess maintenances (maintenance model only)
# ===========================================================================

def build_and_solve_model_2(nb_flights, flights, costs, m_costs,
                            aircraft_init, m_airports, Days, data, model, x, y, z):
    """Locally optimizes by removing excess maintenances."""

    nb_aircrafts = len(aircraft_init)
    Aircraft = range(nb_aircrafts)
    Flights_id = range(1, nb_flights + 1)
    best_obj1 = model.ObjVal

    # Fix the flight->aircraft assignment from phase 1
    for i in Flights_id:
        for t in Aircraft:
            if x[i, t].X > 0.5:
                x[i, t].lb = 1
                x[i, t].ub = 1

    m_Flights_id = {f['id']: f['dest'] for f in flights if f['dest'] in m_airports}
    ap_to_id = {ap: idx for idx, ap in enumerate(m_airports)}

    cost_it = {
        (i, t): m_costs[t][ap_to_id[data['flight_destination'][i]]]
        for i in m_Flights_id for t in Aircraft
    }

    # Keep phase-1 total cost within best_obj1
    model.addConstr(
        quicksum(costs[i - 1][t] * x[i, t] for i in Flights_id for t in Aircraft)
        + quicksum(z[i, t] * cost_it[i, t] for i in m_Flights_id for t in Aircraft)
        <= best_obj1,
    )

    # New objective: minimize maintenance days
    model.setObjective(quicksum(y[d, t] for d in Days for t in Aircraft))

    return model, x, y, z
