import json
import csv
import os
from collections import Counter
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from scipy.stats import pointbiserialr

# Path assoluto della cartella 'project/'
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SANDWICH_FILE = os.path.join(BASE_DIR, "sandwich_enriched.jsonl")
MEME_FILE = os.path.join(BASE_DIR, "meme_and_shitcoins_list.csv")

if __name__ == "__main__":
    print("Analisi memecoin")

    # Caricamento JSONL
    try:
        with open(SANDWICH_FILE, "r") as sandfile:
            existing_sandwich = [json.loads(line) for line in sandfile]
    except json.JSONDecodeError as e:
        print("Errore nel file JSON:", e)
        existing_sandwich = []

    # Caricamento CSV
    existing_meme = []
    try:
        with open(MEME_FILE, newline='') as memefile:
            reader = csv.DictReader(memefile)
            for row in reader:
                existing_meme.append({
                    "nome": row.get("Nome", "").lower(),
                    "ticker": row.get("Ticker", "").lower()
                })
    except Exception as e:
        print("Errore nel file CSV:", e)

    # Crea un set di ticker per confronto veloce
    meme_tickers = {m["ticker"] for m in existing_meme}

    # Conta i sandwich che coinvolgono memecoin
    meme_counter = Counter()
    sandwich_with_meme = 0

    for entry in existing_sandwich:
        try:
            token_start = entry["bot1"]["token_start"].lower()
            token_end = entry["bot1"]["token_end"].lower()
            found = False
            for token in [token_start, token_end]:
                if token in meme_tickers:
                    meme_counter[token] += 1
                    found = True
            if found:
                sandwich_with_meme += 1
        except KeyError:
            continue

    total_sandwich = len(existing_sandwich)
    percentage_meme = (sandwich_with_meme / total_sandwich * 100) if total_sandwich > 0 else 0

    print(f"Sandwich totali: {total_sandwich}")
    print(f"Sandwich con memecoin: {sandwich_with_meme} ({percentage_meme:.2f}%)")
    print("Top 10 memecoin nei sandwich:")
    for token, count in meme_counter.most_common(10):
        print(f"{token.upper()}: {count}")

    compute_units_data = []

    for entry in existing_sandwich:
        try:
            # Compute units totali (bot1 + bot2 + vittime)
            bot1_cu = entry["bot1"]["Details"]["compute_units_consumed"]
            bot2_cu = entry["bot2"]["Details"]["compute_units_consumed"]
            victims_cu = sum(v["Details"]["compute_units_consumed"] for v in entry.get("victims", []))
            total_cu = bot1_cu + bot2_cu + victims_cu

            # Controlla se è coinvolta una memecoin in token_start o token_end di bot1
            token_start = entry["bot1"]["token_start"].lower()
            token_end = entry["bot1"]["token_end"].lower()
            is_meme = (token_start in meme_tickers) or (token_end in meme_tickers)

            compute_units_data.append({
                "total_cu": total_cu,
                "is_meme": is_meme
            })
        except KeyError:
            continue

    df_cu = pd.DataFrame(compute_units_data)

    print("\nStatistiche compute_units per memecoin e non memecoin:")
    print(df_cu.groupby("is_meme")["total_cu"].describe())

    # Calcolo correlazione point biserial
    corr, pval = pointbiserialr(df_cu["is_meme"].astype(int), df_cu["total_cu"])
    print(f"\nCorrelazione point-biserial compute_units - memecoin: r={corr:.3f}, p-value={pval:.3g}")

        # --- PLOTTING ---

    # Grafico a barre: top 5 memecoin
    top5 = meme_counter.most_common(10)
    if top5:
        tokens, counts = zip(*top5)
        fig_bar = go.Figure(go.Bar(
            x=list(tokens),
            y=list(counts),
            marker_color='mediumturquoise'
        ))
        fig_bar.update_layout(
            title="Top 5 Memecoin usate nei Sandwich",
            xaxis_title="Token",
            yaxis_title="Occorrenze",
        )
        fig_bar.show()

    # Grafico a torta: % sandwich con memecoin
    fig_pie = px.pie(
        names=["Con Memecoin", "Senza Memecoin"],
        values=[sandwich_with_meme, total_sandwich - sandwich_with_meme],
        title="Percentuale di Sandwich con Memecoin"
    )
    fig_pie.update_traces(textinfo="percent+label")
    fig_pie.show()
    
    # Boxplot compute_units divisi per memecoin / non memecoin
    fig_box = px.box(
        df_cu, 
        x="is_meme", 
        y="total_cu", 
        title="Compute Units Consumate: Memecoin vs Non Memecoin",
        labels={"is_meme": "Memecoin", "total_cu": "Compute Units Totali"},
        category_orders={"is_meme": [False, True]}
    )
    fig_box.update_xaxes(tickvals=[False, True], ticktext=["No", "Sì"])
    fig_box.show()
