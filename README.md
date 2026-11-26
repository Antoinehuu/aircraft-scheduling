# Aircraft-scheduling 

This Tail assignment project solves a tail assignment problem for each aircraft as part of an ongoing operations research project at CentraleSupélec.



# Projet Structure - Aircraft Scheduling
[View detailed installation tutorial](installation.md)

```
projet/
├── main.py
├── README.md
├── requirements.txt
│
├── src/
│   ├── gurobi/
|   |  ├── main.py            ← Optimization params, inputs selection
|   |  └── model.py
|   |
│   ├── highs/
│   ├── or_tools/
│   ├── hexaly/
│   ├── preprocessing.py      
│   └── data_loader.py
│
├── data                             
├── data_with_maintenance_constraints/
│   └── d=4/
│       └── *.dat                     ← Instances format
│
└── results/                          
```

---

## File descriptions

### `main.py`
**Main file to run**

- Runs the solver on the instances
- Displays a summary of the results
- Handles input/output files

**Usage:**
```bash
python -m src.gurobi.main
python -m src.highs.main
python -m src.highs.main data/d=0.9
python -m src.or_tools.main
python -m src.hexaly.main
python -m src.hexaly.main data/d=0.9 --output src/hexaly/results.csv
```

### Fleet assignment

For instances in `data/`, the solver backends use one binary assignment
`x[i, t]` for each flight `i` and aircraft `t`. Coverage assigns each flight
once. Airport balances group simultaneous departures and make arrivals
available at their scheduled time. Each aircraft operates a route from its
initial base and may end at any airport. The total cost includes every flight
in each route. Equation (12) in the report omits the cost of the final flight
of each route. [Fleet-assignment report](results/Rapport_project_no_maintenances.pdf)

All four solvers start from the same deterministic chronological aircraft
assignment when one is available. For maintenance instances, the shared start
also schedules visits after the final flight of the day, respecting maintenance
history, rolling deadlines, and airport capacity. Start preparation tries
repeatable alternative routes if needed and supplies flight hints alone if it
cannot complete the visits. The solvers can improve the starting schedule.

For benchmark runs, use the same inputs, `--time-limit`, and `--mip-gap`
(default 0.02) for each solver. Reported time includes model construction and
start preparation. The time limit applies to solver calls, and each solver uses
its own stopping rules.
HiGHS also offers `--certify-start` for fleet-only runs. It can return early
as `Target for objective reached` when the starting assignment meets the
requested gap against a separate cost bound.

## Benchmark Results

Each solver cell shows **instances marked `OPTIMAL` / instances run (median solve time for `OPTIMAL` runs)**.
The **Instances** column counts distinct instance filenames across all four
CSVs. Each solver contributes its last row with a finite runtime per filename.
Status matching is case-insensitive. A dash stands for a missing count or
median. The CSVs report elapsed times, and the solver time limit can vary by run.

### Tail assignement model

| Aircraft | Instances | [Gurobi](src/gurobi/results.csv) | [HiGHS](src/highs/results.csv) | [OR-Tools](src/or_tools/results.csv) | [Hexaly](src/hexaly/results.csv) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 121 | 121/121 (0.28 s) | 121/121 (0.81 s) | 121/121 (0.42 s) | 121/121 (2.92 s) |
| 20 | 120 | 120/120 (3.84 s) | 120/120 (16.78 s) | 101/120 (45.07 s) | 120/120 (28.79 s) |
| 30 | 120 | 120/120 (14.47 s) | 88/88 (173.16 s) | 8/56 (236.79 s) | 83/83 (179.03 s) |
| 40 | 120 | 120/120 (147.67 s) | 72/80 (563.62 s) | 0/14 (—) | 76/80 (616.31 s) |

### Tail assignement with mainteances

| Aircraft | Instances | [Gurobi](src/gurobi/results_maintenance.csv) | [HiGHS](src/highs/results_maintenance.csv) | [OR-Tools](src/or_tools/results_maintenance.csv) | [Hexaly](src/hexaly/results_maintenance.csv) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 15 | 15/15 (2.67 s) | 15/15 (4.94 s) | 15/15 (1.48 s) | 15/15 (13.90 s) |
| 20 | 15 | 15/15 (14.84 s) | 5/5 (65.59 s) | 12/15 (34.49 s) | 0/15 (—) |
| 30 | 10 | 4/10 (281.17 s) | — | 7/10 (121.30 s) | 0/10 (—) |

### Plot solver results

Run any of these commands from the repository root to open plots for that solver.

```bash
python -m plot.gurobi
python -m plot.highs
python -m plot.or_tools
python -m plot.hexaly
```

Each available CSV gets a figure with status counts, solve time, objective value,
and MIP gap. Each CSV row counts as a run. The metric plots omit missing or
non-finite values and show the number of runs plotted. The scripts require Matplotlib.

Use `--dataset fleet` or `--dataset maintenance` to select a standard CSV,
`--csv PATH` to read a custom CSV, or `--save-dir PATH` to save PNGs.

```bash
python -m plot.gurobi --dataset maintenance --save-dir /tmp/solver-plots
```

### Compare solvers by aircraft count

```bash
python -m plot.compare
python -m plot.compare --dataset maintenance --save-dir /tmp/solver-plots
```

The comparison opens one figure per dataset by default. Runtime box plots use a
logarithmic scale and include recorded runtimes for time limits and runs without
an objective. A symmetric log scale includes recorded zero times when needed.
The lower charts show the share of plotted runs with a finite objective and the
number of runs behind each bar.

The left column uses instances shared by the displayed solvers, matched by
filename, aircraft count, flight count, and the CSV's `horizon` field. The right
column uses each solver's available instances so larger aircraft counts stay
visible when coverage differs. If a CSV contains repeats, the comparison uses
the last row with a usable runtime for each instance.

### `src/data_loader.py`

Main function:
- `load_dat_file(filename)` → Loads a .dat file and returns all data

- File parsing with regex
Extraction of parameters (nb_flights, horizon, etc.)
Extraction of flights, costs, aircraft, airports

### `src/preprocessing.py`

Main functions:
- `preprocess_flights(flights, airports, aircraft_init, m_airports)` 
- `find_compatible_flights(data, airport, target_fid, flight_type)` 

Optimizations via suitable dictionaries

### `src/formulation.py`

Shared reachability checks, fleet balance rows, and maintenance rules used by
all solver backends.

### `src/__init__.py`

Exports the package's main functions for external use.

---

### Process multiple files

Modify `main()` in `main.py`:

```python
# Option 1: All files in a folder
paths = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".dat")]

# Option 2: Specific files
paths = [
    "data_with_maintenance_constraints/d=4/DataCplex_density=1_p=20_h=15_test_0.dat",
    "data_with_maintenance_constraints/d=4/DataCplex_density=1_p=20_h=15_test_1.dat"
]
```

---

## Pipeline

```
main.py
  │
  ├─→ load_dat_file() (dispatch from folder name if it's a maintenance instance)
  │   └─→ Loads .dat file
  │       └─→ Returns: nb_flights, cap_maintenance, horizon, ...
  │
  ├─→ preprocess_flights()
  │   └─→ Indexes and sorts the data
  │       └─→ Returns: data (optimized dict)
  │
  └─→ build_and_solve_model()
      ├─→ Creates decisions variables (x, y, z)
      ├─→ Adds constraints
      │   ├─→ C1: Coverage
      │   ├─→ C2: Flow (excluding base)
      │   ├─→ C3: Flow (base)
      │   ├─→ C4: Duplicates
      │   └─→ Maintenance
      ├─→ Defines objective
      └─→ Solves the model
          └─→ Returns: (model, x, y, z)
```


## Configuration params

For instance for `src/gurobi/main.py`:

```python
model.setParam("OutputFlag", 1)      # Display logs
model.setParam("Presolve", 1)        # Aggressive presolve
model.setParam("MIPGap", 0.02)       # Gap tolerance 2%
```

To modify as needed:

- MIPGap: Smaller = more time but better solution
- Presolve: -1 (auto), 0 (off), 1 (conservative), 2 (aggressive)
- Threads: Number of parallel threads

---

## .dat file format

Example:
```
Nbflight = 20;
capmaintenance = 5;
horizon = 15;

Flight = {
  <1, CDG, ORY, 100, 150, 1>,
  <2, ORY, CDG, 200, 250, 1>,
  ...
};

Cost = [
  [10, 12, 15, ...],
  [11, 13, 16, ...],
  ...
];

Aircraft = [<1, CDG>, <2, CDG>, ...];

Days = {1, 2, 3, ...};
```
