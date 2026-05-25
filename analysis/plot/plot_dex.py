import matplotlib.pyplot as plt

# === Dati Top 10 piattaforme ===
top_platforms = [
    ('Meteora DLMM', 1767105),
    ('PumpSwap', 762562),
    ('HumidiFi', 591573),
    ('Raydium CPMM', 556960),
    ('Orca Whirlpools', 536964),
    ('Raydium CLMM', 512905),
    ('Meteora DAMM v2', 375473),
    ('Raydium V4', 253441),
    ('SolFi', 206902),
    ('TesseraV4', 149507)
]

# === Separiamo nomi e valori ===
platform_names = [p[0] for p in top_platforms]
platform_values = [p[1] for p in top_platforms]

# === Plot a barre ===
fig, ax = plt.subplots(figsize=(12, 6))
bars = ax.bar(platform_names, platform_values, color="#1f77b4")

# Rimuoviamo il riquadro esterno (spines) tranne gli assi principali
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_visible(True)
ax.spines['bottom'].set_visible(True)

ax.set_xlabel("Piattaforma")
ax.set_ylabel(r"Occorrenze ($10^6$)")
ax.set_xticklabels(platform_names, rotation=45, ha='right')
ax.grid(axis='y', linestyle='--', alpha=0.6)

plt.tight_layout()
plt.show()
