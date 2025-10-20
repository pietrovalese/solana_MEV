import matplotlib.pyplot as plt
import pandas as pd

# === Dati ===
sandwich_data = {
    808: (0.076820, 0.086621), 809: (0.041109, 0.047682), 810: (0.039598, 0.042279),
    811: (0.037512, 0.037741), 812: (0.029867, 0.030239), 813: (0.040938, 0.036343),
    814: (0.035993, 0.034191), 815: (0.034024, 0.032300), 816: (0.036324, 0.032740),
    817: (0.031805, 0.031066), 818: (0.044554, 0.041428), 819: (0.047772, 0.043667),
    820: (0.038755, 0.036231), 821: (0.034870, 0.030382), 822: (0.029684, 0.027450),
    823: (0.028393, 0.028056), 824: (0.021529, 0.021977), 825: (0.024994, 0.025240),
    826: (0.026007, 0.027032), 827: (0.028913, 0.026632), 828: (0.035079, 0.035996),
    829: (0.033576, 0.033312), 830: (0.029310, 0.030727), 831: (0.046632, 0.048778),
    832: (0.043855, 0.037191), 833: (0.028158, 0.027473), 834: (0.028048, 0.026803),
    835: (0.028106, 0.027855), 836: (0.027685, 0.028625), 837: (0.029846, 0.032041),
    838: (0.028359, 0.026959), 839: (0.037128, 0.036888), 840: (0.029874, 0.029806),
    841: (0.023846, 0.026663)
}

arbitrage_data = {
    814: 0.008824, 815: 0.008901, 816: 0.008292, 817: 0.008210, 818: 0.008649, 819: 0.008652,
    822: 0.009757, 823: 0.009097, 824: 0.008437, 825: 0.008048, 826: 0.008754, 827: 0.008268,
    828: 0.008652, 829: 0.009873, 830: 0.008793, 831: 0.008460, 832: 0.009486, 833: 0.008575,
    834: 0.008854, 835: 0.008772, 836: 0.012118
}

prices = {
    808: 143.6573, 809: 145.3860, 810: 152.3921, 811: 149.7146, 812: 150.8312, 813: 148.9629,
    814: 150.7196, 815: 157.6731, 816: 162.4150, 817: 163.4471, 818: 165.4533, 819: 177.1467,
    820: 179.1362, 821: 197.7344, 822: 188.5888, 823: 184.3600, 824: 187.8235, 825: 180.4692,
    826: 171.4623, 827: 161.6427, 828: 165.5742, 829: 169.2173, 830: 179.3796, 831: 180.3806,
    832: 192.9790, 833: 193.2140, 834: 189.7733, 835: 180.9052, 836: 183.6492, 837: 198.2988,
    838: 200.2935, 839: 199.6048, 840: 209.5862, 841: 202.8252
}

# === Creazione DataFrame ===
df_sandwich = pd.DataFrame(
    [(e, v[0], v[1]) for e, v in sandwich_data.items()],
    columns=["epoch", "mean_revenue_sol_sandwich", "std_revenue_sol_sandwich"]
)
df_arbitrage = pd.DataFrame(list(arbitrage_data.items()), columns=["epoch", "mean_revenue_sol_arbitrage"])
df_prices = pd.DataFrame(list(prices.items()), columns=["epoch", "price_usd"])

# Merge
df = (
    df_sandwich
    .merge(df_arbitrage, on="epoch", how="outer")
    .merge(df_prices, on="epoch", how="left")
    .sort_values("epoch")
)

# === Conversione in USD ===
df["mean_revenue_usd_sandwich"] = df["mean_revenue_sol_sandwich"] * df["price_usd"]
df["mean_revenue_usd_arbitrage"] = df["mean_revenue_sol_arbitrage"] * df["price_usd"]

# === Calcolo statistiche ===
mean_sandwich_usd = df["mean_revenue_usd_sandwich"].mean(skipna=True)
mean_arbitrage_usd = df["mean_revenue_usd_arbitrage"].mean(skipna=True)
std_sandwich_usd = df["mean_revenue_usd_sandwich"].std(skipna=True)
std_arbitrage_usd = df["mean_revenue_usd_arbitrage"].std(skipna=True)

# === Coefficienti di variazione (CV = std / mean * 100) ===
cv_sandwich = std_sandwich_usd / mean_sandwich_usd * 100
cv_arbitrage = std_arbitrage_usd / mean_arbitrage_usd * 100
cv_ratio = cv_sandwich / cv_arbitrage

print(f"\n📊 Deviazione standard del revenue medio (USD):")
print(f"   • Sandwich:  {std_sandwich_usd:.4f}")
print(f"   • Arbitrage: {std_arbitrage_usd:.4f}")

print(f"\n📈 Coefficiente di variazione (CV):")
print(f"   • Sandwich:  {cv_sandwich:.2f}%")
print(f"   • Arbitrage: {cv_arbitrage:.2f}%")

print(f"\n🔸 Rapporto CV (Sandwich / Arbitrage): {cv_ratio:.2f}\n")

# === Plot ===
df_common = df.dropna(subset=["mean_revenue_usd_sandwich", "mean_revenue_usd_arbitrage"])

plt.figure(figsize=(12, 6))
plt.plot(df_common["epoch"], df_common["mean_revenue_usd_sandwich"], '-o', label="Sandwich Revenue (USD)")
plt.plot(df_common["epoch"], df_common["mean_revenue_usd_arbitrage"], '-s', label="Arbitrage Revenue (USD)")

plt.title("Revenue Medio per Epoca (in USD)")
plt.xlabel("Epoca")
plt.ylabel("Revenue Medio [USD]")
plt.legend()
plt.grid(True, linestyle="--", alpha=0.6)
plt.tight_layout()
plt.show()
