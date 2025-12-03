import json
import pandas as pd
import matplotlib.pyplot as plt
import re
from datetime import datetime
import seaborn as sns

# === 1️⃣ Funzioni di utilità ===

def load_tokens_txt(path):
    """Legge un file .txt con righe del tipo 'YYYY-MM-DD HH:MM: N token'."""
    data = []
    with open(path, "r") as f:
        for line in f:
            match = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}):\d{2}:\s*(\d+)\s*token", line.strip())
            if match:
                date = match.group(1)
                hour = int(match.group(2))
                tokens = int(match.group(3))
                data.append({"date": date, "hour": hour, "tokens": tokens})

    df = pd.DataFrame(data)
    if df.empty:
        raise ValueError(f"Nessun dato trovato in {path}")
    return df.groupby("hour")["tokens"].mean()


def safe_get_blocktime(obj):
    """Estrae blockTime in modo sicuro."""
    try:
        return obj.get("Details", {}).get("blockTime", None)
    except AttributeError:
        return None


def load_jsonl_sandwiches(path):
    """Legge il file sandwiches_annotated.jsonl e raccoglie tutti i blockTime."""
    block_times = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                print(f"❌ Riga non valida (saltata): {line[:100]}...")
                continue

            # bot1, bot2, victims
            for key in ["bot1", "bot2"]:
                bt = safe_get_blocktime(data.get(key, {}))
                if bt:
                    block_times.append(bt)
            for victim in data.get("victims", []):
                bt = safe_get_blocktime(victim)
                if bt:
                    block_times.append(bt)

    if not block_times:
        raise ValueError(f"Nessun blockTime trovato in {path}")

    df = pd.DataFrame(block_times, columns=["blockTime"])
    df["datetime"] = pd.to_datetime(df["blockTime"], unit="s", errors="coerce")
    df.dropna(subset=["datetime"], inplace=True)
    df["hour"] = df["datetime"].dt.hour
    return df.groupby("hour").size()


def load_jsonl_arbitrages(path):
    """Legge il file arbitrages_annotated.jsonl e raccoglie i blockTime."""
    block_times = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                print(f"⚠️ Riga non valida (saltata): {line[:100]}...")
                continue

            bt = safe_get_blocktime(data)
            if bt:
                block_times.append(bt)

    if not block_times:
        raise ValueError(f"Nessun blockTime trovato in {path}")

    df = pd.DataFrame(block_times, columns=["blockTime"])
    df["datetime"] = pd.to_datetime(df["blockTime"], unit="s", errors="coerce")
    df.dropna(subset=["datetime"], inplace=True)
    df["hour"] = df["datetime"].dt.hour
    return df.groupby("hour").size()

import numpy as np

def gini(x):
    """
    Compute the Gini coefficient of array x.
    """
    x = np.array(x, dtype=float)
    if np.amin(x) < 0:
        raise ValueError("Values cannot be negative for Gini computation.")
    if np.all(x == 0):
        return 0.0
    
    # Sort values
    x_sorted = np.sort(x)
    n = len(x_sorted)
    
    # Gini formula
    cumulative = np.cumsum(x_sorted)
    gini_index = (2 * np.sum((np.arange(1, n+1) * x_sorted))) / (n * np.sum(x_sorted)) - (n + 1) / n
    
    return gini_index

# === 2️⃣ Carica i dati ===

tokens_hourly = load_tokens_txt("hours.txt")
sandwiches_hourly = load_jsonl_sandwiches("sandwiches_annotated.jsonl")
arbitrages_hourly = load_jsonl_arbitrages("arbitrages_annotated.jsonl")

# === 3️⃣ Unisci e allinea le distribuzioni ===

df_compare = pd.DataFrame({
    "tokens": tokens_hourly,
    "sandwiches": sandwiches_hourly,
    "arbitrages": arbitrages_hourly
}).fillna(0)


# === 4️⃣ Plot originale ===

plt.figure(figsize=(12, 6))
plt.plot(df_compare.index, df_compare["tokens"], label="Token (txt)", marker="o")
plt.plot(df_compare.index, df_compare["sandwiches"], label="Sandwiches (jsonl)", marker="s")
plt.plot(df_compare.index, df_compare["arbitrages"], label="Arbitrages (jsonl)", marker="^")

plt.xticks(range(0, 24))
plt.xlabel("Ora del giorno (UTC)")
plt.ylabel("Attività media / conteggio")
plt.title("Distribuzione oraria – Token vs Sandwiches vs Arbitrages")
plt.legend()
plt.grid(True, linestyle="--", alpha=0.6)
plt.tight_layout()
plt.show()

# === 5️⃣ Normalizzazione Min–Max (0–1) ===

df_minmax = df_compare.copy()
for col in df_minmax.columns:
    max_val = df_minmax[col].max()
    if max_val > 0:
        df_minmax[col] = df_minmax[col] / max_val

plt.figure(figsize=(12, 6))
plt.plot(df_minmax.index, df_minmax["tokens"], label="Tokens", marker="o")
plt.plot(df_minmax.index, df_minmax["sandwiches"], label="Sandwiches", marker="s")
plt.plot(df_minmax.index, df_minmax["arbitrages"], label="Arbitrages", marker="^")

plt.xticks(range(0, 24))
plt.xlabel("Hour of day (UTC)")
plt.ylabel("Normalized value (0–1)")
plt.legend()
plt.grid(True, linestyle="--", alpha=0.6)
plt.tight_layout()
plt.show()

# === 6️⃣ Normalizzazione per densità (somma = 1) ===

df_density = df_compare.div(df_compare.sum())

plt.figure(figsize=(12, 6))
plt.plot(df_density.index, df_density["tokens"], label="Token (densità)", marker="o")
plt.plot(df_density.index, df_density["sandwiches"], label="Sandwiches (densità)", marker="s")
plt.plot(df_density.index, df_density["arbitrages"], label="Arbitrages (densità)", marker="^")

plt.xticks(range(0, 24))
plt.xlabel("Ora del giorno (UTC)")
plt.ylabel("Frequenza relativa")
plt.title("Distribuzioni orarie normalizzate (densità, somma = 1)")
plt.legend()
plt.grid(True, linestyle="--", alpha=0.6)
plt.tight_layout()
plt.show()

# === 7️⃣ Correlazione tra distribuzioni ===
corr_matrix = df_compare.corr(method="pearson")
# === Heatmap ===
plt.figure(figsize=(6, 5))
sns.heatmap(
    corr_matrix,
    annot=True,           # mostra i valori numerici
    cmap="coolwarm",       # scala di colori rosso/blu
    center=0,              # colore neutro per 0
    fmt=".2f",             # 2 cifre decimali
    linewidths=0.5,
    square=True,
    cbar_kws={"shrink": 0.8, "label": "Correlazione (Pearson)"}
)

plt.title("Heatmap correlazioni tra distribuzioni orarie")
plt.tight_layout()
plt.show()

print("\n🔍 Correlazione tra distribuzioni orarie (Pearson):")
print(corr_matrix)

print("\n📈 Distribuzioni originali:")
print(df_compare)

gini_tokens = gini(df_density["tokens"])
gini_sandwiches = gini(df_density["sandwiches"])
gini_arbs = gini(df_density["arbitrages"])

print("Gini Tokens:", gini_tokens)
print("Gini Sandwiches:", gini_sandwiches)
print("Gini Arbitrages:", gini_arbs)


from statsmodels.tsa.stattools import grangercausalitytests
import pandas as pd
import numpy as np

# Prepara il dataset per il Granger test
df_granger = df_compare.copy().fillna(0)
df_granger = df_granger.sort_index()  # ordina per sicurezza

series_names = ["tokens", "sandwiches", "arbitrages"]
max_lag = 3  # massimo lag da testare

# Matrice dei p-value più bassi
pval_matrix = pd.DataFrame(np.nan, index=series_names, columns=series_names)

print("\n=== Granger Causality Test (dettagli per coppia) ===")

for y in series_names:
    for x in series_names:
        if x == y:
            continue

        print(f"\n{x} (cause) → {y} (effetto):")
        df_test = df_granger[[y, x]].fillna(0)

        # Test Granger con stampa dettagliata
        results = grangercausalitytests(df_test, max_lag, verbose=True)

        # Trova il p-value più basso tra tutti i lag
        min_p = min([results[lag][0]['ssr_ftest'][1] for lag in results])
        pval_matrix.loc[y, x] = min_p

# Stampa la tabella dei p-value più bassi
print("\n📊 Tabella dei p-value più bassi per Granger causality (lag 1–3):")
print(pval_matrix)

# Crea anche la matrice binaria di significatività
signif_matrix = (pval_matrix < 0.05).astype(int)
print("\n📈 Matrice binaria di causalità (1 = significativo, 0 = non significativo):")
print(signif_matrix)

import networkx as nx
import matplotlib.pyplot as plt

# Serie e matrice dei p-value
series_names = ["tokens", "sandwiches", "arbitrages"]
pval_matrix = pd.DataFrame({
    "tokens": [np.nan, 0.015637, 0.016758],
    "sandwiches": [2.9e-05, np.nan, 0.484935],
    "arbitrages": [3.1e-05, 0.203171, np.nan]
}, index=series_names)

# Crea grafo diretto
G = nx.DiGraph()

# Aggiungi nodi
for node in series_names:
    G.add_node(node)

# Aggiungi archi pesati (solo p < 0.05)
for y in series_names:
    for x in series_names:
        if x == y:
            continue
        p = pval_matrix.loc[y, x]
        if pd.notna(p) and p < 0.05:
            weight = 1 / p
            G.add_edge(x, y, weight=weight, pvalue=p)

# Layout tipo molla per distribuzione più naturale
pos = nx.spring_layout(G, seed=42, k=1.2)

# Disegna il grafo
plt.figure(figsize=(8,6))
plt.gca().set_facecolor('#f0f0f0')  # sfondo chiaro

# Pesatura degli archi per spessore
weights = [G[u][v]['weight']*0.5 for u,v in G.edges()]

# Disegna nodi con ombra
nx.draw_networkx_nodes(G, pos, node_size=2500, node_color='skyblue', edgecolors='black', linewidths=1.5)
nx.draw_networkx_labels(G, pos, font_size=12, font_weight='bold')

# Disegna archi direzionali
nx.draw_networkx_edges(G, pos, arrowstyle='-|>', arrowsize=20, width=weights, edge_color='red')

# Etichette degli archi con p-value
edge_labels = {(u, v): f"p={G[u][v]['pvalue']:.3g}" for u, v in G.edges()}
nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color='black', label_pos=0.5)

plt.title("Granger Causality Network (pesato per p-value)", fontsize=14, fontweight='bold')
plt.axis('off')
plt.tight_layout()
plt.show()
