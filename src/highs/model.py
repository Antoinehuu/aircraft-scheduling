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

from math import fsum

import highspy

from src.formulation import Maintenance, fleet_rows, tail_reachability


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
    reachable = tail_reachability(flights, aircraft_init)
    h = highspy.Highs()
    h.setOptionValue("threads", 10)
    h.setOptionValue("parallel", "on")
    x = h.addVariables(
        flight_ids,
        aircraft,
        ub=[float(i in reachable[t]) for i in flight_ids for t in aircraft],
        obj=[costs[i - 1][t] for i in flight_ids for t in aircraft],
        type=highspy.HighsVarType.kInteger,
        out_array=False,
    )
    _add_rows(h, fleet_rows(flight_ids, aircraft_init, data, reachable, x))
    return h, x, reachable


def _add_rows(h, rows):
    for positive, negative, sense, rhs in rows:
        columns = [var.index for var in positive] + [var.index for var in negative]
        coefficients = [1.0] * len(positive) + [-1.0] * len(negative)
        lower = -highspy.kHighsInf if sense == "<=" else rhs
        upper = highspy.kHighsInf if sense == ">=" else rhs
        h.addRow(lower, upper, len(columns), columns, coefficients)


def build_and_solve_maintenance_model(
    nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
    aircraft_init, airports, m_airports, Days, data, *, initial_maintenance_days=None,
):
    """Build fleet assignment with maintenance at eligible end-of-day arrivals.

    initial_maintenance_days maps each aircraft to its last maintenance day.
    When omitted, use a reproducible draw from the pre-schedule days.
    """
    h, x, reachable = _build_fleet_model(nb_flights, flights, costs, aircraft_init, data)
    maintenance = Maintenance(flights, Days, horizon, m_airports, reachable, initial_maintenance_days)
    aircraft = range(len(aircraft_init))
    flight_ids = range(1, nb_flights + 1)
    bounds = [maintenance.day_bounds(d, t) for d in maintenance.all_days for t in aircraft]
    y = h.addVariables(
        maintenance.all_days,
        aircraft,
        lb=[lower for lower, _ in bounds],
        ub=[upper for _, upper in bounds],
        type=highspy.HighsVarType.kInteger,
        out_array=False,
    )
    z = h.addVariables(
        flight_ids,
        aircraft,
        ub=[float(i in maintenance.eligible[t]) for i in flight_ids for t in aircraft],
        obj=[m_costs[t][maintenance.station_index[i]] if i in maintenance.eligible[t] else 0.0
             for i in flight_ids for t in aircraft],
        type=highspy.HighsVarType.kInteger,
        out_array=False,
    )
    _add_rows(h, maintenance.rows(cap_maintenance, x, y, z))
    return h, x, y, z


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
