# src/or_tools/main.py
"""
OR-Tools (CP-SAT) version of the aircraft scheduling optimizer.
Same inputs / CSV outputs as the Gurobi and HiGHS versions.
"""

import csv
import os
import time

from ortools.sat.python import cp_model
from src import load_dat_file, preprocess_flights
from src.or_tools import build_and_solve


def _compute_gap(solver):
    """Relative MIP gap from CP-SAT's objective value and best bound."""
    obj = solver.ObjectiveValue()
    bound = solver.BestObjectiveBound()
    if obj == 0:
        return 0.0 if bound == 0 else abs(bound)
    return abs(obj - bound) / abs(obj)


def solve_instance(filepath):
    print(f"\n{'='*70}")
    print(f"Processing: {os.path.basename(filepath)}")
    print(f"{'='*70}")

    # ---- load ------------------------------------------------------------
    print("▶ Loading data...")
    (nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
     aircraft_init, airports, m_airports, Days) = load_dat_file(filepath)

    nb_aircrafts = len(aircraft_init)
    print(f"  ✓ {nb_flights} flights, {nb_aircrafts} aircraft, horizon={horizon}")

    # ---- preprocess ------------------------------------------------------
    print("▶ Preprocessing data...")
    data = preprocess_flights(flights, set(range(nb_aircrafts)), aircraft_init)
    print("  ✓ Preprocessing completed")

    # ---- build -----------------------------------------------------------
    print("▶ Building the model (OR-Tools CP-SAT)...")
    start_time = time.perf_counter()

    is_maintenance_instance = "maintenance" in filepath

    model, x, y, z, solver = build_and_solve(
        nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
        aircraft_init, airports, m_airports, Days, data, is_maintenance_instance,
    )

    solver.parameters.log_search_progress = False
    solver.parameters.relative_gap_limit = 0.02
    solver.parameters.max_time_in_seconds = 600

    print("▶ Optimization...")
    status = solver.Solve(model)
    status_name = solver.StatusName(status)

    solve_time = time.perf_counter() - start_time

    # ---- stats -----------------------------------------------------------
    nb_vars = len(model.Proto().variables)
    nb_constrs = len(model.Proto().constraints)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        obj_value = solver.ObjectiveValue() / 1000.0   # undo cost scaling
        gap = _compute_gap(solver)
    else:
        obj_value = None
        gap = None

    results = {
        'filename': os.path.basename(filepath),
        'nb_flights': nb_flights,
        'nb_aircrafts': nb_aircrafts,
        'horizon': horizon,
        'nb_vars': nb_vars,
        'nb_constrs': nb_constrs,
        'nb_nonzeros': None,
        'solve_time': round(solve_time, 2),
        'work_units': None,
        'obj_value': round(obj_value, 2) if obj_value is not None else None,
        'mip_gap': round(gap, 4) if gap is not None else None,
        'status': status_name,
    }

    obj_str = f"{obj_value:.2f}" if obj_value is not None else "N/A"
    gap_str = f"{gap:.4f}" if gap is not None else "N/A"
    print(f"  → {status_name} | obj={obj_str} | gap={gap_str} | time={solve_time:.3f}s")

    return results


def write_results_csv(results, csv_path):
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
    print("\n" + "="*70)
    print("TAIL ASSIGNMENT OPTIMIZATION — OR-TOOLS / CP-SAT")
    print("="*70)

    # folder = "data_with_maintenance_constraints/d=4"
    folder = "data/d=1"

    paths = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".dat")]
    paths.sort()

    for path in paths:
        try:
            results = solve_instance(path)
        except Exception as e:
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
        write_results_csv(results, "./src/or_tools/results.csv")

    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    main()