import json
import matplotlib.pyplot as plt
from collections import Counter
import seaborn as sns
import numpy as np

def plot_data():
    # --- PLOTTAGGIO: Griglia 2x2 ---
    fig, axes = plt.subplots(2, 2, figsize=(18, 16))  # Griglia 2x2
    ax1, ax2, ax3, ax4 = axes.flatten()

    sorted_bots = sorted(active_bots.items(), key=lambda x: x[1], reverse=True)[:8]
    bot_names = [bot[0] for bot in sorted_bots]
    sandwich_counts = [bot[1] for bot in sorted_bots]
    
    bars1 = ax1.bar(bot_names, sandwich_counts, color='skyblue')

    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width() / 2, yval + 0.1, str(yval),
                 ha='center', va='bottom', fontsize=10, fontweight='bold')

    ax1.set_xlabel('Bot')
    ax1.set_ylabel('Numero di sandwich')
    ax1.set_title('Conteggio sandwich per Top 8 bot')
    ax1.set_xticks(range(len(bot_names)))  # Imposta le posizioni degli "ticks"
    ax1.set_xticklabels(bot_names, rotation=45, ha='right')  # Imposta le etichette
    ax1.grid(axis='y', linestyle='--', alpha=0.7)

    # --- Secondo grafico: Top 10 Trade ---
    top_trades = trade_counter.most_common(8)
    trade_labels = [f"{a} <-> {b}" for (a, b), _ in top_trades]
    trade_counts = [count for _, count in top_trades]

    bars2 = ax2.bar(trade_labels, trade_counts, color='salmon')
    for bar, count in zip(bars2, trade_counts):
        ax2.text(bar.get_x() + bar.get_width() / 2, count + 0.1, str(count),
                 ha='center', va='bottom', fontsize=10, fontweight='bold')

    ax2.set_xlabel('Trade')
    ax2.set_ylabel('Occorrenze')
    ax2.set_title('Top 8 trade più frequenti')
    ax2.set_xticks(range(len(trade_labels)))  # Imposta le posizioni degli "ticks"
    ax2.set_xticklabels(trade_labels, rotation=45, ha='right')  # Imposta le etichette
    ax2.grid(axis='y', linestyle='--', alpha=0.7)

    # --- Terzo grafico: Heatmap dei trade più frequenti ---
    top_n = 8
    top_pairs = [pair for pair, _ in trade_counter.most_common(top_n)]
    currencies_top = sorted(set([cur for pair in top_pairs for cur in pair]))

    heat_data = np.zeros((len(currencies_top), len(currencies_top)))

    for i, cur1 in enumerate(currencies_top):
        for j, cur2 in enumerate(currencies_top):
            pair = tuple(sorted((cur1, cur2)))
            heat_data[i, j] = trade_counter.get(pair, 0)

    sns.heatmap(
        heat_data,
        xticklabels=currencies_top,
        yticklabels=currencies_top,
        cmap='Reds',
        annot=True,
        fmt=".0f",
        ax=ax3
    )
    ax3.set_title('Heatmap dei Top 8 trade più frequenti')
    ax3.set_xlabel('Valuta')
    ax3.set_ylabel('Valuta')
    box3 = ax3.get_position()
    ax3.set_position([box3.x0, box3.y0-0.05, box3.width, box3.height])
    
    # --- Quarto grafico: Grafico a torta dei trade più effettuati ---
    top_labels = [f"{a} <-> {b}" for (a, b), _ in top_trades]
    top_counts = [count for _, count in top_trades]
    ax4.pie(top_counts, labels=top_labels, autopct='%1.1f%%', startangle=140, colors=plt.cm.Paired.colors)
    ax4.set_title("Distribuzione dei Top 8 Trade")

    # 🔽 Sposta il grafico a torta leggermente più in basso
    box4 = ax4.get_position()
    ax4.set_position([box4.x0, box4.y0 + 0.1, box4.width, box4.height])

    # Ottimizza layout
    plt.tight_layout()
    plt.show()

def update_data():
    # Carica il file JSON
    with open('sandwich.json', 'r') as f:
        data = json.load(f)

    # Raccogli i nomi dei bot e conteggi
    bot_fields = []
    active_bots = {}

    for entry in data:
        for key, value in entry.items():
            if isinstance(value, dict) and "bot" in value:
                bot_name = value["bot"]
                bot_fields.append(bot_name)
                if bot_name in active_bots:
                    active_bots[bot_name] += 0.5
                else:
                    active_bots[bot_name] = 0.5

    # Conteggio coppie valute
    tuple_currency = []
    for entry in data:
        for key, value in entry.items():
            if isinstance(value, dict) and "currency_start" in value and "currency_end" in value:
                currency_start = value["currency_start"]
                currency_end = value["currency_end"]
                currency = [currency_start + " -> " + currency_end, currency_end + " -> " + currency_start]
                tuple_currency.append(currency)

    # Conta le coppie indipendentemente dall'ordine
    normalized_trades = []
    for pair in tuple_currency:
        for trade in pair:
            src, dst = trade.split(' -> ')
            normalized = tuple(sorted([src, dst]))
            normalized_trades.append(normalized)

    # Conta le occorrenze
    trade_counter = Counter(normalized_trades)

    # Converte i valori dei bot in interi
    for bot in active_bots:
        active_bots[bot] = int(active_bots[bot])

    return active_bots, trade_counter

if __name__=="__main__":
    while True:
        # Aggiorna i dati
        active_bots, trade_counter = update_data()

        # Mostra i grafici
        plot_data()

        # Aspetta che l'utente premi invio per aggiornare i grafici
        input("Premi Invio per aggiornare i grafici...")
