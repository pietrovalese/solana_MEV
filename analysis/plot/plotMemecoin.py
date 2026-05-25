import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Dati (esempio: sostituisci con i tuoi reali)
epochs = [814, 815, 816, 817, 818, 819, 822, 823, 824, 825, 826, 827, 828, 829, 830, 831, 832, 833, 834, 835, 836]
sandwich_count = [3735, 3754, 3834, 5070, 6316, 7902, 2879, 7418, 9180, 8301, 6095, 4707, 5060, 7076, 4665, 4124, 2706, 4059, 3557, 4075, 3265]
arbitrage_count = [20237, 41597, 45417, 60396, 58006, 27384, 21659, 78477, 92471, 97889, 79243, 86644, 61820, 67542, 95054, 87952, 115479, 131501, 72220, 113956, 110325]

df = pd.DataFrame({
    "epoch": epochs,
    "sandwich_count": sandwich_count,
    "arbitrage_count": arbitrage_count
})

# Percentuali memecoin (valori globali)
memecoin_sandwich_pct = 54
memecoin_arbitrage_pct = 95

# Imposta la figura con due sottoplot affiancati
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# === Grafico 1: Eventi per epoca (scala logaritmica) ===
x = np.arange(len(df["epoch"]))
width = 0.4

axes[0].bar(x - width/2, df["sandwich_count"], width, label="Sandwich", color="tab:blue")
axes[0].bar(x + width/2, df["arbitrage_count"], width, label="Arbitrage", color="tab:orange")
axes[0].set_yscale("log")
axes[0].set_xlabel("Epoca")
axes[0].set_ylabel("Numero di eventi (log scale)")
axes[0].set_title("Numero di eventi per epoca")
axes[0].set_xticks(x)
axes[0].set_xticklabels(df["epoch"], rotation=45)
axes[0].legend()
axes[0].grid(True, linestyle="--", alpha=0.6, which="both", axis="y")

# === Grafico 2: Percentuale di eventi da memecoin ===
axes[1].bar(["Sandwich", "Arbitrage"],
            [memecoin_sandwich_pct, memecoin_arbitrage_pct],
            color=["tab:blue", "tab:orange"])
axes[1].set_ylim(0, 100)
axes[1].set_ylabel("Percentuale (%)")
axes[1].set_title("Quota di eventi provenienti da memecoin")

# Aggiungi percentuali sopra le barre
for i, val in enumerate([memecoin_sandwich_pct, memecoin_arbitrage_pct]):
    axes[1].text(i, val + 2, f"{val}%", ha='center', va='bottom', fontsize=11, fontweight='bold')

plt.tight_layout()
plt.show()


import matplotlib.pyplot as plt

# Dati
memecoin_sandwich = 54
memecoin_arbitrage = 99

# Colori coerenti con gli altri grafici
colors = {
    "sandwich": ["tab:blue", "lightgray"],
    "arbitrage": ["tab:orange", "lightgray"]
}

# === Primo grafico: Sandwich ===
fig1, ax1 = plt.subplots(figsize=(4, 4))
# Fetta sbiadita (100% anello)
ax1.pie([100], colors=['#1f77b480'], startangle=90, counterclock=False,
        wedgeprops=dict(width=0.4, edgecolor='white'))
# Fetta memecoin sovrapposta più spessa
ax1.pie([memecoin_sandwich, 100 - memecoin_sandwich],
        colors=['#1f77b4', 'none'], startangle=90, counterclock=False,
        wedgeprops=dict(width=0.45, edgecolor='white'))
ax1.text(0, 0, f"{memecoin_sandwich}%", ha='center', va='center', fontsize=18, fontweight='bold')
plt.show()

# === Secondo grafico: Arbitrage ===
fig2, ax2 = plt.subplots(figsize=(4, 4))
# Fetta sbiadita (100% anello)
ax2.pie([100], colors=['#ff7f0e80'], startangle=90, counterclock=False,
        wedgeprops=dict(width=0.4, edgecolor='white'))
# Fetta memecoin sovrapposta più spessa
ax2.pie([memecoin_arbitrage, 100 - memecoin_arbitrage],
        colors=['#ff7f0e', 'none'], startangle=90, counterclock=False,
        wedgeprops=dict(width=0.45, edgecolor='white'))
ax2.text(0, 0, f">{memecoin_arbitrage}%", ha='center', va='center', fontsize=18, fontweight='bold')
plt.show()


