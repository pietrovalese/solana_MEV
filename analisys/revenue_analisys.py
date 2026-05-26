import pandas as pd
import matplotlib.pyplot as plt


def plot_compare_sandwich_arbitrage_usd(df_sandwich, df_arbitrage, prices):
    """
    Plot a stacked bar chart comparing sandwich and arbitrage revenue per epoch,
    overlaid with the average SOL/USD price for each epoch.

    The two input DataFrames must share an epoch-based index and contain columns
    ``sum_revenue_SOL`` and ``sum_revenue_USD``. Only epochs present in both
    DataFrames are included in the plot and summary.

    Args:
        df_sandwich (pd.DataFrame): Per-epoch sandwich revenue with columns
            ``sum_revenue_SOL`` and ``sum_revenue_USD``.
        df_arbitrage (pd.DataFrame): Per-epoch arbitrage revenue with columns
            ``sum_revenue_SOL`` and ``sum_revenue_USD``.
        prices (dict): Mapping of epoch number to average SOL/USD price.
    """
    df_sandwich = df_sandwich.rename(columns={
        "sum_revenue_SOL": "sum_revenue_SOL_sandwich",
        "sum_revenue_USD": "sum_revenue_USD_sandwich"
    })
    df_arbitrage = df_arbitrage.rename(columns={
        "sum_revenue_SOL": "sum_revenue_SOL_arbitrage",
        "sum_revenue_USD": "sum_revenue_USD_arbitrage"
    })

    # Keep only epochs present in both DataFrames
    common_epochs = df_sandwich.index.intersection(df_arbitrage.index)
    df_merged = df_sandwich.loc[common_epochs].join(df_arbitrage.loc[common_epochs])

    df_merged["price_usd"] = [prices[e] for e in df_merged.index]

    df_merged["sum_total_USD"] = (
        df_merged["sum_revenue_USD_sandwich"] + df_merged["sum_revenue_USD_arbitrage"]
    )
    df_merged["sum_total_SOL"] = (
        df_merged["sum_revenue_SOL_sandwich"] + df_merged["sum_revenue_SOL_arbitrage"]
    )

    # Stacked bar chart (sandwich + arbitrage) with SOL price on secondary axis
    fig, ax1 = plt.subplots(figsize=(16, 8))

    ax1.bar(df_merged.index.astype(str),
            df_merged["sum_revenue_USD_sandwich"],
            label="Sandwich", color="steelblue")

    ax1.bar(df_merged.index.astype(str),
            df_merged["sum_revenue_USD_arbitrage"],
            bottom=df_merged["sum_revenue_USD_sandwich"],
            label="Arbitrage", color="orange")

    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Revenue (USD)")
    ax1.tick_params(axis='x', rotation=45)

    ax2 = ax1.twinx()
    ax2.plot(df_merged.index.astype(str), df_merged["price_usd"],
             color="green", linewidth=2.5, marker="o", label="SOL Price (USD)")
    ax2.set_ylabel("SOL Price (USD)", color="green")
    ax2.tick_params(axis='y', labelcolor='green')

    # Combined legend from both axes
    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(handles1 + handles2, labels1 + labels2, loc="upper left")

    plt.tight_layout()
    plt.show()

    # Detailed per-epoch table
    print("\nREVENUE PER EPOCH (common epochs only, USD):\n")
    print(df_merged[[
        "sum_revenue_USD_sandwich", "sum_revenue_USD_arbitrage", "sum_total_USD",
        "sum_revenue_SOL_sandwich", "sum_revenue_SOL_arbitrage", "sum_total_SOL",
        "price_usd"
    ]].round(2))

    # Grand totals over common epochs
    total_usd_sandwich  = df_merged["sum_revenue_USD_sandwich"].sum()
    total_usd_arbitrage = df_merged["sum_revenue_USD_arbitrage"].sum()
    total_usd           = df_merged["sum_total_USD"].sum()

    total_sol_sandwich  = df_merged["sum_revenue_SOL_sandwich"].sum()
    total_sol_arbitrage = df_merged["sum_revenue_SOL_arbitrage"].sum()
    total_sol           = df_merged["sum_total_SOL"].sum()

    print("\nGRAND TOTAL (common epochs only):")
    print(f"  Sandwich:  {total_usd_sandwich:,.2f} USD  ({total_sol_sandwich:,.3f} SOL)")
    print(f"  Arbitrage: {total_usd_arbitrage:,.2f} USD  ({total_sol_arbitrage:,.3f} SOL)")
    print("-" * 60)
    print(f"  TOTAL:     {total_usd:,.2f} USD  ({total_sol:,.3f} SOL)")


# =======================
# === DATA ===
# =======================

# Average SOL/USD price per epoch
prices = {
    814: 143.66, 815: 145.39, 816: 152.39, 817: 149.71, 818: 150.83, 819: 148.96,
    820: 150.72, 821: 157.67, 822: 162.41, 823: 163.45, 824: 165.45, 825: 177.15,
    826: 179.14, 827: 197.73, 828: 188.59, 829: 184.36, 830: 187.82, 831: 180.47,
    832: 171.46, 833: 161.64, 834: 165.57, 835: 169.22, 836: 179.38, 837: 180.38,
    838: 192.98, 839: 193.21, 840: 189.77, 841: 180.91, 842: 183.65, 843: 198.30,
    844: 200.29, 845: 199.60, 846: 209.59, 847: 202.83, 848: 202.46
}

# Per-epoch sandwich revenue (epochs 808–848)
df_sum_rev_sandwich = pd.DataFrame({
    808: [198.040735,  36147.695013],
    809: [98.619650,   18000.705996],
    810: [119.664515,  21841.952937],
    811: [93.704762,   17103.608246],
    812: [61.914574,   11301.054566],
    813: [104.105854,  19002.083931],
    814: [111.145070,  20286.927876],
    815: [109.794980,  20040.500542],
    816: [120.595934,  22011.961506],
    817: [137.938198,  25177.385544],
    818: [242.238376,  44214.938671],
    819: [325.565728,  59424.394094],
    820: [224.935191,  41056.647719],
    821: [185.716585,  33898.210338],
    822: [72.667021,   13263.661808],
    823: [180.548646,  32954.924203],
    824: [169.799755,  30992.966115],
    825: [181.230409,  33079.364061],
    826: [138.511499,  25282.028111],
    827: [117.270446,  21404.971633],
    828: [155.399728,  28364.578647],
    829: [207.665831,  37904.530873],
    830: [119.993599,  21902.019402],
    831: [171.185343,  31245.872593],
    832: [105.340848,  19227.503124],
    833: [97.960039,   17880.309398],
    834: [87.398939,   15952.628082],
    835: [100.198978,  18288.975282],
    836: [76.909309,   14037.991902],
    837: [120.818537,  22052.592496],
    838: [129.403084,  23619.500349],
    839: [129.837322,  23698.760340],
    840: [107.457846,  19613.911539],
    841: [76.354756,   13936.771260],
    842: [75.615037,   13801.753058],
    843: [82.977055,   15145.516889],
    844: [70.780325,   12919.289509],
    845: [45.083293,   8228.898660],
    846: [75.458257,   13773.136445],
    847: [103.047877,  18808.975069],
    848: [57.214734,   10443.208889]
}, index=["sum_revenue_SOL", "sum_revenue_USD"]).T

# Per-epoch arbitrage revenue (epochs 814–848, some epochs missing)
df_sum_rev_arbitrage = pd.DataFrame({
    814: [179.358911,   31603.830133],
    815: [374.860926,   66052.146281],
    816: [378.123760,   66627.071991],
    817: [498.404933,   87821.144466],
    818: [503.732700,   88759.920519],
    819: [238.135066,   41960.447562],
    822: [235.058513,   41418.345287],
    823: [784.278865,  138193.390566],
    824: [853.165191,  150331.464600],
    825: [849.186735,  149630.443114],
    826: [773.641171,  136318.981981],
    827: [776.512086,  136824.849884],
    828: [573.316250,  101020.848599],
    829: [715.039025,  125993.025834],
    830: [885.069753,  155953.188954],
    831: [789.403876,  139096.440043],
    832: [1216.708316, 214389.364584],
    833: [1268.046555, 223435.388401],
    834: [700.584122,  123446.008169],
    835: [1133.262769, 199685.891591],
    836: [1770.447021, 311960.563412],
    837: [1993.791964, 351314.926191],
    838: [1338.029820, 235766.747927],
    839: [846.383298,  149136.465235],
    840: [1118.620093, 197105.787598],
    841: [1009.378765, 177856.984505],
    842: [1382.750839, 243646.788517],
    843: [1401.287903, 246913.100841],
    844: [1291.018171, 227483.088366],
    845: [863.399533,  152134.800866],
    846: [1648.215431, 290422.818980],
    847: [610.193998,  107518.870263],
    848: [969.864383,  170894.376308]
}, index=["sum_revenue_SOL", "sum_revenue_USD"]).T

# =======================
# === EXECUTION ===
# =======================

plot_compare_sandwich_arbitrage_usd(df_sum_rev_sandwich, df_sum_rev_arbitrage, prices)