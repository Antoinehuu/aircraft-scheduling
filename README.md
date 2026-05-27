# Aircraft-scheduling tuto installation

Ce projet de Tail assignement résout un problème d'attribution des tâches pour chaque avion dans le cadre d'un projet en cours de recherche opérationnelle à CentraleSupélec. 

## 1. Cloner le projet

```bash
git clone https://github.com/yourusername/aircraft-scheduling.git
cd aircraft-scheduling
```

---

## 2. Créer un environnement virtuel

### Sur Linux/Mac:
```bash
python3 -m venv venv
source venv/bin/activate
```

### Sur Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

---

## 3. Installer les modules

Nécéssite une license Gurobi, il y a un tuto pour une license académique à la fin.

```bash
pip install -r requirements.txt
```

---

## 4. Vérifier que ça marche

```bash
# Test simple
python -c "import gurobipy; print('✓ OK')"
```

---

# 📂 Structure du Projet - Aircraft Scheduling

## Arborescence

```
projet/
├── main.py                           ← Script principal à exécuter
├── README.md                         ← Ce fichier
├── requirements.txt
│
├── src/                              ← Package d'optimisation
│   ├── __init__.py
│   ├── data_loader.py
│   ├── preprocessing.py              ← Prétraitement des données
│   └── model.py                      ← Implémentation et résolution du modèle
│
├── data                              ← Data sans les maintenances
├── data_with_maintenance_constraints/
│   └── d=4/
│       └── *.dat                     ← Fichiers d'instances
│
└── results/                          ← Résultats des exécutions
```

---

## Description des fichiers

### `main.py`
**Fichier principal à exécuter**

- Lance le solveur sur les instances
- Affiche un résumé des résultats
- Gère les fichiers d'entrée/sortie

**Utilisation:**
```bash
python main.py
```

### `src/data_loader.py`
**Chargement des données**

Fonction principale:
- `load_dat_file(filename)` → Charge un fichier .dat et retourne toutes les données

Responsabilités:
- Parsing du fichier avec regex
- Extraction des paramètres (nb_flights, horizon, etc.)
- Extraction des vols, coûts, avions, aéroports

### `src/preprocessing.py`
**Prétraitement des données**

Fonctions principales:
- `preprocess_flights(flights, airports, aircraft_init, m_airports)` → Pré-traite les données
- `find_compatible_flights(data, airport, target_fid, flight_type)` → Recherche binaire

Optimisations via des dictionnaires adaptés

### `src/model.py`
**Construction et résolution du modèle**

- `build_and_solve_model(...)` → Construit le modèle Gurobi
- `_add_flow_constraints()` → Contraintes C2
- `_add_base_constraints()` → Contraintes C3
- `_add_duplicate_constraints()` → Contraintes C4
- `_add_maintenance_constraints()` → Contraintes de maintenance

### `src/__init__.py`
**Package init**

Exporte les fonctions principales du package pour utilisation externe.

---

## Utilisation

### Exécution simple

```bash
python main.py
```

### Traiter plusieurs fichiers

Modifier `main()` dans `main.py`:

```python
# Option 1: Tous les fichiers d'un dossier
paths = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".dat")]

# Option 2: Fichiers spécifiques
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
  │   └─→ Charge fichier .dat
  │       └─→ Returns: nb_flights, cap_maintenance, horizon, ...
  │
  ├─→ preprocess_flights()
  │   └─→ Indexe et trie les données
  │       └─→ Returns: data (dict optimisé)
  │
  └─→ build_and_solve_model()
      ├─→ Crée variables Gurobi (x, y, z)
      ├─→ Ajoute contraintes
      │   ├─→ C1: Couverture
      │   ├─→ C2: Flux (hors base)
      │   ├─→ C3: Flux (base)
      │   ├─→ C4: Doublons
      │   └─→ Maintenance
      ├─→ Définit objectif
      └─→ Résout le modèle
          └─→ Returns: (model, x, y, z)
```


## 🔧 Configuration Gurobi

Dans `main.py`:

```python
model.setParam("OutputFlag", 1)      # Afficher les logs
model.setParam("Presolve", 2)        # Présolve agressif
model.setParam("MIPGap", 0.02)       # Gap tolérance 2%
```

À modifier selon les besoins:
- MIPGap: Plus petit = plus de temps mais meilleure solution
- Presolve: -1 (auto), 0 (off), 1 (conservatif), 2 (agressif)
- Threads: Nombre de threads parallèles

---

## Format du fichier .dat

Exemple:
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

Pour déboguer un problème:

1. **Vérifier le chargement:**
   ```python
   from src.data_loader import load_dat_file
   data = load_dat_file("path/to/file.dat")
   print(data)
   ```

2. **Vérifier le prétraitement:**
   ```python
   from src.preprocessing import preprocess_flights
   preprocessed = preprocess_flights(...)
   print(f"Aéroports trouvés: {list(preprocessed['departures_sorted'].keys())}")
   ```

3. **Vérifier le modèle:**
   ```python
   model.write("debug.lp")  # Exporte le modèle en format LP
   ```

---

## Installation license académique


• Allez sur la page principale du site de Gurobi et connectez-vous à votre compte Gurobi via l’onglet Login, si
vous ne l’êtes pas.

• Cliquez sur l’onglet Downloads and licenses. Dans le paragraphe Request a license, cliquez sur l’onglet
Academic License.

• Acceptez les conditions d’utilisation de la licence académique. Comme vous pouvez le voir, votre licence
académique Gurobi a bien été générée. Vous pouvez désormais installer votre licence en suivant les
instructions données dans le paragraphe Installation sous le tableau de détails. Nous donnons quelques
indications supplémentaires ci-dessous :

– Sur macOs ou Linux.

∗ Copiez la commande grbgetkey <clé>, ouvrez une fenêtre de terminal, collez la commande dans
votrefenêtredeterminaletexécutez-la. Ilvousestdemandédechoisirledossierdanslequelstocker
votre fichier de licence, tapez entrer afin de choisir le dossier par défaut. Nous vous recommandons
de choisir le dossier par défaut et non un dossier personnel, autrement cela engendre des étapes
supplémentaires (déclaration d’une variable d’environnement par ligne de commandes etc.).

∗ Vous pouvez vérifier que votre licence est bien installée en tapant la commande gurobi.sh et en
vérifiant qu’une ligne Academic license - for non-commercial use only - expires <date> est écrite
dans le texte aﬃché.

– Sur Windows.

∗ Ouvrez le shell Gurobi en double-cliquant sur l’icône Gurobi9.1.1 ajoutée sur le bureau après
l’installation.

∗ Saisissez la <clé> fournie dans le paragraphe Installation.

∗ Indiquez le nom du répertoire où stocker le fichier de licence ou appuyer sur la touche Entrée du
clavier pour sélectionner l’emplacement par défaut.
