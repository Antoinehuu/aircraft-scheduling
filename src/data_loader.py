# src/data_loader.py
"""
Module pour charger et parser les fichiers .dat
"""

import re
from collections import defaultdict


def load_dat_file(filename):
    """
    Charge un fichier .dat et extrait toutes les données nécessaires.
    
    Args:
        filename: Chemin vers le fichier .dat
        
    Returns:
        tuple: (nb_flights, cap_maintenance, horizon, flights, costs, m_costs, 
                aircraft_init, airports, m_airports, Days)
    """
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extraction des paramètres
    nb_flight = int(re.search(r'Nbflight\s*=\s*(\d+);', content).group(1))
    cap_maintenance = int(re.search(r'capmaintenance\s*=\s*(\d+);', content).group(1))
    horizon = int(re.search(r'horizon\s*=\s*(\d+);', content).group(1))

    # Extraction des vols
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

    # Extraction des coûts
    cost_section = re.search(r'Cost\s*=\s*\[(.*?)\];', content, re.DOTALL).group(1)
    costs_raw = re.findall(r'\[(.*?)\]', cost_section)
    costs = [list(map(float, c.strip(',').split(','))) for c in costs_raw if c.strip()]

    # Extraction des coûts de maintenance
    m_cost_section = re.search(r'CostMaintenance\s*=\s*\[(.*?)\];', content, re.DOTALL).group(1)
    m_costs_raw = re.findall(r'\[(.*?)\]', m_cost_section)
    m_costs = [list(map(float, c.strip(',').split(','))) for c in m_costs_raw if c.strip()]
    
    # Extraction des avions
    aircraft_raw = re.findall(r'<(.*?)>', re.search(r'Aircraft\s*=\s*\[(.*?)\];', content, re.DOTALL).group(1))
    aircraft_init = {}
    for a in aircraft_raw:
        idx, city = a.split(',')
        aircraft_init[int(idx)] = city.strip()
        
    # Extraction des aéroports
    airports_raw = re.search(r'Airports\s*=\s*\{(.*?)\};', content, re.DOTALL).group(1)
    airports = {a.strip(): True for a in airports_raw.split(',') if a.strip()}
    
    # Extraction des aéroports de maintenance
    m_airports_raw = re.search(r'Airportmaintenance\s*=\s\s*\{(.*?)\};', content, re.DOTALL).group(1)
    m_airports = {a.strip(): True for a in m_airports_raw.split(',') if a.strip()}
    
    # Extraction des jours
    Days_raw = re.search(r'Days\s*=\s\s*\{(.*?)\};', content, re.DOTALL).group(1)
    Days_dict = {int(a.strip()): True for a in Days_raw.split(',') if a.strip()}
    Days = list(Days_dict.keys())
    Days = Days[1:]  # Supprimer le premier jour
    
    return nb_flight, cap_maintenance, horizon, flights, costs, m_costs, aircraft_init, airports, m_airports, Days
