# src/gurobi/main.py
"""
Gurobi version of the aircraft scheduling optimizer.
Same inputs / CSV outputs as the HiGHS and OR-Tools versions.
"""

import csv
import os
import time

import gurobipy
from src import load_dat_file, preprocess_flights
from src.gurobi import build_and_solve


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
    print("▶ Building the model (Gurobi)...")
    start_time = time.perf_counter()

    is_maintenance_instance = "maintenance" in filepath

    model, x, y, z = build_and_solve(
        nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
        aircraft_init, airports, m_airports, Days, data, is_maintenance_instance
    )

    # Solver options (mirror the HiGHS block)
    model.setParam("OutputFlag", 0)       # HiGHS: output_flag
    model.setParam("Presolve", 1)         # HiGHS: presolve on by default
    model.setParam("MIPGap", 0.02)        # HiGHS: mip_rel_gap
    model.setParam("TimeLimit", 600)      # HiGHS: time_limit

    print("▶ Optimization...")
    model.optimize()

    solve_time = time.perf_counter() - start_time

    # ---- stats -----------------------------------------------------------
    nb_vars = model.NumVars
    nb_constrs = model.NumConstrs
    nb_nonzeros = model.NumNZs
    nb_work = model.Work

    # Solution info
    status_code = model.status
    status_name = _gurobi_status_name(status_code)

    # Objective and gap are only meaningful if a feasible solution exists
    obj_value = None
    gap = None
    if status_code == gurobipy.GRB.OPTIMAL or model.SolCount > 0:
        obj_value = model.ObjVal
        gap = model.MIPGap

    results = {
        'filename': os.path.basename(filepath),
        'nb_flights': nb_flights,
        'nb_aircrafts': nb_aircrafts,
        'horizon': horizon,
        'nb_vars': nb_vars,
        'nb_constrs': nb_constrs,
        'nb_nonzeros': nb_nonzeros,
        'solve_time': round(solve_time, 2),
        'work_units': round(nb_work, 2),   # Gurobi exposes it; HiGHS doesn't
        'obj_value': round(obj_value, 2) if obj_value is not None else None,
        'mip_gap': round(gap, 4) if gap is not None else None,
        'status': status_name,
    }

    obj_str = f"{obj_value:.2f}" if obj_value is not None else "N/A"
    gap_str = f"{gap:.4f}" if gap is not None else "N/A"
    print(f"  → {status_name} | obj={obj_str} | gap={gap_str} | time={solve_time:.3f}s")

    return results


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
    print("\n" + "="*70)
    print("TAIL ASSIGNMENT OPTIMIZATION — Gurobi")
    print("="*70)

    # folder = "data_with_maintenance_constraints/d=4"
    folder = "data/d=1"

    # Option 1: one file
    # paths = ["data_with_maintenance_constraints/d=4/DataCplex_density=1_p=10_h=15_test_0.dat"]

    # Option 2: all files in folder
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
        write_results_csv(results, "src/gurobi/results.csv")

    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    main()