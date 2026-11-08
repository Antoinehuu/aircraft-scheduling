import re
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict

# ============================================
# REFERENCE TABLE (from your results)
# ============================================
reference_data = {
    (10, 15): {"time": (60, 90), "vars": 38000},
    (10, 20): {"time": (100, 100), "vars": 43000},
    (10, 30): {"time": (90, 90), "vars": 47000},
    (20, 15): {"time": (200, 500), "vars": 210000},
    (30, 15): {"time": (3000, 13000), "vars": 500000},
}


paths = ["data.text"] 

datacplex_data = defaultdict(list)
density = None

for path in paths:
    pattern = r"DataCplex_density=([0-9]*\.?[0-9]+)_p=(\d+)_h=(\d+)_test_\d+\.dat.*Time=([\d\.]+)s"
    
    try:
        with open(path, "r") as f:
            for line in f:
                m = re.search(pattern, line)
                if m:
                    d = float(m.group(1))
                    p = int(m.group(2))
                    h = int(m.group(3))
                    t = float(m.group(4))
                    
                    density = d
                    datacplex_data[(p, h)].append(t)
    except FileNotFoundError:
        print(f"⚠️  File {path} not found. Using test data only.")

# ============================================
# DATACPLEX AVERAGE COMPUTATION
# ============================================
datacplex_avg = {}
for (p, h), times in datacplex_data.items():
    datacplex_avg[(p, h)] = np.mean(times)

# ============================================
# VISUALIZATION: COMPARISON
# ============================================
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

# --- CHART 1: Solution times ---
ax1.set_title("Comparison of solution times", fontsize=14, fontweight='bold')

# Reference data
for p in [10, 20, 30]:
    times_ref = []
    hs_ref = []
    for (p_ref, h_ref), data in reference_data.items():
        if p_ref == p:
            hs_ref.append(h_ref)
            t_min, t_max = data["time"]
            times_ref.append(np.mean([t_min, t_max]))
    
    if hs_ref:
        ax1.plot(hs_ref, times_ref, marker='s', linestyle='--', linewidth=2, 
                markersize=8, label=f"Reference p={p}", alpha=0.7)

# DataCplex data
for p in sorted(set([key[0] for key in datacplex_avg])):
    hs_dc = []
    times_dc = []
    for (p_dc, h_dc), t in datacplex_avg.items():
        if p_dc == p:
            hs_dc.append(h_dc)
            times_dc.append(t)
    
    if hs_dc:
        hs_dc_sorted = sorted(zip(hs_dc, times_dc))
        hs_dc = [x[0] for x in hs_dc_sorted]
        times_dc = [x[1] for x in hs_dc_sorted]
        ax1.plot(hs_dc, times_dc, marker='o', linewidth=2.5, markersize=10, 
                label=f"DataCplex (d={density}) p={p}")

ax1.set_xlabel("Horizon (h)", fontsize=12)
ax1.set_ylabel("Solution time (s)", fontsize=12)
ax1.set_yscale("log")
ax1.legend(fontsize=10)
ax1.grid(True, alpha=0.3)

# # --- CHART 2: Number of variables ---
# ax2.set_title("Number of variables as a function of h", fontsize=14, fontweight='bold')

# for p in [10, 20, 30]:
#     hs_ref = []
#     vars_ref = []
#     for (p_ref, h_ref), data in reference_data.items():
#         if p_ref == p:
#             hs_ref.append(h_ref)
#             vars_ref.append(data["vars"])
    
#     if hs_ref:
#         ax2.plot(hs_ref, vars_ref, marker='s', linestyle='--', linewidth=2, 
#                 markersize=8, label=f"Reference p={p}", alpha=0.7)

# ax2.set_xlabel("Horizon (h)", fontsize=12)
# ax2.set_ylabel("Number of variables", fontsize=12)
# ax2.set_yscale("log")
# ax2.legend(fontsize=10)
# ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()

# ============================================
# COMPARISON TABLE
# ============================================
print("\n" + "="*80)
print("DETAILED COMPARISON".center(80))
print("="*80 + "\n")

print(f"{'(p, h)':<10} | {'Reference':<25} | {'DataCplex':<20} | {'Difference':<15}")
print("-"*80)

for (p, h) in sorted(reference_data.keys()):
    t_min, t_max = reference_data[(p, h)]["time"]
    t_ref_avg = (t_min + t_max) / 2
    
    if (p, h) in datacplex_avg:
        t_dc = datacplex_avg[(p, h)]
        diff_pct = ((t_dc - t_ref_avg) / t_ref_avg) * 100
        diff_str = f"{diff_pct:+.1f}%"
        print(f"({p:2d}, {h:2d}) | {t_min:5.0f}–{t_max:5.0f}s (avg {t_ref_avg:6.0f}s) | {t_dc:8.2f}s | {diff_str:>10}")
    else:
        print(f"({p:2d}, {h:2d}) | {t_min:5.0f}–{t_max:5.0f}s (avg {t_ref_avg:6.0f}s) | {'N/A':>20} | {'N/A':>10}")

print("\n" + "="*80)