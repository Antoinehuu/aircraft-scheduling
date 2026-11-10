# src/highs/model.py
"""
HiGHS (highspy) implementation of the aircraft scheduling model.

Mirrors the Gurobi build_and_solve_model: same arguments, same return shape.
Only the modelling primitives change (addVariable / addConstr / changeColsIntegrality).
"""

import bisect
import random

import highspy

# HiGHS variable indices must be plain ints. We map (i, t) tuples to a column index.
# We use three separate index spaces packed into one contiguous range:
#   x columns : offset_x .. offset_x + nb_flights*nb_aircrafts - 1
#   y columns : offset_y .. offset_y + len(tot_days)*nb_aircrafts - 1
#   z columns : offset_z .. offset_z + nb_flights*nb_aircrafts - 1


def build_and_solve_model(
    nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
    aircraft_init, airports, m_airports, Days, data,
):
    """
    Builds the HiGHS model for the aircraft scheduling problem.

    Returns:
        (h, x, y, z) where h is the highspy.Highs instance and x, y, z are
        dicts mapping (index, aircraft) -> column index in the HiGHS model.
    """
    nb_aircrafts = len(aircraft_init)
    Aircraft = list(range(nb_aircrafts))
    Flights_id = list(range(1, nb_flights + 1))

    # ---- useful mappings (identical to Gurobi version) -------------------
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

    # ---- HiGHS instance --------------------------------------------------
    h = highspy.Highs()

    # ---- variable layout -------------------------------------------------
    # We will add all variables first (with bounds and integrality),
    # then add constraints by column indices.

    # x : binary, one per (flight, aircraft)
    x = {}
    for i in Flights_id:
        for t in Aircraft:
            idx = h.addVariable(lb=0.0, ub=1.0, type=highspy.HighsVarType.kInteger)
            x[i, t] = idx

    # y : binary, one per (day, aircraft) for fictitious + real days
    y = {}
    for d in tot_days:
        for t in Aircraft:
            idx = h.addVariable(lb=0.0, ub=1.0, type=highspy.HighsVarType.kInteger)
            y[d, t] = idx

    # z : binary, one per (flight, aircraft)
    z = {}
    for i in Flights_id:
        for t in Aircraft:
            idx = h.addVariable(lb=0.0, ub=1.0, type=highspy.HighsVarType.kInteger)
            z[i, t] = idx

    # ---- C1 coverage -----------------------------------------------------
    # sum_t x[i,t] == 1  for each flight i
    for i in Flights_id:
        h.addConstr(
            sum(x[i, t] for t in Aircraft) == 1,
            name=f"coverage_{i}",
        )

    # ---- C2 flow (excluding base) ----------------------------------------
    _add_flow_constraints(h, Aircraft, aircraft_init, data, x, airports_set)

    # ---- C3 flow (base) --------------------------------------------------
    _add_base_constraints(h, Aircraft, aircraft_init, data, x)

    # ---- C4 duplicates ---------------------------------------------------
    _add_duplicate_constraints(h, Aircraft, flights, x)

    # ---- maintenance constraints -----------------------------------------
    _add_maintenance_constraints(
        h, Aircraft, Days, Days_fictive, tot_days, horizon,
        Flights_id, flights, flights_by_day, flights_by_origin_day,
        m_airports, cap_maintenance, x, y, z,
    )

    # ---- objective -------------------------------------------------------
    cost_it = {
        (i, t): m_costs[t][ap_to_id[data['flight_destination'][i]]]
        for i in m_Flights_id for t in Aircraft
    }

    # Build objective coefficient vector (length = number of variables)
    num_vars = h.getNumCol()
    obj = [0.0] * num_vars

    for i in Flights_id:
        for t in Aircraft:
            obj[x[i, t]] = costs[i - 1][t]

    for i in m_Flights_id:
        for t in Aircraft:
            obj[z[i, t]] = cost_it[i, t]

    # Apply objective coefficients and minimisation sense
    for col, coef in enumerate(obj):
        if coef != 0.0:
            h.changeColCost(col, coef)
    h.changeObjectiveSense(highspy.ObjSense.kMinimize)

    return h, x, y, z


# ---------------------------------------------------------------------------
# Constraint helpers (direct port of the Gurobi version)
# ---------------------------------------------------------------------------

def _add_flow_constraints(h, Aircraft, aircraft_init, data, x, airports_set):
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

                # sum_arrivals - sum_departures >= x[target_fid, t]
                # <=> sum_arrivals - sum_departures - x[target_fid, t] >= 0
                # HiGHS: addConstr(lower <= expr <= upper)
                expr = (
                    sum(x[f, t] for f in arrivals_fids)
                    - sum(x[f, t] for f in departures_fids)
                    - x[target_fid, t]
                )
                h.addConstr(expr >= 0, name=f"flow_{t}_{airport}_{target_fid}")


def _add_base_constraints(h, Aircraft, aircraft_init, data, x):
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

            # sum_arrivals - sum_departures >= x[target_fid, t] - 1
            # <=> sum_arrivals - sum_departures - x[target_fid, t] >= -1
            expr = (
                sum(x[f, t] for f in arrivals_fids)
                - sum(x[f, t] for f in departures_fids)
                - x[target_fid, t]
            )
            h.addConstr(expr >= -1, name=f"base_{t}_{airport}_{target_fid}")


def _add_duplicate_constraints(h, Aircraft, flights, x):
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
            h.addConstr(x[i, t] + x[j, t] <= 1, name=f"dup_{i}_{j}_{t}")


def _add_maintenance_constraints(
    h, Aircraft, Days, Days_fictive, tot_days, horizon,
    Flights_id, flights, flights_by_day, flights_by_origin_day,
    m_airports, cap_maintenance, x, y, z,
):
    flight_departure = {i['id']: i['departure'] for i in flights}
    flight_arrival = {i['id']: i['arrival'] for i in flights}

    # Initial maintenance day (one random fictitious day per aircraft)
    d_m = [random.choice(Days_fictive) for _ in Aircraft]
    for t in Aircraft:
        for d in Days_fictive:
            target = 1 if d == d_m[t] else 0
            h.addConstr(y[d, t] == target, name=f"init_maint_{d}_{t}")

    # At least one maintenance every `horizon` days
    for t in Aircraft:
        for d0 in tot_days:
            if d0 + horizon in tot_days:
                window = [d for d in range(d0 + 1, d0 + horizon + 1) if d in tot_days]
                if window:
                    h.addConstr(
                        sum(y[d, t] for d in window) >= 1,
                        name=f"maint_window_{t}_{d0}",
                    )

    # z implies x
    for i in Flights_id:
        for t in Aircraft:
            h.addConstr(x[i, t] >= z[i, t], name=f"z_implies_x_{i}_{t}")

    # The last flight of the day matches the maintenance airport
    for t in Aircraft:
        for d in Days:
            for i in flights_by_day[d]:
                for j in flights_by_day[d]:
                    if flight_departure[j] > flight_arrival[i]:
                        h.addConstr(
                            z[i, t] + x[j, t] <= 1,
                            name=f"last_flight_{t}_{d}_{i}_{j}",
                        )

    # If an aircraft is sent for maintenance, there is a flight for it
    for t in Aircraft:
        for d in Days:
            trigger = [
                z[j["id"], t]
                for k in m_airports
                for j in flights_by_origin_day.get((k, d), [])
            ]
            if trigger:
                h.addConstr(
                    sum(trigger) == y[d, t],
                    name=f"maint_link_{t}_{d}",
                )
            else:
                h.addConstr(y[d, t] == 0, name=f"maint_link_empty_{t}_{d}")

    # Maintenance capacity per (airport, day)
    for k in m_airports:
        for d in Days:
            trigger = [
                z[i["id"], t]
                for t in Aircraft
                for i in flights_by_origin_day.get((k, d), [])
            ]
            if trigger:
                h.addConstr(
                    sum(trigger) <= cap_maintenance,
                    name=f"maint_cap_{k}_{d}",
                )
