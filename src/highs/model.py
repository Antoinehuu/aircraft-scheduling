# src/highs/model.py
"""
HiGHS (highspy) implementation of the aircraft scheduling model.

Two model builders:

    build_and_solve_model(...)              -> fleet assignment only
    build_and_solve_maintenance_model(...)  -> fleet assignment + maintenance

Both return (h, x, y, z):
    x : dict {(flight, aircraft): col_index}   (always populated)
    y : dict {(day,    aircraft): col_index}   (empty in the no-maintenance model)
    z : dict {(flight, aircraft): col_index}   (empty in the no-maintenance model)
"""

import bisect
import random

import highspy

# HiGHS variable indices must be plain ints. We map (i, t) tuples to a column index.
# We use three separate index spaces packed into one contiguous range:
#   x columns : offset_x .. offset_x + nb_flights*nb_aircrafts - 1
#   y columns : offset_y .. offset_y + len(tot_days)*nb_aircrafts - 1
#   z columns : offset_z .. offset_z + nb_flights*nb_aircrafts - 1


def build_and_solve(
            nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
            aircraft_init, airports, m_airports, Days, data, maintenance=True
            ):
    if maintenance==True:
        return build_and_solve_maintenance_model(
                nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
                aircraft_init, airports, m_airports, Days, data, )
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
    return h, x, {}, {}


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
    aircraft_init, airports, m_airports, Days, data,
):
    """
    Fleet-assignment model WITH maintenance constraints.

    Returns:
        (h, x, y, z) — all three variable dicts populated.
    """
    nb_aircrafts = len(aircraft_init)
    Aircraft = list(range(nb_aircrafts))
    Flights_id = list(range(1, nb_flights + 1))

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

    # ---- HiGHS instance --------------------------------------------------
    h = highspy.Highs()

    # ---- variables -------------------------------------------------------
    x = {}
    for i in Flights_id:
        for t in Aircraft:
            x[i, t] = h.addVariable(
                lb=0.0, ub=1.0, type=highspy.HighsVarType.kInteger
            )

    y = {}
    for d in tot_days:
        for t in Aircraft:
            y[d, t] = h.addVariable(
                lb=0.0, ub=1.0, type=highspy.HighsVarType.kInteger
            )

    z = {}
    for i in Flights_id:
        for t in Aircraft:
            z[i, t] = h.addVariable(
                lb=0.0, ub=1.0, type=highspy.HighsVarType.kInteger
            )

    # ---- fleet constraints ----------------------------------------------
    _add_coverage_constraints(h, Aircraft, Flights_id, x)
    _add_flow_constraints(h, Aircraft, aircraft_init, data, x, airports_set)
    _add_base_constraints(h, Aircraft, aircraft_init, data, x)
    _add_duplicate_constraints(h, Aircraft, flights, x)

    # ---- maintenance constraints ----------------------------------------
    _add_maintenance_constraints(
        h, Aircraft, Days, Days_fictive, tot_days, horizon,
        Flights_id, flights, flights_by_day, flights_by_origin_day,
        m_airports, cap_maintenance, x, y, z,
    )

    # ---- objective: flight costs + maintenance positioning costs --------
    cost_it = {
        (i, t): m_costs[t][ap_to_id[data['flight_destination'][i]]]
        for i in m_Flights_id for t in Aircraft
    }

    obj = [0.0] * h.getNumCol()
    for i in Flights_id:
        for t in Aircraft:
            obj[x[i, t]] = costs[i - 1][t]
    for i in m_Flights_id:
        for t in Aircraft:
            obj[z[i, t]] = cost_it[i, t]

    _apply_objective(h, obj)

    return h, x, y, z


# ===========================================================================
# Maintenance constraint helpers
# ===========================================================================

def _add_coverage_constraints(h, Aircraft, Flights_id, x):
    """C1 — every flight is assigned exactly once."""
    for i in Flights_id:
        h.addConstr(
            sum(x[i, t] for t in Aircraft) == 1,
            name=f"coverage_{i}",
        )


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


# ===========================================================================
# Objective helpers
# ===========================================================================

def _apply_objective(h, obj):
    """Push a dense coefficient vector to HiGHS and set minimise sense."""
    for col, coef in enumerate(obj):
        if coef != 0.0:
            h.changeColCost(col, coef)
    h.changeObjectiveSense(highspy.ObjSense.kMinimize)
