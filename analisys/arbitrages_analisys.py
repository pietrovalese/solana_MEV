import json
import re
import time
import os
import csv
from collections import Counter
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import ccxt
from matplotlib.patches import Patch

# =======================
# === CONFIGURATION ===
# =======================
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
FILE_PATH = os.path.join(BASE_DIR, "arbitrages_annotated.jsonl")
MEMECOIN_CSV_PATH = os.path.join(BASE_DIR, "meme_and_shitcoins_list.csv")

# Solana epoch configuration
EPOCH_808_START = datetime(2025, 6, 25, 6, 58, 38)
EPOCH_DURATION_HOURS = 48
START_EPOCH = 814
END_EPOCH = 848

# ============================
# === UTILITY FUNCTIONS ===
# ============================

def load_memecoins(csv_path):
    """
    Load memecoin tickers from a CSV file.

    Reads the CSV at the given path and returns a set of uppercase ticker symbols
    for all rows where the 'Tipo' column equals 'meme'.

    Args:
        csv_path (str): Path to the CSV file containing coin data.

    Returns:
        set: A set of uppercase memecoin ticker strings.
    """
    memecoin_tickers = set()
    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Tipo'].strip().lower() == 'meme' and row['Ticker']:
                memecoin_tickers.add(row['Ticker'].strip().upper())
    return memecoin_tickers


def get_sol_usd_price():
    """
    Fetch the current SOL/USDT price from Binance.

    Returns:
        float or None: The latest SOL/USDT price, or None if the request fails.
    """
    try:
        exchange = ccxt.binance()
        ticker = exchange.fetch_ticker('SOL/USDT')
        return float(ticker['last'])
    except Exception as e:
        print(f"Error fetching SOL/USD price: {e}")
        return None


def get_sol_usd_24h_data():
    """
    Fetch the last 24 hours of hourly OHLCV data for SOL/USDT from Binance.

    Returns:
        pd.DataFrame or None: DataFrame with columns
            ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'datetime'],
            or None if the request fails.
    """
    try:
        exchange = ccxt.binance()
        since = exchange.milliseconds() - 24 * 60 * 60 * 1000
        ohlcv = exchange.fetch_ohlcv('SOL/USDT', timeframe='1h', since=since, limit=24)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching SOL/USD historical data: {e}")
        return None


def get_epoch_average_price(exchange, epoch_start, epoch_end):
    """
    Compute the average closing price of SOL/USDT over a given epoch time range.

    Fetches up to 48 hourly candles starting from epoch_start and filters
    out candles beyond epoch_end before computing the mean closing price.

    Args:
        exchange: An initialised ccxt exchange instance.
        epoch_start (datetime): Start of the epoch.
        epoch_end (datetime): End of the epoch.

    Returns:
        float or None: Mean closing price over the epoch, or None on failure.
    """
    try:
        start_ms = int(epoch_start.timestamp() * 1000)
        ohlc = exchange.fetch_ohlcv('SOL/USDT', timeframe='1h', since=start_ms, limit=48)
        if ohlc:
            df_period = pd.DataFrame(ohlc, columns=['timestamp', 'open', 'high', 'low', 'close', 'vol'])
            df_period = df_period[df_period['timestamp'] <= int(epoch_end.timestamp() * 1000)]
            if not df_period.empty:
                return df_period['close'].mean()
        return None
    except Exception as e:
        print(f"Error fetching epoch price data: {e}")
        return None


def print_summary(most_freq_token, memecoin_arbitrage_count, top10_platform,
                  total_arbitrages, bot_set, df_epoch):
    """
    Print a summary of the computed analysis results.

    Args:
        most_freq_token (list): Top 10 most frequent tokens as (token, count) pairs.
        memecoin_arbitrage_count (int): Number of arbitrages involving at least one memecoin.
        top10_platform (list): Top 10 most used platforms as (platform, count) pairs.
        total_arbitrages (int): Total number of arbitrage records analysed.
        bot_set (set): Set of unique bot identifiers.
        df_epoch (pd.DataFrame): Per-epoch summary DataFrame.
    """
    print("\n=== COMPUTED DATA SUMMARY ===")
    print(f"Top 10 tokens: {most_freq_token}")
    print(f"Total arbitrages analysed: {total_arbitrages}")
    print(f"Top 10 platforms: {top10_platform}")
    print(f"Arbitrages involving memecoins: {memecoin_arbitrage_count} "
          f"({(memecoin_arbitrage_count / total_arbitrages * 100):.2f}%)")
    print(f"Number of unique bots: {len(bot_set)}")
    print(f"Number of epochs (filtered): {len(df_epoch)}")
    print("\nPer-epoch summary:")
    print(df_epoch.to_string(index=False))


# =======================
# === DATA LOADING ===
# =======================

memecoin_tickers = load_memecoins(MEMECOIN_CSV_PATH)
sol_usd_price = get_sol_usd_price()

data = []
with open(FILE_PATH, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        # Fix malformed keys such as duplicate {"bot""bot" → {"bot"
        line = re.sub(r'\{"bot""bot"', '{"bot"', line)
        try:
            record = json.loads(line)
            data.append(record)
        except json.JSONDecodeError as e:
            print("Error on line:", line[:100])
            print("Details:", e)

print(f"Records loaded successfully: {len(data)}")

# ========================
# === MAIN ANALYSIS ===
# ========================

tokens = Counter()
platforms = Counter()
bot_set = set()
epoch_data = {}
revenues, revenues_usd, compute_units_list, fee_per_cu_list = [], [], [], []
memecoin_arbitrage_count = total_arbitrages = 0

for entry in data:
    total_arbitrages += 1
    bot = entry.get('bot')
    revenue_sol = entry.get('revenue_sol', 0)

    # Values above 0.1 are assumed to be in USD and are converted to SOL
    if revenue_sol > 0.1:
        revenue_sol = revenue_sol / sol_usd_price

    trades = entry.get('trades', [])
    details = entry.get('Details', {})
    epoch = details.get('epoch')
    fee_sol = details.get('fee', {}).get('total_fee', 0) / 1_000_000_000
    real_revenue = revenue_sol - fee_sol
    real_revenue_usd = real_revenue * sol_usd_price if sol_usd_price else None

    arbitrage_has_memecoin = any(
        trade['from_token'].upper() in memecoin_tickers or trade['to_token'].upper() in memecoin_tickers
        for trade in trades
    )

    fee_per_cu = details.get("fee", {}).get("fee_per_cu", np.nan)
    fee_per_cu_list.append(fee_per_cu)

    compute_units = details.get("compute_units_consumed", np.nan)
    compute_units_list.append(compute_units)

    for trade in trades:
        from_token = trade['from_token'].upper()
        to_token = trade['to_token'].upper()
        platform = trade['platform']
        tokens[from_token] += 1
        tokens[to_token] += 1
        platforms[platform] += 1

    if arbitrage_has_memecoin:
        memecoin_arbitrage_count += 1

    bot_set.add(bot)

    if epoch is not None and epoch >= START_EPOCH:
        if epoch not in epoch_data:
            epoch_data[epoch] = {'bots': set(), 'revenues': [], 'revenues_usd': [], 'count': 0}
        epoch_data[epoch]['bots'].add(bot)
        epoch_data[epoch]['revenues'].append(real_revenue)
        if real_revenue_usd is not None:
            epoch_data[epoch]['revenues_usd'].append(real_revenue_usd)
        epoch_data[epoch]['count'] += 1

    revenues.append(real_revenue)
    revenues_usd.append(real_revenue_usd)

# ========================
# === BUILD DATAFRAME ===
# ========================

epoch_summary = []
for epoch, info in sorted(epoch_data.items()):
    avg_rev = sum(info['revenues']) / len(info['revenues'])
    avg_rev_usd = (sum(info['revenues_usd']) / len(info['revenues_usd'])
                   if info['revenues_usd'] else None)
    epoch_summary.append({
        'epoch': epoch,
        'unique_bots': len(info['bots']),
        'avg_revenue': avg_rev,
        'avg_revenue_usd': avg_rev_usd,
        'arbitrages_count': info['count']
    })

df_epoch = pd.DataFrame(epoch_summary).sort_values("epoch")

# Remove SOL from the token counter since it appears in almost every trade
tokens.pop("SOL", None)

# Keep only epochs with at least one arbitrage and ensure a continuous x-axis
df_epoch = df_epoch[df_epoch["arbitrages_count"] > 0].copy()
df_epoch.sort_values("epoch", inplace=True)
df_epoch.reset_index(drop=True, inplace=True)

# ========================
# === CORRELATION DATA ===
# ========================

df_corr = pd.DataFrame({
    'revenue': revenues,
    'compute_units': compute_units_list
}).dropna()

pearson_corr = df_corr['revenue'].corr(df_corr['compute_units'], method='pearson')
spearman_corr = df_corr['revenue'].corr(df_corr['compute_units'], method='spearman')

df_fee_corr = pd.DataFrame({
    'revenue': revenues,
    'fee_per_cu': fee_per_cu_list
}).dropna()

pearson_fee_corr = df_fee_corr['revenue'].corr(df_fee_corr['fee_per_cu'], method='pearson')
spearman_fee_corr = df_fee_corr['revenue'].corr(df_fee_corr['fee_per_cu'], method='spearman')

df_multi = pd.DataFrame({
    'revenue': revenues,
    'compute_units': compute_units_list,
    'fee_per_cu': fee_per_cu_list,
    'total_fee': [entry.get("Details", {}).get("fee", {}).get("total_fee", np.nan) for entry in data],
    'priority_fee': [entry.get("Details", {}).get("fee", {}).get("priority_fee", np.nan) for entry in data],
    'num_trades': [len(entry.get("trades", [])) for entry in data]
}).dropna()

# =====================
# === SOL PRICE PER EPOCH ===
# =====================

exchange = ccxt.binance()

print(f"Fetching SOL price data for epochs {START_EPOCH}-{END_EPOCH}...")

epoch_price_data = []

for epoch in range(START_EPOCH, END_EPOCH + 1):
    hours_from_start = (epoch - START_EPOCH) * EPOCH_DURATION_HOURS
    epoch_start = EPOCH_808_START + timedelta(hours=hours_from_start)
    epoch_end = epoch_start + timedelta(hours=EPOCH_DURATION_HOURS)

    avg_price = get_epoch_average_price(exchange, epoch_start, epoch_end)
    if avg_price is not None:
        epoch_price_data.append({
            "epoch": epoch,
            "start_date": epoch_start,
            "end_date": epoch_end,
            "avg_price_usd": avg_price
        })
        print(f"Epoch {epoch}: average price = ${avg_price:.2f}")
    time.sleep(0.2)  # Avoid hitting Binance rate limits

df_sol_epochs = pd.DataFrame(epoch_price_data)
sol_price_usd_mean = df_sol_epochs["avg_price_usd"].mean()
print(f"\nGlobal average price across all epochs: {sol_price_usd_mean:.2f} USD")

# =====================
# === PLOTTING FUNCTIONS ===
# =====================

def plot_top_tokens():
    """
    Plot a bar chart of the 10 most frequent tokens, highlighting memecoins in green.
    """
    top_tokens = tokens.most_common(10)
    tokens_labels, tokens_counts = zip(*top_tokens) if top_tokens else ([], [])
    bar_colors = ['lightgreen' if token in memecoin_tickers else 'skyblue' for token in tokens_labels]

    plt.figure(figsize=(10, 4))
    plt.bar(tokens_labels, tokens_counts, color=bar_colors)
    plt.title("Most frequent tokens")
    plt.ylabel("Frequency")
    plt.xticks(rotation=45)
    plt.legend(handles=[
        Patch(facecolor='lightgreen', label='Memecoin'),
        Patch(facecolor='skyblue', label='Other')
    ])
    plt.tight_layout()
    plt.show()
    return top_tokens


def plot_memecoin_pie():
    """
    Plot a pie chart showing the share of arbitrages that involve at least one memecoin.
    """
    sizes = [memecoin_arbitrage_count, total_arbitrages - memecoin_arbitrage_count]
    labels = ['With memecoin', 'Without memecoin']
    colors = ['lightgreen', 'lightgray']

    plt.figure(figsize=(6, 6))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors)
    plt.title(f'Arbitrages with memecoins ({memecoin_arbitrage_count} out of {total_arbitrages})')
    plt.axis('equal')
    plt.tight_layout()
    plt.show()


def plot_top_platforms():
    """
    Plot a bar chart of the 10 most frequently used trading platforms.

    Returns:
        list: Top 10 platforms as (platform, count) pairs.
    """
    top_platforms = platforms.most_common(10)
    platform_labels, platform_counts = zip(*top_platforms) if top_platforms else ([], [])

    plt.figure(figsize=(10, 4))
    plt.bar(platform_labels, platform_counts, color='lightgreen')
    plt.title("Most frequent platforms")
    plt.ylabel("Frequency")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()
    return top_platforms


def plot_unique_bots_per_epoch():
    """
    Plot a bar chart of the number of unique bots active per epoch.
    """
    plt.figure(figsize=(12, 5))
    x_positions = range(len(df_epoch))
    plt.bar(x_positions, df_epoch["unique_bots"], color='orange')
    plt.title("Unique bots per epoch")
    plt.xlabel("Epoch")
    plt.ylabel("Number of unique bots")
    plt.xticks(x_positions, df_epoch["epoch"], rotation=45)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.show()


def plot_avg_revenue_and_sol_24h():
    """
    Display two side-by-side plots:
    - Left: bar chart of average revenue per epoch (SOL).
    - Right: SOL/USD price over the last 24 hours.
    """
    sol_24h_df = get_sol_usd_24h_data()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 5), gridspec_kw={'width_ratios': [1, 1.2]})

    x_positions = range(len(df_epoch))
    ax1.bar(x_positions, df_epoch["avg_revenue"], color='tab:blue')
    ax1.set_title("Average revenue per epoch (SOL)")
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Average revenue (SOL)")
    ax1.set_xticks(x_positions)
    ax1.set_xticklabels(df_epoch["epoch"], rotation=45)
    ax1.grid(axis='y', linestyle='--', alpha=0.7)

    if sol_24h_df is not None and not sol_24h_df.empty:
        ax2.plot(sol_24h_df['datetime'].to_numpy(), sol_24h_df['close'].to_numpy(), color='tab:red')
        ax2.set_title("SOL/USD price – last 24h")
        ax2.set_xlabel("Time")
        ax2.set_ylabel("SOL/USD price")
        ax2.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%H:%M'))
        ax2.grid(True, linestyle='--', alpha=0.7)
    else:
        ax2.text(0.5, 0.5, "SOL price data unavailable", ha='center', va='center')
        ax2.axis('off')

    plt.tight_layout()
    plt.show()


def plot_arbitrages_per_epoch():
    """
    Plot a histogram of arbitrage count per epoch (from epoch 814 onward)
    and print descriptive statistics.
    """
    df_epoch_filtered = df_epoch[df_epoch["epoch"] >= START_EPOCH]

    plt.figure(figsize=(14, 6))
    plt.bar(df_epoch_filtered["epoch"].astype(str),
            df_epoch_filtered["arbitrages_count"],
            color='teal', alpha=0.7)
    plt.title("Number of arbitrages per epoch")
    plt.xlabel("Epoch", fontsize=12)
    plt.ylabel("Number of arbitrages", fontsize=12)
    plt.xticks(rotation=45)
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.show()

    print("\nARBITRAGE STATISTICS PER EPOCH:")
    print(f"Total arbitrages (from epoch {START_EPOCH}): {df_epoch_filtered['arbitrages_count'].sum()}")
    print(df_epoch_filtered.to_string())
    print(f"Average arbitrages per epoch: {df_epoch_filtered['arbitrages_count'].mean():.2f}")
    peak_idx = df_epoch_filtered['arbitrages_count'].idxmax()
    low_idx = df_epoch_filtered['arbitrages_count'].idxmin()
    print(f"Epoch with most arbitrages:  {df_epoch_filtered.loc[peak_idx, 'epoch']} "
          f"({df_epoch_filtered['arbitrages_count'].max()} arbitrages)")
    print(f"Epoch with fewest arbitrages: {df_epoch_filtered.loc[low_idx, 'epoch']} "
          f"({df_epoch_filtered['arbitrages_count'].min()} arbitrages)")


def plot_revenue_and_price():
    """
    Plot average revenue per epoch (bar, left axis) overlaid with the average
    SOL/USD price per epoch (line, right axis). Missing price values are
    interpolated linearly.
    """
    df_epoch_filtered = df_epoch[df_epoch["epoch"] >= START_EPOCH]
    df_sol_epochs_filtered = df_sol_epochs[df_sol_epochs["epoch"] >= START_EPOCH]

    all_epochs = df_epoch_filtered["epoch"].unique()
    df_sol_complete = pd.DataFrame({'epoch': all_epochs})
    df_sol_complete = df_sol_complete.merge(df_sol_epochs_filtered, on='epoch', how='left')
    df_sol_complete['avg_price_usd'] = df_sol_complete['avg_price_usd'].interpolate(method='linear')

    fig, ax1 = plt.subplots(figsize=(14, 6))

    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Average revenue (SOL)", color='green')
    ax1.bar(df_epoch_filtered["epoch"].astype(str), df_epoch_filtered["avg_revenue"],
            color='green', alpha=0.6, label='Average revenue')
    ax1.tick_params(axis='y', labelcolor='green')
    ax1.tick_params(axis='x', rotation=45)

    ax2 = ax1.twinx()
    ax2.set_ylabel("Average SOL price (USD)", color='orange')
    ax2.plot(df_sol_complete['epoch'].astype(str).to_numpy(),
             df_sol_complete['avg_price_usd'].to_numpy(),
             color='orange', marker='o', linewidth=2, markersize=4,
             label='SOL price')
    ax2.tick_params(axis='y', labelcolor='orange')
    ax2.grid(True, alpha=0.3)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

    plt.tight_layout()
    plt.show()


def plot_and_print_sum_revenue_per_epoch():
    """
    Plot the total (summed) revenue per epoch in SOL (bar, left axis) overlaid with
    the average SOL/USD price per epoch (line, right axis). Also prints a table of
    per-epoch sums and the grand total in both SOL and USD.
    """
    sum_rev = {}
    for epoch, info in epoch_data.items():
        if epoch >= START_EPOCH:
            rev_array = np.array(info['revenues'])
            if len(rev_array) > 0:
                sum_rev[epoch] = {
                    "sum_revenue_SOL": rev_array.sum(),
                    "sum_revenue_USD": rev_array.sum() * sol_price_usd_mean
                }

    df_sum_rev = pd.DataFrame.from_dict(sum_rev, orient='index').sort_index()
    df_sol_epochs_filtered = df_sol_epochs[df_sol_epochs["epoch"] >= START_EPOCH]

    all_epochs = df_sum_rev.index.values
    df_sol_complete = pd.DataFrame({'epoch': all_epochs})
    df_sol_complete = df_sol_complete.merge(df_sol_epochs_filtered, on='epoch', how='left')
    df_sol_complete['avg_price_usd'] = df_sol_complete['avg_price_usd'].interpolate(method='linear')

    fig, ax1 = plt.subplots(figsize=(14, 6))

    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Total revenue (SOL)", color='darkblue')
    ax1.bar(df_sum_rev.index.astype(str), df_sum_rev["sum_revenue_SOL"],
            color='darkblue', alpha=0.6, label='Total revenue')
    ax1.tick_params(axis='y', labelcolor='darkblue')
    ax1.tick_params(axis='x', rotation=45)

    ax2 = ax1.twinx()
    ax2.set_ylabel("Average SOL price (USD)", color='orange')
    ax2.plot(df_sol_complete['epoch'].astype(str).to_numpy(),
             df_sol_complete['avg_price_usd'].to_numpy(),
             color='orange', marker='o', linewidth=2, markersize=4,
             label='SOL price')
    ax2.tick_params(axis='y', labelcolor='orange')
    ax2.grid(True, alpha=0.3)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

    plt.tight_layout()
    plt.show()

    print("\nTOTAL REVENUE PER EPOCH:")
    print(df_sum_rev)

    total_sol = df_sum_rev["sum_revenue_SOL"].sum()
    total_usd = df_sum_rev["sum_revenue_USD"].sum()
    print(f"\nGRAND TOTAL REVENUE ACROSS ALL EPOCHS (from {START_EPOCH} onward):")
    print(f"  {total_sol:.6f} SOL")
    print(f"  ~{total_usd:.2f} USD (at mean price of {sol_price_usd_mean:.2f} USD/SOL)")


def plot_correlation_heatmaps():
    """
    Plot Pearson and Spearman correlation heatmaps for the multi-feature DataFrame
    (revenue, compute_units, fee_per_cu, total_fee, priority_fee, num_trades).
    """
    plt.figure(figsize=(10, 6))
    sns.heatmap(df_multi.corr(method='pearson'), annot=True, cmap='coolwarm', fmt=".2f")
    plt.title("Correlation matrix (Pearson)")
    plt.tight_layout()
    plt.show()

    plt.figure(figsize=(10, 6))
    sns.heatmap(df_multi.corr(method='spearman'), annot=True, cmap='coolwarm', fmt=".2f")
    plt.title("Correlation matrix (Spearman)")
    plt.tight_layout()
    plt.show()


# =====================
# === MAIN EXECUTION ===
# =====================

top_tokens = plot_top_tokens()
plot_memecoin_pie()
top_platforms = plot_top_platforms()
plot_unique_bots_per_epoch()
plot_avg_revenue_and_sol_24h()
plot_correlation_heatmaps()
plot_revenue_and_price()
plot_and_print_sum_revenue_per_epoch()
plot_arbitrages_per_epoch()

print_summary(top_tokens, memecoin_arbitrage_count, top_platforms,
              total_arbitrages, bot_set, df_epoch)

print(f"\n=== CORRELATION: REVENUE vs COMPUTE UNITS ===")
print(f"Pearson correlation (linear):   {pearson_corr:.4f}")
print(f"Spearman correlation (monotone): {spearman_corr:.4f}")

print(f"\n=== CORRELATION: REVENUE vs FEE PER CU ===")
print(f"Pearson correlation (linear):   {pearson_fee_corr:.4f}")
print(f"Spearman correlation (monotone): {spearman_fee_corr:.4f}")