import pandas as pd
import json
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
from statsmodels.tsa.stattools import grangercausalitytests, adfuller, ccf
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from scipy import stats
from scipy.stats import spearmanr, pearsonr
import warnings
warnings.filterwarnings('ignore')

plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

print("=" * 80)
print("ADVANCED MEV ANALYSIS: Extended Tests & Robustness Checks")
print("=" * 80)

# === Load Data Functions ===
def load_sandwich_times(path):
    times = []
    with open(path, "r") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if "bot1" in data and "Details" in data["bot1"]:
                    bt = data["bot1"]["Details"].get("blockTime")
                    if bt:
                        times.append(pd.to_datetime(bt, unit="s"))
            except json.JSONDecodeError:
                continue
    return times

def load_arbitrage_times(path):
    times = []
    with open(path, "r") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if "Details" in data:
                    bt = data["Details"].get("blockTime")
                    if bt:
                        times.append(pd.to_datetime(bt, unit="s"))
            except json.JSONDecodeError:
                continue
    return times

print("\n[1/10] Loading data...")
tokens_df = pd.read_csv("memecoin.csv", parse_dates=["launched_at"])
tokens_df["launched_at"] = pd.to_datetime(
    tokens_df["launched_at"].str.replace(" (stimato)", "", regex=False)
)
sandwich_times = load_sandwich_times("sandwiches_annotated.jsonl")
arbitrages_times = load_arbitrage_times("arbitrages_annotated.jsonl")

print(f"   ✓ Loaded {len(tokens_df)} tokens, {len(sandwich_times)} sandwiches, {len(arbitrages_times)} arbitrages")

# === Create Multiple Time Resolution Series ===
def series_per_interval(event_times, freq='T', start=None, end=None):
    if len(event_times) == 0:
        return pd.Series(dtype=float)
    s = pd.Series(1, index=pd.to_datetime(event_times))
    s = s.sort_index()
    if start is None:
        start = s.index.min().floor(freq)
    if end is None:
        end = s.index.max().ceil(freq)
    s = s.groupby(s.index.floor(freq)).sum()
    all_intervals = pd.date_range(start=start, end=end, freq=freq)
    s = s.reindex(all_intervals, fill_value=0)
    return s

print("\n[2/10] Creating time series at multiple resolutions...")

# Store datasets at different frequencies
datasets = {}
frequencies = {
    '5s': '5S',        # 1 secondo
    '30s': '30S',      # 30 secondi
    '1min': '1T',      # 1 minuto
    '15min': '15T',    # 15 minuti
    '30min': '30T',    # 30 minuti
    '1hour': 'H',      # 1 ora
    '2hour': '2H',     # 2 ore
    '4hour': '4H'      # 4 ore
}

token_times = tokens_df["launched_at"].dropna()

for name, freq in frequencies.items():
    tokens_series = series_per_interval(token_times, freq=freq)
    sandwich_series = series_per_interval(sandwich_times, freq=freq)
    arbitrages_series = series_per_interval(arbitrages_times, freq=freq)
    
    common_start = max(tokens_series.index.min(), 
                      sandwich_series.index.min(), 
                      arbitrages_series.index.min())
    common_end = min(tokens_series.index.max(), 
                    sandwich_series.index.max(), 
                    arbitrages_series.index.max())
    print(f"Periodo di osservazione: {common_end-common_start}")
    df = pd.DataFrame({
        "tokens": tokens_series.loc[common_start:common_end],
        "sandwiches": sandwich_series.loc[common_start:common_end],
        "arbitrages": arbitrages_series.loc[common_start:common_end]
    }).fillna(0)
    
    datasets[name] = df
    print(f"   ✓ {name}: {len(df)} intervals")

# ============================================================
# TEST 1: Cross-Correlation Function (CCF) Analysis
# ============================================================
print("\n" + "=" * 80)
print("TEST 1: CROSS-CORRELATION ANALYSIS")
print("=" * 80)
print("Purpose: Find optimal lag and check lead-lag relationships\n")

def calculate_ccf(x, y, max_lag=24):
    """Calculate cross-correlation function"""
    ccf_values = []
    lags = range(-max_lag, max_lag + 1)
    
    for lag in lags:
        if lag < 0:
            corr = np.corrcoef(x[:lag], y[-lag:])[0, 1]
        elif lag > 0:
            corr = np.corrcoef(x[lag:], y[:-lag])[0, 1]
        else:
            corr = np.corrcoef(x, y)[0, 1]
        ccf_values.append(corr)
    
    return lags, ccf_values

df_1h = datasets['1hour']
fig, axes = plt.subplots(3, 1, figsize=(14, 10))
pairs = [
    ('sandwiches', 'tokens', 'Sandwiches vs Tokens'),
    ('arbitrages', 'tokens', 'Arbitrages vs Tokens'),
    ('sandwiches', 'arbitrages', 'Sandwiches vs Arbitrages')
]

ccf_results = {}

for idx, (x_name, y_name, title) in enumerate(pairs):
    x = df_1h[x_name].values
    y = df_1h[y_name].values
    
    lags, ccf_vals = calculate_ccf(x, y, max_lag=24)
    ccf_results[f"{x_name}_to_{y_name}"] = (lags, ccf_vals)
    
    max_corr_idx = np.argmax(np.abs(ccf_vals))
    optimal_lag = lags[max_corr_idx]
    max_corr = ccf_vals[max_corr_idx]
    
    axes[idx].plot(lags, ccf_vals, linewidth=2)
    axes[idx].axhline(y=0, color='black', linestyle='--', alpha=0.3)
    axes[idx].axvline(x=0, color='red', linestyle='--', alpha=0.3)
    axes[idx].axvline(x=optimal_lag, color='green', linestyle='--', alpha=0.5, 
                     label=f'Max corr at lag {optimal_lag}')
    axes[idx].set_xlabel('Lag (hours)')
    axes[idx].set_ylabel('Cross-correlation')
    axes[idx].set_title(f'{title}\nOptimal lag: {optimal_lag}h (corr={max_corr:.3f})')
    axes[idx].grid(True, alpha=0.3)
    axes[idx].legend()
    
    print(f"{title}:")
    print(f"  Optimal lag: {optimal_lag} hours (correlation: {max_corr:.3f})")
    if optimal_lag > 0:
        print(f"  → {x_name} leads {y_name} by {optimal_lag} hours")
    elif optimal_lag < 0:
        print(f"  → {y_name} leads {x_name} by {-optimal_lag} hours")
    else:
        print(f"  → Contemporaneous relationship")

plt.tight_layout()
plt.savefig('ccf_analysis.png', dpi=300, bbox_inches='tight')
print("\n✅ Saved CCF plot to 'ccf_analysis.png'")
#plt.show()

# ============================================================
# TEST 2: Multi-Resolution Granger Causality
# ============================================================
print("\n" + "=" * 80)
print("TEST 2: GRANGER CAUSALITY AT MULTIPLE TIME RESOLUTIONS")
print("=" * 80)
print("Purpose: Check if results are robust across different time scales\n")

multi_res_results = {}

for freq_name, df in datasets.items():
    print(f"\n{'='*60}")
    print(f"Testing at {freq_name} resolution")
    print(f"{'='*60}")
    
    df_log = np.log1p(df)
    max_lag = min(5, len(df) // 20)  # Adaptive lag based on sample size
    
    results = {}
    for y in ['tokens', 'sandwiches', 'arbitrages']:
        for x in ['tokens', 'sandwiches', 'arbitrages']:
            if x == y:
                continue
            
            try:
                df_test = df_log[[y, x]].fillna(0)
                granger_results = grangercausalitytests(df_test, max_lag, verbose=False)
                
                best_lag = min(granger_results.keys(), 
                             key=lambda lag: granger_results[lag][0]['ssr_ftest'][1])
                best_p = granger_results[best_lag][0]['ssr_ftest'][1]
                
                results[f"{x}_to_{y}"] = {
                    'p_value': best_p,
                    'lag': best_lag,
                    'significant': best_p < 0.05
                }
                
                if best_p < 0.05:
                    print(f"  ✅ {x:12s} → {y:12s}: p={best_p:.12f} at lag {best_lag}")
            except:
                pass
    
    multi_res_results[freq_name] = results

# Summary table
print("\n" + "=" * 80)
print("SUMMARY: Significant Relationships Across Resolutions")
print("=" * 80)

summary_df = pd.DataFrame(index=frequencies.keys(), 
                         columns=['sandwiches→tokens', 'arbitrages→tokens', 
                                'sandwiches→arbitrages', 'tokens→sandwiches',
                                'tokens→arbitrages', 'arbitrages→sandwiches'])

for freq_name in frequencies.keys():
    if freq_name in multi_res_results:
        for relationship in summary_df.columns:
            x, y = relationship.split('→')
            key = f"{x}_to_{y}"
            if key in multi_res_results[freq_name]:
                p_val = multi_res_results[freq_name][key]['p_value']
                lag = multi_res_results[freq_name][key]['lag']
                summary_df.loc[freq_name, relationship] = f"{p_val:.3f} (L{lag})"

print(summary_df.to_string())

# ============================================================
# TEST 3: Time-of-Day and Day-of-Week Effects
# ============================================================
print("\n" + "=" * 80)
print("TEST 3: TEMPORAL PATTERNS (Time-of-Day & Day-of-Week)")
print("=" * 80)
print("Purpose: Check if MEV and launches follow daily/weekly patterns\n")

df_1h_indexed = df_1h.copy()
df_1h_indexed['hour'] = df_1h_indexed.index.hour
df_1h_indexed['dayofweek'] = df_1h_indexed.index.dayofweek
df_1h_indexed['day_name'] = df_1h_indexed.index.day_name()

# Hour of day analysis
hourly_patterns = df_1h_indexed.groupby('hour')[['tokens', 'sandwiches', 'arbitrages']].mean()

# Day of week analysis
daily_patterns = df_1h_indexed.groupby('day_name')[['tokens', 'sandwiches', 'arbitrages']].mean()
day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
daily_patterns = daily_patterns.reindex(day_order)

fig, axes = plt.subplots(2, 1, figsize=(14, 10))

# Hour of day plot
for col in hourly_patterns.columns:
    axes[0].plot(hourly_patterns.index, hourly_patterns[col], marker='o', 
                label=col.capitalize(), linewidth=2)
axes[0].set_xlabel('Hour of Day (UTC)')
axes[0].set_ylabel('Average Count')
axes[0].set_title('Activity Patterns by Hour of Day')
axes[0].legend()
axes[0].grid(True, alpha=0.3)
axes[0].set_xticks(range(0, 24, 2))

# Day of week plot
x_pos = range(len(day_order))
width = 0.25
for idx, col in enumerate(daily_patterns.columns):
    offset = (idx - 1) * width
    axes[1].bar([x + offset for x in x_pos], daily_patterns[col], width, 
               label=col.capitalize(), alpha=0.8)
axes[1].set_xlabel('Day of Week')
axes[1].set_ylabel('Average Count')
axes[1].set_title('Activity Patterns by Day of Week')
axes[1].set_xticks(x_pos)
axes[1].set_xticklabels(day_order, rotation=45)
axes[1].legend()
axes[1].grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plt.savefig('temporal_patterns.png', dpi=300, bbox_inches='tight')
print("\n✅ Saved temporal patterns to 'temporal_patterns.png'")
#plt.show()

# Statistical test for time-of-day effect
print("\nKruskal-Wallis Test for Hour-of-Day Effect:")
for col in ['tokens', 'sandwiches', 'arbitrages']:
    groups = [df_1h_indexed[df_1h_indexed['hour'] == h][col].values 
              for h in range(24)]
    stat, p_value = stats.kruskal(*groups)
    print(f"  {col}: H={stat:.2f}, p={p_value:.12f} {'✅ SIGNIFICANT' if p_value < 0.05 else ''}")

# ============================================================
# TEST 4: Rolling Window Granger Causality
# ============================================================
print("\n" + "=" * 80)
print("TEST 4: ROLLING WINDOW GRANGER CAUSALITY")
print("=" * 80)
print("Purpose: Check if causal relationships change over time\n")

df_log = np.log1p(df_1h)
window_size = 168  # 1 week in hours
step_size = 24     # 1 day step

rolling_results = {
    'sandwiches_to_tokens': [],
    'arbitrages_to_tokens': [],
    'timestamps': []
}

print(f"Running rolling window analysis (window={window_size}h, step={step_size}h)...")

for i in range(0, len(df_log) - window_size, step_size):
    window_data = df_log.iloc[i:i+window_size]
    timestamp = window_data.index[window_size//2]
    
    try:
        # Test sandwiches → tokens
        df_test = window_data[['tokens', 'sandwiches']].fillna(0)
        results = grangercausalitytests(df_test, 3, verbose=False)
        min_p_sand = min([results[lag][0]['ssr_ftest'][1] for lag in results])
        
        # Test arbitrages → tokens
        df_test = window_data[['tokens', 'arbitrages']].fillna(0)
        results = grangercausalitytests(df_test, 3, verbose=False)
        min_p_arb = min([results[lag][0]['ssr_ftest'][1] for lag in results])
        
        rolling_results['sandwiches_to_tokens'].append(min_p_sand)
        rolling_results['arbitrages_to_tokens'].append(min_p_arb)
        rolling_results['timestamps'].append(timestamp)
    except:
        continue

# Plot rolling results
fig, ax = plt.subplots(figsize=(14, 6))
ax.plot(rolling_results['timestamps'], rolling_results['sandwiches_to_tokens'], 
        label='Sandwiches → Tokens', linewidth=2, alpha=0.7)
ax.plot(rolling_results['timestamps'], rolling_results['arbitrages_to_tokens'], 
        label='Arbitrages → Tokens', linewidth=2, alpha=0.7)
ax.axhline(y=0.05, color='red', linestyle='--', label='p=0.05 threshold')
ax.set_xlabel('Time')
ax.set_ylabel('P-value')
ax.set_title('Rolling Window Granger Causality Test (1-week windows)')
ax.legend()
ax.grid(True, alpha=0.3)
ax.set_yscale('log')
plt.tight_layout()
plt.savefig('rolling_granger.png', dpi=300, bbox_inches='tight')
print("✅ Saved rolling window analysis to 'rolling_granger.png'")
#plt.show()

# ============================================================
# TEST 5: Lead-Lag Analysis with Different Lag Structures
# ============================================================
print("\n" + "=" * 80)
print("TEST 5: DETAILED LEAD-LAG ANALYSIS")
print("=" * 80)
print("Purpose: Test specific lag hypotheses\n")

df_log = np.log1p(df_1h)

# Test specific lags from 1 to 12 hours
print("\nTesting MEV → Tokens at different specific lags:")
print("-" * 60)

for lag in range(1, 13):
    try:
        # Sandwiches → Tokens
        df_test = df_log[['tokens', 'sandwiches']].fillna(0)
        results = grangercausalitytests(df_test, lag, verbose=False)
        p_sand = results[lag][0]['ssr_ftest'][1]
        
        # Arbitrages → Tokens
        df_test = df_log[['tokens', 'arbitrages']].fillna(0)
        results = grangercausalitytests(df_test, lag, verbose=False)
        p_arb = results[lag][0]['ssr_ftest'][1]
        
        sig_sand = "✅" if p_sand < 0.05 else "  "
        sig_arb = "✅" if p_arb < 0.05 else "  "
        
        print(f"Lag {lag:2d}h: Sandwiches p={p_sand:.12f} {sig_sand} | Arbitrages p={p_arb:.12f} {sig_arb}")
    except:
        continue

# ============================================================
# TEST 6: Volatility and Volume Analysis
# ============================================================
print("\n" + "=" * 80)
print("TEST 6: VOLATILITY CONTROL VARIABLE")
print("=" * 80)
print("Purpose: Check if results hold when controlling for market volatility\n")

# Calculate rolling volatility (std dev) as proxy for market conditions
df_1h['volatility'] = df_1h['arbitrages'].rolling(window=6, center=True).std().fillna(0)
df_1h['high_volatility'] = (df_1h['volatility'] > df_1h['volatility'].median()).astype(int)

# Split into high and low volatility periods
high_vol = df_1h[df_1h['high_volatility'] == 1]
low_vol = df_1h[df_1h['high_volatility'] == 0]

print(f"\nHigh volatility periods: {len(high_vol)} hours")
print(f"Low volatility periods: {len(low_vol)} hours")

for vol_name, vol_data in [('High Volatility', high_vol), ('Low Volatility', low_vol)]:
    print(f"\n{vol_name}:")
    print("-" * 40)
    
    df_test = np.log1p(vol_data[['tokens', 'sandwiches', 'arbitrages']].fillna(0))
    
    if len(df_test) > 20:  # Need sufficient data
        try:
            # Test sandwiches → tokens
            test_data = df_test[['tokens', 'sandwiches']]
            results = grangercausalitytests(test_data, 3, verbose=False)
            min_p = min([results[lag][0]['ssr_ftest'][1] for lag in results])
            print(f"  Sandwiches → Tokens: p={min_p:.4f} {'✅' if min_p < 0.05 else ''}")
            
            # Test arbitrages → tokens  
            test_data = df_test[['tokens', 'arbitrages']]
            results = grangercausalitytests(test_data, 3, verbose=False)
            min_p = min([results[lag][0]['ssr_ftest'][1] for lag in results])
            print(f"  Arbitrages → Tokens: p={min_p:.4f} {'✅' if min_p < 0.05 else ''}")
        except Exception as e:
            print(f"  Could not compute (error: {str(e)})")

# ============================================================
# TEST 7: MULTIVARIATE VAR CAUSALITY ANALYSIS
# ============================================================
print("\n" + "=" * 80)
print("TEST 7: MULTIVARIATE VAR — FULL SYSTEM CAUSALITY")
print("=" * 80)
print("Purpose: Determine if tokens jointly cause MEV or vice versa using multivariate Wald tests\n")

from statsmodels.tsa.api import VAR

var_results = {}

for freq_name, df in datasets.items():

    print(f"\n{'-'*70}")
    print(f"Multivariate VAR at {freq_name} frequency")
    print(f"{'-'*70}")

    df_log = np.log1p(df).astype(float)

    # Need enough data
    if len(df_log) < 30:
        print("Not enough data for VAR — skipping.")
        continue

    # Fit VAR model
    model = VAR(df_log)
    order_selection = model.select_order(maxlags=10)
    selected_lag = order_selection.aic

    if selected_lag is None or selected_lag < 1:
        selected_lag = 1

    print(f"Selected lag (AIC): {selected_lag}")

    try:
        var_model = model.fit(selected_lag)
    except Exception as e:
        print(f"Could not fit VAR: {e}")
        continue

    # TEST DI CAUSALITÀ MULTIVARIATA
    tests = {
        "tokens → sandwiches": var_model.test_causality("sandwiches", ["tokens"], kind="wald"),
        "tokens → arbitrages": var_model.test_causality("arbitrages", ["tokens"], kind="wald"),
        "sandwiches → tokens": var_model.test_causality("tokens", ["sandwiches"], kind="wald"),
        "arbitrages → tokens": var_model.test_causality("tokens", ["arbitrages"], kind="wald"),
        "sandwiches → arbitrages": var_model.test_causality("arbitrages", ["sandwiches"], kind="wald"),
        "arbitrages → sandwiches": var_model.test_causality("sandwiches", ["arbitrages"], kind="wald"),

        # Joint MEV → tokens
        "MEV (sandwich+arbitrages) → tokens":
            var_model.test_causality("tokens", ["sandwiches", "arbitrages"], kind="wald"),

        # Joint tokens → MEV
        "tokens → MEV (sandwich+arbitrages)":
            var_model.test_causality(["sandwiches", "arbitrages"], ["tokens"], kind="wald")
    }

    freq_results = {}
    for name_test, test_res in tests.items():
        pval = test_res.pvalue
        freq_results[name_test] = pval

        sig = "SIGNIFICANT" if pval < 0.05 else "ns"
        print(f"{name_test:40s}  p={pval:.12f}  {sig}")

    var_results[freq_name] = freq_results

# === HEATMAP MULTIVARIATA ===
print("\nCreating multivariate VAR p-value heatmap...")

# Costruzione tabella
heatmap_df = pd.DataFrame(var_results).T

plt.figure(figsize=(16, 8))
sns.heatmap(heatmap_df.astype(float), annot=True, fmt=".3f",
            cmap="viridis_r", linewidths=0.5, cbar=True)
plt.title("Multivariate VAR Causality — p-values")
plt.tight_layout()
plt.savefig("var_multivariate_heatmap.png", dpi=300)
#plt.show()

print("\n✅ Saved VAR multivariate heatmap to 'var_multivariate_heatmap.png'")


# ============================================================
# TEST 8: MULTIVARIATE TRANSFER ENTROPY (IDTxl)
# ============================================================
print("\n" + "=" * 80)
print("TEST 8: MULTIVARIATE TRANSFER ENTROPY (IDTxl)")
print("=" * 80)

try:
    from idtxl.data import Data
    from idtxl.multivariate_te import MultivariateTE
    import jpype
except ImportError:
    print("❌ ERRORE: Libreria 'idtxl' o 'jpype1' non installata.")
    print("   Installa con: pip install idtxl jpype1")
    print("   Skipping Transfer Entropy analysis...")
else:
    # 1. SELEZIONE DEL DATASET
    target_freq = '1min' 
    print(f"Using dataset resolution: {target_freq}")

    if target_freq not in datasets:
        print(f"❌ Dataset {target_freq} non trovato nei dati caricati.")
    else:
        df_te = datasets[target_freq].copy()
        
        # 2. PRE-PROCESSING
        # Normalizzazione Z-Score
        df_te = (df_te - df_te.mean()) / df_te.std()
        df_te = df_te.fillna(0)

        # Aggiungiamo piccolo rumore per stabilità numerica
        noise = np.random.normal(0, 1e-6, df_te.shape)
        df_te = df_te + noise

        # 3. PREPARAZIONE DATI PER IDTxl
        # Shape: (Processi, Campioni) -> (3, N)
        data_values = df_te[['tokens', 'sandwiches', 'arbitrages']].values.T
        
        print(f"Data shape: {data_values.shape} (Should be 3, N)")
        
        # Definizione oggetto Data
        data_idtxl = Data(
            data_values, 
            dim_order='ps', 
            normalise=False
        )

        # 4. CONFIGURAZIONE IDTxl
        network_analysis = MultivariateTE()
        
        settings = {
            'cmi_estimator': 'JidtGaussianCMI', 
            'max_lag_sources': 5,
            'min_lag_sources': 1,
            'verbose': False
        }

        print("Starting Multivariate TE analysis (this may take a few minutes)...")
        
        try:
            # Esecuzione analisi
            results = network_analysis.analyse_network(settings=settings, data=data_idtxl)

            print("\n" + "-" * 70)
            print("RISULTATI TRANSFER ENTROPY")
            print("-" * 70)
            
            # Mappiamo gli indici ai nomi
            names = {0: 'tokens', 1: 'sandwiches', 2: 'arbitrages'}
            
            # Soglia di significatività
            ALPHA = 0.05
            
            # Prima stampiamo tutte le chiavi disponibili per debug
            print("\nEsplorazione struttura risultati:")
            for target_idx in range(len(names)):
                target_results = results.get_single_target(target_idx)
                print(f"\nTarget: {names[target_idx]}")
                print(f"  Chiavi disponibili: {list(target_results.keys())}")
                break  # Stampa solo il primo per vedere la struttura
            
            print(f"\n{'='*70}")
            print(f"Relazioni causali rilevate:")
            print("="*70)
            
            found_sig = False
            te_results = {}
            
            # Iteriamo su tutti i target
            for target_idx in range(len(names)):
                target_results = results.get_single_target(target_idx)
                
                print(f"\n--- Target: {names[target_idx]} ---")
                
                # Verifica se ci sono sorgenti selezionate
                if 'selected_vars_sources' in target_results and target_results['selected_vars_sources']:
                    
                    selected_sources = target_results['selected_vars_sources']
                    
                    # Ottieni TE e p-values se disponibili
                    if 'selected_sources_te' in target_results:
                        te_values = target_results['selected_sources_te']
                    else:
                        te_values = [0.0] * len(selected_sources)
                    
                    if 'selected_sources_pval' in target_results:
                        p_values = target_results['selected_sources_pval']
                    else:
                        p_values = [1.0] * len(selected_sources)
                    
                    # Itera sulle sorgenti selezionate
                    for idx, source_tuple in enumerate(selected_sources):
                        source_idx = source_tuple[0]
                        lag = source_tuple[1]
                        
                        te_val = te_values[idx] if idx < len(te_values) else 0.0
                        p_val = p_values[idx] if idx < len(p_values) else 1.0
                        
                        is_significant = p_val < ALPHA
                        
                        key = f"{names[source_idx]}_to_{names[target_idx]}"
                        te_results[key] = {
                            'te': te_val,
                            'p_value': p_val,
                            'lag': lag,
                            'significant': is_significant
                        }
                        
                        sig_marker = "✅ SIGNIFICATIVA" if is_significant else "   ns"
                        
                        print(f"  {names[source_idx]:<12} -> {names[target_idx]:<12} | "
                              f"TE={te_val:.6f} | p={p_val:.6f} | lag={lag} | {sig_marker}")
                        
                        if is_significant:
                            found_sig = True
                else:
                    print(f"  Nessuna sorgente selezionata per {names[target_idx]}")
            
            print("\n" + "="*70)
            if found_sig:
                print("✅ Trovate relazioni causali statisticamente significative!")
            else:
                print("⚠️  Nessuna relazione causale statisticamente significativa trovata.")
                print("    Possibili cause:")
                print("    - Relazioni troppo deboli per essere rilevate")
                print("    - Necessità di maggiore densità temporale")
                print("    - Relazioni non lineari non catturate da questo metodo")

            print("\n✅ Analisi Transfer Entropy completata.")

        except Exception as e:
            print(f"❌ Errore durante l'esecuzione di IDTxl: {e}")
            print(f"Dettagli: {type(e).__name__}")
            import traceback
            traceback.print_exc()

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)