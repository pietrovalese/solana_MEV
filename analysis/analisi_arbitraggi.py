import json
import pandas as pd
import matplotlib.pyplot as plt
from collections import Counter
import os
import numpy as np
import ccxt
import csv
from matplotlib.patches import Patch
import seaborn as sns

# =======================
# === CONFIGURAZIONE ===
# =======================
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
FILE_PATH = os.path.join(BASE_DIR, "arbitrages_annotated.jsonl")
MEMECOIN_CSV_PATH = os.path.join(BASE_DIR, "meme_and_shitcoins_list.csv")

# ============================
# === FUNZIONI DI UTILITÀ ===
# ============================
def load_memecoins(csv_path):
    memecoin_tickers = set()
    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Tipo'].strip().lower() == 'meme' and row['Ticker']:
                memecoin_tickers.add(row['Ticker'].strip().upper())
    return memecoin_tickers

def get_sol_usd_price():
    try:
        exchange = ccxt.binance()
        ticker = exchange.fetch_ticker('SOL/USDT')
        return float(ticker['last'])
    except Exception as e:
        print(f"Errore nel fetch del prezzo SOL/USD: {e}")
        return None

def get_sol_usd_24h_data():
    try:
        exchange = ccxt.binance()
        since = exchange.milliseconds() - 24 * 60 * 60 * 1000
        ohlcv = exchange.fetch_ohlcv('SOL/USDT', timeframe='1h', since=since, limit=24)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Errore nel fetch storico SOL/USD: {e}")
        return None


def stampa_risultati(most_freq_token, memecoin_arbitrage_count, top10_platform, total_arbitrages, bot_set, df_epoch):
    print("\n=== RIEPILOGO DATI CALCOLATI ===")
    print(f"Top 10 token: {most_freq_token}")
    print(f"Totale arbitraggi analizzati: {total_arbitrages}")
    print(f"Top 10 Piattaforme: {top10_platform}")
    print(f"Arbitraggi che coinvolgono memecoin: {memecoin_arbitrage_count} ({(memecoin_arbitrage_count / total_arbitrages * 100):.2f}%)")
    print(f"Numero di bot unici: {len(bot_set)}")
    print(f"Numero di epoche (filtrate): {len(df_epoch)}")
    print("\nRiepilogo per epoca:")
    print(df_epoch.to_string(index=False))

# =======================
# === CARICAMENTO DATI ===
# =======================
memecoin_tickers = load_memecoins(MEMECOIN_CSV_PATH)
sol_usd_price = get_sol_usd_price()

import re

data = []
with open(FILE_PATH, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        # Sostituisce {{ o chiavi duplicate "bot""bot" con "bot"
        line = re.sub(r'\{"bot""bot"', '{"bot"', line)
        try:
            record = json.loads(line)
            data.append(record)
        except json.JSONDecodeError as e:
            print("Errore su riga:", line[:100])
            print("Dettagli:", e)

print(f"Record letti correttamente: {len(data)}")

# ========================
# === ANALISI PRINCIPALE ===
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

    if epoch is not None and epoch >= 814:
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
# === COSTRUISCI DATAFRAME ===
# ========================
epoch_summary = []
for epoch, info in sorted(epoch_data.items()):
    avg_rev = sum(info['revenues']) / len(info['revenues'])
    avg_rev_usd = sum(info['revenues_usd']) / len(info['revenues_usd']) if info['revenues_usd'] else None
    epoch_summary.append({
        'epoch': epoch,
        'unique_bots': len(info['bots']),
        'avg_revenue': avg_rev,
        'avg_revenue_usd': avg_rev_usd,
        'arbitrages_count': info['count']
    })

df_epoch = pd.DataFrame(epoch_summary).sort_values("epoch")
tokens.pop("SOL", None)

# ========================
# === FILTRO EPOCHE VIA IQR ===
# ========================
# Filtra le epoche vuote
df_epoch = df_epoch[df_epoch["arbitrages_count"] > 0].copy()

# Ordina per epoca
df_epoch.sort_values("epoch", inplace=True)

# Assicura che l'asse X sia continuo (solo epoche presenti)
df_epoch.reset_index(drop=True, inplace=True)

# ========================
# === CORRELAZIONI ===
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
# === VISUALIZZAZIONE ===
# =====================

# 1. Token più frequenti
top_tokens = tokens.most_common(10)
tokens_labels, tokens_counts = zip(*top_tokens) if top_tokens else ([], [])
bar_colors = ['lightgreen' if token in memecoin_tickers else 'skyblue' for token in tokens_labels]

plt.figure(figsize=(10, 4))
plt.bar(tokens_labels, tokens_counts, color=bar_colors)
plt.title("Token più frequenti")
plt.ylabel("Frequenza")
plt.xticks(rotation=45)
plt.legend(handles=[
    Patch(facecolor='lightgreen', label='Memecoin'),
    Patch(facecolor='skyblue', label='Altro')
])
plt.tight_layout()
plt.show()

# 2. Percentuale arbitraggi con memecoin
sizes = [memecoin_arbitrage_count, total_arbitrages - memecoin_arbitrage_count]
labels = ['Con memecoin', 'Senza memecoin']
colors = ['lightgreen', 'lightgray']

plt.figure(figsize=(6, 6))
plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors)
plt.title(f'Arbitraggi con memecoin ({memecoin_arbitrage_count} su {total_arbitrages})')
plt.axis('equal')
plt.tight_layout()
plt.show()

# 3. Piattaforme più usate
top_platforms = platforms.most_common(10)
platform_labels, platform_counts = zip(*top_platforms) if top_platforms else ([], [])

plt.figure(figsize=(10, 4))
plt.bar(platform_labels, platform_counts, color='lightgreen')
plt.title("Piattaforme più frequenti")
plt.ylabel("Frequenza")
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# 4. Bot unici per epoca (solo epoche filtrate)
plt.figure(figsize=(12, 5))
x_positions = range(len(df_epoch))
plt.bar(x_positions, df_epoch["unique_bots"], color='orange')
plt.title("Bot unici per epoca")
plt.xlabel("Epoca")
plt.ylabel("Numero di bot unici")
plt.xticks(x_positions, df_epoch["epoch"], rotation=45)
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.show()


# 5. Revenue medio + Prezzo SOL 24h
sol_24h_df = get_sol_usd_24h_data()
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 5), gridspec_kw={'width_ratios': [1, 1.2]})

from datetime import datetime, timedelta
import time

# ============================
# === PREZZO SOL PER EPOCA ===
# ============================
exchange = ccxt.binance()

# Configurazione epoche Solana
EPOCH_808_START = datetime(2025, 6, 25, 6, 58, 38)  # inizio epoca 808
EPOCH_DURATION_HOURS = 48
START_EPOCH = 814
END_EPOCH = 848

print(f"Raccolta dati prezzo SOL per epoche {START_EPOCH}-{END_EPOCH}...")

epoch_price_data = []

def get_epoch_average_price(epoch_start, epoch_end):
    try:
        start_ms = int(epoch_start.timestamp() * 1000)
        ohlc = exchange.fetch_ohlcv('SOL/USDT', timeframe='1h', since=start_ms, limit=48)
        if ohlc:
            df_period = pd.DataFrame(ohlc, columns=['timestamp','open','high','low','close','vol'])
            df_period = df_period[df_period['timestamp'] <= int(epoch_end.timestamp() * 1000)]
            if not df_period.empty:
                return df_period['close'].mean()
        return None
    except Exception as e:
        print(f"Errore nel recupero dati: {e}")
        return None

for epoch in range(START_EPOCH, END_EPOCH + 1):
    hours_from_808 = (epoch - START_EPOCH) * EPOCH_DURATION_HOURS
    epoch_start = EPOCH_808_START + timedelta(hours=hours_from_808)
    epoch_end = epoch_start + timedelta(hours=EPOCH_DURATION_HOURS)

    avg_price = get_epoch_average_price(epoch_start, epoch_end)
    if avg_price is not None:
        epoch_price_data.append({
            "epoch": epoch,
            "start_date": epoch_start,
            "end_date": epoch_end,
            "avg_price_usd": avg_price
        })
        print(f"Epoca {epoch}: prezzo medio = ${avg_price:.2f}")
    time.sleep(0.2)  # per sicurezza, contro rate-limit

df_sol_epochs = pd.DataFrame(epoch_price_data)
sol_price_usd_mean = df_sol_epochs["avg_price_usd"].mean()
print(f"\nPrezzo medio globale su tutte le epoche: {sol_price_usd_mean:.2f} USD")


# Revenue medio per epoca
x_positions = range(len(df_epoch))
ax1.bar(x_positions, df_epoch["avg_revenue"], color='tab:blue')
ax1.set_title("Revenue medio per epoca (SOL)")
ax1.set_xlabel("Epoca")
ax1.set_ylabel("Revenue medio (SOL)")
ax1.set_xticks(x_positions)
ax1.set_xticklabels(df_epoch["epoch"], rotation=45)
ax1.grid(axis='y', linestyle='--', alpha=0.7)

# Prezzo SOL 24h
if sol_24h_df is not None and not sol_24h_df.empty:
    ax2.plot(sol_24h_df['datetime'].to_numpy(), sol_24h_df['close'].to_numpy(), color='tab:red')
    ax2.set_title("Prezzo SOL/USD ultime 24h")
    ax2.set_xlabel("Ora")
    ax2.set_ylabel("Prezzo SOL/USD")
    ax2.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%H:%M'))
    ax2.grid(True, linestyle='--', alpha=0.7)
else:
    ax2.text(0.5, 0.5, "Dati prezzo SOL non disponibili", ha='center', va='center')
    ax2.axis('off')

plt.tight_layout()
plt.show()


# Aggiungi questa funzione dopo le altre funzioni di plotting

def plot_arbitrages_per_epoch():
    """Mostra un istogramma con il numero di arbitraggi per epoca (da 814 in poi)"""
    df_epoch_filtered = df_epoch[df_epoch["epoch"] >= 814]
    
    plt.figure(figsize=(14, 6))
    plt.bar(df_epoch_filtered["epoch"].astype(str), 
            df_epoch_filtered["arbitrages_count"],
            color='teal', alpha=0.7)
    
    plt.xlabel("Epoca", fontsize=12)
    plt.ylabel("Numero di arbitraggi", fontsize=12)
    plt.xticks(rotation=45)
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.show()
    
    # Stampa statistiche
    print("\n📊 STATISTICHE ARBITRAGGI PER EPOCA:")
    print(f"Totale arbitraggi (da epoca 814): {df_epoch_filtered['arbitrages_count'].sum()}")
    print(f"{df_epoch_filtered}")
    print(f"Media arbitraggi per epoca: {df_epoch_filtered['arbitrages_count'].mean():.2f}")
    print(f"Epoca con più arbitraggi: {df_epoch_filtered.loc[df_epoch_filtered['arbitrages_count'].idxmax(), 'epoch']} ({df_epoch_filtered['arbitrages_count'].max()} arbitraggi)")
    print(f"Epoca con meno arbitraggi: {df_epoch_filtered.loc[df_epoch_filtered['arbitrages_count'].idxmin(), 'epoch']} ({df_epoch_filtered['arbitrages_count'].min()} arbitraggi)")

def plot_revenue_and_price():
    # Filtro i dati dall'epoca 814 in poi
    df_epoch_filtered = df_epoch[df_epoch["epoch"] >= 814]
    df_sol_epochs_filtered = df_sol_epochs[df_sol_epochs["epoch"] >= 814]
    
    # Creo un dataframe completo con tutte le epoche
    all_epochs = df_epoch_filtered["epoch"].unique()
    df_sol_complete = pd.DataFrame({'epoch': all_epochs})
    df_sol_complete = df_sol_complete.merge(df_sol_epochs_filtered, on='epoch', how='left')
    
    # Interpolo i valori mancanti
    df_sol_complete['avg_price_usd'] = df_sol_complete['avg_price_usd'].interpolate(method='linear')
    
    fig, ax1 = plt.subplots(figsize=(14, 6))
    
    # Primo asse y: Revenue medio (barre verdi)
    color = 'green'
    ax1.set_xlabel("Epoca")
    ax1.set_ylabel("Revenue medio (SOL)", color=color)
    ax1.bar(df_epoch_filtered["epoch"].astype(str), df_epoch_filtered["avg_revenue"],
            color=color, alpha=0.6, label='Revenue medio')
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.tick_params(axis='x', rotation=45)
    
    # Secondo asse y: Prezzo SOL (linea arancione)
    ax2 = ax1.twinx()
    color = 'orange'
    ax2.set_ylabel("Prezzo medio SOL (USD)", color=color)
    ax2.plot(df_sol_complete['epoch'].astype(str).to_numpy(),
             df_sol_complete['avg_price_usd'].to_numpy(),
             color=color, marker='o', linewidth=2, markersize=4,
             label='Prezzo SOL')
    ax2.tick_params(axis='y', labelcolor=color)
    ax2.grid(True, alpha=0.3)
    
    # Legend combinata
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    
    plt.tight_layout()
    plt.show()

def plot_and_print_sum_revenue_per_epoch():
    # Calcola la somma dei revenue per epoca da epoch_data (solo da 814 in poi)
    sum_rev = {}
    for epoch, info in epoch_data.items():
        if epoch >= 814:
            rev_array = np.array(info['revenues'])
            rev_array_clean = rev_array
            if len(rev_array_clean) > 0:
                sum_rev[epoch] = {
                    "sum_revenue_SOL": rev_array_clean.sum(),
                    "sum_revenue_USD": rev_array_clean.sum() * sol_price_usd_mean
                }
    
    df_sum_rev = pd.DataFrame.from_dict(sum_rev, orient='index').sort_index()
    df_sol_epochs_filtered = df_sol_epochs[df_sol_epochs["epoch"] >= 814]
    
    # Creo un dataframe completo con tutte le epoche
    all_epochs = df_sum_rev.index.values
    df_sol_complete = pd.DataFrame({'epoch': all_epochs})
    df_sol_complete = df_sol_complete.merge(df_sol_epochs_filtered, on='epoch', how='left')
    
    # Interpolo i valori mancanti
    df_sol_complete['avg_price_usd'] = df_sol_complete['avg_price_usd'].interpolate(method='linear')
    
    fig, ax1 = plt.subplots(figsize=(14, 6))
    
    # Primo asse y: Somma revenue (barre blu scuro)
    color = 'darkblue'
    ax1.set_xlabel("Epoca")
    ax1.set_ylabel("Somma Revenue (SOL)", color=color)
    ax1.bar(df_sum_rev.index.astype(str), df_sum_rev["sum_revenue_SOL"],
            color=color, alpha=0.6, label='Somma Revenue')
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.tick_params(axis='x', rotation=45)
    
    # Secondo asse y: Prezzo SOL (linea arancione)
    ax2 = ax1.twinx()
    color = 'orange'
    ax2.set_ylabel("Prezzo medio SOL (USD)", color=color)
    ax2.plot(df_sol_complete['epoch'].astype(str).to_numpy(),
             df_sol_complete['avg_price_usd'].to_numpy(),
             color=color, marker='o', linewidth=2, markersize=4,
             label='Prezzo SOL')
    ax2.tick_params(axis='y', labelcolor=color)
    ax2.grid(True, alpha=0.3)
    
    # Legend combinata
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    
    plt.tight_layout()
    plt.show()
    
    # Stampa tabella dei valori
    print("\n🔹 SOMMA DEI REVENUE PER EPOCA:")
    print(df_sum_rev)
    
    # Stampa somma totale
    total_sol = df_sum_rev["sum_revenue_SOL"].sum()
    total_usd = df_sum_rev["sum_revenue_USD"].sum()
    print("\n🎯 SOMMA TOTALE DELLA REVENUE SU TUTTE LE EPOCHE (da 814 in poi):")
    print(f"→ {total_sol:.6f} SOL")
    print(f"→ ≈ {total_usd:.2f} USD (al prezzo medio di {sol_price_usd_mean:.2f} USD/SOL)")

plt.figure(figsize=(10, 6))
sns.heatmap(df_multi.corr(method='pearson'), annot=True, cmap='coolwarm', fmt=".2f")
plt.title("Matrice di Correlazione (Pearson)")
plt.tight_layout()
plt.show()

plt.figure(figsize=(10, 6))
sns.heatmap(df_multi.corr(method='spearman'), annot=True, cmap='coolwarm', fmt=".2f")
plt.title("Matrice di Correlazione (SPEARMAN)")
plt.tight_layout()
plt.show()


plot_revenue_and_price()
plot_and_print_sum_revenue_per_epoch()
plot_arbitrages_per_epoch()

# ========================
# === STAMPA RISULTATI ===
# ========================
stampa_risultati(top_tokens, memecoin_arbitrage_count, top_platforms, total_arbitrages, bot_set, df_epoch)
print(f"\n=== CORRELAZIONE REVENUE - COMPUTE UNITS===")
print(f"Correlazione Pearson (lineare):  {pearson_corr:.4f}")
print(f"Correlazione Spearman (monotona): {spearman_corr:.4f}")

print(f"\n=== CORRELAZIONE: REVENUE - FEE X CU ===")
print(f"Correlazione Pearson (lineare):  {pearson_fee_corr:.4f}")
print(f"Correlazione Spearman (monotona): {spearman_fee_corr:.4f}")
