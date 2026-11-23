"""Read solver CSVs and plot one dashboard per file."""

import argparse
import csv
from collections import Counter
from math import isfinite
from pathlib import Path
from statistics import median


DATASETS = {
    "fleet": ("results.csv", "Fleet assignment"),
    "maintenance": ("results_maintenance.csv", "Maintenance scheduling"),
}
RESULTS_ROOT = Path(__file__).resolve().parents[1] / "src"
NUMERIC_COLUMNS = ("nb_flights", "solve_time", "obj_value", "mip_gap")


def read_results(path, required_columns=("status", *NUMERIC_COLUMNS)):
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        missing = set(required_columns).difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(sorted(missing))}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path} has no result rows")
    return rows


def numeric_value(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def status_label(value):
    status = (value or "").strip()
    if status.upper().startswith("ERROR:"):
        return "Error"
    label = status.replace("_", " ").capitalize()
    return {"Time limit reached": "Time limit", "": "Missing status"}.get(label, label)


def plot_metric(axis, rows, column, label, unit, multiplier=1):
    points = []
    for row in rows:
        flights = numeric_value(row["nb_flights"])
        value = numeric_value(row[column])
        if flights is not None and value is not None:
            points.append((flights, value * multiplier))

    axis.set(xlabel="Number of flights", ylabel=label)
    axis.grid(alpha=0.2)
    axis.set_axisbelow(True)
    if not points:
        axis.set_title(label)
        axis.text(0.5, 0.5, "No finite values to plot", transform=axis.transAxes,
                  ha="center", va="center")
        return

    flights, values = zip(*points)
    typical = median(values)
    axis.scatter(flights, values, s=18, alpha=0.55, color="#007c83", edgecolors="none")
    axis.set_title(f"{label} · median {typical:,.2f}{unit} · {len(points):,} runs")


def plot_results(plt, rows, title):
    figure, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    figure.suptitle(f"{title} · {len(rows):,} runs", fontsize=16)

    status_axis = axes[0, 0]
    statuses, counts = zip(*Counter(status_label(row["status"]) for row in rows).most_common())
    bars = status_axis.barh(statuses, counts, color="#345d8c")
    status_axis.bar_label(bars, padding=4)
    status_axis.set(title="Solver status", xlabel="Number of runs", xlim=(0, max(counts) * 1.18))
    status_axis.invert_yaxis()

    plot_metric(axes[0, 1], rows, "solve_time", "Solve time (s)", " s")
    plot_metric(axes[1, 0], rows, "obj_value", "Objective value", "")
    plot_metric(axes[1, 1], rows, "mip_gap", "MIP gap (%)", "%", multiplier=100)
    return figure


def plot_backend(parser, save_dir):
    try:
        import matplotlib
    except ModuleNotFoundError as error:
        if error.name != "matplotlib":
            raise
        parser.error("Matplotlib is required. Install it with `python -m pip install matplotlib`.")

    if save_dir is not None:
        matplotlib.use("Agg")
        save_dir.mkdir(parents=True, exist_ok=True)

    from matplotlib import pyplot as plt

    return plt


def save_plot(plt, figure, output):
    figure.savefig(output, dpi=160)
    plt.close(figure)
    print(f"Saved {output}")


def main(solver, solver_name):
    parser = argparse.ArgumentParser(description=f"Plot benchmark results for {solver_name}.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--dataset", choices=("all", *DATASETS), default="all",
                        help="select the standard result files (default: all available)")
    source.add_argument("--csv", type=Path, help="plot a custom results CSV")
    parser.add_argument("--save-dir", type=Path, help="save PNGs to this directory")
    args = parser.parse_args()

    if args.csv is not None:
        sources = [(args.csv, args.csv.stem)]
    else:
        solver_dir = RESULTS_ROOT / solver
        datasets = DATASETS if args.dataset == "all" else (args.dataset,)
        sources = [(solver_dir / DATASETS[key][0], DATASETS[key][1]) for key in datasets]
        if args.dataset == "all":
            sources = [(path, title) for path, title in sources if path.exists()]
            if not sources:
                parser.error(f"No standard results CSVs found in {solver_dir}")

    try:
        results = [(path, title, read_results(path)) for path, title in sources]
    except (OSError, ValueError) as error:
        parser.error(str(error))

    plt = plot_backend(parser, args.save_dir)
    for path, title, rows in results:
        figure = plot_results(plt, rows, f"{solver_name} · {title}")
        if args.save_dir is not None:
            save_plot(plt, figure, args.save_dir / f"{solver}_{path.stem}.png")

    if args.save_dir is None:
        plt.show()
