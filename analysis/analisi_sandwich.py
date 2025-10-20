# sandwich_analysis_plotting.py

import json
import pandas as pd
import matplotlib.pyplot as plt
from collections import Counter, defaultdict
from tqdm import tqdm
import ccxt
import os
import numpy as np
import seaborn as sns
from matplotlib.patches import Patch
from datetime import datetime, timedelta
import time
# -------------------------------
# 📥 PARTE 1: RACCOLTA E PREPARAZIONE DATI
# -------------------------------

# Percorsi file
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
sandwich_path = os.path.join(BASE_DIR, "sandwiches_unique.jsonl")
meme_list_path = os.path.join(BASE_DIR, "meme_and_shitcoins_list.csv")

# Lettura memecoin
memecoin_df = pd.read_csv(meme_list_path)
memecoin_tickers = set(memecoin_df['Ticker'].dropna().str.upper())


def remove_outliers_iqr(data, multiplier=1.5):
    """
    Rimuove outlier usando il metodo IQR
    
    Args:
        data: array di valori
        multiplier: moltiplicatore per IQR (default 1.5, più alto = meno restrittivo)
    
    Returns:
        array filtrato senza outlier
    """
    if len(data) == 0:
        return np.array([])
    
    data = np.array(data)
    Q1 = np.percentile(data, 25)
    Q3 = np.percentile(data, 75)
    IQR = Q3 - Q1
    
    lower_bound = Q1 - multiplier * IQR
    upper_bound = Q3 + multiplier * IQR
    
    # Filtra i dati
    filtered_data = data[(data >= lower_bound) & (data <= upper_bound)]
    return filtered_data

def estrai_metriche_corr(data):
    # Estrai metriche bot1
    b1 = data.get("bot1", {})
    b2 = data.get("bot2", {})
    
    def estrai_fee_info(bot):
        det = bot.get("Details", {})
        fee = det.get("fee", {})
        return {
            "compute_units": det.get("compute_units_consumed", np.nan),
            "fee_total": fee.get("total_fee", np.nan),
            "priority_fee": fee.get("priority_fee", np.nan),
            "transaction_fee": fee.get("transaction_fee", np.nan),
            "fee_per_cu": fee.get("fee_per_cu", np.nan),
        }
    
    b1_metrics = estrai_fee_info(b1)
    b2_metrics = estrai_fee_info(b2)
    
    # Revenue come lo calcoli già (SOL token_start)
    try:
        if b1.get("token_start", "").lower() == "sol":
            value_start = float(b1.get("value_start", "0").replace(",", ""))
            value_end = float(b2.get("value_end", "0").replace(",", ""))
            fee1 = b1_metrics["fee_total"] / 1e9
            fee2 = b2_metrics["fee_total"] / 1e9
            revenue = value_end - value_start - fee1 - fee2
        else:
            revenue = np.nan
    except Exception:
        revenue = np.nan
    
    # Combina tutto in un dict
    row = {
        "b1_cu": b1_metrics["compute_units"],
        "b1_fee_total": b1_metrics["fee_total"],
        "b1_priority_fee": b1_metrics["priority_fee"],
        "b1_fee_per_cu": b1_metrics["fee_per_cu"],
        "b2_cu": b2_metrics["compute_units"],
        "b2_fee_total": b2_metrics["fee_total"],
        "b2_priority_fee": b2_metrics["priority_fee"],
        "b2_fee_per_cu": b2_metrics["fee_per_cu"],
        "revenue": revenue,
    }
    
    return row

# Inizializzazione contatori
total_sol_sandwich = 0
memecoin_sandwich = 0
bot_counter = Counter()
token_counter = Counter()
epoch_counter = Counter()
all_bots = set()
revenue_data = {}

value_end_array=[]

# Parsing file JSONL
with open(sandwich_path, 'r') as file:
    for line in tqdm(file):
        data = json.loads(line)

        bot_name = data['bot1']['bot'].split(":")[-1].strip()
        bot_counter[bot_name] += 1
        all_bots.add(bot_name)

        token_end = data['bot1']['token_end']
        if token_end.lower() != 'sol':
            token_counter[token_end] += 1
            total_sol_sandwich += 1
            if token_end.upper() in memecoin_tickers:
                memecoin_sandwich += 1

        try:
            epoch = data['bot1']['Details']['epoch']
            epoch_counter[epoch] += 1

            if data['bot1']['token_start'].lower() == 'sol':
                value_start = float(data['bot1']['value_start'].replace(",", ""))
                value_end = float(data['bot2']['value_end'].replace(",", ""))
                value_end_array.append(value_end)
                fee1 = data['bot1']['Details']['fee']['total_fee'] / 1e9
                fee2 = data['bot2']['Details']['fee']['total_fee'] / 1e9
                revenue = value_end - value_start - fee1 - fee2

                if epoch not in revenue_data:
                    revenue_data[epoch] = []
                revenue_data[epoch].append(revenue)

        except (KeyError, ValueError, TypeError):
            continue

# -------------------------------
# 📈 PARTE 2: ANALISI DATI
# -------------------------------

# 1. Calcolo percentuali meme
non_meme_sandwich = total_sol_sandwich - memecoin_sandwich
percent_meme = memecoin_sandwich / total_sol_sandwich * 100 if total_sol_sandwich else 0
percent_non_meme = 100 - percent_meme

# 2. Classificazione meme nei top token
top_tokens = token_counter.most_common(10)
meme_status = [
    (token, count, "Meme" if token.upper() in memecoin_tickers else "Non-Meme")
    for token, count in top_tokens
]
meme_df = pd.DataFrame(meme_status, columns=["Token", "Count", "Type"])

# -------------------------------
# 📈 CALCOLO STATISTICHE REVENUE PER EPOCA
# -------------------------------

# 1. Filtraggio epoche via IQR (già presente)
epoch_df = pd.DataFrame.from_dict(epoch_counter, orient='index', columns=['count'])
Q1 = epoch_df['count'].quantile(0.25)
Q2 = epoch_df['count'].quantile(0.50)
Q3 = epoch_df['count'].quantile(0.75)
threshold = Q2 - Q1
valid_epochs = epoch_df[epoch_df['count'] >= threshold].index
epoch_df_filtered = epoch_df.loc[valid_epochs].sort_index()

# 2. Calcolo media, deviazione standard, min e max revenue per epoca (SOL)
rev_stats = {}
outlier_summary = {}  # Per tenere traccia degli outlier rimossi

print("📊 RIMOZIONE OUTLIER PER EPOCA:")
for epoch, values in revenue_data.items():
    if epoch in valid_epochs:
        rev_array = np.array(values)
        
        # Rimuovi outlier con IQR
        rev_array_clean = remove_outliers_iqr(rev_array, multiplier=1.5)
        
        # Calcola statistiche sui dati puliti
        if len(rev_array_clean) > 0:
            rev_stats[epoch] = {
                "mean_revenue": rev_array_clean.mean(),
                "std_revenue": rev_array_clean.std(),
                "min_revenue": rev_array_clean.min(),
                "max_revenue": rev_array_clean.max(),
            }
            
            # Tieni traccia degli outlier rimossi
            outliers_removed = len(rev_array) - len(rev_array_clean)
            outlier_pct = (outliers_removed / len(rev_array)) * 100
            outlier_summary[epoch] = {
                "original_count": len(rev_array),
                "clean_count": len(rev_array_clean),
                "outliers_removed": outliers_removed,
                "outlier_percentage": outlier_pct
            }
            
            print(f"Epoca {epoch}: {len(rev_array)} → {len(rev_array_clean)} "
                  f"({outlier_pct:.1f}% outlier rimossi)")
        else:
            print(f"⚠️ Epoca {epoch}: Tutti i valori erano outlier!")

# Crea DataFrame pulito
rev_df = pd.DataFrame.from_dict(rev_stats, orient='index').sort_index()

exchange = ccxt.binance()

# Configurazione epoche Solana
EPOCH_808_START = datetime(2025, 6, 25, 6, 58, 38)  # Inizio esatto epoca 808
EPOCH_DURATION_HOURS = 48  # Durata di ogni epoca in ore
START_EPOCH = 808
END_EPOCH = 841

print(f"Raccolta dati dall'epoca {START_EPOCH} all'epoca {END_EPOCH}")

# Lista per salvare i dati
epoch_data = []

# Funzione per ottenere il prezzo medio nei 2 giorni dell'epoca
def get_epoch_average_price(epoch_start, epoch_end):
    try:
        # Converti in timestamp milliseconds
        start_ms = int(epoch_start.timestamp() * 1000)
        end_ms = int(epoch_end.timestamp() * 1000)
        
        # Fetch dati OHLCV per i 2 giorni (48 ore con timeframe 1h)
        ohlc = exchange.fetch_ohlcv('SOL/USDT', timeframe='1h', since=start_ms, limit=48)
        
        if ohlc:
            df_period = pd.DataFrame(ohlc, columns=['timestamp','open','high','low','close','vol'])
            # Filtra solo i dati nel range dell'epoca
            df_period = df_period[df_period['timestamp'] <= end_ms]
            
            if not df_period.empty:
                return df_period['close'].mean()
        
        return None
    except Exception as e:
        print(f"Errore nel recupero dati: {e}")
        return None

# Raccolta dati per ogni epoca da 808 a 841
for epoch in range(START_EPOCH, END_EPOCH + 1):
    # Calcola inizio e fine dell'epoca (48 ore)
    hours_from_808 = (epoch - START_EPOCH) * EPOCH_DURATION_HOURS
    epoch_start = EPOCH_808_START + timedelta(hours=hours_from_808)
    epoch_end = epoch_start + timedelta(hours=EPOCH_DURATION_HOURS)
    
    print(f"Raccogliendo dati per epoca {epoch} ({epoch_start.strftime('%Y-%m-%d %H:%M')} - {epoch_end.strftime('%Y-%m-%d %H:%M')})")
    
    # Ottieni prezzo medio per questa epoca (media dei 2 giorni)
    avg_price = get_epoch_average_price(epoch_start, epoch_end)
    
    if avg_price is not None:
        epoch_data.append({
            'epoch': epoch,
            'start_date': epoch_start,
            'end_date': epoch_end,
            'avg_price_usd': avg_price
        })
        print(f"Epoca {epoch}: Prezzo medio ${avg_price:.4f}")
    else:
        print(f"Nessun dato disponibile per epoca {epoch}")
    
    # Pausa per evitare rate limiting
    time.sleep(0.1)

# Crea DataFrame finale
df_sol_epochs = pd.DataFrame(epoch_data)
sol_price_usd_mean = df_sol_epochs['avg_price_usd'].mean()  # Media di tutte le epoche

# 4. Calcolo revenue in USD
rev_usd_stats = rev_df * sol_price_usd_mean
rev_usd_stats = rev_usd_stats.rename(columns={
    "mean_revenue": "mean_revenue_usd",
    "std_revenue": "std_revenue_usd",
    "min_revenue": "min_revenue_usd",
    "max_revenue": "max_revenue_usd"
})

# 5. Combina SOL e USD in un unico DataFrame
combined_rev_df = rev_df.join(rev_usd_stats)

# 6. Media totale revenue su tutte le epoche filtrate
all_revenues_filtered = [v for e in valid_epochs for v in revenue_data.get(e, [])]
all_revenues_clean = remove_outliers_iqr(all_revenues_filtered, multiplier=1.5)
all_revenues_filtered=all_revenues_clean

mean_revenue_sol = np.mean(all_revenues_filtered)
mean_revenue_usd = mean_revenue_sol * sol_price_usd_mean


# 5. Numero bot unici per epoca
unique_bots_per_epoch = defaultdict(set)
with open(sandwich_path, 'r') as file:
    for line in tqdm(file):
        try:
            data = json.loads(line)
            epoch = data['bot1']['Details']['epoch']
            bot_name = data['bot1']['bot'].split(":")[-1].strip()
            if epoch in valid_epochs:
                unique_bots_per_epoch[epoch].add(bot_name)
        except KeyError:
            continue

unique_bot_counts = {epoch: len(bots) for epoch, bots in unique_bots_per_epoch.items()}
df_unique_bots = pd.DataFrame.from_dict(unique_bot_counts, orient='index', columns=["unique_bots"]).sort_index()

corr_records = []

with open(sandwich_path, 'r') as file:
    for line in tqdm(file):
        data = json.loads(line)
        corr_records.append(estrai_metriche_corr(data))

df_corr = pd.DataFrame(corr_records)

# Rimuovi righe con revenue NaN (se vuoi)
df_corr = df_corr.dropna(subset=['revenue'])

# --- CALCOLA CORRELAZIONI ---
pearson_corr = df_corr.corr(method='pearson')
spearman_corr = df_corr.corr(method='spearman')

# -------------------------------
# 📊 PARTE 3: PLOTTING
# -------------------------------

def plot_pie():
    labels = ['Meme Coin', 'Non-Meme Coin']
    sizes = [memecoin_sandwich, non_meme_sandwich]
    colors = ['orange', 'lightgray']
    plt.figure(figsize=(6, 6))
    plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    plt.title("Distribuzione sandwich token")
    plt.axis('equal')
    plt.tight_layout()
    plt.show()

def plot_top_tokens():
    colors = meme_df["Type"].map({"Meme": "orange", "Non-Meme": "gray"})
    plt.figure(figsize=(10, 6))
    plt.bar(meme_df["Token"], meme_df["Count"], color=colors)
    plt.title("Top 10 Token: Meme vs Non-Meme")
    plt.xlabel("Token")
    plt.ylabel("Conteggio")
    plt.xticks(rotation=45)
    plt.legend(handles=[
        Patch(facecolor='orange', label='Memecoin'),
        Patch(facecolor='gray', label='Non-Memecoin')
    ])
    plt.tight_layout()
    plt.show()

def plot_epoch_counts():
    epoch_df_filtered.plot(kind='bar', figsize=(12, 6), legend=False)
    plt.title("Numero di sandwich per epoca")
    plt.xlabel("Epoca")
    plt.ylabel("Conteggio")
    plt.tight_layout()
    plt.show()

def plot_unique_bots():
    plt.figure(figsize=(12, 6))
    plt.bar(df_unique_bots.index.astype(str), df_unique_bots["unique_bots"], color="purple")
    plt.title("Numero di bot unici per epoca")
    plt.xlabel("Epoca")
    plt.ylabel("Bot unici")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

def plot_revenue_and_price():
    fig, ax1 = plt.subplots(figsize=(14, 6))
    
    # Primo asse y: Revenue medio (barre verdi)
    color = 'green'
    ax1.set_xlabel("Epoca")
    ax1.set_ylabel("Revenue medio (SOL)", color=color)
    ax1.bar(rev_df.index.astype(str), rev_df['mean_revenue'], 
            color=color, alpha=0.6, label='Revenue medio')
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.tick_params(axis='x', rotation=45)
    
    # Secondo asse y: Prezzo SOL (linea arancione)
    ax2 = ax1.twinx()
    color = 'orange'
    ax2.set_ylabel("Prezzo medio SOL (USD)", color=color)
    ax2.plot(df_sol_epochs['epoch'].astype(str).to_numpy(), 
             df_sol_epochs['avg_price_usd'].to_numpy(),
             color=color, marker='o', linewidth=2, markersize=4, 
             label='Prezzo SOL')
    ax2.tick_params(axis='y', labelcolor=color)
    
    # Legend combinata
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    
    plt.tight_layout()
    plt.show()

def plot_and_print_sum_revenue_per_epoch():
    # Calcola la somma dei revenue per epoca (con outlier rimossi)
    sum_rev = {}
    for epoch, values in revenue_data.items():
        if epoch in valid_epochs:
            rev_array_clean = remove_outliers_iqr(values, multiplier=1.5)
            if len(rev_array_clean) > 0:
                sum_rev[epoch] = {
                    "sum_revenue_SOL": rev_array_clean.sum(),
                    "sum_revenue_USD": rev_array_clean.sum() * sol_price_usd_mean
                }
    
    df_sum_rev = pd.DataFrame.from_dict(sum_rev, orient='index').sort_index()
    
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
    ax2.plot(df_sol_epochs['epoch'].astype(str).to_numpy(), 
             df_sol_epochs['avg_price_usd'].to_numpy(),
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
    print("\n🔹 SOMMA DEI REVENUE PER EPOCA (con outlier rimossi):")
    print(df_sum_rev)
    
    # Stampa somma totale
    total_sol = df_sum_rev["sum_revenue_SOL"].sum()
    total_usd = df_sum_rev["sum_revenue_USD"].sum()
    print("\n🎯 SOMMA TOTALE DELLA REVENUE SU TUTTE LE EPOCHE:")
    print(f"→ {total_sol:.6f} SOL")
    print(f"→ ≈ {total_usd:.2f} USD (al prezzo medio di {sol_price_usd_mean:.2f} USD/SOL)")

def plot_sandwiches_per_epoch():
    """Mostra un istogramma con il numero di sandwich per epoca (filtrate via IQR)"""
    
    plt.figure(figsize=(14, 6))
    plt.bar(epoch_df_filtered.index.astype(str), 
            epoch_df_filtered['count'],
            color='coral', alpha=0.7)
    
    plt.xlabel("Epoca", fontsize=12)
    plt.ylabel("Numero di sandwich", fontsize=12)
    plt.xticks(rotation=45)
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.show()
    
    # Stampa statistiche
    print("\n📊 STATISTICHE SANDWICH PER EPOCA:")
    print(f"Totale sandwich (epoche filtrate): {epoch_df_filtered['count'].sum()}")
    print(f"Media sandwich per epoca: {epoch_df_filtered['count'].mean():.2f}")
    print(f"Epoca con più sandwich: {epoch_df_filtered['count'].idxmax()} ({epoch_df_filtered['count'].max()} sandwich)")
    print(f"Epoca con meno sandwich: {epoch_df_filtered['count'].idxmin()} ({epoch_df_filtered['count'].min()} sandwich)")

def plot_heatmap(corr_matrix, title):
    plt.figure(figsize=(10,8))
    sns.heatmap(corr_matrix, annot=True, cmap="coolwarm", center=0)
    plt.title(title)
    plt.xticks(rotation=45, ha='right')
    plt.yticks(rotation=0)
    plt.tight_layout()
    plt.show()

# -------------------------------
# 📤 ESECUZIONE DEI PLOT
# -------------------------------

plot_pie()
plot_top_tokens()
plot_epoch_counts()
plot_unique_bots()
plot_sandwiches_per_epoch()
plot_revenue_and_price()
plot_and_print_sum_revenue_per_epoch()
plot_heatmap(pearson_corr, "Heatmap Correlazione Pearson")
plot_heatmap(spearman_corr, "Heatmap Correlazione Spearman")


# -------------------------------
# 📃 STAMPA RISULTATI TESTUALI
# -------------------------------

def print_summary_statistics(
    bot_counter,
    all_bots,
    token_counter,
    meme_df,
    epoch_df_filtered,
    df_unique_bots,
    combined_rev_df,
    mean_revenue_sol,
    mean_revenue_usd,
    mean_sol_usd,
    total_sol_sandwich,
    memecoin_sandwich,
    #program_name_counter,
):
    print("🔹 TOP 10 BOT PIÙ PRESENTI:")
    print(bot_counter.most_common(10))
    
    print(f"\n🔹 NUMERO TOTALE DI BOT UNICI: {len(all_bots)}")
    
    print("\n🔹 TOP 10 TOKEN_END PIÙ USATI (con classificazione Meme/Non-Meme):")
    print(meme_df)

    print("\n🔹 NUMERO DI SANDWICH PER EPOCA (filtrate via IQR):")
    print(epoch_df_filtered)

    print("\n🔹 NUMERO DI BOT UNICI PER EPOCA (filtrate via IQR):")
    print(df_unique_bots)

    print("\n🔹 STATISTICHE DELLA REVENUE PER EPOCA:")
    print(combined_rev_df)

    print("\n🎯 MEDIA GLOBALE DELLA REVENUE SULLE EPOCHE FILTRATE:")
    print(f"→ {mean_revenue_sol:.6f} SOL")
    print(f"→ ≈ {mean_revenue_usd:.2f} USD (al prezzo medio di {mean_sol_usd:.2f} USD/SOL)")
    
    print(max(value_end_array))

    percent_meme = memecoin_sandwich / total_sol_sandwich * 100 if total_sol_sandwich else 0
    percent_non_meme = 100 - percent_meme
    print("\n🔹 DISTRIBUZIONE MEMECOIN NEI SANDWICH:")
    print(f"- Totale considerati: {total_sol_sandwich}")
    print(f"- Con memecoin: {memecoin_sandwich} ({percent_meme:.2f}%)")
    print(f"- Con token NON meme: {total_sol_sandwich - memecoin_sandwich} ({percent_non_meme:.2f}%)")
    

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
