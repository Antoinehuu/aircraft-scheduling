# Aircraft-scheduling installation tutorial

This Tail assignment project solves a task assignment problem for each aircraft as part of an ongoing operations research project at CentraleSupélec.

## 1. Clone the project

```bash
git clone https://github.com/antoinehuu/aircraft-scheduling.git
cd aircraft-scheduling
```

---

## 2. Create a virtual environment

Gurobi only support 3.10, 3.11, 3.12, 3.13, 3.14 python version, if you have a > 3.14 version replace python3 by python3.14
### On Linux/Mac:
```bash
python3 -m venv venv
source venv/bin/activate
```

### On Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

---

## 3. Install modules

Requires a Gurobi license; there is a tutorial for an academic license at the end.

```bash
pip install -r requirements.txt
```

---

## 4. Check if it works

```bash
python -c "import gurobipy; print('OK')"
```

---

# Projet Structure - Aircraft Scheduling

## Tree

```
projet/
├── main.py
├── README.md
├── requirements.txt
│
├── src/                              ← Optimization package
│   ├── __init__.py
│   ├── data_loader.py
│   ├── preprocessing.py
│   └── model.py
│
├── data                              ← Data sans les maintenances
├── data_with_maintenance_constraints/
│   └── d=4/
│       └── *.dat                     ← Instances format
│
└── results/                          
```

---


---

## File descriptions

### `main.py`
**Main file to run**

- Runs the solver on the instances
- Displays a summary of the results
- Handles input/output files

**Usage:**
```bash
python main.py
‘‘‘

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

### `src/model.py`

- `build_and_solve_model(...)`
- `_add_flow_constraints()` → Contraints C2
- `_add_base_constraints()` → Contraints C3
- `_add_duplicate_constraints()` → Contraints C4
- `_add_maintenance_constraints()` → Maintenance contraints

### `src/__init__.py`

Exports the package's main functions for external use.

---

## Usage

### To execute

```bash
python main.py
```

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
  ├─→ load_dat_file()
  │   └─→ Loads .dat file
  │       └─→ Returns: nb_flights, cap_maintenance, horizon, ...
  │
  ├─→ preprocess_flights()
  │   └─→ Indexes and sorts the data
  │       └─→ Returns: data (optimized dict)
  │
  └─→ build_and_solve_model()
      ├─→ Creates Gurobi variables (x, y, z)
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


## 🔧 Configuration Gurobi

Dans `main.py`:

```python
model.setParam("OutputFlag", 1)      # Display logs
model.setParam("Presolve", 2)        # Aggressive presolve
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

---

## Debug

To debug a problem:

1. **Check the loading:**
   ```python
   from src.data_loader import load_dat_file
   data = load_dat_file("path/to/file.dat")
   print(data)
   ```

2. **Check the preprocessing:**
   ```python
   from src.preprocessing import preprocess_flights
   preprocessed = preprocess_flights(...)
   print(f"Aéroports trouvés: {list(preprocessed['departures_sorted'].keys())}")
   ```

3. **Check the model:**
   ```python
   model.write("debug.lp")  # Exports the model in LP format, constraints are labeled
   ```

---

## Academic license installation

• Go to the main page of the Gurobi website and log in to your Gurobi account via the Login tab, if
you are not already logged in.

• Click on the Downloads and licenses tab. In the Request a license paragraph, click on the
Academic License tab.

• Accept the terms of use of the academic license. As you can see, your Gurobi academic license has been generated. You can now install your license by following the
instructions given in the Installation paragraph under the details table. We give a few
additional indications below:

– On macOS or Linux.

* Copy the command grbgetkey <key>, open a terminal window, paste the command into
your terminal window and run it. You are asked to choose the folder in which to store
your license file; press Enter to choose the default folder. We recommend
choosing the default folder and not a personal folder, otherwise this generates additional steps
(setting an environment variable via command line, etc.).

* You can check that your license is properly installed by typing the command gurobi.sh and
checking that a line Academic license - for non-commercial use only - expires <date> is written
in the displayed text.

– On Windows.

* Open the Gurobi shell by double-clicking on the Gurobi9.1.1 icon added to the desktop after
installation.

* Enter the <key> provided in the Installation paragraph.

* Specify the name of the directory where to store the license file or press the Enter key on the
keyboard to select the default location.