"""Hexaly implementation of the shared tail-assignment formulation."""

from itertools import chain

from hexaly.optimizer import HexalyOptimizer, HxSolutionStatus

from src.formulation import Maintenance, fleet_rows, tail_reachability


def build_and_solve(
    nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
    aircraft_init, airports, m_airports, Days, data, is_maintenance_instance,
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
    return result


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
    optimizer = HexalyOptimizer()
    model = optimizer.model
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
    model.minimize(model.sum(coef * var for coef, var in terms))
    return optimizer, x, y, z


def _binary(model, name, lower, upper):
    return model.bool() if lower != upper else model.create_constant(lower)


def _add_rows(model, rows):
    for positive, negative, sense, rhs in rows:
        lhs = model.sum(positive) - model.sum(negative)
        if sense == "=":
            model.constraint(lhs == rhs)
        elif sense == "<=":
            model.constraint(lhs <= rhs)
        else:
            model.constraint(lhs >= rhs)


def prepare_maintenance_refinement(optimizer, x, y, days):
    """Fix flights and minimize visits within the incumbent operating cost."""
    if optimizer.solution.status not in (HxSolutionStatus.FEASIBLE, HxSolutionStatus.OPTIMAL):
        raise ValueError("Phase two requires a feasible phase-one solution.")
    model = optimizer.model
    cost = model.get_objective(0)
    incumbent_cost = cost.value
    assigned = [var for var in x.values() if var.value]
    model.open()
    for var in assigned:
        model.constraint(var == 1)
    model.constraint(cost <= incumbent_cost)
    model.remove_objective(0)
    days = set(days)
    model.minimize(model.sum(var for (day, _), var in y.items() if day in days))
    model.close()
    return cost


def build_and_solve_model_2(nb_flights, flights, costs, m_costs,
                            aircraft_init, m_airports, Days, data, optimizer, x, y, z):
    prepare_maintenance_refinement(optimizer, x, y, Days)
    return optimizer, x, y, z
