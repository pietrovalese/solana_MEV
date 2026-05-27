import json
import re
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import networkx as nx
from scipy import stats
from statsmodels.tsa.stattools import grangercausalitytests
from statsmodels.tsa.api import VAR

warnings.filterwarnings('ignore')
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

# ─── Caricamento dati ────────────────────────────────────────────────────────

def load_tokens_txt(path):
    data = []
    with open(path) as f:
        for line in f:
            m = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}):\d{2}:\s*(\d+)\s*token", line.strip())
            if m:
                data.append({"hour": int(m.group(2)), "tokens": int(m.group(3))})
    df = pd.DataFrame(data)
    if df.empty:
        raise ValueError(f"Nessun dato in {path}")
    return df.groupby("hour")["tokens"].mean()


def _extract_blocktimes_jsonl(path, keys):
    """Legge un .jsonl estraendo blockTime secondo lo schema indicato in keys."""
    times = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            for key in keys:
                src = obj.get(key, obj) if key else obj
                if isinstance(src, list):
                    for item in src:
                        bt = (item or {}).get("Details", {}).get("blockTime")
                        if bt:
                            times.append(bt)
                else:
                    bt = (src or {}).get("Details", {}).get("blockTime")
                    if bt:
                        times.append(bt)
    return times


def load_jsonl_hourly(path, keys):
    times = _extract_blocktimes_jsonl(path, keys)
    if not times:
        raise ValueError(f"Nessun blockTime trovato in {path}")
    df = pd.DataFrame({"blockTime": times})
    df["hour"] = pd.to_datetime(df["blockTime"], unit="s", errors="coerce").dt.hour
    df.dropna(inplace=True)
    return df.groupby("hour").size()


def load_event_times(path, keys):
    times = _extract_blocktimes_jsonl(path, keys)
    return [pd.to_datetime(t, unit="s") for t in times]


def series_per_interval(event_times, freq, start=None, end=None):
    if not event_times:
        return pd.Series(dtype=float)
    s = pd.Series(1, index=pd.to_datetime(event_times)).sort_index()
    s = s.groupby(s.index.floor(freq)).sum()
    start = start or s.index.min().floor(freq)
    end   = end   or s.index.max().ceil(freq)
    return s.reindex(pd.date_range(start=start, end=end, freq=freq), fill_value=0)


def gini(x):
    x = np.sort(np.array(x, dtype=float))
    n = len(x)
    if np.all(x == 0):
        return 0.0
    return (2 * np.dot(np.arange(1, n + 1), x)) / (n * x.sum()) - (n + 1) / n


# ─── Dati orari (Script 1) ───────────────────────────────────────────────────

tokens_hourly     = load_tokens_txt("hours.txt")
sandwiches_hourly = load_jsonl_hourly("sandwiches_annotated.jsonl", ["bot1", "bot2", "victims"])
arbitrages_hourly = load_jsonl_hourly("arbitrages_annotated.jsonl", [None])

df_hourly = pd.DataFrame({
    "tokens":     tokens_hourly,
    "sandwiches": sandwiches_hourly,
    "arbitrages": arbitrages_hourly
}).fillna(0)

# ─── Dati timestamp (Script 2) ───────────────────────────────────────────────

tokens_df = pd.read_csv("memecoin.csv", parse_dates=["launched_at"])
tokens_df["launched_at"] = pd.to_datetime(
    tokens_df["launched_at"].str.replace(" (stimato)", "", regex=False))
token_times     = tokens_df["launched_at"].dropna()
sandwich_times  = load_event_times("sandwiches_annotated.jsonl", ["bot1"])
arbitrage_times = load_event_times("arbitrages_annotated.jsonl", [None])

print(f"Token: {len(tokens_df)}  |  Sandwich: {len(sandwich_times)}  |  Arbitrage: {len(arbitrage_times)}")

frequencies = {"5s": "5S", "30s": "30S", "1min": "1T", "15min": "15T",
               "30min": "30T", "1hour": "H", "2hour": "2H", "4hour": "4H"}

datasets = {}
for name, freq in frequencies.items():
    ts = series_per_interval(token_times,    freq)
    ss = series_per_interval(sandwich_times, freq)
    ar = series_per_interval(arbitrage_times, freq)
    common_start = max(ts.index.min(), ss.index.min(), ar.index.min())
    common_end   = min(ts.index.max(), ss.index.max(), ar.index.max())
    df = pd.DataFrame({"tokens": ts, "sandwiches": ss, "arbitrages": ar}).loc[
        common_start:common_end].fillna(0)
    datasets[name] = df
    print(f"{name}: {len(df)} intervalli  |  durata: {common_end - common_start}")

df_1h = datasets["1hour"]

# ─── Plot 1: Distribuzione oraria grezza ─────────────────────────────────────

plt.figure(figsize=(12, 5))
for col, marker in zip(df_hourly.columns, ["o", "s", "^"]):
    plt.plot(df_hourly.index, df_hourly[col], label=col.capitalize(), marker=marker)
plt.xticks(range(24))
plt.xlabel("Ora (UTC)"); plt.ylabel("Attivita media / conteggio")
plt.title("Distribuzione oraria: Token vs Sandwiches vs Arbitrages")
plt.legend(); plt.grid(True, linestyle="--", alpha=0.6); plt.tight_layout(); plt.show()

# ─── Plot 2: Min-Max normalizzato ────────────────────────────────────────────

df_minmax = df_hourly.div(df_hourly.max()).fillna(0)
plt.figure(figsize=(12, 5))
for col, marker in zip(df_minmax.columns, ["o", "s", "^"]):
    plt.plot(df_minmax.index, df_minmax[col], label=col.capitalize(), marker=marker)
plt.xticks(range(24))
plt.xlabel("Ora (UTC)"); plt.ylabel("Valore normalizzato (0-1)")
plt.title("Distribuzione oraria normalizzata (Min-Max)")
plt.legend(); plt.grid(True, linestyle="--", alpha=0.6); plt.tight_layout(); plt.show()

# ─── Plot 3: Densita (somma = 1) ─────────────────────────────────────────────

df_density = df_hourly.div(df_hourly.sum())
plt.figure(figsize=(12, 5))
for col, marker in zip(df_density.columns, ["o", "s", "^"]):
    plt.plot(df_density.index, df_density[col], label=col.capitalize(), marker=marker)
plt.xticks(range(24))
plt.xlabel("Ora (UTC)"); plt.ylabel("Frequenza relativa")
plt.title("Distribuzione oraria per densita (somma = 1)")
plt.legend(); plt.grid(True, linestyle="--", alpha=0.6); plt.tight_layout(); plt.show()

# ─── Correlazione + heatmap ──────────────────────────────────────────────────

corr_matrix = df_hourly.corr(method="pearson")
plt.figure(figsize=(6, 5))
sns.heatmap(corr_matrix, annot=True, cmap="coolwarm", center=0,
            fmt=".2f", linewidths=0.5, square=True,
            cbar_kws={"shrink": 0.8, "label": "Correlazione (Pearson)"})
plt.title("Heatmap correlazioni distribuzioni orarie")
plt.tight_layout(); plt.show()
print("\nCorrelazione (Pearson):\n", corr_matrix)

# ─── Gini ────────────────────────────────────────────────────────────────────

for col in df_density.columns:
    print(f"Gini {col}: {gini(df_density[col]):.4f}")

# ─── Test 1: Cross-correlazione ──────────────────────────────────────────────

def ccf_manual(x, y, max_lag=24):
    lags = range(-max_lag, max_lag + 1)
    vals = []
    for lag in lags:
        if lag < 0:
            vals.append(np.corrcoef(x[:lag], y[-lag:])[0, 1])
        elif lag > 0:
            vals.append(np.corrcoef(x[lag:], y[:-lag])[0, 1])
        else:
            vals.append(np.corrcoef(x, y)[0, 1])
    return list(lags), vals

pairs = [("sandwiches", "tokens"), ("arbitrages", "tokens"), ("sandwiches", "arbitrages")]
fig, axes = plt.subplots(3, 1, figsize=(14, 10))
for ax, (xn, yn) in zip(axes, pairs):
    lags, vals = ccf_manual(df_1h[xn].values, df_1h[yn].values)
    opt_lag = lags[np.argmax(np.abs(vals))]
    ax.plot(lags, vals, linewidth=2)
    ax.axhline(0, color="black", linestyle="--", alpha=0.3)
    ax.axvline(0, color="red",   linestyle="--", alpha=0.3)
    ax.axvline(opt_lag, color="green", linestyle="--", alpha=0.5,
               label=f"Max corr a lag {opt_lag}")
    ax.set_title(f"{xn} vs {yn} — lag ottimale: {opt_lag}h (r={vals[lags.index(opt_lag)]:.3f})")
    ax.set_xlabel("Lag (ore)"); ax.set_ylabel("Cross-correlazione")
    ax.grid(True, alpha=0.3); ax.legend()
    print(f"{xn} vs {yn}: lag ottimale = {opt_lag}h")
plt.tight_layout()
plt.savefig("ccf_analysis.png", dpi=300, bbox_inches="tight")
print("Salvato: ccf_analysis.png")

# ─── Test 2: Granger multi-risoluzione ───────────────────────────────────────

series_names = ["tokens", "sandwiches", "arbitrages"]
multi_res = {}

for freq_name, df in datasets.items():
    df_log  = np.log1p(df)
    max_lag = max(1, min(5, len(df) // 20))
    res = {}
    for y in series_names:
        for x in series_names:
            if x == y:
                continue
            try:
                gr = grangercausalitytests(df_log[[y, x]].fillna(0), max_lag, verbose=False)
                best = min(gr, key=lambda lag: gr[lag][0]["ssr_ftest"][1])
                p = gr[best][0]["ssr_ftest"][1]
                res[f"{x}_to_{y}"] = {"p_value": p, "lag": best, "significant": p < 0.05}
                if p < 0.05:
                    print(f"[{freq_name}] {x} -> {y}: p={p:.6f}  lag={best}")
            except Exception:
                pass
    multi_res[freq_name] = res

# ─── Test 3: Pattern temporali ───────────────────────────────────────────────

df_t = df_1h.copy()
df_t["hour"]       = df_t.index.hour
df_t["day_name"]   = df_t.index.day_name()
df_t["dayofweek"]  = df_t.index.dayofweek

hourly_pat = df_t.groupby("hour")[series_names].mean()
daily_pat  = df_t.groupby("day_name")[series_names].mean().reindex(
    ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"])

fig, axes = plt.subplots(2, 1, figsize=(14, 10))
for col in series_names:
    axes[0].plot(hourly_pat.index, hourly_pat[col], marker="o", label=col.capitalize())
axes[0].set(xlabel="Ora (UTC)", ylabel="Conteggio medio",
            title="Pattern per ora del giorno")
axes[0].set_xticks(range(0, 24, 2)); axes[0].legend(); axes[0].grid(True, alpha=0.3)

x_pos, width = range(7), 0.25
for i, col in enumerate(series_names):
    axes[1].bar([x + (i-1)*width for x in x_pos], daily_pat[col],
                width, label=col.capitalize(), alpha=0.8)
axes[1].set(xlabel="Giorno", ylabel="Conteggio medio", title="Pattern per giorno della settimana")
axes[1].set_xticks(list(x_pos))
axes[1].set_xticklabels(daily_pat.index, rotation=45)
axes[1].legend(); axes[1].grid(True, alpha=0.3, axis="y")
plt.tight_layout()
plt.savefig("temporal_patterns.png", dpi=300, bbox_inches="tight")
print("Salvato: temporal_patterns.png")

print("\nKruskal-Wallis (effetto ora del giorno):")
for col in series_names:
    groups = [df_t[df_t["hour"] == h][col].values for h in range(24)]
    h, p = stats.kruskal(*groups)
    print(f"  {col}: H={h:.2f}  p={p:.6f}  {'SIGNIFICATIVO' if p < 0.05 else ''}")

# ─── Test 4: Rolling Granger ─────────────────────────────────────────────────

df_log   = np.log1p(df_1h)
win, step = 168, 24
roll = {"sandwiches_to_tokens": [], "arbitrages_to_tokens": [], "timestamps": []}

for i in range(0, len(df_log) - win, step):
    w = df_log.iloc[i:i+win]
    ts = w.index[win // 2]
    try:
        p_s = min(grangercausalitytests(w[["tokens","sandwiches"]].fillna(0), 3, verbose=False)[lag][0]["ssr_ftest"][1]
                  for lag in range(1, 4))
        p_a = min(grangercausalitytests(w[["tokens","arbitrages"]].fillna(0), 3, verbose=False)[lag][0]["ssr_ftest"][1]
                  for lag in range(1, 4))
        roll["sandwiches_to_tokens"].append(p_s)
        roll["arbitrages_to_tokens"].append(p_a)
        roll["timestamps"].append(ts)
    except Exception:
        continue

fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(roll["timestamps"], roll["sandwiches_to_tokens"], label="Sandwiches -> Tokens")
ax.plot(roll["timestamps"], roll["arbitrages_to_tokens"], label="Arbitrages -> Tokens")
ax.axhline(0.05, color="red", linestyle="--", label="p=0.05")
ax.set_yscale("log"); ax.set(xlabel="Tempo", ylabel="p-value",
    title="Rolling Granger Causality (finestre di 1 settimana)")
ax.legend(); ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("rolling_granger.png", dpi=300, bbox_inches="tight")
print("Salvato: rolling_granger.png")

# ─── Test 5: Lead-lag per lag specifici ──────────────────────────────────────

print("\nGranger MEV -> Tokens per lag specifici:")
for lag in range(1, 13):
    try:
        p_s = grangercausalitytests(df_log[["tokens","sandwiches"]].fillna(0), lag, verbose=False)[lag][0]["ssr_ftest"][1]
        p_a = grangercausalitytests(df_log[["tokens","arbitrages"]].fillna(0), lag, verbose=False)[lag][0]["ssr_ftest"][1]
        print(f"  Lag {lag:2d}h  | Sandwiches p={p_s:.6f} {'OK' if p_s<0.05 else '  '}"
              f"  | Arbitrages p={p_a:.6f} {'OK' if p_a<0.05 else '  '}")
    except Exception:
        continue

# ─── Test 6: Controllo volatilita ────────────────────────────────────────────

df_1h["volatility"]     = df_1h["arbitrages"].rolling(6, center=True).std().fillna(0)
df_1h["high_volatility"]= (df_1h["volatility"] > df_1h["volatility"].median()).astype(int)

for label, subset in [("Alta volatilita", df_1h[df_1h["high_volatility"]==1]),
                       ("Bassa volatilita", df_1h[df_1h["high_volatility"]==0])]:
    print(f"\n{label} ({len(subset)} ore):")
    if len(subset) > 20:
        dl = np.log1p(subset[series_names].fillna(0))
        for y, x in [("tokens","sandwiches"), ("tokens","arbitrages")]:
            try:
                gr = grangercausalitytests(dl[[y,x]], 3, verbose=False)
                p  = min(gr[lag][0]["ssr_ftest"][1] for lag in gr)
                print(f"  {x} -> {y}: p={p:.4f} {'OK' if p<0.05 else ''}")
            except Exception as e:
                print(f"  Errore: {e}")

# ─── Test 7: VAR multivariato ────────────────────────────────────────────────

var_results = {}
for freq_name, df in datasets.items():
    df_log = np.log1p(df).astype(float)
    if len(df_log) < 30:
        continue
    try:
        model = VAR(df_log)
        sel_lag = max(1, model.select_order(10).aic or 1)
        fitted  = model.fit(sel_lag)
        print(f"\nVAR [{freq_name}]  lag={sel_lag}")

        tests_def = {
            "tokens->sandwiches":   ("sandwiches", ["tokens"]),
            "tokens->arbitrages":   ("arbitrages", ["tokens"]),
            "sandwiches->tokens":   ("tokens",     ["sandwiches"]),
            "arbitrages->tokens":   ("tokens",     ["arbitrages"]),
            "sandwiches->arbitrages":("arbitrages", ["sandwiches"]),
            "arbitrages->sandwiches":("sandwiches", ["arbitrages"]),
            "MEV->tokens":          ("tokens",     ["sandwiches","arbitrages"]),
            "tokens->MEV":          (["sandwiches","arbitrages"], ["tokens"]),
        }
        freq_res = {}
        for name, (endog, exog) in tests_def.items():
            p = fitted.test_causality(endog, exog, kind="wald").pvalue
            freq_res[name] = p
            print(f"  {name:40s}  p={p:.6f}  {'SIGNIFICATIVO' if p<0.05 else ''}")
        var_results[freq_name] = freq_res
    except Exception as e:
        print(f"  Errore VAR [{freq_name}]: {e}")

heatmap_df = pd.DataFrame(var_results).T
if not heatmap_df.empty:
    plt.figure(figsize=(16, 8))
    sns.heatmap(heatmap_df.astype(float), annot=True, fmt=".3f",
                cmap="viridis_r", linewidths=0.5)
    plt.title("VAR Multivariato — p-values")
    plt.tight_layout()
    plt.savefig("var_multivariate_heatmap.png", dpi=300)
    print("Salvato: var_multivariate_heatmap.png")

# ─── Granger Causality Network ────────────────────────────────────────────────
# (usa i p-value del Granger orario di Script 1)

pval_matrix = pd.DataFrame(np.nan, index=series_names, columns=series_names)
df_log_h = np.log1p(df_hourly)
for y in series_names:
    for x in series_names:
        if x == y:
            continue
        try:
            gr = grangercausalitytests(df_log_h[[y,x]].fillna(0), 3, verbose=False)
            pval_matrix.loc[y, x] = min(gr[lag][0]["ssr_ftest"][1] for lag in gr)
        except Exception:
            pass

print("\nGranger p-value matrix (oraria):\n", pval_matrix)
signif = (pval_matrix < 0.05).astype(int)
print("\nMatrice binaria di causalita:\n", signif)

G = nx.DiGraph()
G.add_nodes_from(series_names)
for y in series_names:
    for x in series_names:
        if x == y:
            continue
        p = pval_matrix.loc[y, x]
        if pd.notna(p) and p < 0.05:
            G.add_edge(x, y, weight=1/p, pvalue=p)

pos = nx.spring_layout(G, seed=42, k=1.2)
plt.figure(figsize=(8, 6))
plt.gca().set_facecolor("#f0f0f0")
weights = [G[u][v]["weight"] * 0.5 for u, v in G.edges()]
nx.draw_networkx_nodes(G, pos, node_size=2500, node_color="skyblue",
                       edgecolors="black", linewidths=1.5)
nx.draw_networkx_labels(G, pos, font_size=12, font_weight="bold")
nx.draw_networkx_edges(G, pos, arrowstyle="-|>", arrowsize=20,
                       width=weights, edge_color="red")
nx.draw_networkx_edge_labels(
    G, pos,
    edge_labels={(u, v): f"p={G[u][v]['pvalue']:.3g}" for u, v in G.edges()},
    font_color="black", label_pos=0.5)
plt.title("Granger Causality Network", fontsize=14, fontweight="bold")
plt.axis("off"); plt.tight_layout(); plt.show()

# ─── Test 8: Transfer Entropy (IDTxl, opzionale) ─────────────────────────────

try:
    from idtxl.data import Data
    from idtxl.multivariate_te import MultivariateTE

    target_freq = "1min"
    df_te = (datasets[target_freq].copy() if target_freq in datasets else None)
    if df_te is not None:
        df_te = ((df_te - df_te.mean()) / df_te.std()).fillna(0)
        df_te += np.random.normal(0, 1e-6, df_te.shape)
        data_idtxl = Data(df_te[series_names].values.T, dim_order="ps", normalise=False)

        results = MultivariateTE().analyse_network(
            settings={"cmi_estimator": "JidtGaussianCMI",
                      "max_lag_sources": 5, "min_lag_sources": 1, "verbose": False},
            data=data_idtxl)

        names = {i: n for i, n in enumerate(series_names)}
        for tidx in range(3):
            tr = results.get_single_target(tidx)
            sources = tr.get("selected_vars_sources", [])
            tes     = tr.get("selected_sources_te",   [0]*len(sources))
            pvals   = tr.get("selected_sources_pval", [1]*len(sources))
            for i, (sidx, lag) in enumerate(sources):
                p = pvals[i]; te = tes[i]
                print(f"TE  {names[sidx]} -> {names[tidx]}  TE={te:.6f}  p={p:.6f}  lag={lag}"
                      f"  {'SIGNIFICATIVO' if p<0.05 else ''}")
    print("Transfer Entropy completata.")
except ImportError:
    print("idtxl non installato — Transfer Entropy saltata.")
except Exception as e:
    print(f"Errore Transfer Entropy: {e}")

print("\nAnalisi completata.")