"""Run Hexaly on one .dat instance or a directory of instances."""

import math
from pathlib import Path
from time import perf_counter

from hexaly.optimizer import HxSolutionStatus

from src import load_dat_file, preprocess_flights
from src.hexaly import build_and_solve
from src.hexaly.model import prepare_maintenance_refinement
from src.solver_cli import fleet_start_for, results_for, run_batch


_FEASIBLE = (HxSolutionStatus.FEASIBLE, HxSolutionStatus.OPTIMAL)


def solve_instance(filepath, time_limit=600, mip_gap=0.02):
    filepath = str(filepath)
    instance = load_dat_file(filepath)
    data = preprocess_flights(instance[3], instance[7], instance[6])
    maintenance = "maintenance" in filepath
    start = perf_counter()
    optimizer, x, y, _ = build_and_solve(*instance, data, maintenance)
    with optimizer:
        model = optimizer.model
        model.close()
        optimizer.param.verbosity = 0
        optimizer.param.set_gap_limit(mip_gap)
        assignment, _ = fleet_start_for(instance)
        if assignment:
            solution = optimizer.solution
            for (i, t), var in x.items():
                if var.is_decision():
                    solution.set_value(var, int(assignment[i] == t))
        solver_seconds = max(1, int(time_limit))
        deadline = perf_counter() + solver_seconds
        optimizer.param.time_limit = solver_seconds
        optimizer.solve()

        counts = model.nb_decisions, model.nb_constraints, None
        solution = optimizer.solution
        status = solution.status.name
        cost = gap = None
        if solution.status in _FEASIBLE:
            cost = model.get_objective(0).value
            bound = solution.get_objective_bound(0)
            gap = solution.get_objective_gap(0)
            if not math.isfinite(gap):
                gap = None
            if maintenance and deadline - perf_counter() >= 1:
                original_cost = prepare_maintenance_refinement(optimizer, x, y, instance[9])
                optimizer.param.set_gap_limit(0)
                optimizer.param.time_limit = max(1, int(deadline - perf_counter()))
                optimizer.solve()
                if optimizer.solution.status in _FEASIBLE:
                    visits = model.get_objective(0).value
                    print(f"Maintenance refinement | {optimizer.solution.status.name} | visits={visits:.0f}")
                    if original_cost.value < cost:
                        cost = original_cost.value
                        gap = abs(cost - bound) / max(1, abs(cost), abs(bound)) if math.isfinite(bound) else None
        return results_for(filepath, instance, counts, start, status, cost, gap)


def main():
    return run_batch(solve_instance, "data/d=0.9", Path(__file__).parent, __doc__)


if __name__ == "__main__":
    raise SystemExit(main())
