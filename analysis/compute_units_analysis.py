import pandas as pd
import plotly.express as px
import os
import json
from scipy.stats import pearsonr, spearmanr

# Path della cartella project/
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SANDWICH_FILE = os.path.join(BASE_DIR, "sandwiches_annotated.jsonl")

if __name__ == "__main__":
    try:
        with open(SANDWICH_FILE, "r") as f:
            entries = [json.loads(line) for line in f]
    except json.JSONDecodeError as e:
        print("Errore JSON:", e)
        entries = []

    data = []
    for entry in entries:
        try:
            bot1 = entry["bot1"]["Details"]
            bot2 = entry["bot2"]["Details"]
            
            v0 = float(entry["bot1"]["value_start"].replace(',', ''))
            v1 = float(entry["bot2"]["value_end"].replace(',', ''))
            profit = v1 - v0
            
            total_pf = bot1["fee"]["priority_fee"] + bot2["fee"]["priority_fee"]
            
            data.append({"total_priority_fee": total_pf, "profit": profit})
        except Exception as e:
            print("Skippata entry:", e)

    df = pd.DataFrame(data)
    
    if df.shape[0] < 2 or df["total_priority_fee"].nunique() < 2:
        print("Dati insufficienti per correlazione o grafico.")
        exit(0)

    # Correlazione
    p_corr, _ = pearsonr(df["total_priority_fee"], df["profit"])
    s_corr, _ = spearmanr(df["total_priority_fee"], df["profit"])
    print(f"Pearson corr: {p_corr:.4f} – Spearman corr: {s_corr:.4f}")

    # Scatter con trendline OLS
    fig = px.scatter(
        df,
        x="total_priority_fee",
        y="profit",
        trendline="ols",
        title="Total Priority Fee vs Profit",
        labels={"total_priority_fee": "Somma Priority Fee (SOL)", "profit": "Profitto (SOL)"}
    )
    fig.show()

    # Trendline details
    results = px.get_trendline_results(fig)
    ols = results.iloc[0]["px_fit_results"]
    print("\n📊 OLS Summary:\n", ols.summary())
