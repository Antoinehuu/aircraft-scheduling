"""Batch input and CSV output for the solver runners."""

import argparse
import csv
from math import fsum, isfinite
from pathlib import Path
from time import perf_counter

from src.formulation import initial_fleet_assignment

CSV_FIELDS = (
    "filename", "nb_flights", "nb_aircrafts", "horizon", "nb_vars",
    "nb_constrs", "nb_nonzeros", "solve_time", "work_units", "obj_value",
    "mip_gap", "status",
)


def results_for(filepath, instance, counts, start, status, cost, gap, work=None):
    return dict(zip(CSV_FIELDS, (
        Path(filepath).name, instance[0], len(instance[6]), instance[2], *counts,
        round(perf_counter() - start, 2), round(work, 2) if work is not None else None,
        round(cost, 2) if cost is not None else None,
        round(gap, 4) if gap is not None else None, status,
    )))


def write_results_csv(results, csv_path):
    with open(csv_path, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        if file.tell() == 0:
            writer.writeheader()
        writer.writerow(results)


def default_results_path(input_path, output_dir):
    filename = "results_maintenance.csv" if "maintenance" in str(input_path) else "results.csv"
    return output_dir / filename


def fleet_start_for(instance):
    flights, costs, aircraft_init = instance[3], instance[4], instance[6]
    assignment = initial_fleet_assignment(flights, costs, aircraft_init)
    if assignment:
        cost = fsum(costs[i - 1][t] for i, t in assignment.items())
        print(f"Fleet start | flights={len(assignment)} | flight cost={cost:.2f}")
        return assignment, cost
    return None, None


def run_batch(solve_instance, default_input, output_dir, description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("input", type=Path, nargs="?", default=Path(default_input))
    parser.add_argument("--output", type=Path, help="override the solver's default results CSV")
    parser.add_argument("--time-limit", type=int, default=600, help="solver seconds per instance")
    parser.add_argument("--mip-gap", type=float, default=0.02, help="relative operating-cost gap (default: 0.02)")
    args = parser.parse_args()
    if args.time_limit <= 0:
        parser.error("--time-limit must be positive")
    if not isfinite(args.mip_gap) or args.mip_gap < 0:
        parser.error("--mip-gap must be a nonnegative finite number")
    if args.input.is_dir():
        paths = sorted(path for path in args.input.glob("*.dat") if path.is_file())
    else:
        paths = [args.input] if args.input.is_file() and args.input.suffix == ".dat" else []
    if not paths:
        parser.error(f"No .dat instances found at {args.input}")
    output = args.output or default_results_path(args.input, output_dir)

    failed = False
    for path in paths:
        try:
            results = solve_instance(path, args.time_limit, args.mip_gap)
        except Exception as exc:
            failed = True
            results = {"filename": path.name, "status": f"ERROR: {exc}"}
            print(f"{path.name} | {results['status']}")
        else:
            print(f"{path.name} | {results['status']} | "
                  f"obj={results['obj_value']} | gap={results['mip_gap']} | "
                  f"time={results['solve_time']}s")
        write_results_csv(results, output)
    print(f"Results appended to {output}")
    return int(failed)
