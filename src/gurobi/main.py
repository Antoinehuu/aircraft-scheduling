import os
import csv
import time

from src import load_dat_file, preprocess_flights
from src.gurobi import (
    build_and_solve_model,
    # build_and_solve_model_2,
)


def solve_instance(filepath):
    """
    Solves an instance of the problem.
    
    Args:
        filepath: Path to the .dat file
        
    Returns:
        dict: Results (time, problem dimensions, etc.)
    """

    print(f"\n{'='*70}")
    print(f"Processing: {os.path.basename(filepath)}")
    print(f"{'='*70}")

    # Load the data
    print("▶ Loading data...")
    nb_flights, cap_maintenance, horizon, flights, costs, m_costs, \
        aircraft_init, airports, m_airports, Days = load_dat_file(filepath)

    nb_aircrafts = len(aircraft_init)
    print(f"  ✓ {nb_flights} flights, {nb_aircrafts} aircraft, horizon={horizon}")

    print("▶ Preprocessing data...")
    data = preprocess_flights(flights, set(range(nb_aircrafts)), aircraft_init, m_airports)
    print("  ✓ Preprocessing completed")

    print("▶ Building the model...")
    start_time = time.perf_counter()

    model, x, y, z = build_and_solve_model(
        nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
        aircraft_init, airports, m_airports, Days, data
    )

    model.setParam("OutputFlag", 0)
    model.setParam("Presolve", 1)
    model.setParam("MIPGap", 0.02)
    model.setParam("TimeLimit", 600)

    print("▶ Optimization...")
    model.optimize()

    model.write("model.lp")

    # Statistics (captured right after first solve)
    nb_vars = model.NumVars
    nb_constrs = model.NumConstrs
    nb_nonzeros = model.NumNZs
    nb_work = model.Work
    
    # # Gurobi parameters
    # model.setParam("OutputFlag", 0)
    # model.setParam("Presolve", 1)
    # model.setParam("MIPGap", 0.01)   
    # model.setParam("TimeLimit", 10)

    # # 2nd optimization to reduce maintenances 
    # # and reach a local minimum 
    # model, x, y, z = build_and_solve_model_2(
    #     nb_flights, flights, costs, m_costs,
    #     aircraft_init, m_airports, Days, data, model, x, y, z
    #     )

    # model.setParam("Presolve", -1)
    # model.optimize()

    solve_time = time.perf_counter() - start_time

    obj_value = model.ObjVal if model.status == 2 else None
    mip_gap = model.MIPGap if model.status == 2 else None

    results = {
        'filename': os.path.basename(filepath),
        'nb_flights': nb_flights,
        'nb_aircrafts': nb_aircrafts,
        'horizon': horizon,
        'nb_vars': nb_vars,
        'nb_constrs': nb_constrs,
        'nb_nonzeros': nb_nonzeros,
        'solve_time': round(solve_time, 2),
        'work_units': round(nb_work, 2),
        'obj_value': round(obj_value, 2) if obj_value is not None else None,
        'mip_gap': round(mip_gap, 4) if mip_gap is not None else None,
        'status': model.status,
    }

    # Short progress print (no full summary)
    status_str = 'Optimal' if model.status == 2 else f'status={model.status}'
    obj_str = f"{obj_value:.2f}" if obj_value is not None else "N/A"
    print(f"  → {status_str} | obj={obj_str} | time={solve_time:.3f}s")

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
    """Main function"""

    print("\n" + "="*70)
    print("TAIL ASSIGNMENT OPTIMIZATION")
    print("="*70)

    # Files to process
    folder = "data_with_maintenance_constraints/d=4"
    # folder = "data/d=0.9"

    # Option 1: A specific file
    # paths = ["data_with_maintenance_constraints/d=4/DataCplex_density=1_p=10_h=15_test_0.dat"]

    # Option 2: All files in a folder
    paths = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".dat")]

    paths.sort()

    for path in paths:
        try:
            results = solve_instance(path)
        except Exception as e:
            print(f"Error for {os.path.basename(path)}: {e}")
            import traceback
            traceback.print_exc()
            # Optionally record failures too:
            results = {
                'filename': os.path.basename(path),
                'nb_flights': None, 'nb_aircrafts': None, 'horizon': None,
                'nb_vars': None, 'nb_constrs': None, 'nb_nonzeros': None,
                'solve_time': None, 'work_units': None,
                'obj_value': None, 'mip_gap': None,
                'status': f'ERROR: {e}',
            }
        write_results_csv(results, "results_maintenance.csv")

    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    main()
