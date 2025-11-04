import matplotlib.pyplot as plt
import pandas as pd

# Dati sandwich (epoch -> unique_bots)
sandwich_data = {
    808: 29, 809: 33, 810: 34, 811: 36, 812: 34, 813: 31,
    814: 34, 815: 30, 816: 32, 817: 34, 818: 33, 819: 37,
    820: 33, 821: 35, 822: 34, 823: 40, 824: 36, 825: 41,
    826: 35, 827: 33, 828: 35, 829: 38, 830: 35, 831: 33,
    832: 25, 833: 25, 834: 25, 835: 30, 836: 40, 837: 40,
    838: 41, 839: 39, 840: 39, 841: 37, 842: 35, 843: 36,
    844: 37, 845: 34, 846: 33, 847: 34, 848: 32
}

# Dati arbitrage (epoch -> unique_bots)
arbitrage_data = {
    814: 108, 815: 120, 816: 121, 817: 128, 818: 123, 819: 118,
    822: 118, 823: 131, 824: 133, 825: 136, 826: 132, 827: 127,
    828: 127, 829: 134, 830: 127, 831: 129, 832: 143, 833: 143,
    834: 134, 835: 133, 836: 131, 837: 129, 838: 134, 839: 130,
    840: 136, 841: 138, 842: 133, 843: 129, 844: 126, 845: 123,
    846: 127, 847: 120, 848: 118
}

# Creazione DataFrame
df_sandwich = pd.DataFrame(list(sandwich_data.items()), columns=["epoch", "unique_bots_sandwich"])
df_arbitrage = pd.DataFrame(list(arbitrage_data.items()), columns=["epoch", "unique_bots_arbitrage"])

# Merge
df = pd.merge(df_sandwich, df_arbitrage, on="epoch", how="inner").sort_values("epoch")

# Plot con linee (solo epoche comuni)
plt.figure(figsize=(12, 6))
plt.plot(df["epoch"], df["unique_bots_sandwich"], marker="o", label="Sandwich")
plt.plot(df["epoch"], df["unique_bots_arbitrage"], marker="s", label="Arbitrage")

plt.xlabel("Epoca")
plt.ylabel("Numero di bot unici")
plt.legend()
plt.grid(True, linestyle="--", alpha=0.5)
plt.tight_layout()
plt.show()
