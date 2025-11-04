import pandas as pd
import matplotlib.pyplot as plt

# ===========================
# DATI HARD-CODATI
# ===========================

# Epoche per sandwich
epochs_sandwich = [
    808, 809, 810, 811, 812, 813, 814, 815, 816, 817,
    818, 819, 820, 821, 822, 823, 824, 825, 826, 827,
    828, 829, 830, 831, 832, 833, 834, 835, 836, 837,
    838, 839, 840, 841, 842, 843, 844, 845, 846, 847, 848
]

num_sandwiches = [
    2868, 2772, 3530, 2898, 2443, 3094, 3735, 3754, 3834, 5070,
    6316, 7902, 6582, 6189, 2879, 7418, 9180, 8301, 6095, 4707,
    5060, 7076, 4665, 4124, 2706, 4059, 3557, 4075, 3265, 4849,
    5219, 4046, 4429, 4027, 3421, 2263, 1616, 1613, 1863, 2188, 1599
]

num_bots_sandwich = [
    29, 33, 34, 36, 34, 31, 34, 30, 32, 34,
    33, 37, 33, 35, 34, 40, 36, 41, 35, 33,
    35, 38, 35, 33, 25, 25, 25, 30, 40, 40,
    41, 39, 39, 37, 39, 35, 25, 29, 29, 34, 30
]


# Epoche per arbitraggio
epochs_arbitrage = [
    814, 815, 816, 817, 818, 819, 822, 823, 824, 825,
    826, 827, 828, 829, 830, 831, 832, 833, 834, 835,
    836, 837, 838, 839, 840, 841, 842, 843, 844, 845,
    846, 847, 848
]

num_arbitrages = [
    20237, 41597, 45417, 60396, 58006, 27384, 21659, 78477, 92471, 97889,
    79243, 86644, 61820, 67542, 95054, 87952, 115479, 131501, 72220, 113956,
    130480, 93274, 134446, 86974, 101030, 93054, 114334, 120289, 111270, 95984,
    118655, 56311, 50526
]

num_bots_arbitrage = [
    108, 120, 121, 128, 123, 118, 118, 131, 133, 136,
    132, 127, 127, 134, 127, 129, 143, 143, 134, 133,
    138, 122, 133, 130, 132, 135, 133, 132, 122, 122,
    126, 126, 122
]

# ===========================
# CREAZIONE DATAFRAME
# ===========================
df_sandwich = pd.DataFrame({
    "epoch": epochs_sandwich,
    "num_sandwiches": num_sandwiches,
    "num_bots_sandwich": num_bots_sandwich
})

df_arbitrage = pd.DataFrame({
    "epoch": epochs_arbitrage,
    "num_arbitrages": num_arbitrages,
    "num_bots_arbitrage": num_bots_arbitrage
})

# ===========================
# CALCOLO METRICHE
# ===========================
# Sandwich per bot
df_sandwich["sandwich_per_bot"] = df_sandwich["num_sandwiches"] / df_sandwich["num_bots_sandwich"]

# Arbitrage per bot
df_arbitrage["arbitrage_per_bot"] = df_arbitrage["num_arbitrages"] / df_arbitrage["num_bots_arbitrage"]

media_sandwich = df_sandwich["sandwich_per_bot"].mean()
std_sandwich = df_sandwich["sandwich_per_bot"].std()
df_sandwich["coeff_variazione"] = (std_sandwich / media_sandwich) * 100

# === Coefficiente di variazione per arbitrage per bot (su tutte le epoche) ===
media_arbitrage = df_arbitrage["arbitrage_per_bot"].mean()
std_arbitrage = df_arbitrage["arbitrage_per_bot"].std()
df_arbitrage["coeff_variazione"] = (std_arbitrage / media_arbitrage) * 100

print("CV Sandwich per bot (%):", df_sandwich["coeff_variazione"].iloc[0].round(2))
print("CV Arbitrage per bot (%):", df_arbitrage["coeff_variazione"].iloc[0].round(2))

# ===========================
# STAMPA RIEPILOGO STATISTICO
# ===========================
print("=== Sandwich per bot ===")
print(df_sandwich["sandwich_per_bot"].describe().round(2))
print("\n=== Arbitrage per bot ===")
print(df_arbitrage["arbitrage_per_bot"].describe().round(2))
