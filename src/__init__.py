
# src/__init__.py
"""
Package d'optimisation d'horaires d'avions
"""
 
from .data_loader import load_dat_file
from .preprocessing import preprocess_flights, find_compatible_flights
from .model import build_and_solve_model
 
__all__ = [
    'load_dat_file',
    'preprocess_flights',
    'find_compatible_flights',
    'build_and_solve_model'
]
 