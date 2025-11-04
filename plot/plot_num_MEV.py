import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# === Numero di SANDWICH per epoca ===
sandwich_counts = {
    808: 2868, 809: 2772, 810: 3530, 811: 2898, 812: 2443, 813: 3094,
    814: 3735, 815: 3754, 816: 3834, 817: 5070, 818: 6316, 819: 7902,
    820: 6582, 821: 6189, 822: 2879, 823: 7418, 824: 9180, 825: 8301,
    826: 6095, 827: 4707, 828: 5060, 829: 7076, 830: 4665, 831: 4124,
    832: 2706, 833: 4059, 834: 3557, 835: 4075, 836: 3265, 837: 4849,
    838: 5219, 839: 4046, 840: 4429, 841: 4027, 842: 3421, 843: 2263,
    844: 1616, 845: 1613, 846: 1863, 847: 2188, 848: 1599
}

# === Numero di ARBITRAGGI per epoca ===
arbitrage_counts = {
    814: 20237, 815: 41597, 816: 45417, 817: 60396, 818: 58006, 819: 27384,
    822: 21659, 823: 78477, 824: 92471, 825: 97889, 826: 79243, 827: 86644,
    828: 61820, 829: 67542, 830: 95054, 831: 87952, 832: 115479, 833: 131501,
    834: 72220, 835: 113956, 836: 130480, 837: 93274, 838: 134446, 839: 86974,
    840: 101030, 841: 93054, 842: 114334, 843: 120289, 844: 111270, 845: 95984,
    846: 118655, 847: 56311, 848: 50526
}

# === Creazione DataFrame ===
df_sandwich = pd.DataFrame(list(sandwich_counts.items()), columns=["epoch", "sandwich_count"])
df_arbitrage = pd.DataFrame(list(arbitrage_counts.items()), columns=["epoch", "arbitrage_count"])

# Merge per avere solo le epoche in comune
df = df_sandwich.merge(df_arbitrage, on="epoch", how="inner").sort_values("epoch")

# === Calcolo medie geometriche (adatte a scala log) ===
mean_sandwich_log = np.exp(np.mean(np.log(df["sandwich_count"])))
mean_arbitrage_log = np.exp(np.mean(np.log(df["arbitrage_count"])))

# === Plot con scala logaritmica e linee medie geometriche ===
x = np.arange(len(df["epoch"]))
width = 0.4

fig, ax = plt.subplots(figsize=(12, 6))
ax.bar(x - width/2, df["sandwich_count"], width, label="Sandwich count", color="#1f77b4")
ax.bar(x + width/2, df["arbitrage_count"], width, label="Arbitrage count", color="#ff7f0e")

# Scala logaritmica sull'asse y
ax.set_yscale("log")

# Linee orizzontali delle medie geometriche
ax.axhline(mean_sandwich_log, color="#0b3d91", linestyle="--", linewidth=2)
ax.axhline(mean_arbitrage_log, color="#b35400", linestyle="--", linewidth=2)

# Etichette a lato asse y (a sinistra)
ax.text(-1.63, mean_sandwich_log, f"{mean_sandwich_log:.0f}", color="#0b3d91",
        va='center', ha='right', fontweight='bold')
ax.text(-1.63, mean_arbitrage_log, f"{mean_arbitrage_log:.0f}", color="#b35400",
        va='center', ha='right', fontweight='bold')

ax.set_xlabel("Epoca")
ax.set_ylabel("Numero di eventi")
ax.set_xticks(x)
ax.set_xticklabels(df["epoch"], rotation=45)
ax.legend()
ax.grid(True, linestyle="--", alpha=0.6, which="both", axis="y")
plt.tight_layout()
plt.show()
