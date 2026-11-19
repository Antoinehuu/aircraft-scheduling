"""OR-Tools CP-SAT implementation of the shared tail-assignment formulation."""

from itertools import chain

from ortools.sat.python import cp_model

from src.formulation import Maintenance, fleet_rows, tail_reachability


def build_and_solve(
    nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
    aircraft_init, airports, m_airports, Days, data, is_maintenance_instance, time_limit_seconds=600.0, num_workers=8, log_search_progress=True,
    *, initial_maintenance_days=None,
):
    args = (nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
            aircraft_init, airports, m_airports, Days, data)
    if is_maintenance_instance:
        result = build_and_solve_maintenance_model(
            *args, initial_maintenance_days=initial_maintenance_days
        )
    else:
        result = build_and_solve_model(*args)
    return (*result, _solver(time_limit_seconds, num_workers, log_search_progress))


def _solver(time_limit_seconds, num_workers, log_search_progress):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = num_workers
    solver.parameters.log_search_progress = log_search_progress
    return solver


def _int_cost(cost):
    """Preserve the CP-SAT runner's three decimal places of cost precision."""
    return int(round(cost * 1000))


def build_and_solve_model(
    nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
    aircraft_init, airports, m_airports, Days, data,
):
    """Build the fleet-only model and return it with the assignment variables."""
    return _build(nb_flights, flights, costs, aircraft_init, data)


def build_and_solve_maintenance_model(
    nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
    aircraft_init, airports, m_airports, Days, data, *, initial_maintenance_days=None,
):
    """Build the fleet model with maintenance at eligible end-of-day arrivals."""
    reachable = tail_reachability(flights, aircraft_init)
    maintenance = Maintenance(flights, Days, horizon, m_airports, reachable, initial_maintenance_days)
    return _build(nb_flights, flights, costs, aircraft_init, data, reachable,
                  maintenance, cap_maintenance, m_costs)


def _build(nb_flights, flights, costs, aircraft_init, data, reachable=None,
           maintenance=None, capacity=None, m_costs=None):
    if reachable is None:
        reachable = tail_reachability(flights, aircraft_init)
    model = cp_model.CpModel()
    flight_ids = range(1, nb_flights + 1)
    aircraft = range(len(aircraft_init))
    x = {(i, t): _binary(model, f"x_{i}_{t}", 0, int(i in reachable[t]))
         for i in flight_ids for t in aircraft}
    _add_rows(model, fleet_rows(flight_ids, aircraft_init, data, reachable, x))
    terms = ((costs[i - 1][t], var) for (i, t), var in x.items() if i in reachable[t])
    y, z = {}, {}
    if maintenance is not None:
        y = {(d, t): _binary(model, f"y_{d}_{t}", *maintenance.day_bounds(d, t))
             for d in maintenance.all_days for t in aircraft}
        z = {(i, t): _binary(model, f"z_{i}_{t}", 0, int(i in maintenance.eligible[t]))
             for i in flight_ids for t in aircraft}
        _add_rows(model, maintenance.rows(capacity, x, y, z))
        terms = chain(terms, maintenance.cost_terms(m_costs, z))
    model.minimize(cp_model.LinearExpr.sum([_int_cost(coef) * var for coef, var in terms]))
    return model, x, y, z


def _binary(model, name, lower, upper):
    return model.new_int_var(lower, upper, name)


def _add_rows(model, rows):
    for positive, negative, sense, rhs in rows:
        lhs = cp_model.LinearExpr.sum(positive) - cp_model.LinearExpr.sum(negative)
        if sense == "=":
            model.add(lhs == rhs)
        elif sense == "<=":
            model.add(lhs <= rhs)
        else:
            model.add(lhs >= rhs)


def _operating_cost(model):
    objective = model.proto.objective
    return cp_model.LinearExpr.weighted_sum(
        [model.get_int_var_from_proto_index(i) for i in objective.vars], list(objective.coeffs)
    )


def _set_visit_objective(model, y, days, cost, cost_limit):
    model.add(cost <= cost_limit)
    days = set(days)
    model.minimize(cp_model.LinearExpr.sum([var for (day, _), var in y.items() if day in days]))


def prepare_maintenance_refinement(model, solver, x, y, z, days):
    """Fix flights, keep the incumbent as a hint, and return the cost expression."""
    cost = _operating_cost(model)
    cost_limit = solver.value(cost)
    model.clear_hints()
    for decisions in (x, y, z):
        for var in decisions.values():
            model.add_hint(var, solver.value(var))
    for var in x.values():
        if solver.value(var):
            model.add(var == 1)
    _set_visit_objective(model, y, days, cost, cost_limit)
    return cost


def build_and_solve_model_2(
    nb_flights, flights, costs, m_costs, aircraft_init, m_airports, Days, data,
    first_solution_x, first_obj,
    time_limit_seconds=120.0, num_workers=8, log_search_progress=True,
    *, cap_maintenance, horizon, initial_maintenance_days=None,
):
    """Rebuild and refine a saved assignment with the original maintenance parameters.

    first_obj is the CP-SAT objective in scaled cost units.
    """
    model, x, y, z = build_and_solve_maintenance_model(
        nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
        aircraft_init, {}, m_airports, Days, data,
        initial_maintenance_days=initial_maintenance_days,
    )
    for key, var in x.items():
        model.add(var == first_solution_x.get(key, 0))
    _set_visit_objective(model, y, Days, _operating_cost(model), round(first_obj))
    return model, x, y, z, _solver(time_limit_seconds, num_workers, log_search_progress)
