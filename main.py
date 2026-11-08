import os
import time

# Import the modules
from src.data_loader import load_dat_file
from src.preprocessing import preprocess_flights
from src.model import build_and_solve_model
from src.model import build_and_solve_model_2

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
    
    # Preprocessing
    print("▶ Preprocessing data...")
    data = preprocess_flights(flights, set(range(nb_aircrafts)), aircraft_init, m_airports)
    print(f"  ✓ Preprocessing completed")
    
    
    # Build and solve the model
    print("▶ Building the model...")
    start_time = time.perf_counter()
    
    model, x, y, z = build_and_solve_model(
        nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
        aircraft_init, airports, m_airports, Days, data
    )
    
    # Gurobi parameters
    model.setParam("OutputFlag", 1)
    model.setParam("Presolve", 2)
    model.setParam("MIPGap", 0.02)
    
    print("▶ Optimization...")
    model.optimize()
    
    model.write("model.lp")
    
    solve_time = time.perf_counter() - start_time
    
    # Statistics
    nb_vars = model.NumVars
    nb_constrs = model.NumConstrs
    nb_nonzeros = model.NumNZs
    nb_work = model.Work
    
    # Gurobi parameters
    model.setParam("OutputFlag", 1)
    model.setParam("Presolve", 1)
    model.setParam("MIPGap", 0.02)   
    
    # 2nd optimization to reduce maintenances 
    # and reach a local minimum 
    model, x, y, z = build_and_solve_model_2(
        nb_flights, flights, costs, m_costs,
        aircraft_init, m_airports, Days, data, model, x, y, z
        )
        
    model.setParam("Presolve", -1)
    model.optimize()
    
    results = {
        'filename': os.path.basename(filepath),
        'nb_flights': nb_flights,
        'nb_aircrafts': nb_aircrafts,
        'nb_vars': nb_vars,
        'nb_constrs': nb_constrs,
        'nb_nonzeros': nb_nonzeros,
        'solve_time': solve_time,
        'work_units': nb_work,
        'obj_value': model.ObjVal if model.status == 2 else None,
        'status': model.status
    }
    
    # Display results
    print(f"\n▶ Results:")
    print(f"  Status: {'Optimal' if model.status == 2 else 'Suboptimal/Infeasible'}")
    print(f"  Objective: {results['obj_value']:.2f}" if results['obj_value'] else "  Objective: N/A")
    print(f"  Time: {solve_time:.3f}s")
    print(f"  Gurobi work: {nb_work:.3f} units")
    print(f"  Variables: {nb_vars}")
    print(f"  Constraints: {nb_constrs}")
    print(f"  Non-zeros: {nb_nonzeros}")
    
    return results


def main():
    """Main function"""
    
    print("\n" + "="*70)
    print("TAIL ASSIGNMENT OPTIMIZATION")
    print("="*70)
    
    # Files to process
    folder = "data_with_maintenance_constraints/d=4"
    
    # Option 1: A specific file
    paths = ["data_with_maintenance_constraints/d=4/DataCplex_density=1_p=10_h=15_test_0.dat"]
    
    # Option 2: All files in a folder
    #paths = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".dat")]
    
    paths.sort()
    
    # Solve all files
    all_results = []
    
    for path in paths:
        try:
            results = solve_instance(path)
            
            all_results.append(results)
        except Exception as e:
            print(f"❌ Error for {os.path.basename(path)}: {e}")
            import traceback
            traceback.print_exc()
    
    # Final summary
    print(f"\n{'='*70}")
    print("FINAL SUMMARY")
    print(f"{'='*70}")
    
    for res in all_results:
        print(f"\n{res['filename']}")
        print(f"  Flights: {res['nb_flights']}, Aircraft: {res['nb_aircrafts']}")
        print(f"  Time: {res['solve_time']:.3f}s | Work: {res['work_units']:.3f} | "
              f"Vars: {res['nb_vars']} | Constrs: {res['nb_constrs']}")
        if res['obj_value']:
            print(f"  Objective: {res['obj_value']:.2f}")
    
    print(f"\n{'='*70}\n")
    
    return all_results


if __name__ == "__main__":
    results = main()
