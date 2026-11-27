"""Run OR-Tools CP-SAT on one .dat instance or a directory of instances."""

from pathlib import Path
from time import perf_counter

from ortools.sat.python import cp_model

from src import load_dat_file, preprocess_flights
from src.or_tools import build_and_solve
from src.or_tools.model import prepare_maintenance_refinement
from src.solver_cli import results_for, run_batch, start_values_for


def solve_instance(filepath, time_limit=600, mip_gap=0.02):
    filepath = str(filepath)
    instance = load_dat_file(filepath)
    data = preprocess_flights(instance[3], instance[7], instance[6])
    maintenance = "maintenance" in filepath
    start = perf_counter()
    model, x, y, z, solver = build_and_solve(*instance, data, maintenance, log_search_progress=False)
    solver.parameters.relative_gap_limit = mip_gap
    values, _ = start_values_for(instance, x, y, z)
    for var, value in values:
        model.add_hint(var, value)
    deadline = perf_counter() + time_limit
    solver.parameters.max_time_in_seconds = time_limit
    status = solver.solve(model)
    status_name = solver.status_name(status)
    counts = len(model.proto.variables), len(model.proto.constraints), None
    cost = gap = None
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        cost = solver.objective_value
        bound = solver.best_objective_bound
        if maintenance and perf_counter() < deadline:
            original_cost = prepare_maintenance_refinement(model, solver, x, y, z, instance[9])
            solver.parameters.relative_gap_limit = 0
            solver.parameters.max_time_in_seconds = max(0, deadline - perf_counter())
            status = solver.solve(model)
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                print(f"Maintenance refinement | {solver.status_name(status)} | visits={solver.objective_value:.0f}")
                cost = min(cost, solver.value(original_cost))
        gap = abs(cost - bound) / abs(cost) if cost else abs(bound)
        cost /= 1000
    return results_for(filepath, instance, counts, start, status_name, cost, gap)


def main():
    return run_batch(solve_instance, "data/d=0.95", Path(__file__).parent, __doc__)


if __name__ == "__main__":
    raise SystemExit(main())
