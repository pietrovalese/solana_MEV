import pandas as pd
import matplotlib.pyplot as plt

def plot_compare_sandwich_arbitrage(df_sandwich, df_arbitrage):
    # Merge sulle epoche comuni
    df_merged = df_sandwich.join(df_arbitrage, lsuffix="_sandwich", rsuffix="_arbitrage", how="inner")
    
    # Calcolo totale per epoca
    df_merged["sum_total_SOL"] = df_merged["sum_revenue_SOL_sandwich"] + df_merged["sum_revenue_SOL_arbitrage"]
    df_merged["sum_total_USD"] = df_merged["sum_revenue_USD_sandwich"] + df_merged["sum_revenue_USD_arbitrage"]

    # Plot stacked bar
    plt.figure(figsize=(14, 7))
    plt.bar(df_merged.index.astype(str), df_merged["sum_revenue_SOL_sandwich"], label="Sandwich", color="steelblue")
    plt.bar(df_merged.index.astype(str), df_merged["sum_revenue_SOL_arbitrage"],
            bottom=df_merged["sum_revenue_SOL_sandwich"], label="Arbitrage", color="orange")

    plt.title("Revenue per Epoca")
    plt.xlabel("Epoca")
    plt.ylabel("Revenue (SOL)")
    plt.xticks(rotation=45)
    plt.legend()
    plt.tight_layout()
    plt.show()

    # Stampa tabella con i valori
    print("\n🔹 REVENUE PER EPOCA (Sandwich + Arbitrage):")
    print(df_merged[[
        "sum_revenue_SOL_sandwich", "sum_revenue_SOL_arbitrage", "sum_total_SOL",
        "sum_revenue_USD_sandwich", "sum_revenue_USD_arbitrage", "sum_total_USD"
    ]])

    # Stampa totale complessivo
    total_sol = df_merged["sum_total_SOL"].sum()
    total_usd = df_merged["sum_total_USD"].sum()
    print("\n🎯 SOMMA TOTALE SU TUTTE LE EPOCHE COMUNI:")
    print(f"→ {total_sol:.6f} SOL")
    print(f"→ ≈ {total_usd:.2f} USD")

# ================================
# ESEMPIO USO (con i tuoi dati)
# ================================

# DataFrame dei sandwich
df_sum_rev_sandwich = pd.DataFrame({
    808: [198.040735, 34742.733835],
    809: [98.619650, 17301.068216],
    810: [119.664515, 20993.016486],
    811: [93.704762, 16438.838181],
    812: [61.914574, 10861.813754],
    813: [104.105854, 18263.525353],
    814: [111.145070, 19498.430959],
    815: [109.794980, 19261.581575],
    816: [120.595934, 21156.417291],
    817: [137.938198, 24198.810030],
    818: [242.238376, 42496.425989],
    819: [325.565728, 57114.731841],
    820: [224.935191, 39460.889093],
    821: [185.716585, 32580.680424],
    822: [72.667021, 12748.139867],
    823: [180.548646, 31674.057218],
    824: [169.799755, 29788.355029],
    825: [181.230409, 31793.660443],
    826: [138.511499, 24299.385429],
    827: [117.270446, 20573.019440],
    828: [155.399728, 27262.125730],
    829: [207.665831, 36431.286333],
    830: [119.993599, 21050.748333],
    831: [171.185343, 30031.431729],
    832: [105.340848, 18480.183124],
    833: [97.960039, 17185.351101],
    834: [87.398939, 15332.593440],
    835: [100.198978, 17578.133270],
    836: [76.909309, 13492.373886],
    837: [120.818537, 21195.469066],
    838: [129.403084, 22701.475535],
    839: [129.837322, 22777.654908],
    840: [107.457846, 18851.572910],
    841: [76.354756, 13395.087411]
}, index=["sum_revenue_SOL", "sum_revenue_USD"]).T

# DataFrame degli arbitraggi
df_sum_rev_arbitrage = pd.DataFrame({
    814: [178.441274, 30483.235670],
    815: [369.452237, 63113.759257],
    816: [376.349563, 64292.033808],
    817: [495.412898, 84631.698500],
    818: [501.328648, 85642.289823],
    819: [236.711205, 40437.524814],
    822: [207.177308, 35392.230516],
    823: [701.536022, 119843.842184],
    824: [767.370590, 131090.403092],
    825: [777.053757, 132744.584632],
    826: [679.717266, 116116.530247],
    827: [705.868647, 120583.987201],
    828: [528.144286, 90223.222233],
    829: [658.411150, 112476.792909],
    830: [827.158397, 141303.991919],
    831: [736.170128, 125760.408299],
    832: [1074.197665, 183505.866148],
    833: [1103.017711, 188429.212886],
    834: [628.716493, 107404.035945],
    835: [976.197372, 166764.414142],
    836: [1294.878913, 221204.983290]
}, index=["sum_revenue_SOL", "sum_revenue_USD"]).T

# Eseguo la funzione
plot_compare_sandwich_arbitrage(df_sum_rev_sandwich, df_sum_rev_arbitrage)
