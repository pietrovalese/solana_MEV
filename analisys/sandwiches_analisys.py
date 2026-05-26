import json
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import ccxt
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.patches import Patch
from tqdm import tqdm


# =======================
# === CONFIGURATION ===
# =======================

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SANDWICH_PATH  = os.path.join(BASE_DIR, "sandwiches_annotated.jsonl")
MEME_LIST_PATH = os.path.join(BASE_DIR, "meme_and_shitcoins_list.csv")

# Solana epoch configuration
EPOCH_808_START  = datetime(2025, 6, 25, 6, 58, 38)
EPOCH_DURATION_H = 48
START_EPOCH      = 808
END_EPOCH        = 848

memecoin_df      = pd.read_csv(MEME_LIST_PATH)
memecoin_tickers = set(memecoin_df["Ticker"].dropna().str.upper())

exchange = ccxt.binance()


# =======================
# === UTILITY FUNCTIONS ===
# =======================

def remove_outliers_iqr(data: np.ndarray, multiplier: float = 1.5) -> np.ndarray:
    """
    Remove outliers from an array using the IQR method.

    Values outside [Q1 - multiplier*IQR, Q3 + multiplier*IQR] are discarded.

    Args:
        data (np.ndarray): Input array of numeric values.
        multiplier (float): IQR multiplier for the outlier fence. Defaults to 1.5.

    Returns:
        np.ndarray: Filtered array, or an empty array if the input is empty.
    """
    if len(data) == 0:
        return np.array([])
    data = np.array(data)
    Q1, Q3 = np.percentile(data, 25), np.percentile(data, 75)
    IQR = Q3 - Q1
    return data[(data >= Q1 - multiplier * IQR) & (data <= Q3 + multiplier * IQR)]


def extract_fee_info(bot: dict) -> dict:
    """
    Extract compute units and fee breakdown from a bot's Details field.

    Args:
        bot (dict): A bot entry from a sandwich record (bot1 or bot2).

    Returns:
        dict: Keys: compute_units, fee_total, priority_fee, transaction_fee, fee_per_cu.
              Missing values are returned as np.nan.
    """
    det = bot.get("Details", {})
    fee = det.get("fee", {})
    return {
        "compute_units":   det.get("compute_units_consumed", np.nan),
        "fee_total":       fee.get("total_fee", np.nan),
        "priority_fee":    fee.get("priority_fee", np.nan),
        "transaction_fee": fee.get("transaction_fee", np.nan),
        "fee_per_cu":      fee.get("fee_per_cu", np.nan),
    }


def extract_corr_metrics(data: dict) -> dict:
    """
    Extract bot fee metrics and net SOL revenue from a sandwich record.

    Revenue is computed as value_end - value_start - fee1 - fee2 when
    token_start is SOL; otherwise revenue is set to np.nan.

    Args:
        data (dict): A single parsed sandwich record.

    Returns:
        dict: Keys: b1_cu, b1_fee_total, b1_priority_fee, b1_fee_per_cu,
              b2_cu, b2_fee_total, b2_priority_fee, b2_fee_per_cu, revenue.
    """
    b1 = data.get("bot1", {})
    b2 = data.get("bot2", {})
    b1_metrics = extract_fee_info(b1)
    b2_metrics = extract_fee_info(b2)

    try:
        if b1.get("token_start", "").lower() == "sol":
            value_start = float(b1.get("value_start", "0").replace(",", ""))
            value_end   = float(b2.get("value_end",   "0").replace(",", ""))
            fee1        = b1_metrics["fee_total"] / 1e9
            fee2        = b2_metrics["fee_total"] / 1e9
            revenue     = value_end - value_start - fee1 - fee2
        else:
            revenue = np.nan
    except Exception:
        revenue = np.nan

    return {
        "b1_cu":           b1_metrics["compute_units"],
        "b1_fee_total":    b1_metrics["fee_total"],
        "b1_priority_fee": b1_metrics["priority_fee"],
        "b1_fee_per_cu":   b1_metrics["fee_per_cu"],
        "b2_cu":           b2_metrics["compute_units"],
        "b2_fee_total":    b2_metrics["fee_total"],
        "b2_priority_fee": b2_metrics["priority_fee"],
        "b2_fee_per_cu":   b2_metrics["fee_per_cu"],
        "revenue":         revenue,
    }


def get_epoch_average_price(epoch_start: datetime, epoch_end: datetime) -> float | None:
    """
    Fetch the average SOL/USDT closing price over a 48-hour epoch window from Binance.

    Args:
        epoch_start (datetime): Start of the epoch.
        epoch_end (datetime): End of the epoch.

    Returns:
        float or None: Mean closing price over the epoch, or None on failure.
    """
    try:
        start_ms = int(epoch_start.timestamp() * 1000)
        end_ms   = int(epoch_end.timestamp() * 1000)
        ohlc     = exchange.fetch_ohlcv("SOL/USDT", timeframe="1h", since=start_ms, limit=48)
        if ohlc:
            df_period = pd.DataFrame(ohlc, columns=["timestamp", "open", "high", "low", "close", "vol"])
            df_period = df_period[df_period["timestamp"] <= end_ms]
            if not df_period.empty:
                return df_period["close"].mean()
        return None
    except Exception as e:
        print(f"Error fetching price data: {e}")
        return None


# =======================
# === DATA COLLECTION ===
# =======================

total_sol_sandwich = 0
memecoin_sandwich  = 0
bot_counter        = Counter()
token_counter      = Counter()
epoch_counter      = Counter()
all_bots           = set()
revenue_data       = {}
value_end_array    = []
corr_records       = []
unique_bots_per_epoch = defaultdict(set)

with open(SANDWICH_PATH, "r") as file:
    for line in tqdm(file):
        data     = json.loads(line)
        bot_name  = data["bot1"]["bot"].split(":")[-1].strip()
        token_end = data["bot1"]["token_end"]

        bot_counter[bot_name] += 1
        all_bots.add(bot_name)

        if token_end.lower() != "sol":
            token_counter[token_end] += 1
            total_sol_sandwich += 1
            if token_end.upper() in memecoin_tickers:
                memecoin_sandwich += 1

        corr_records.append(extract_corr_metrics(data))

        try:
            epoch = data["bot1"]["Details"]["epoch"]
            epoch_counter[epoch] += 1
            unique_bots_per_epoch[epoch].add(bot_name)

            if data["bot1"]["token_start"].lower() == "sol":
                value_start = float(data["bot1"]["value_start"].replace(",", ""))
                value_end   = float(data["bot2"]["value_end"].replace(",", ""))
                value_end_array.append(value_end)
                fee1    = data["bot1"]["Details"]["fee"]["total_fee"] / 1e9
                fee2    = data["bot2"]["Details"]["fee"]["total_fee"] / 1e9
                revenue = value_end - value_start - fee1 - fee2
                revenue_data.setdefault(epoch, []).append(revenue)

        except (KeyError, ValueError, TypeError):
            continue

# =======================
# === DATA ANALYSIS ===
# =======================

# Memecoin share
non_meme_sandwich = total_sol_sandwich - memecoin_sandwich
percent_meme      = memecoin_sandwich / total_sol_sandwich * 100 if total_sol_sandwich else 0
percent_non_meme  = 100 - percent_meme

# Top token classification (meme vs non-meme)
top_tokens  = token_counter.most_common(10)
meme_status = [
    (token, count, "Meme" if token.upper() in memecoin_tickers else "Non-Meme")
    for token, count in top_tokens
]
meme_df = pd.DataFrame(meme_status, columns=["Token", "Count", "Type"])

# Epoch filtering via IQR on sandwich counts
epoch_df      = pd.DataFrame.from_dict(epoch_counter, orient="index", columns=["count"])
Q1, Q2        = epoch_df["count"].quantile(0.25), epoch_df["count"].quantile(0.50)
threshold     = Q2 - Q1
valid_epochs  = epoch_df[epoch_df["count"] >= threshold].index
epoch_df_filtered = epoch_df.loc[valid_epochs].sort_index()

# Revenue statistics per epoch with outlier removal
rev_stats       = {}
outlier_summary = {}

print("OUTLIER REMOVAL PER EPOCH:")
for epoch, values in revenue_data.items():
    if epoch in valid_epochs:
        rev_array       = np.array(values)
        rev_array_clean = remove_outliers_iqr(rev_array, multiplier=1.5)

        if len(rev_array_clean) > 0:
            rev_stats[epoch] = {
                "mean_revenue": rev_array_clean.mean(),
                "std_revenue":  rev_array_clean.std(),
                "min_revenue":  rev_array_clean.min(),
                "max_revenue":  rev_array_clean.max(),
            }
            outliers_removed = len(rev_array) - len(rev_array_clean)
            outlier_pct      = outliers_removed / len(rev_array) * 100
            outlier_summary[epoch] = {
                "original_count":     len(rev_array),
                "clean_count":        len(rev_array_clean),
                "outliers_removed":   outliers_removed,
                "outlier_percentage": outlier_pct,
            }
            print(f"Epoch {epoch}: {len(rev_array)} -> {len(rev_array_clean)} "
                  f"({outlier_pct:.1f}% outliers removed)")
        else:
            print(f"Epoch {epoch}: all values were outliers, skipped.")

rev_df = pd.DataFrame.from_dict(rev_stats, orient="index").sort_index()

# SOL price per epoch via Binance OHLCV
print(f"Fetching SOL price data from epoch {START_EPOCH} to {END_EPOCH}")

epoch_price_data = []
for epoch in range(START_EPOCH, END_EPOCH + 1):
    hours_from_start = (epoch - START_EPOCH) * EPOCH_DURATION_H
    epoch_start      = EPOCH_808_START + timedelta(hours=hours_from_start)
    epoch_end        = epoch_start + timedelta(hours=EPOCH_DURATION_H)

    print(f"Fetching epoch {epoch} "
          f"({epoch_start.strftime('%Y-%m-%d %H:%M')} - {epoch_end.strftime('%Y-%m-%d %H:%M')})")

    avg_price = get_epoch_average_price(epoch_start, epoch_end)
    if avg_price is not None:
        epoch_price_data.append({
            "epoch":         epoch,
            "start_date":    epoch_start,
            "end_date":      epoch_end,
            "avg_price_usd": avg_price,
        })
        print(f"  Epoch {epoch}: avg price ${avg_price:.4f}")
    else:
        print(f"  No data available for epoch {epoch}")

    time.sleep(0.1)  # Avoid hitting Binance rate limits

df_sol_epochs      = pd.DataFrame(epoch_price_data)
sol_price_usd_mean = df_sol_epochs["avg_price_usd"].mean()

# USD revenue statistics
rev_usd_stats = (rev_df * sol_price_usd_mean).rename(columns={
    "mean_revenue": "mean_revenue_usd",
    "std_revenue":  "std_revenue_usd",
    "min_revenue":  "min_revenue_usd",
    "max_revenue":  "max_revenue_usd",
})
combined_rev_df = rev_df.join(rev_usd_stats)

# Global mean revenue across all filtered epochs
all_revenues_clean = remove_outliers_iqr(
    [v for e in valid_epochs for v in revenue_data.get(e, [])],
    multiplier=1.5
)
mean_revenue_sol = np.mean(all_revenues_clean)
mean_revenue_usd = mean_revenue_sol * sol_price_usd_mean

# Unique bots per epoch
unique_bot_counts = {epoch: len(bots) for epoch, bots in unique_bots_per_epoch.items()}
df_unique_bots = pd.DataFrame.from_dict(
    unique_bot_counts, orient="index", columns=["unique_bots"]
).sort_index()

# Pearson and Spearman correlation matrices
df_corr       = pd.DataFrame(corr_records).dropna(subset=["revenue"])
pearson_corr  = df_corr.corr(method="pearson")
spearman_corr = df_corr.corr(method="spearman")


# =======================
# === PLOTTING ===
# =======================

def plot_pie():
    """Plot a pie chart showing the split between meme-coin and non-meme-coin sandwiches."""
    plt.figure(figsize=(6, 6))
    plt.pie(
        [memecoin_sandwich, non_meme_sandwich],
        labels=["Meme Coin", "Non-Meme Coin"],
        colors=["orange", "lightgray"],
        autopct="%1.1f%%",
        startangle=90,
    )
    plt.title("Sandwich token distribution")
    plt.axis("equal")
    plt.tight_layout()
    plt.show()


def plot_top_tokens():
    """Plot a bar chart of the top 10 sandwich tokens, colored by meme/non-meme classification."""
    colors = meme_df["Type"].map({"Meme": "orange", "Non-Meme": "gray"})
    plt.figure(figsize=(10, 6))
    plt.bar(meme_df["Token"], meme_df["Count"], color=colors)
    plt.title("Top 10 tokens: Meme vs Non-Meme")
    plt.xlabel("Token")
    plt.ylabel("Count")
    plt.xticks(rotation=45)
    plt.legend(handles=[
        Patch(facecolor="orange", label="Memecoin"),
        Patch(facecolor="gray",   label="Non-Memecoin"),
    ])
    plt.tight_layout()
    plt.show()


def plot_epoch_counts():
    """Plot a bar chart of sandwich counts per epoch (IQR-filtered epochs only)."""
    epoch_df_filtered.plot(kind="bar", figsize=(12, 6), legend=False)
    plt.title("Number of sandwiches per epoch")
    plt.xlabel("Epoch")
    plt.ylabel("Count")
    plt.tight_layout()
    plt.show()


def plot_unique_bots():
    """Plot a bar chart of unique bot counts per epoch."""
    plt.figure(figsize=(12, 6))
    plt.bar(df_unique_bots.index.astype(str), df_unique_bots["unique_bots"], color="purple")
    plt.title("Unique bots per epoch")
    plt.xlabel("Epoch")
    plt.ylabel("Unique bots")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()


def _add_sol_price_axis(ax1: plt.Axes) -> plt.Axes:
    """
    Add a secondary y-axis with the SOL/USD price line to an existing axes object.

    Args:
        ax1 (plt.Axes): The primary axes to which the secondary axis is twinned.

    Returns:
        plt.Axes: The secondary axes carrying the SOL price line.
    """
    ax2 = ax1.twinx()
    ax2.set_ylabel("Average SOL price (USD)", color="orange")
    ax2.plot(
        df_sol_epochs["epoch"].astype(str).to_numpy(),
        df_sol_epochs["avg_price_usd"].to_numpy(),
        color="orange", marker="o", linewidth=2, markersize=4, label="SOL price",
    )
    ax2.tick_params(axis="y", labelcolor="orange")
    return ax2


def plot_revenue_and_price():
    """Plot mean revenue per epoch (bars) overlaid with the SOL/USD price (line) on a dual axis."""
    fig, ax1 = plt.subplots(figsize=(14, 6))
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Mean revenue (SOL)", color="green")
    ax1.bar(rev_df.index.astype(str), rev_df["mean_revenue"],
            color="green", alpha=0.6, label="Mean revenue")
    ax1.tick_params(axis="y", labelcolor="green")
    ax1.tick_params(axis="x", rotation=45)

    ax2 = _add_sol_price_axis(ax1)
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    plt.tight_layout()
    plt.show()


def plot_and_print_sum_revenue_per_epoch():
    """
    Plot total revenue per epoch (bars) with the SOL price (line) and print a summary table.

    Outliers are removed from each epoch's revenue list before summing.
    """
    sum_rev = {
        epoch: {
            "sum_revenue_SOL": clean.sum(),
            "sum_revenue_USD": clean.sum() * sol_price_usd_mean,
        }
        for epoch, values in revenue_data.items()
        if epoch in valid_epochs
        for clean in [remove_outliers_iqr(values, multiplier=1.5)]
        if len(clean) > 0
    }
    df_sum_rev = pd.DataFrame.from_dict(sum_rev, orient="index").sort_index()

    fig, ax1 = plt.subplots(figsize=(14, 6))
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Total revenue (SOL)", color="darkblue")
    ax1.bar(df_sum_rev.index.astype(str), df_sum_rev["sum_revenue_SOL"],
            color="darkblue", alpha=0.6, label="Total revenue")
    ax1.tick_params(axis="y", labelcolor="darkblue")
    ax1.tick_params(axis="x", rotation=45)

    ax2 = _add_sol_price_axis(ax1)
    ax2.grid(True, alpha=0.3)
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    plt.tight_layout()
    plt.show()

    print("\nTOTAL REVENUE PER EPOCH (outliers removed):")
    print(df_sum_rev)

    total_sol = df_sum_rev["sum_revenue_SOL"].sum()
    total_usd = df_sum_rev["sum_revenue_USD"].sum()
    print("\nGRAND TOTAL REVENUE ACROSS ALL EPOCHS:")
    print(f"  {total_sol:.6f} SOL")
    print(f"  ~{total_usd:.2f} USD (at avg price {sol_price_usd_mean:.2f} USD/SOL)")


def plot_sandwiches_per_epoch():
    """
    Plot a histogram of sandwich counts per epoch (IQR-filtered) and print summary statistics.
    """
    plt.figure(figsize=(14, 6))
    plt.bar(epoch_df_filtered.index.astype(str), epoch_df_filtered["count"],
            color="coral", alpha=0.7)
    plt.xlabel("Epoch", fontsize=12)
    plt.ylabel("Number of sandwiches", fontsize=12)
    plt.xticks(rotation=45)
    plt.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.show()

    print("\nSANDWICH STATISTICS PER EPOCH:")
    print(f"Total sandwiches (filtered epochs): {epoch_df_filtered['count'].sum()}")
    print(f"Mean sandwiches per epoch: {epoch_df_filtered['count'].mean():.2f}")
    print(f"Epoch with most sandwiches : {epoch_df_filtered['count'].idxmax()} "
          f"({epoch_df_filtered['count'].max()})")
    print(f"Epoch with fewest sandwiches: {epoch_df_filtered['count'].idxmin()} "
          f"({epoch_df_filtered['count'].min()})")


def plot_heatmap(corr_matrix: pd.DataFrame, title: str) -> None:
    """
    Render a heatmap of a correlation matrix with annotated values.

    Args:
        corr_matrix (pd.DataFrame): Square correlation matrix to visualise.
        title (str): Title displayed above the heatmap.
    """
    plt.figure(figsize=(10, 8))
    sns.heatmap(corr_matrix, annot=True, cmap="coolwarm", center=0)
    plt.title(title)
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()
    plt.show()


# =======================
# === EXECUTION ===
# =======================

plot_pie()
plot_top_tokens()
plot_epoch_counts()
plot_unique_bots()
plot_sandwiches_per_epoch()
plot_revenue_and_price()
plot_and_print_sum_revenue_per_epoch()
plot_heatmap(pearson_corr,  "Pearson Correlation Heatmap")
plot_heatmap(spearman_corr, "Spearman Correlation Heatmap")


# =======================
# === SUMMARY ===
# =======================

def print_summary_statistics(
    bot_counter:        Counter,
    all_bots:           set,
    token_counter:      Counter,
    meme_df:            pd.DataFrame,
    epoch_df_filtered:  pd.DataFrame,
    df_unique_bots:     pd.DataFrame,
    combined_rev_df:    pd.DataFrame,
    mean_revenue_sol:   float,
    mean_revenue_usd:   float,
    mean_sol_usd:       float,
    total_sol_sandwich: int,
    memecoin_sandwich:  int,
) -> None:
    """
    Print a full text summary of all analysis results to stdout.

    Covers top bots, tokens, epoch stats, revenue, and memecoin distribution.

    Args:
        bot_counter (Counter): Bot activity counts.
        all_bots (set): Set of all unique bot identifiers.
        token_counter (Counter): Token frequency counts (excluding SOL).
        meme_df (pd.DataFrame): Top-10 tokens with meme/non-meme classification.
        epoch_df_filtered (pd.DataFrame): Per-epoch sandwich counts after IQR filtering.
        df_unique_bots (pd.DataFrame): Unique bot counts per epoch.
        combined_rev_df (pd.DataFrame): Per-epoch revenue stats in SOL and USD.
        mean_revenue_sol (float): Global mean revenue in SOL (outliers removed).
        mean_revenue_usd (float): Global mean revenue in USD.
        mean_sol_usd (float): Average SOL/USD price used for conversion.
        total_sol_sandwich (int): Total sandwiches with a non-SOL token end.
        memecoin_sandwich (int): Count of sandwiches involving a memecoin.
    """
    print("TOP 10 MOST ACTIVE BOTS:")
    print(bot_counter.most_common(10))

    print(f"\nTOTAL UNIQUE BOTS: {len(all_bots)}")

    print("\nTOP 10 TOKEN_END (with Meme/Non-Meme classification):")
    print(meme_df)

    print("\nSANDWICHES PER EPOCH (IQR-filtered):")
    print(epoch_df_filtered)

    print("\nUNIQUE BOTS PER EPOCH (IQR-filtered):")
    print(df_unique_bots)

    print("\nREVENUE STATISTICS PER EPOCH:")
    print(combined_rev_df)

    print("\nGLOBAL MEAN REVENUE ACROSS FILTERED EPOCHS:")
    print(f"  {mean_revenue_sol:.6f} SOL")
    print(f"  ~{mean_revenue_usd:.2f} USD (at avg price {mean_sol_usd:.2f} USD/SOL)")

    print(f"\nMax value_end observed: {max(value_end_array)}")

    pct_meme     = memecoin_sandwich / total_sol_sandwich * 100 if total_sol_sandwich else 0
    pct_non_meme = 100 - pct_meme
    print("\nMEMECOIN DISTRIBUTION IN SANDWICHES:")
    print(f"  Total considered : {total_sol_sandwich}")
    print(f"  With memecoin    : {memecoin_sandwich} ({pct_meme:.2f}%)")
    print(f"  Without memecoin : {total_sol_sandwich - memecoin_sandwich} ({pct_non_meme:.2f}%)")


print_summary_statistics(
    bot_counter,
    all_bots,
    token_counter,
    meme_df,
    epoch_df_filtered,
    df_unique_bots,
    combined_rev_df,
    mean_revenue_sol,
    mean_revenue_usd,
    sol_price_usd_mean,
    total_sol_sandwich,
    memecoin_sandwich,
)