# src/highs/main.py
"""
HiGHS version of the aircraft scheduling optimizer.
Same inputs / CSV outputs as the Gurobi and OR-Tools versions.
"""

import csv
import os
import time

import highspy
from src import load_dat_file, preprocess_flights
from src.highs import build_and_solve_model


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
    data = preprocess_flights(flights, set(range(nb_aircrafts)),
                              aircraft_init, m_airports)
    print("  ✓ Preprocessing completed")

    # ---- build -----------------------------------------------------------
    print("▶ Building the model (HiGHS)...")
    start_time = time.perf_counter()

    h, x, y, z = build_and_solve_model(
        nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
        aircraft_init, airports, m_airports, Days, data,
    )

    # Solver options (mirror the Gurobi block)
    # HiGHS uses setOptionValue, not setParam
    h.setOptionValue("output_flag", True)       # OutputFlag
    h.setOptionValue("mip_rel_gap", 0.02)       # MIPGap
    h.setOptionValue("time_limit", 600.0)       # TimeLimit
    # Presolve is on by default; set explicitly if you want:
    # h.setOptionValue("presolve", "on")

    print("▶ Optimization...")
    h.run()

    solve_time = time.perf_counter() - start_time

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

    # Objective and gap are only meaningful if a feasible solution exists
    # info.objective_function_value is kHighsInf if no feasible solution
    obj_value = None
    gap = None
    if info.objective_function_value != highspy.kHighsInf:
        obj_value = info.objective_function_value
        # mip_gap is available in info for MIP models
        gap = info.mip_gap

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
    print("TAIL ASSIGNMENT OPTIMIZATION — HiGHS")
    print("="*70)

    folder = "data_with_maintenance_constraints/d=4"

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
        write_results_csv(results, "results_maintenance_highs.csv")

    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    main()
