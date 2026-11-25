# src/highs/main.py
"""
HiGHS version of the aircraft scheduling optimizer.
Same inputs / CSV outputs as the Gurobi and OR-Tools versions.
"""

import argparse
import csv
import math
import os
import time
from pathlib import Path

import highspy
from src import load_dat_file, preprocess_flights
from src.highs import build_and_solve
from src.highs.model import minimize_maintenance_visits
from src.solver_cli import default_results_path


def solve_instance(filepath, time_limit=600.0):
    filepath = str(filepath)
    print(f"\n{'='*70}")
    print(f"Processing: {os.path.basename(filepath)}")
    print(f"{'='*70}")

    # ---- load ------------------------------------------------------------
    print("▶ Loading data...")
    instance = load_dat_file(filepath)
    (nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
     aircraft_init, airports, m_airports, Days) = instance

    nb_aircrafts = len(aircraft_init)
    print(f"  ✓ {nb_flights} flights, {nb_aircrafts} aircraft, horizon={horizon}")

    # ---- preprocess ------------------------------------------------------
    print("▶ Preprocessing data...")
    data = preprocess_flights(flights, set(range(nb_aircrafts)), aircraft_init)
    print("  ✓ Preprocessing completed")

    # ---- build -----------------------------------------------------------
    print("▶ Building the model (HiGHS)...")
    start_time = time.perf_counter()

    is_maintenance_instance = "maintenance" in filepath

    h, x, y, _ = build_and_solve(*instance, data, maintenance=is_maintenance_instance)

    # Solver options (mirror the Gurobi block)
    # HiGHS uses setOptionValue, not setParam
    h.setOptionValue("output_flag", True)       # OutputFlag
    h.setOptionValue("mip_rel_gap", 0.02)       # MIPGap
    h.setOptionValue("time_limit", time_limit)  # TimeLimit

    optimization_start = time.perf_counter()
    if is_maintenance_instance:
        print("▶ Finding a fleet assignment to seed the maintenance solve...")
        _seed_maintenance_solve(h, x, instance, data, min(10.0, time_limit / 5))
        remaining = max(0.0, time_limit - (time.perf_counter() - optimization_start))
        h.setOptionValue("time_limit", remaining)

    print("▶ Optimization...")
    h.run()

    # ---- stats -----------------------------------------------------------
    # HiGHS exposes model dimensions via the LP object
    lp = h.getLp()
    nb_vars = lp.num_col_
    nb_constrs = lp.num_row_
    # Nonzeros: h.getNumNz() returns the current matrix nonzeros
    nb_nonzeros = h.getNumNz()

    # Solution info
    info = h.getInfo()
    model_status = h.getModelStatus()
    status_name = h.modelStatusToString(model_status)

    obj_value = None
    gap = None
    if info.primal_solution_status == highspy.SolutionStatus.kSolutionStatusFeasible:
        obj_value = info.objective_function_value
        gap = info.mip_gap
        dual_bound = info.mip_dual_bound

        remaining = time_limit - (time.perf_counter() - optimization_start)
        if is_maintenance_instance and remaining > 0:
            print("▶ Minimizing maintenance visits with flight assignments fixed...")
            refined_cost = minimize_maintenance_visits(h, x, y, Days, remaining)
            if refined_cost is not None:
                secondary_status = h.modelStatusToString(h.getModelStatus())
                print(f"  → {secondary_status} | maintenance visits={h.getObjectiveValue():.0f}")
                if refined_cost < obj_value:
                    obj_value = refined_cost
                    difference = max(0.0, obj_value - dual_bound)
                    if difference == 0.0:
                        gap = 0.0
                    else:
                        gap = difference / abs(obj_value) if obj_value else math.inf

    solve_time = time.perf_counter() - start_time

    results = {
        'filename': os.path.basename(filepath),
        'nb_flights': nb_flights,
        'nb_aircrafts': nb_aircrafts,
        'horizon': horizon,
        'nb_vars': nb_vars,
        'nb_constrs': nb_constrs,
        'nb_nonzeros': nb_nonzeros,
        'solve_time': round(solve_time, 2),
        'work_units': None,   # not exposed the same way as Gurobi
        'obj_value': round(obj_value, 2) if obj_value is not None else None,
        'mip_gap': round(gap, 4) if gap is not None else None,
        'status': status_name,
    }

    obj_str = f"{obj_value:.2f}" if obj_value is not None else "N/A"
    gap_str = f"{gap:.4f}" if gap is not None else "N/A"
    print(f"  → {status_name} | obj={obj_str} | gap={gap_str} | time={solve_time:.3f}s")

    return results


def _seed_maintenance_solve(h, x, instance, data, time_limit):
    fleet, fleet_x, _, _ = build_and_solve(*instance, data, maintenance=False)
    fleet.setOptionValue("output_flag", False)
    fleet.setOptionValue("time_limit", time_limit)
    fleet.setOptionValue("mip_rel_gap", 0.02)
    fleet.run()
    if fleet.getInfo().primal_solution_status == highspy.SolutionStatus.kSolutionStatusFeasible:
        fleet_values = fleet.getSolution().col_value
        columns = [x[key].index for key in fleet_x]
        values = [float(fleet_values[var.index] > 0.5) for var in fleet_x.values()]
        h.setSolution(len(columns), columns, values)


def write_results_csv(results, csv_path):
    """Append one instance result to the CSV file."""
    if not results:
        print("No results to write.")
        return

    fieldnames = list(results.keys())
    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0

    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(results)

    print(f"Result appended to: {csv_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?", default=Path("data/d=0.95"))
    parser.add_argument("--output", type=Path, help="override the solver's default results CSV")
    parser.add_argument("--time-limit", type=float, default=600.0, help="solver seconds per instance")
    args = parser.parse_args()
    if not math.isfinite(args.time_limit) or args.time_limit <= 0:
        parser.error("--time-limit must be a positive finite number")
    if args.input.is_dir():
        paths = sorted(path for path in args.input.glob("*.dat") if path.is_file())
    else:
        paths = [args.input] if args.input.is_file() and args.input.suffix == ".dat" else []
    if not paths:
        parser.error(f"No .dat instances found at {args.input}")
    output = args.output or default_results_path(args.input, Path(__file__).parent)

    print("\n" + "="*70)
    print("TAIL ASSIGNMENT OPTIMIZATION — HiGHS")
    print("="*70)

    failed = False
    for path in paths:
        try:
            results = solve_instance(path, args.time_limit)
        except Exception as e:
            failed = True
            print(f"Error for {os.path.basename(path)}: {e}")
            import traceback
            traceback.print_exc()
            results = {
                'filename': os.path.basename(path),
                'nb_flights': None, 'nb_aircrafts': None, 'horizon': None,
                'nb_vars': None, 'nb_constrs': None, 'nb_nonzeros': None,
                'solve_time': None, 'work_units': None,
                'obj_value': None, 'mip_gap': None,
                'status': f'ERROR: {e}',
            }
        write_results_csv(results, output)

    print(f"\n{'='*70}\n")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
