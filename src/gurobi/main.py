"""Run Gurobi on one .dat instance or a directory of instances."""

from math import inf
from pathlib import Path
from time import perf_counter

import gurobipy

from src import load_dat_file, preprocess_flights
from src.gurobi import build_and_solve
from src.gurobi.model import prepare_maintenance_refinement
from src.solver_cli import fleet_start_for, results_for, run_batch


def solve_instance(filepath, time_limit=600, mip_gap=0.02):
    filepath = str(filepath)
    instance = load_dat_file(filepath)
    data = preprocess_flights(instance[3], instance[7], instance[6])
    maintenance = "maintenance" in filepath
    start = perf_counter()
    model, x, y, _ = build_and_solve(*instance, data, maintenance)
    with model:
        model.Params.OutputFlag = 0
        model.Params.Presolve = 1
        model.Params.MIPGap = mip_gap
        assignment, _ = fleet_start_for(instance)
        if assignment:
            for (i, t), var in x.items():
                var.Start = int(assignment[i] == t)
        deadline = perf_counter() + time_limit
        model.Params.TimeLimit = time_limit
        model.optimize()

        counts = model.NumVars, model.NumConstrs, model.NumNZs
        status = _gurobi_status_name(model.Status)
        work = model.Work
        cost = gap = None
        if model.SolCount:
            cost, gap, bound = model.ObjVal, model.MIPGap, model.ObjBound
            if maintenance and perf_counter() < deadline:
                original_cost = prepare_maintenance_refinement(model, x, y, instance[9])
                model.Params.MIPGap = 0
                model.Params.TimeLimit = max(0, deadline - perf_counter())
                model.optimize()
                work += model.Work
                if model.SolCount:
                    print(f"Maintenance refinement | {_gurobi_status_name(model.Status)} | visits={model.ObjVal:.0f}")
                    refined = original_cost.getValue()
                    if refined < cost:
                        cost = refined
                        gap = abs(cost - bound) / abs(cost) if cost else (0 if bound == 0 else inf)
        return results_for(filepath, instance, counts, start, status, cost, gap, work)


def _gurobi_status_name(status_code):
    """Map Gurobi status codes to readable names (like HiGHS's modelStatusToString)."""
    names = {
        gurobipy.GRB.LOADED: 'LOADED',
        gurobipy.GRB.OPTIMAL: 'OPTIMAL',
        gurobipy.GRB.INFEASIBLE: 'INFEASIBLE',
        gurobipy.GRB.INF_OR_UNBD: 'INF_OR_UNBD',
        gurobipy.GRB.UNBOUNDED: 'UNBOUNDED',
        gurobipy.GRB.CUTOFF: 'CUTOFF',
        gurobipy.GRB.ITERATION_LIMIT: 'ITERATION_LIMIT',
        gurobipy.GRB.NODE_LIMIT: 'NODE_LIMIT',
        gurobipy.GRB.TIME_LIMIT: 'TIME_LIMIT',
        gurobipy.GRB.SOLUTION_LIMIT: 'SOLUTION_LIMIT',
        gurobipy.GRB.INTERRUPTED: 'INTERRUPTED',
        gurobipy.GRB.NUMERIC: 'NUMERIC',
        gurobipy.GRB.SUBOPTIMAL: 'SUBOPTIMAL',
        gurobipy.GRB.INPROGRESS: 'INPROGRESS',
        gurobipy.GRB.USER_OBJ_LIMIT: 'USER_OBJ_LIMIT',
    }
    return names.get(status_code, f'status={status_code}')


def main():
    return run_batch(solve_instance, "data/d=0.9", Path(__file__).parent, __doc__)


if __name__ == "__main__":
    raise SystemExit(main())
