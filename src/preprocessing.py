# src/preprocessing.py
"""
Data preprocessing module for Gurobi optimization
"""

import bisect
from collections import defaultdict


def preprocess_flights(flights, airports, aircraft_init, m_airports):
    """
    Complete data preprocessing to avoid recomputations.
    
    Optimizations:
    - Single sorts instead of repeated ones
    - Pre-computed temporal indices
    - Immutable structures for O(1) access
    
    Args:
        flights: List of flights
        airports: Set of airports
        aircraft_init: Dict {aircraft_id: initial_airport}
        m_airports: Set of maintenance airports
        
    Returns:
        dict: Dictionary with preprocessed data
    """
    
    # Index by airport and flight type
    flights_by_origin = defaultdict(list)
    flights_by_destination = defaultdict(list)
    
    # Immutable mappings
    flight_departure_time = {}
    flight_arrival_time = {}
    flight_origin = {}
    flight_destination = {}
    
    # First pass: indexing
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
    
    # Second pass: single sorts
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
    
    # Create dictionary of flights by ID
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
    Finds compatible flights using binary search.
    
    Args:
        data: Preprocessed data
        airport: Airport to consider
        target_fid: Target flight ID
        flight_type: 'arrivals' or 'departures'
        
    Returns:
        list: IDs of compatible flights
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