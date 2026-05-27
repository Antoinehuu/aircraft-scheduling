# src/preprocessing.py
"""
Module de prétraitement des données pour optimisation Gurobi
"""

import bisect
from collections import defaultdict


def preprocess_flights(flights, airports, aircraft_init, m_airports):
    """
    Prétraitement complet des données pour éviter les recalculs.
    
    Optimisations:
    - Tris uniques au lieu de répétés
    - Index temporels pré-calculés
    - Structures immuables pour accès O(1)
    
    Args:
        flights: Liste des vols
        airports: Set des aéroports
        aircraft_init: Dict {aircraft_id: airport_initial}
        m_airports: Set des aéroports de maintenance
        
    Returns:
        dict: Dictionnaire avec données prétraitées
    """
    
    # Index par aéroport et type de vol
    flights_by_origin = defaultdict(list)
    flights_by_destination = defaultdict(list)
    
    # Mappings immuables
    flight_departure_time = {}
    flight_arrival_time = {}
    flight_origin = {}
    flight_destination = {}
    
    # Première passe: indexation
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
    
    # Deuxième passe: tris uniques
    departures_sorted = {}
    arrivals_sorted = {}
    
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
    
    # Créer dictionnaire des vols par ID
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
        'T': T  
    }


def find_compatible_flights(data, airport, target_fid, flight_type='arrivals'):
    """
    Trouve les vols compatibles avec recherche binaire.
    
    Args:
        data: Données prétraitées
        airport: Aéroport à considérer
        target_fid: ID du vol cible
        flight_type: 'arrivals' ou 'departures'
        
    Returns:
        list: IDs des vols compatibles
    """
    if flight_type == 'arrivals':
        arrivals = data['arrivals_sorted'].get(airport, [])
        arrival_times = [data['flight_arrival_time'][fid] for fid in arrivals]
        target_time = data['flight_departure_time'][target_fid]
        
        idx = bisect.bisect_right(arrival_times, target_time)
        return arrivals[:idx]
    
    elif flight_type == 'departures':
        departures = data['departures_sorted'].get(airport, [])
        departure_times = [data['flight_departure_time'][fid] for fid in departures]
        target_time = data['flight_departure_time'][target_fid]
        
        idx = bisect.bisect_left(departure_times, target_time)
        return departures[:idx]
    
    return []
