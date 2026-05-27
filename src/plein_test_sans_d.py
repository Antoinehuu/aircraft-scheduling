
import re
from gurobipy import *
from collections import defaultdict
import bisect
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import random

def load_dat_file(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    nb_flight = int(re.search(r'Nbflight\s*=\s*(\d+);', content).group(1))
    
    cap_maintenance = int(re.search(r'capmaintenance\s*=\s*(\d+);', content).group(1))
    
    horizon = int(re.search(r'horizon\s*=\s*(\d+);', content).group(1))

    flights_raw = re.findall(r'<(.*?)>', re.search(r'Flight\s*=\s*\{(.*?)\};', content, re.DOTALL).group(1))
    flights = []
    for f in flights_raw:
        parts = f.split(',')
        flights.append({
            'id': int(parts[0]),
            'origin': parts[1].strip(),
            'dest': parts[2].strip(),
            'departure': float(parts[3]),
            'arrival': float(parts[4]),
            'day':int(parts[5])
        })

    cost_section = re.search(r'Cost\s*=\s*\[(.*?)\];', content, re.DOTALL).group(1)
    costs_raw = re.findall(r'\[(.*?)\]', cost_section)
    costs = [list(map(float, c.strip(',').split(','))) for c in costs_raw if c.strip()]

    m_cost_section = re.search(r'CostMaintenance\s*=\s*\[(.*?)\];', content, re.DOTALL).group(1)
    m_costs_raw = re.findall(r'\[(.*?)\]', m_cost_section)
    m_costs = [list(map(float, c.strip(',').split(','))) for c in m_costs_raw if c.strip()]
    
    aircraft_raw = re.findall(r'<(.*?)>', re.search(r'Aircraft\s*=\s*\[(.*?)\];', content, re.DOTALL).group(1))
    aircraft_init = {}
    for a in aircraft_raw:
        idx, city = a.split(',')
        aircraft_init[int(idx)] = city.strip()
        
    airports_raw = re.search(r'Airports\s*=\s*\{(.*?)\};', content, re.DOTALL).group(1)
    airports = {a.strip(): True for a in airports_raw.split(',') if a.strip()}
    
    m_airports_raw = re.search(r'Airportmaintenance\s*=\s\s*\{(.*?)\};', content, re.DOTALL).group(1)
    m_airports = {a.strip(): True for a in m_airports_raw.split(',') if a.strip()}
    
    Days_raw = re.search(r'Days\s*=\s\s*\{(.*?)\};', content, re.DOTALL).group(1)
    Days_dict = {int(a.strip()): True for a in Days_raw.split(',') if a.strip()}
    Days = list(Days_dict.keys())
    Days=Days[1:]
    return nb_flight, cap_maintenance, horizon, flights, costs, m_costs, aircraft_init, airports, m_airports, Days

def preprocess_flights(flights, airports, aircraft_init,m_airports):
    """
    Prétraitement complet des données pour éviter les recalculs.
    Retourne des structures optimisées.
    """
    
    # Index par aéroport et type de vol
    flights_by_origin = defaultdict(list)
    flights_by_destination = defaultdict(list)
    
    # Index temporel pour recherche rapide
    departure_by_airport = defaultdict(dict)  # {airport: {flight_id: time}}
    arrival_by_airport = defaultdict(dict)
    
    # Mappings immuables
    flight_departure_time = {}  # {flight_id: time}
    flight_arrival_time = {}    # {flight_id: time}
    flight_origin = {}
    flight_destination = {}
    
    for flight in flights:
        fid = flight['id']
        origin = flight['origin']
        dest = flight['dest']
        dep_time = flight['departure']
        arr_time = flight['arrival']
        
        flights_by_origin[origin].append(fid)
        flights_by_destination[dest].append(fid)
        
        flight_departure_time[fid] = dep_time
        flight_arrival_time[fid] = arr_time
        flight_origin[fid] = origin
        flight_destination[fid] = dest
        
        departure_by_airport[origin][fid] = dep_time
        arrival_by_airport[dest][fid] = arr_time
    
    # Tri une seule fois (O(n log n) au lieu de répété)
    departures_sorted = {}  # {airport: [flight_ids] triés par departure}
    arrivals_sorted = {}    # {airport: [flight_ids] triés par arrival}
    
    for airport in flights_by_origin.keys():
        departures_sorted[airport] = sorted(
            flights_by_origin[airport],
            key=lambda fid: flight_departure_time[fid]
        )
    
    for airport in flights_by_destination.keys():
        arrivals_sorted[airport] = sorted(
            flights_by_destination[airport],
            key=lambda fid: flight_arrival_time[fid]
        )
    T = {f['id']: f for f in flights}
    
    
    return {
        'departures_sorted': departures_sorted,
        'arrivals_sorted': arrivals_sorted,
        'flight_departure_time': flight_departure_time,
        'flight_arrival_time': flight_arrival_time,
        'flight_origin': flight_origin,
        'flight_destination': flight_destination,
        'flights_by_origin': flights_by_origin,
        'flights_by_destination': flights_by_destination,      
        'T':T  
    }
  
  
# Utilisation
def model_feasible(path):
    nb_flights, cap_maintenance, horizon, flights, costs, m_costs, aircraft_init, airports, m_airports, Days  = load_dat_file(path)
    nb_aircrafts = len(aircraft_init)
    Aircraft = range(nb_aircrafts)
    Flights_id = range(1,nb_flights+1)
    m_Flights_id = {f['id']:f['dest'] for f in flights if f['dest'] in m_airports}
    flight_departure = {i['id']: i['departure'] for i in flights}
    flight_arrival   = {i['id']: i['arrival'] for i in flights}
    flight_day       = {i['id']: i['day'] for i in flights}

    flights_by_day = {
        d: [i for i in Flights_id if flight_day[i] == d]
        for d in Days
    }

    flights_by_origin_day = {
        (k, d): [j for j in flights if j["origin"] == k and j["day"] == d]
        for k in m_airports
        for d in Days
    }

    data = preprocess_flights(flights, set(Aircraft), aircraft_init,m_airports)
    Days_fictive=[i for i in range(-horizon +1,1)]
    tot_days=Days_fictive+Days

    ap_to_id = {ap: idx for idx, ap in enumerate(m_airports)}

    model = Model("xij")
    x = model.addVars(Flights_id, Aircraft,
                    vtype=GRB.BINARY, name="x")
    y = model.addVars(tot_days, Aircraft,
                    vtype=GRB.BINARY, name="y")
    z = model.addVars(Flights_id, Aircraft,
                    vtype=GRB.BINARY, name="z")

    airports = set(data['departures_sorted'].keys())

    # C1 — Couverture
    model.addConstrs((quicksum(x[i, t] for t in Aircraft) == 1
                    for i in Flights_id),
                        name="couverture");
    # C2
    for t in Aircraft:
        for k in airports:
            if k == aircraft_init.get(t):
                continue
            departures = data['departures_sorted'].get(k, [])
            departure_times = [data['flight_departure_time'][fid] for fid in departures]
            arrivals = data['arrivals_sorted'].get(k, [])
            arrival_times = [data['flight_arrival_time'][fid] for fid in arrivals]
            for target_fid in departures:
                target_time = data['flight_departure_time'][target_fid]
                
                # Vols ARRIVANT AVANT le départ du vol cible (arrival <= departure)
                idx_arrivals = bisect.bisect_right(arrival_times, target_time)
                arrivals_fids = arrivals[:idx_arrivals]

                # Vols PARTANT AVANT le vol cible (departure < departure_cible)
                idx_departures = bisect.bisect_left(departure_times, target_time)
                departures_fids = departures[:idx_departures]
                
                sum_arrivals = quicksum(x[f, t] for f in arrivals_fids)
                sum_departures = quicksum(x[f, t] for f in departures_fids)
                
                model.addConstr(sum_arrivals - sum_departures >= x[target_fid, t],
                        f"flow_{t}_{k}_{target_fid}")
    # C3
    for t in Aircraft:
        k = aircraft_init.get(t)
        departures = data['departures_sorted'].get(k, [])
        departure_times = [data['flight_departure_time'][fid] for fid in departures]
        arrivals = data['arrivals_sorted'].get(k, [])
        arrival_times = [data['flight_arrival_time'][fid] for fid in arrivals]

        for target_fid in departures:
            target_time = data['flight_departure_time'][target_fid]
        
            # Vols ARRIVANT AVANT le départ du vol cible (arrival <= departure)
            idx_arrivals = bisect.bisect_right(arrival_times, target_time)
            arrivals_fids = arrivals[:idx_arrivals]

            # Vols PARTANT AVANT le vol cible (departure < departure_cible
            idx_departures = bisect.bisect_left(departure_times, target_time)
            departures_fids = departures[:idx_departures]
            
            sum_arrivals = quicksum(x[f, t] for f in arrivals_fids)
            sum_departures = quicksum(x[f, t] for f in departures_fids)
            
            model.addConstr(sum_arrivals - sum_departures >= x[target_fid, t] - 1,
                    f"flow_{t}_{k}_{target_fid}")
            
            
    # C4 — Doublons
    seen = {}
    Doublons = []
    for fi in flights:
        key = (fi['departure'], fi['arrival'], fi['origin'], fi['dest'])
        if key in seen:
            Doublons.append((seen[key], fi['id']))
        else:
            seen[key] = fi['id']
            
    #condition initiale de maintenance par avion
    d_m=[random.choice(Days_fictive)  for _ in Aircraft] #liste des jours fictifs auxquels on met une maintenance

    model.addConstrs(
        (y[d, t] == (1 if d == d_m[t] else 0)
        for t in Aircraft
        for d in Days_fictive)
    )
    
    #Au moins une maintenance tout les horizons jours 

    model.addConstrs(
        (quicksum(y[d, t] for d in range(d0+1, d0 + horizon + 1) if d in tot_days) >= 1
            for t in Aircraft
            for d0 in tot_days
            if d0 + horizon in tot_days
        ),
        name="maintenance_window"
    );
 
    #L'avion arrive à destination pour la maintenance

    model.addConstrs(
        (x[i, t] >= z[i, t]
        for i in Flights_id
        for t in Aircraft),
        name="arrival_for_maintenance"
    );
                
    #Le dernier vol du jour match avec l'aéroport de maintenance

    model.addConstrs(
        (
            z[i, t] + x[j, t] <= 1
            for t in Aircraft
            for d in Days
            for i in flights_by_day[d]
            for j in flights_by_day[d]
            if flight_departure[j] > flight_arrival[i]
        ),
        name="last_flight_logic"
    );


    #Si on envoie un avion en maintenance alors il y a un vol pour le réaliser

    model.addConstrs(
        (
            quicksum(z[j["id"], t] for k in m_airports for j in flights_by_origin_day[k, d]) == y[d, t]
            for t in Aircraft
            for d in Days
        ),
        name="maintenance_flight_link"
    );
    
    #contrainte de capmaintenance
    model.addConstrs(
        quicksum(z[i["id"],t] for t in Aircraft for i in flights_by_origin_day[k,d])<=cap_maintenance
        for k in m_airports
        for d in Days
    )
            
            
    cost_it = {(i, t): m_costs[t][ap_to_id[data['flight_destination'][i]]] for i in m_Flights_id for t in Aircraft}
    
    
    model.setObjective(
        quicksum(costs[i-1][t]*x[i,t] for i in Flights_id for t in Aircraft)
        + quicksum(z[i,t]*cost_it[i,t] for i in m_Flights_id for t in Aircraft)
    )

    model.setParam("OutputFlag",1)
    model.setParam("Presolve", 2)
    model.setParam("MIPGap", 0.02)
    #model.setParam("MIPFocus", 2)
    
    model.optimize()

    nb_vars = model.NumVars
    nb_constrs = model.NumConstrs
    nb_nonzeros = model.NumNZs
    nb_work = model.Work
    
    best0bj1 = model.ObjVal
    
    for i in Flights_id:
        for t in Aircraft:
            if x[i,t].X > 0.5:
                x[i,t].lb = 1
                x[i,t].ub = 1
        
    model.addConstr(quicksum(costs[i-1][t]*x[i,t] for i in Flights_id for t in Aircraft)
        + quicksum(z[i,t]*cost_it[i,t] for i in m_Flights_id for t in Aircraft) <= best0bj1)
    
    model.setObjective(quicksum(y[d,t] for d in Days for t in Aircraft))
    
    model.setParam("Presolve", -1)
    model.optimize()

    #########################SCHEDULE#####################################
    # schedule = {}
    

    # for t in Aircraft:
    #     flights_used = []
    #     maintenance_used = []

    #     for i in Flights_id:
    #         if x[i, t].X > 0.5:
    #             flights_used.append(data['T'][i])
    #         if z[i,t].X > 0.5 :
    #             maintenance_used.append(data['T'][i])
            

    #     flights_used.sort(key=lambda f: f["departure"])
    #     schedule[t] = flights_used
    
    # fig, ax = plt.subplots(figsize=(20, 8))

    # for t in Aircraft:
    #     # ─── vols ────────────────────────────────────────────────────────────────
    #     for f in schedule[t]:
    #         x_dep = f['departure']
    #         x_arr = f['arrival']
    #         ax.plot([x_dep, x_arr], [t, t], 'b-', linewidth=4)
    
    #     # ─── maintenances ────────────────────────────────────────────────────────
    #     for i in Flights_id:
    #         if z[i, t].X > 0.5:
    #             ax.plot(flight_departure[i], t, 'r*', markersize=12)

    # # ─── mise en forme ────────────────────────────────────────────────────────────
    # ax.set_yticks(list(Aircraft))
    # ax.set_yticklabels([f"Avion {t} ({d_m[t]})" for t in Aircraft])
    # day_duration = 1440  # minutes par jour
    # days_list = sorted(set(f['day'] for t in Aircraft for f in schedule[t]))

    # for d in days_list:
    #     ax.axvline(x=d * day_duration, color='gray', linestyle='--', alpha=0.3, linewidth=0.8)

    # ax.set_xlabel("Jour")
    # ax.set_xticks([d * day_duration for d in days_list])
    # ax.set_xticklabels([f"J{d}" for d in days_list])
    # ax.set_title("Planning des avions")
    # ax.grid(True, alpha=0.3)

    # blue_patch = mpatches.Patch(color='blue', label='En vol')
    # red_patch  = mpatches.Patch(color='red',  label='Maintenance')
    # ax.legend(handles=[blue_patch, red_patch])

    # plt.tight_layout()
    # plt.title(path)
    # plt.show()
    
    return nb_work, (nb_vars, nb_constrs, nb_nonzeros)
    



import os
import time

# Dossier contenant tous les fichiers .dat
folder = "../Data_with_maintenance_constraints/d=0"
folder2 = "../Data_with_maintenance_constraints/d=5"

# Liste de tous les chemins complets vers les fichiers .dat


#paths = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".dat")]
#paths += [os.path.join(folder2, f) for f in os.listdir(folder2) if f.endswith(".dat")]
paths = ["../Data_with_maintenance_constraints/d=4/DataCplex_density=1_p=20_h=15_test_0.dat"]




paths.sort()


results = []

for path in paths:
    start = time.perf_counter()
    
    work, size = model_feasible(path)

    runtime = time.perf_counter() - start
    
    results.append((path, size, runtime, work))
    
    print(f"{os.path.basename(path)} |  Time={runtime:.3f}s | Work={work:.3f} units | Size= {size}")

print(results)