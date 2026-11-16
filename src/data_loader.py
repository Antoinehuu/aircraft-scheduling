"""
Module to load and parse .dat files
"""

import re
from collections import defaultdict


def dat_file_maintenance(filename):
    """
    Loads a .dat file and extracts all necessary data.
    
    Args:
        filename: Path to the .dat file
        
    Returns:
        tuple: (nb_flights, cap_maintenance, horizon, flights, costs, m_costs, 
                aircraft_init, airports, m_airports, Days)
    """
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parameter extraction
    nb_flight = int(re.search(r'Nbflight\s*=\s*(\d+);', content).group(1))
    cap_maintenance = int(re.search(r'capmaintenance\s*=\s*(\d+);', content).group(1))
    horizon = int(re.search(r'horizon\s*=\s*(\d+);', content).group(1))

    # Flight extraction
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
            'day': int(parts[5])
        })

    # Cost extraction
    cost_section = re.search(r'Cost\s*=\s*\[(.*?)\];', content, re.DOTALL).group(1)
    costs_raw = re.findall(r'\[(.*?)\]', cost_section)
    costs = [list(map(float, c.strip(',').split(','))) for c in costs_raw if c.strip()]

    # Maintenance cost extraction
    m_cost_section = re.search(r'CostMaintenance\s*=\s*\[(.*?)\];', content, re.DOTALL).group(1)
    m_costs_raw = re.findall(r'\[(.*?)\]', m_cost_section)
    m_costs = [list(map(float, c.strip(',').split(','))) for c in m_costs_raw if c.strip()]
    
    # Aircraft extraction
    aircraft_raw = re.findall(r'<(.*?)>', re.search(r'Aircraft\s*=\s*\[(.*?)\];', content, re.DOTALL).group(1))
    aircraft_init = {}
    for a in aircraft_raw:
        idx, city = a.split(',')
        aircraft_init[int(idx)] = city.strip()
        
    # Airport extraction
    airports_raw = re.search(r'Airports\s*=\s*\{(.*?)\};', content, re.DOTALL).group(1)
    airports = {a.strip(): True for a in airports_raw.split(',') if a.strip()}
    
    # Maintenance airport extraction
    m_airports_raw = re.search(r'Airportmaintenance\s*=\s\s*\{(.*?)\};', content, re.DOTALL).group(1)
    m_airports = {a.strip(): True for a in m_airports_raw.split(',') if a.strip()}
    
    # Day extraction
    Days_raw = re.search(r'Days\s*=\s\s*\{(.*?)\};', content, re.DOTALL).group(1)
    Days_dict = {int(a.strip()): True for a in Days_raw.split(',') if a.strip()}
    Days = list(Days_dict.keys())
    Days = Days[1:]  # Remove the first day
    
    return nb_flight, cap_maintenance, horizon, flights, costs, m_costs, aircraft_init, airports, m_airports, Days


def dat_file(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # ---- parameters ------------------------------------------------------
    nb_flight = int(re.search(r'Nbflight\s*=\s*(\d+);', content).group(1))

    m = re.search(r'capmaintenance\s*=\s*(\d+);', content)
    cap_maintenance = int(m.group(1)) if m else 0

    m = re.search(r'horizon\s*=\s*(\d+);', content)
    horizon = int(m.group(1)) if m else 0

    # ---- flights ---------------------------------------------------------
    flights_raw = re.findall(
        r'<(.*?)>',
        re.search(r'Flight\s*=\s*\{(.*?)\};', content, re.DOTALL).group(1),
    )
    flights = []
    for f in flights_raw:
        parts = f.split(',')
        flights.append({
            'id': int(parts[0]),
            'origin': parts[1].strip(),
            'dest': parts[2].strip(),
            'departure': float(parts[3]),
            'arrival': float(parts[4]),
            'day': int(parts[5]) if len(parts) > 5 else 1,
        })

    # ---- flight costs ----------------------------------------------------
    cost_section = re.search(r'Cost\s*=\s*\[(.*?)\];', content, re.DOTALL).group(1)
    costs_raw = re.findall(r'\[(.*?)\]', cost_section)
    costs = [list(map(float, c.strip(',').split(','))) for c in costs_raw if c.strip()]

    # ---- maintenance costs (optional) ------------------------------------
    m = re.search(r'CostMaintenance\s*=\s*\[(.*?)\];', content, re.DOTALL)
    if m:
        m_costs_raw = re.findall(r'\[(.*?)\]', m.group(1))
        m_costs = [list(map(float, c.strip(',').split(','))) for c in m_costs_raw if c.strip()]
    else:
        # No maintenance costs: one zero row per aircraft, matching cost width
        nb_aircrafts = len(re.findall(r'<', re.search(r'Aircraft\s*=\s*\[(.*?)\];', content, re.DOTALL).group(1)))
        width = len(costs[0]) if costs else 0
        m_costs = [[0.0] * width for _ in range(nb_aircrafts)]

    # ---- aircraft --------------------------------------------------------
    aircraft_raw = re.findall(
        r'<(.*?)>',
        re.search(r'Aircraft\s*=\s*\[(.*?)\];', content, re.DOTALL).group(1),
    )
    aircraft_init = {}
    for a in aircraft_raw:
        idx, city = a.split(',')
        aircraft_init[int(idx)] = city.strip()

    # ---- airports --------------------------------------------------------
    airports_raw = re.search(r'Airports\s*=\s*\{(.*?)\};', content, re.DOTALL).group(1)
    airports = {a.strip(): True for a in airports_raw.split(',') if a.strip()}

    # ---- maintenance airports (optional) ---------------------------------
    m = re.search(r'Airportmaintenance\s*=\s*[\s]*\{(.*?)\};', content, re.DOTALL)
    if m:
        m_airports = {a.strip(): True for a in m.group(1).split(',') if a.strip()}
    else:
        # No maintenance airports: fall back to the full airport set
        m_airports = dict(airports)

    # ---- days (optional) -------------------------------------------------
    m = re.search(r'Days\s*=\s*[\s]*\{(.*?)\};', content, re.DOTALL)
    if m:
        Days_dict = {int(a.strip()): True for a in m.group(1).split(',') if a.strip()}
        Days = list(Days_dict.keys())
        Days = Days[1:]  # Remove the first day (original behaviour)
    else:
        # Derive days from flights, or default to a single day
        days_from_flights = sorted({f['day'] for f in flights})
        Days = days_from_flights if days_from_flights else [1]

    return (
        nb_flight,
        cap_maintenance,
        horizon,
        flights,
        costs,
        m_costs,
        aircraft_init,
        airports,
        m_airports,
        Days,
    )

def load_dat_file(filename):
    if "maintenance" in filename:
        return dat_file_maintenance(filename)
    return dat_file(filename)