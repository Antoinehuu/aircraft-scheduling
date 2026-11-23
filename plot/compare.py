"""Compare solver runtime and objective availability by aircraft count."""

import argparse
from collections import defaultdict
from pathlib import Path
import sys

from .results import DATASETS, RESULTS_ROOT, numeric_value, plot_backend, read_results, save_plot


SOLVERS = {
    "gurobi": ("Gurobi", "#2066a4"),
    "highs": ("HiGHS", "#c75b12"),
    "or_tools": ("OR-Tools", "#008267"),
    "hexaly": ("Hexaly", "#8e54a0"),
}
INSTANCE_COLUMNS = ("nb_aircrafts", "filename", "nb_flights", "horizon")
REQUIRED_COLUMNS = (*INSTANCE_COLUMNS, "solve_time", "obj_value")


def load_runs(path):
    runs = {}
    for row in read_results(path, REQUIRED_COLUMNS):
        aircraft = numeric_value(row["nb_aircrafts"])
        seconds = numeric_value(row["solve_time"])
        identity = tuple((row[column] or "").strip() for column in INSTANCE_COLUMNS[1:])
        if aircraft is None or aircraft <= 0 or not aircraft.is_integer() or not all(identity):
            continue
        if seconds is not None and seconds >= 0:
            runs[(int(aircraft), *identity)] = (seconds, numeric_value(row["obj_value"]) is not None)
    return runs


def group_runs(runs_by_solver, instances=None):
    groups = defaultdict(list)
    for solver, runs in runs_by_solver.items():
        for instance, result in runs.items():
            if instances is None or instance in instances:
                groups[solver, instance[0]].append(result)
    return groups


def plot_groups(time_axis, objective_axis, groups, counts, solvers):
    width = 0.8 / len(solvers)
    for index, solver in enumerate(solvers):
        label, color = SOLVERS[solver]
        offset = (index - (len(solvers) - 1) / 2) * width
        positions, times, rates, sizes = [], [], [], []
        for position, count in enumerate(counts):
            runs = groups.get((solver, count))
            if not runs:
                continue
            seconds, objectives = zip(*runs)
            positions.append(position + offset)
            times.append(seconds)
            rates.append(100 * sum(objectives) / len(runs))
            sizes.append(len(runs))

        if positions:
            time_axis.boxplot(
                times, positions=positions, widths=width * 0.76, manage_ticks=False,
                patch_artist=True, boxprops={"facecolor": color, "edgecolor": color, "alpha": 0.72},
                medianprops={"color": "black", "linewidth": 1.5},
                whiskerprops={"color": color}, capprops={"color": color},
                flierprops={"marker": ".", "markeredgecolor": color, "alpha": 0.65},
            )
            bars = objective_axis.bar(positions, rates, width=width * 0.76, color=color, label=label)
            objective_axis.bar_label(bars, labels=[str(size) for size in sizes], padding=3, fontsize=8)

    for axis in (time_axis, objective_axis):
        axis.set_xlim(-0.5, len(counts) - 0.5)
        axis.set_xticks(range(len(counts)), labels=counts)
        axis.set_axisbelow(True)
        axis.grid(axis="y", alpha=0.24)
        if not groups:
            axis.text(0.5, 0.5, "No shared instances", transform=axis.transAxes,
                      ha="center", va="center")


def plot_comparison(plt, runs_by_solver, title):
    from matplotlib.patches import Patch

    common = set.intersection(*(set(runs) for runs in runs_by_solver.values()))
    counts = sorted({instance[0] for runs in runs_by_solver.values() for instance in runs})
    figure = plt.figure(figsize=(13, 8), layout="constrained")
    grid = figure.add_gridspec(3, 2, height_ratios=(0.13, 1, 0.55))
    legend_axis = figure.add_subplot(grid[0, :])
    legend_axis.set_axis_off()
    legend_axis.legend(
        handles=[Patch(facecolor=SOLVERS[solver][1], label=SOLVERS[solver][0])
                 for solver in runs_by_solver],
        loc="center", ncols=len(runs_by_solver), frameon=False,
    )
    matched_time = figure.add_subplot(grid[1, 0])
    all_time = figure.add_subplot(grid[1, 1], sharey=matched_time)
    matched_objective = figure.add_subplot(grid[2, 0], sharex=matched_time)
    all_objective = figure.add_subplot(grid[2, 1], sharex=all_time, sharey=matched_objective)
    figure.suptitle(f"{title} · Solver comparison", fontsize=16)

    has_zero = any(seconds == 0 for runs in runs_by_solver.values() for seconds, _ in runs.values())
    if has_zero:
        matched_time.set_yscale("symlog", linthresh=0.01)
    else:
        matched_time.set_yscale("log")
    matched_time.set_ylabel("Solve time (s)")
    matched_objective.set(ylabel="Runs with an objective (%)", ylim=(0, 113), yticks=(0, 25, 50, 75, 100))

    matched_time.set_title(f"Shared instances · {len(common):,} total")
    all_time.set_title("All available instances · coverage varies by solver")
    plot_groups(matched_time, matched_objective, group_runs(runs_by_solver, common), counts, runs_by_solver)
    plot_groups(all_time, all_objective, group_runs(runs_by_solver), counts, runs_by_solver)
    for axis in (matched_time, all_time):
        axis.tick_params(labelbottom=False)
    for axis in (matched_objective, all_objective):
        axis.set_xlabel("Number of aircraft · bar labels show run counts")
    return figure


def main():
    parser = argparse.ArgumentParser(description="Compare solver results by aircraft count.")
    parser.add_argument("--dataset", choices=("all", *DATASETS), default="all",
                        help="select a benchmark dataset (default: both)")
    parser.add_argument("--save-dir", type=Path, help="save PNGs to this directory")
    args = parser.parse_args()

    comparisons = []
    datasets = DATASETS if args.dataset == "all" else (args.dataset,)
    for dataset in datasets:
        filename, title = DATASETS[dataset]
        runs_by_solver = {}
        for solver in SOLVERS:
            path = RESULTS_ROOT / solver / filename
            try:
                runs = load_runs(path)
            except FileNotFoundError:
                print(f"Skipping missing results file {path}", file=sys.stderr)
                continue
            except (OSError, ValueError) as error:
                parser.error(str(error))
            if runs:
                runs_by_solver[solver] = runs
            else:
                print(f"Skipping {path} with no usable runtimes", file=sys.stderr)

        if len(runs_by_solver) >= 2:
            comparisons.append((dataset, title, runs_by_solver))
        else:
            print(f"{title} needs usable runtime data from at least two solvers", file=sys.stderr)

    if not comparisons:
        parser.error("No datasets available for comparison")

    plt = plot_backend(parser, args.save_dir)
    for dataset, title, runs_by_solver in comparisons:
        figure = plot_comparison(plt, runs_by_solver, title)
        if args.save_dir is not None:
            save_plot(plt, figure, args.save_dir / f"solver_comparison_{dataset}.png")
    if args.save_dir is None:
        plt.show()


if __name__ == "__main__":
    main()
