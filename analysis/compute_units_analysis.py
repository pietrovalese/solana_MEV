import pandas as pd
import plotly.express as px
from scipy.stats import pearsonr, spearmanr
import os
import json

# Path assoluto della cartella 'project/'
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SANDWICH_FILE = os.path.join(BASE_DIR, "sandwich_enriched.jsonl")

if __name__ == "__main__":
    try:
        with open(SANDWICH_FILE, "r") as sandfile:
            existing_sandwich = [json.loads(line) for line in sandfile]
    except json.JSONDecodeError as e:
        print("Errore nel file JSON:", e)
        existing_sandwich = []

compute_profit_data = []
victim_data = []

for entry in existing_sandwich:
    try:
        bot1_cu = entry["bot1"]["Details"]["compute_units_consumed"]
        bot2_cu = entry["bot2"]["Details"]["compute_units_consumed"]
        victims_cu = sum(v["Details"]["compute_units_consumed"] for v in entry.get("victims", []))
        total_cu = bot1_cu + bot2_cu + victims_cu
        
        if entry["bot1"]["token_start"] == "sol":
            value_start = float(entry["bot1"]["value_start"].replace(',', ''))
            value_end = float(entry["bot2"]["value_end"].replace(',', ''))
            profit = value_end - value_start
        
        num_victims = len(entry.get("victims", []))
    
        victim_data.append({
            "total_cu": total_cu,
            "num_victims": num_victims,
        })
        
        compute_profit_data.append({
            "total_cu": total_cu,
            "profit": profit
        })
    except Exception as e:
        print(f"Errore nell'entry: {e}")
        continue

df_cp = pd.DataFrame(compute_profit_data)
df_vict = pd.DataFrame(victim_data)

# Statistiche base
print(df_cp.describe())

# Scatter plot compute units vs profitto
fig1 = px.scatter(df_cp, x="total_cu", y="profit",
                 trendline="ols",
                 title="Relazione tra Compute Units Consumate e Profitto negli Attacchi Sandwich",
                 labels={"total_cu": "Compute Units Totali", "profit": "Profitto"})
fig1.show()

# Scatter plot compute units vs numero vittime
fig2 = px.scatter(df_vict, x="total_cu", y="num_victims",
                  trendline="ols",
                  title="Relazione tra Compute Units Consumate e Numero di Vittime negli Attacchi Sandwich",
                  labels={"total_cu": "Compute Units Totali", "num_victims": "Numero Vittime"})
fig2.show()

# Correlazione Pearson compute units vs profitto
if df_cp["total_cu"].nunique() > 1 and df_cp["profit"].nunique() > 1:
    corr, p_value = pearsonr(df_cp["total_cu"], df_cp["profit"])
    print(f"Correlazione Pearson compute_units-profitto: r={corr:.3f}, p-value={p_value:.3g}")
else:
    print("Variabili compute_units o profitto costanti, Pearson non calcolabile.")

# Correlazioni compute_units vs num_victims
if df_vict["total_cu"].nunique() > 1 and df_vict["num_victims"].nunique() > 1:
    r_pearson, p_pearson = pearsonr(df_vict["total_cu"], df_vict["num_victims"])
    print(f"Correlazione Pearson compute_units-num_victims: r={r_pearson:.3f}, p={p_pearson:.3f}")
    
    r_spearman, p_spearman = spearmanr(df_vict["total_cu"], df_vict["num_victims"])
    print(f"Correlazione Spearman compute_units-num_victims: r={r_spearman:.3f}, p={p_spearman:.3f}")
else:
    print("Variabili compute_units o num_victims costanti, correlazioni non calcolabili.")
