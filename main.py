#!/usr/bin/env python3
# main.py
"""
Script principal pour résoudre les problèmes d'optimisation d'horaires d'avions
"""

import os
import time
import sys

# Importer les modules
from src.data_loader import load_dat_file
from src.preprocessing import preprocess_flights
from src.model import build_and_solve_model
from src.model import build_and_solve_model_2

def solve_instance(filepath):
    """
    Résout une instance du problème.
    
    Args:
        filepath: Chemin vers le fichier .dat
        
    Returns:
        dict: Résultats (temps, dimensions du problème, etc.)
    """
    
    print(f"\n{'='*70}")
    print(f"Traitement: {os.path.basename(filepath)}")
    print(f"{'='*70}")
    
    # Charger les données
    print("▶ Chargement des données...")
    nb_flights, cap_maintenance, horizon, flights, costs, m_costs, \
        aircraft_init, airports, m_airports, Days = load_dat_file(filepath)
    
    nb_aircrafts = len(aircraft_init)
    print(f"  ✓ {nb_flights} vols, {nb_aircrafts} avions, horizon={horizon}")
    
    # Prétraitement
    print("▶ Prétraitement des données...")
    data = preprocess_flights(flights, set(range(nb_aircrafts)), aircraft_init, m_airports)
    print(f"  ✓ Prétraitement complété")
    
    
    # Construire et résoudre le modèle
    print("▶ Construction du modèle...")
    start_time = time.perf_counter()
    
    model, x, y, z = build_and_solve_model(
        nb_flights, cap_maintenance, horizon, flights, costs, m_costs,
        aircraft_init, airports, m_airports, Days, data
    )
    
    # Paramètres Gurobi
    model.setParam("OutputFlag", 1)
    model.setParam("Presolve", 2)
    model.setParam("MIPGap", 0.02)
    
    print("▶ Optimisation...")
    model.optimize()
    
    model.write("model.lp")
    
    solve_time = time.perf_counter() - start_time
    
    # Statistiques
    nb_vars = model.NumVars
    nb_constrs = model.NumConstrs
    nb_nonzeros = model.NumNZs
    nb_work = model.Work
    
    # Paramètres Gurobi
    model.setParam("OutputFlag", 1)
    model.setParam("Presolve", 1)
    model.setParam("MIPGap", 0.02)   
    
    # 2ème optimisation pour réduire les maintenances 
    # et atteindre un minimum local 
    model, x, y, z = build_and_solve_model_2(
        nb_flights, flights, costs, m_costs,
        aircraft_init, m_airports, Days, data, model, x, y, z
        )
        
    model.setParam("Presolve", -1)
    model.optimize()
    
    results = {
        'filename': os.path.basename(filepath),
        'nb_flights': nb_flights,
        'nb_aircrafts': nb_aircrafts,
        'nb_vars': nb_vars,
        'nb_constrs': nb_constrs,
        'nb_nonzeros': nb_nonzeros,
        'solve_time': solve_time,
        'work_units': nb_work,
        'obj_value': model.ObjVal if model.status == 2 else None,
        'status': model.status
    }
    
    # Affichage des résultats
    print(f"\n▶ Résultats:")
    print(f"  Statut: {'Optimal' if model.status == 2 else 'Suboptimal/Infeasible'}")
    print(f"  Objectif: {results['obj_value']:.2f}" if results['obj_value'] else "  Objectif: N/A")
    print(f"  Temps: {solve_time:.3f}s")
    print(f"  Travail Gurobi: {nb_work:.3f} unités")
    print(f"  Variables: {nb_vars}")
    print(f"  Contraintes: {nb_constrs}")
    print(f"  Non-zéros: {nb_nonzeros}")
    
    return results


def main():
    """Fonction principale"""
    
    print("\n" + "="*70)
    print("OPTIMISATION TAIL ASSIGNEMENT")
    print("="*70)
    
    # Fichiers à traiter
    folder = "data_with_maintenance_constraints/d=4"
    
    # Option 1: Un fichier spécifique
    paths = ["data_with_maintenance_constraints/d=4/DataCplex_density=1_p=10_h=15_test_0.dat"]
    
    # Option 2: Tous les fichiers d'un dossier
    #paths = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".dat")]
    
    paths.sort()
    
    # Résoudre tous les fichiers
    all_results = []
    
    for path in paths:
        try:
            results = solve_instance(path)
            
            all_results.append(results)
        except Exception as e:
            print(f"❌ Erreur pour {os.path.basename(path)}: {e}")
            import traceback
            traceback.print_exc()
    
    # Résumé final
    print(f"\n{'='*70}")
    print("RÉSUMÉ FINAL")
    print(f"{'='*70}")
    
    for res in all_results:
        print(f"\n{res['filename']}")
        print(f"  Vols: {res['nb_flights']}, Avions: {res['nb_aircrafts']}")
        print(f"  Temps: {res['solve_time']:.3f}s | Travail: {res['work_units']:.3f} | "
              f"Vars: {res['nb_vars']} | Constrs: {res['nb_constrs']}")
        if res['obj_value']:
            print(f"  Objectif: {res['obj_value']:.2f}")
    
    print(f"\n{'='*70}\n")
    
    return all_results


if __name__ == "__main__":
    results = main()
