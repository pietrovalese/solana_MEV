import matplotlib.pyplot as plt
import numpy as np

# === Dati ===
labels = ["Sandwich", "Arbitraggio"]
values = [25079.15, 119920.85]
colors = ["#1f77b4", "#ff7f0e"]

# === Calcolo raggio proporzionale all’area ===
max_value = max(values)
scale = 1.5 / np.sqrt(max_value)  # scala per dimensioni visive
radii = [np.sqrt(v) * scale for v in values]

# === Posizioni: più ravvicinate ===
positions = [-1.2, 1.5]  # ridotto il gap

# === Plot ===
fig, ax = plt.subplots(figsize=(10, 6))

for x, r, color, label, val in zip(positions, radii, colors, labels, values):
    # Disegna la bolla
    bubble = plt.Circle((x, 0), r, color=color, alpha=0.85)
    ax.add_artist(bubble)
    # Testo centrato dentro la bolla
    ax.text(x, 0, f"{label}\n${val:,.0f}", 
            ha='center', va='center', color='white',
            fontsize=18, fontweight='bold')

# === Pulizia layout ===
ax.set_xlim(-3, 3.5)
ax.set_ylim(-2, 2)
ax.set_aspect('equal')
ax.axis('off')

plt.tight_layout()
plt.show()
