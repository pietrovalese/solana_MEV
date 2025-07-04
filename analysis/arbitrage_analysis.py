import pandas as pd
import plotly.express as px
from scipy.stats import pearsonr, spearmanr
import os
import json
from collections import Counter

# Path assoluto della cartella 'project/'
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
ARB_FILE = os.path.join(BASE_DIR, "arbitrages.jsonl")
MEME_FILE = os.path.join(BASE_DIR, "meme_and_shitcoins_list.csv")

if __name__ == "__main__":
    try:
        with open(ARB_FILE, "r") as arbfile:
            existing_arbitrages = [json.loads(line) for line in arbfile]
    except json.JSONDecodeError as e:
        print("Errore nel file JSON:", e)
        existing_arbitrages = []
    
    revenues = []
    platform_counter = Counter()

    # Raccogli revenue
    for data in existing_arbitrages:
        revenue = data.get("revenue_sol", 0)
        revenues.append(revenue)
    
    
    # Conta le piattaforme usate nei trades
    for data in existing_arbitrages:
        for trade in data.get("trades", []):
            platform = trade.get("platform")
            if platform:
                platform_counter[platform] += 1
                
    token_counter = Counter()

    for arb in existing_arbitrages:
        for trade in arb.get("trades", []):
            from_token = trade.get("from_token")
            to_token = trade.get("to_token")

            if from_token and from_token != "SOL":
                token_counter[from_token] += 1
            if to_token and to_token != "SOL":
                token_counter[to_token] += 1


    # Statistiche sul revenue
    total_revenue = sum(revenues)
    average_revenue = total_revenue / len(revenues) if revenues else 0
    max_revenue = max(revenues) if revenues else 0
    min_revenue = min(revenues) if revenues else 0

    # Stampa risultati
    print(f"📊 Totale Revenue: {total_revenue:.6f} SOL")
    print(f"📈 Revenue medio: {average_revenue:.6f} SOL")
    print(f"🔺 Revenue massimo: {max_revenue:.6f} SOL")
    print(f"🔻 Revenue minimo: {min_revenue:.6f} SOL")
    print("\n🏆 Piattaforme più frequenti:")
    for platform, count in platform_counter.most_common():
        print(f"  - {platform}: {count} volte")
    
    # Calcola il numero di trade per ogni arbitraggio
    num_trades_per_arb = [len(data.get("trades", [])) for data in existing_arbitrages]
    

    # DataFrame per visualizzazione
    df_trades = pd.DataFrame({
        "num_trades": num_trades_per_arb,
        "revenue_sol": revenues  # già raccolti prima
    })

    pearson_corr, _ = pearsonr(df_trades["num_trades"], df_trades["revenue_sol"])
    spearman_corr, _ = spearmanr(df_trades["num_trades"], df_trades["revenue_sol"])

    print(f"📎 Pearson correlation: {pearson_corr:.4f}")
    print(f"📎 Spearman correlation: {spearman_corr:.4f}")



    # Leggi il CSV delle memecoin
    memecoin_df = pd.read_csv(MEME_FILE)  # aggiorna il path

    # Crea un set con i ticker delle memecoin (in maiuscolo per evitare mismatch)
    memecoin_set = set(memecoin_df["Ticker"].str.upper())

    # Lista dei token coinvolti negli arbitraggi (già in token_counter)
    tokens_involved = set(token_counter.keys())

    # Trova quali token sono memecoin
    memecoin_in_arbitrage = tokens_involved.intersection(memecoin_set)

    print(f"Token coinvolti che sono memecoin ({len(memecoin_in_arbitrage)}):")
    print(sorted(memecoin_in_arbitrage))

    # Conta il totale di occorrenze per le memecoin
    memecoin_counts = {token: count for token, count in token_counter.items() if token.upper() in memecoin_set}

    print("\nConteggio memecoin negli arbitraggi:")
    for token, count in sorted(memecoin_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"- {token}: {count} occorrenze")


    fig_trade_count = px.histogram(
    df_trades,
    x="num_trades",
    title="Distribuzione del numero di trade per arbitraggio",
    labels={"num_trades": "Numero di trades"},
    template="plotly_white",
    text_auto=True
    )

    # Aggiungi contorno alle barre
    fig_trade_count.update_traces(
        marker_line_width=1,          # spessore del bordo
        marker_line_color="black"     # colore del bordo
    )

    fig_trade_count.update_layout(
        xaxis=dict(range=[0, df_trades["num_trades"].max() + 1])
    )

    fig_trade_count.show()


    
    # crea DataFrame da Counter
    df_platforms = pd.DataFrame(platform_counter.items(), 
                                columns=["platform", "count"])

    # Plot: piattaforme ordinate per frequenza
    fig_plat = px.bar(df_platforms.sort_values(by="count", ascending=False),
                      x="platform", y="count",
                      title="Piattaforme più usate nei trades",
                      labels={"platform": "Piattaforma", "count": "Numero di trades"},
                      template="plotly_white")
    fig_plat.update_layout(xaxis_tickangle=-45)
    fig_plat.show()
    
    # DataFrame ordinato decrescente per count
    df_tokens = pd.DataFrame(token_counter.items(), columns=["token", "count"])
    df_tokens["is_memecoin"] = df_tokens["token"].str.upper().isin(memecoin_set)
    df_tokens = df_tokens.sort_values(by="count", ascending=False)
    df_tokens = df_tokens[df_tokens["count"] >= 10]

    fig = px.bar(
        df_tokens,
        x="token",
        y="count",
        color="is_memecoin",
        color_discrete_map={True: "crimson", False: "steelblue"},
        category_orders={"token": df_tokens["token"].tolist()},  # forza ordine asse X
        title="Token più usati negli arbitraggi (memecoin evidenziate)",
        labels={"token": "Token", "count": "Frequenza", "is_memecoin": "Memecoin"},
        template="plotly_white"
    )

    fig.update_layout(xaxis_tickangle=-45)

    fig.show()


