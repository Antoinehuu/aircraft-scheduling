"""Run Hexaly on one .dat instance or a directory of instances."""

import argparse
import csv
import math
import time
from pathlib import Path

from hexaly.optimizer import HxSolutionStatus

from src import load_dat_file, preprocess_flights
from src.hexaly import build_and_solve


CSV_FIELDS = (
    "filename", "nb_flights", "nb_aircrafts", "horizon", "nb_vars",
    "nb_constrs", "nb_nonzeros", "solve_time", "work_units", "obj_value",
    "mip_gap", "status",
)


def solve_instance(filepath, time_limit=600):
    filepath = str(filepath)
    instance = load_dat_file(filepath)
    nb_flights, _, horizon, flights, _, _, aircraft_init, _, _, _ = instance
    nb_aircrafts = len(aircraft_init)
    data = preprocess_flights(flights, set(range(nb_aircrafts)), aircraft_init)

    start = time.perf_counter()
    optimizer, _, _, _ = build_and_solve(*instance, data, "maintenance" in filepath)
    with optimizer:
        model = optimizer.model
        model.close()
        optimizer.param.verbosity = 0
        optimizer.param.time_limit = time_limit
        optimizer.param.set_gap_limit(0.02)
        optimizer.solve()
        solve_time = time.perf_counter() - start

        solution = optimizer.solution
        status = solution.status
        obj_value = gap = None
        if status in (HxSolutionStatus.FEASIBLE, HxSolutionStatus.OPTIMAL):
            obj_value = round(model.get_objective(0).value, 2)
            objective_gap = solution.get_objective_gap(0)
            if math.isfinite(objective_gap):
                gap = round(objective_gap, 4)

        return {
            "filename": Path(filepath).name,
            "nb_flights": nb_flights,
            "nb_aircrafts": nb_aircrafts,
            "horizon": horizon,
            "nb_vars": model.nb_decisions,
            "nb_constrs": model.nb_constraints,
            "nb_nonzeros": None,
            "solve_time": round(solve_time, 2),
            "work_units": None,
            "obj_value": obj_value,
            "mip_gap": gap,
            "status": status.name,
        }


def write_results_csv(results, csv_path):
    with open(csv_path, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        if file.tell() == 0:
            writer.writeheader()
        writer.writerow(results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?", default=Path("data/d=0.9"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("results.csv"))
    parser.add_argument("--time-limit", type=int, default=600, help="seconds per instance")
    args = parser.parse_args()
    if args.time_limit <= 0:
        parser.error("--time-limit must be positive")
    if args.input.is_dir():
        paths = sorted(path for path in args.input.glob("*.dat") if path.is_file())
    else:
        paths = [args.input] if args.input.is_file() and args.input.suffix == ".dat" else []
    if not paths:
        parser.error(f"No .dat instances found at {args.input}")

    failed = False
    for path in paths:
        try:
            results = solve_instance(path, args.time_limit)
        except Exception as exc:
            failed = True
            results = {"filename": path.name, "status": f"ERROR: {exc}"}
            print(f"{path.name} | {results['status']}")
        else:
            print(f"{path.name} | {results['status']} | "
                  f"obj={results['obj_value']} | gap={results['mip_gap']} | "
                  f"time={results['solve_time']}s")
        write_results_csv(results, args.output)
    print(f"Results appended to {args.output}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
