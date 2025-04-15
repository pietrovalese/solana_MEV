import json
import pandas as pd
from dash import Dash, dcc, html
from dash.dependencies import Output, Input
import plotly.express as px
import plotly.graph_objects as go
import os

# --- Funzioni di utilità ---

def clean_token(token):
    return token.replace("bot: ", "").replace("victim: ", "").strip()

def normalize_pair(t1, t2):
    return tuple(sorted([t1, t2]))

# --- Preparazione Heatmap ---

# --- Preparazione Heatmap ---

def prepare_heatmap_data(data, top_n_tokens=10, epoch=None):
    trade_count = {}
    token_freq = {}

    for entry in data:
        # Rimuovi il filtro sull'epoca se epoch è una stringa vuota
        epoch_values = entry.get("bot1", {}).get("Details", {}).get("Epoch", [])
        if epoch is None or epoch == "" or (epoch_values and (epoch == epoch_values[0] or epoch_values[0] == "")):  # Ignora epoca se vuoto
            for side in ["bot1", "bot2"]:
                bot = entry.get(side, {})
                t1 = clean_token(bot.get("token_start", ""))
                t2 = clean_token(bot.get("token_end", ""))
                if t1 and t2:
                    pair = normalize_pair(t1, t2)
                    trade_count[pair] = trade_count.get(pair, 0) + 1
                    token_freq[t1] = token_freq.get(t1, 0) + 1
                    token_freq[t2] = token_freq.get(t2, 0) + 1

            for victim in entry.get("victims", []):
                t1 = clean_token(victim.get("token_start", ""))
                t2 = clean_token(victim.get("token_end", ""))
                if t1 and t2:
                    pair = normalize_pair(t1, t2)
                    trade_count[pair] = trade_count.get(pair, 0) + 1
                    token_freq[t1] = token_freq.get(t1, 0) + 1
                    token_freq[t2] = token_freq.get(t2, 0) + 1

    # Seleziona i token più frequenti
    top_tokens = set([token for token, _ in sorted(token_freq.items(), key=lambda x: x[1], reverse=True)[:top_n_tokens]])

    # Filtra solo le coppie tra i top token
    filtered_trade_count = {pair: count for pair, count in trade_count.items()
                            if pair[0] in top_tokens and pair[1] in top_tokens}

    tokens = sorted(top_tokens)
    matrix = pd.DataFrame(0, index=tokens, columns=tokens)

    for (t1, t2), count in filtered_trade_count.items():
        matrix.at[t1, t2] = count
        matrix.at[t2, t1] = count

    return matrix



def create_heatmap(matrix):
    fig = go.Figure(data=go.Heatmap(
        z=matrix.values,
        x=matrix.columns,
        y=matrix.index,
        colorscale='Blues',
        hoverongaps=False
    ))

    fig.update_layout(
        title='Heatmap delle coppie di token più scambiate (Top Token)',
        xaxis_nticks=36,
        plot_bgcolor="#222",
        paper_bgcolor="#222",
        font_color="white",
        height=700
    )

    return fig

# --- Top bot/trade ---

def top_bot(data, n, epoch=None):
    bot_name_dict = {}

    for entry in data:
        # Rimuovi il filtro sull'epoca se epoch è una stringa vuota
        epoch_values = entry.get("bot1", {}).get("Details", {}).get("Epoch", [])
        if epoch is None or epoch == "" or (epoch_values and (epoch == epoch_values[0] or epoch_values[0] == "")):  # Ignora epoca se vuoto
            raw_bot_name = entry.get("bot1", {}).get("bot", "")
            bot_name = clean_token(raw_bot_name)
            if bot_name:
                bot_name_dict[bot_name] = bot_name_dict.get(bot_name, 0) + 1

    sorted_bots = sorted(bot_name_dict.items(), key=lambda x: x[1], reverse=True)
    return sorted_bots[:n]

def top_trades(data, n, epoch=None):
    trade_count = {}

    for entry in data:
        # Rimuovi il filtro sull'epoca se epoch è una stringa vuota
        epoch_values = entry.get("bot1", {}).get("Details", {}).get("Epoch", [])
        if epoch is None or epoch == "" or (epoch_values and (epoch == epoch_values[0] or epoch_values[0] == "")):  # Ignora epoca se vuoto
            for side in ["bot1", "bot2"]:
                bot = entry.get(side, {})
                t1 = clean_token(bot.get("token_start", ""))
                t2 = clean_token(bot.get("token_end", ""))
                if t1 and t2:
                    pair = f"{min(t1, t2)} <-> {max(t1, t2)}"
                    trade_count[pair] = trade_count.get(pair, 0) + 1

            for victim in entry.get("victims", []):
                t1 = clean_token(victim.get("token_start", ""))
                t2 = clean_token(victim.get("token_end", ""))
                if t1 and t2:
                    pair = f"{min(t1, t2)} <-> {max(t1, t2)}"
                    trade_count[pair] = trade_count.get(pair, 0) + 1

    sorted_trades = sorted(trade_count.items(), key=lambda x: x[1], reverse=True)
    return sorted_trades[:n]

# --- Caricamento dati ---

def load_data():
    if not os.path.exists("sandwich.jsonl"):
        return []
    with open("sandwich.jsonl", "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]

# --- Generazione grafici ---

def generate_figures(data, epoch):
    top_bots = top_bot(data, 8, epoch)
    top_trades_list = top_trades(data, 8, epoch)

    df_bots = pd.DataFrame(top_bots, columns=["Bot", "Frequenza"])
    df_trades = pd.DataFrame(top_trades_list, columns=["Trade", "Frequenza"])

    fig_bots = px.bar(df_bots, x="Bot", y="Frequenza", title="Top 8 Bot per Frequenza", color="Bot")
    fig_bots.update_layout(plot_bgcolor="#222", paper_bgcolor="#222", font_color="white")

    fig_trades = px.bar(df_trades, x="Trade", y="Frequenza", title="Top 8 Trade Pairs", color="Trade")
    fig_trades.update_layout(plot_bgcolor="#222", paper_bgcolor="#222", font_color="white", xaxis_tickangle=45)

    return fig_bots, fig_trades

# --- Dash app ---

app = Dash(__name__)
app.title = "Sandwich Attack Dashboard"

app.layout = html.Div(style={"backgroundColor": "#222", "color": "white", "padding": "20px"}, children=[
    html.H1("Sandwich Attack Dashboard", style={"textAlign": "center"}),
    html.Div([
        dcc.Dropdown(
            id="epoch-dropdown",
            options=[
                {"label": "All", "value": ""},  # Modifica per usare una stringa vuota
                {"label": "Epoca 770", "value": "770"},
                {"label": "Epoca 771", "value": "771"},
                {"label": "Epoca 772", "value": "772"},
                # Aggiungi altre epoche se necessario
            ],
            value="",  # Imposta su una stringa vuota per selezionare "Allepoch" di default
            style={"backgroundColor": "#444", "color": "white", "border": "1px solid #555", "borderRadius": "5px"}
        ),
        dcc.Graph(id="bot-chart"),
        dcc.Graph(id="trade-chart"),
        dcc.Graph(id="heatmap-chart"),
    ]),
    dcc.Interval(id="interval-component", interval=120*1000, n_intervals=0),
    html.Div("Dati aggiornati ogni 120 secondi", style={"textAlign": "center", "marginTop": "10px", "fontSize": "14px"})
])

# --- Callback aggiornamento grafici ---

@app.callback(
    [Output("bot-chart", "figure"),
     Output("trade-chart", "figure"),
     Output("heatmap-chart", "figure")],
    [Input("epoch-dropdown", "value"),
     Input("interval-component", "n_intervals")]
)
def update_graphs(epoch, n):
    data = load_data()
    fig_bots, fig_trades = generate_figures(data, epoch)
    # Genera anche la heatmap, applicando il filtro dell'epoca
    matrix = prepare_heatmap_data(data, epoch=epoch)
    fig_heatmap = create_heatmap(matrix)
    return fig_bots, fig_trades, fig_heatmap

# --- Avvio ---

if __name__ == '__main__':
    app.run(debug=True)
