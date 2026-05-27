# src/model.py
"""
Module de construction et résolution du modèle d'optimisation
"""

import bisect
import random
from gurobipy import Model, GRB, quicksum


def build_and_solve_model(nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
                          aircraft_init, airports, m_airports, Days, data):
    """
    Construit et résout le modèle d'optimisation.
    
    Args:
        nb_flights: Nombre de vols
        cap_maintenance: Capacité de maintenance
        horizon: Horizon de maintenance
        flights: Liste des vols
        costs: Coûts des vols
        m_costs: Coûts de maintenance
        aircraft_init: Aéroports initiaux des avions
        airports: Set des aéroports
        m_airports: Set des aéroports de maintenance
        Days: Liste des jours
        data: Données prétraitées
        
    Returns:
        tuple: (model, x, y, z, nb_vars, nb_constrs, nb_nonzeros)
    """
    
    nb_aircrafts = len(aircraft_init)
    Aircraft = range(nb_aircrafts)
    Flights_id = range(1, nb_flights + 1)
    
    
    # Dictionnaires utiles
    m_Flights_id = {f['id']: f['dest'] for f in flights if f['dest'] in m_airports}
    flight_day = {i['id']: i['day'] for i in flights}
    
    flights_by_day = {
        d: [i for i in Flights_id if flight_day[i] == d]
        for d in Days
    }
    
    flights_by_origin_day = {
        (k, d): [j for j in flights if j["origin"] == k and j["day"] == d]
        for k in m_airports
        for d in Days
    }
    
    # Jours fictifs
    Days_fictive = [i for i in range(-horizon + 1, 1)]
    tot_days = Days_fictive + Days
    
    # Mapping aéroports
    ap_to_id = {ap: idx for idx, ap in enumerate(m_airports)}
    
    # Création du modèle
    model = Model("aircraft_scheduling")
    
    # Variables
    x = model.addVars(Flights_id, Aircraft, vtype=GRB.BINARY, name="x")
    y = model.addVars(tot_days, Aircraft, vtype=GRB.BINARY, name="y")
    z = model.addVars(Flights_id, Aircraft, vtype=GRB.BINARY, name="z")
    
    airports_set = set(data['departures_sorted'].keys())
    
    # C1 — Couverture
    model.addConstrs(
        (quicksum(x[i, t] for t in Aircraft) == 1 for i in Flights_id),
        name="couverture"
    )
    
    # C2 — Flux (hors base)
    _add_flow_constraints(model, Aircraft, aircraft_init, data, x, airports_set)
    
    # C3 — Flux (base)
    _add_base_constraints(model, Aircraft, aircraft_init, data, x)
    
    # C4 — Doublons
    _add_duplicate_constraints(model, Aircraft, flights, x)
    
    # Contraintes de maintenance
    _add_maintenance_constraints(model, Aircraft, Days, Days_fictive, tot_days,
                                 horizon, Flights_id, flights, flights_by_day, flights_by_origin_day,
                                 m_airports, cap_maintenance, x, y, z)
    
    # Objectif
    cost_it = {
        (i, t): m_costs[t][ap_to_id[data['flight_destination'][i]]]
        for i in m_Flights_id for t in Aircraft
    }
    
    model.setObjective(
        quicksum(costs[i-1][t] * x[i, t] for i in Flights_id for t in Aircraft)
        + quicksum(z[i, t] * cost_it[i, t] for i in m_Flights_id for t in Aircraft)
    )
    
    # model.computeIIS()
    # model.write("model.ilp")
    
    return model, x, y, z


def _add_flow_constraints(model, Aircraft, aircraft_init, data, x, airports_set):
    """Ajoute les contraintes de flux (hors base) - C2"""
    for t in Aircraft:
        for airport in airports_set:
            if airport == aircraft_init.get(t):
                continue
            
            departures = data['departures_sorted'].get(airport, [])
            departure_times = [data['flight_departure_time'][fid] for fid in departures]
            arrivals = data['arrivals_sorted'].get(airport, [])
            arrival_times = [data['flight_arrival_time'][fid] for fid in arrivals]
            
            for target_fid in departures:
                target_time = data['flight_departure_time'][target_fid]
                
                idx_arrivals = bisect.bisect_right(arrival_times, target_time)
                arrivals_fids = arrivals[:idx_arrivals]
                
                idx_departures = bisect.bisect_left(departure_times, target_time)
                departures_fids = departures[:idx_departures]
                
                sum_arrivals = quicksum(x[f, t] for f in arrivals_fids)
                sum_departures = quicksum(x[f, t] for f in departures_fids)
                
                model.addConstr(
                    sum_arrivals - sum_departures >= x[target_fid, t],
                    f"flow_{t}_{airport}_{target_fid}"
                )


def _add_base_constraints(model, Aircraft, aircraft_init, data, x):
    """Ajoute les contraintes de flux (base) - C3"""
    for t in Aircraft:
        airport = aircraft_init.get(t)
        departures = data['departures_sorted'].get(airport, [])
        departure_times = [data['flight_departure_time'][fid] for fid in departures]
        arrivals = data['arrivals_sorted'].get(airport, [])
        arrival_times = [data['flight_arrival_time'][fid] for fid in arrivals]
        
        for target_fid in departures:
            target_time = data['flight_departure_time'][target_fid]
            
            idx_arrivals = bisect.bisect_right(arrival_times, target_time)
            arrivals_fids = arrivals[:idx_arrivals]
            
            idx_departures = bisect.bisect_left(departure_times, target_time)
            departures_fids = departures[:idx_departures]
            
            sum_arrivals = quicksum(x[f, t] for f in arrivals_fids)
            sum_departures = quicksum(x[f, t] for f in departures_fids)
            
            model.addConstr(
                sum_arrivals - sum_departures >= x[target_fid, t] - 1,
                f"base_{t}_{airport}_{target_fid}"
            )


def _add_duplicate_constraints(model, Aircraft, flights, x):
    """Ajoute les contraintes de doublons - C4"""
    seen = {}
    Doublons = []
    for fi in flights:
        key = (fi['departure'], fi['arrival'], fi['origin'], fi['dest'])
        if key in seen:
            Doublons.append((seen[key], fi['id']))
        else:
            seen[key] = fi['id']
    
    if Doublons:
        model.addConstrs(
            (x[i, t] + x[j, t] <= 1 for t in Aircraft for (i, j) in Doublons),
            name="doublons"
        )


def _add_maintenance_constraints(model, Aircraft, Days, Days_fictive, tot_days, horizon,
                                Flights_id, flights, flights_by_day, flights_by_origin_day,
                                m_airports, cap_maintenance, x, y, z):
    """Ajoute les contraintes de maintenance"""
    
    flight_departure = {i['id']: i['departure'] for i in flights}
    flight_arrival = {i['id']: i['arrival'] for i in flights}
    
    # Condition initiale de maintenance
    d_m = [random.choice(Days_fictive) for _ in Aircraft]
    
    model.addConstrs(
        (y[d, t] == (1 if d == d_m[t] else 0) for t in Aircraft for d in Days_fictive),
        name="initial_maintenance"
    )
    
    # Au moins une maintenance tous les horizon jours
    model.addConstrs(
        (quicksum(y[d, t] for d in range(d0 + 1, d0 + horizon + 1) if d in tot_days) >= 1
         for t in Aircraft for d0 in tot_days if d0 + horizon in tot_days),
        name="maintenance_window"
    )
    
    # L'avion arrive à destination pour la maintenance
    model.addConstrs(
        (x[i, t] >= z[i, t] for i in Flights_id for t in Aircraft),
        name="arrival_for_maintenance"
    )
    
    # Le dernier vol du jour match avec l'aéroport de maintenance
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
    
    # Si on envoie un avion en maintenance alors il y a un vol pour le réaliser
    model.addConstrs(
        (quicksum(z[j["id"], t] for k in m_airports 
                  for j in flights_by_origin_day.get((k, d), [])) == y[d, t]
         for t in Aircraft for d in Days),
        name="maintenance_flight_link"
    )
    
    # Contrainte de capacité maintenance
    model.addConstrs(
        (quicksum(z[i["id"], t] for t in Aircraft 
                  for i in flights_by_origin_day.get((k, d), [])) <= cap_maintenance
         for k in m_airports for d in Days),
        name="maintenance_capacity"
    )

def build_and_solve_model_2(
    nb_flights, flights, costs, m_costs,
    aircraft_init, m_airports, Days, data, model, x, y, z):
    """optimise localement en retirant les maintenances en trop"""

    nb_aircrafts = len(aircraft_init)
    Aircraft = range(nb_aircrafts)
    Flights_id = range(1, nb_flights + 1)
    best0bj1 = model.ObjVal
    
    for i in Flights_id:
        for t in Aircraft:
            if x[i,t].X > 0.5:
                x[i,t].lb = 1
                x[i,t].ub = 1
    
    m_Flights_id = {f['id']: f['dest'] for f in flights if f['dest'] in m_airports}
    ap_to_id = {ap: idx for idx, ap in enumerate(m_airports)}
    
    cost_it = {
        (i, t): m_costs[t][ap_to_id[data['flight_destination'][i]]]
        for i in m_Flights_id for t in Aircraft
    }
        
    model.addConstr(quicksum(costs[i-1][t]*x[i,t] for i in Flights_id for t in Aircraft)
        + quicksum(z[i,t]*cost_it[i,t] for i in m_Flights_id for t in Aircraft) <= best0bj1)
    
    model.setObjective(quicksum(y[d,t] for d in Days for t in Aircraft))
    
    return model, x, y, z