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

### Maintenance scheduling

```bash
python -m src.gurobi.main data_with_maintenance_constraints/d=4
python -m src.highs.main data_with_maintenance_constraints/d=4
python -m src.or_tools.main data_with_maintenance_constraints/d=4
python -m src.hexaly.main data_with_maintenance_constraints/d=4
```

Each runner accepts a directory or a single `.dat` file. Input paths containing
`maintenance` write to `src/<solver>/results_maintenance.csv` by default.
Other runs write to `src/<solver>/results.csv`. Use `--output` to set a different path.

Maintenance uses the airport where the aircraft lands after its last flight
of the day. A rolling window controls when maintenance is due. The inputs have no initial maintenance
history, so all four backends use the same reproducible sample by default.
Programmatic callers can pass `initial_maintenance_days` to supply the last
maintenance day for each aircraft.

The runners use a fleet-only solution to seed the cost solve when available.
If time remains after finding a feasible schedule, they fix the selected
flight assignments and minimize maintenance visits within the cost cap.
`--time-limit` sets the solver budget per instance. The CSV reports operating
cost and its gap, and the console shows the maintenance visit count when
refinement succeeds. [Maintenance report](results/Rapport_projet.pdf#page=9)

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
