"""Gurobi implementation of the shared tail-assignment formulation."""

from itertools import chain

from gurobipy import GRB, Model, quicksum

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
    model = Model("aircraft_scheduling")
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
    model.setObjective(quicksum(coef * var for coef, var in terms), GRB.MINIMIZE)
    return model, x, y, z


def _binary(model, name, lower, upper):
    return model.addVar(lb=lower, ub=upper, vtype=GRB.BINARY, name=name)


def _add_rows(model, rows):
    for positive, negative, sense, rhs in rows:
        lhs = quicksum(positive) - quicksum(negative)
        if sense == "=":
            model.addConstr(lhs == rhs)
        elif sense == "<=":
            model.addConstr(lhs <= rhs)
        else:
            model.addConstr(lhs >= rhs)


def prepare_maintenance_refinement(model, x, y, days):
    """Fix flights, warm-start the visit objective, and return the cost expression."""
    cost = model.getObjective()
    incumbent_cost = model.ObjVal
    variables = model.getVars()
    incumbent = model.getAttr(GRB.Attr.X, variables)
    assigned = [var for var in x.values() if var.X > 0.5]
    for var in assigned:
        var.lb = var.ub = 1
    model.setAttr(GRB.Attr.Start, variables, incumbent)
    model.addConstr(cost <= incumbent_cost)
    days = set(days)
    model.setObjective(quicksum(var for (day, _), var in y.items() if day in days))
    return cost


def build_and_solve_model_2(nb_flights, flights, costs, m_costs,
                            aircraft_init, m_airports, Days, data, model, x, y, z):
    prepare_maintenance_refinement(model, x, y, Days)
    return model, x, y, z
