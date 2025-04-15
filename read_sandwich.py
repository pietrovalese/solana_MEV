import json
import pandas as pd
from dash import Dash, dcc, html
from dash.dependencies import Output, Input
import plotly.express as px
import plotly.graph_objects as go
import os
import re

# --- Funzioni di utilità ---

def clean_token(token):
    return token.replace("bot: ", "").replace("victim: ", "").strip()

def clean_fee(fee_str):
    """Estrae il primo numero decimale valido da una stringa, oppure 0.0 se non trovato."""
    if not fee_str:
        return 0.0
    matches = re.findall(r"\d*\.?\d+", fee_str)
    return float(matches[0]) if matches else 0.0


def parse_number(value):
    """Converte stringhe con virgole in float."""
    if isinstance(value, str):
        return float(value.replace(",", ""))
    return float(value)

def normalize_pair(t1, t2):
    return tuple(sorted([t1, t2]))

# --- Preparazione Heatmap ---

def prepare_heatmap_data(data, top_n_tokens=8, epoch=None):
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
        colorscale='Reds',
        hoverongaps=False,
        zmin=0,
    ))

    fig.update_layout(
        title='Heatmap delle coppie di token più scambiate (Top Token)',
        plot_bgcolor="#222",
        paper_bgcolor="#222",
        font_color="white",
        height=700,
        margin=dict(l=80, r=40, t=80, b=50),  # Aumentato il margine sinistro
        xaxis=dict(
            tickangle=45,
            tickfont=dict(size=12),
        ),
        yaxis=dict(
            tickfont=dict(size=12),
            ticks="outside",         # Etichette fuori dall'asse
            ticklen=10,              # Lunghezza dei tick
        )
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

def avg_fee_and_priority_fee(data, epoch=None):
    fee_list = []
    priority_fee_list = []
    
    for entry in data:
        epoch_values = entry.get("bot1", {}).get("Details", {}).get("Epoch", [])
        if epoch is None or epoch == "" or (epoch_values and (epoch == epoch_values[0] or epoch_values[0] == "")):  
            # Fee bot1
            bot1_fee = entry.get("bot1", {}).get("Details", {}).get("Fee", "")
            if bot1_fee:
                fee_list.append(clean_fee(bot1_fee))
            
            # Fee bot2
            bot2_fee = entry.get("bot2", {}).get("Details", {}).get("Fee", "")
            if bot2_fee:
                fee_list.append(clean_fee(bot2_fee))
            
            # Victims
            for victim in entry.get("victims", []):
                victim_fee = victim.get("Details", {}).get("Fee", "")
                if victim_fee:
                    fee_list.append(clean_fee(victim_fee))
                
                victim_priority_fee = victim.get("Details", {}).get("Priority Fee", "")
                if victim_priority_fee:
                    priority_fee_list.append(clean_fee(victim_priority_fee))

    avg_fee = sum(fee_list) / len(fee_list) if fee_list else 0
    max_fee = max(fee_list) if fee_list else 0
    min_fee = min(fee_list) if fee_list else 0

    avg_priority_fee = sum(priority_fee_list) / len(priority_fee_list) if priority_fee_list else 0
    max_priority_fee = max(priority_fee_list) if priority_fee_list else 0
    min_priority_fee = min(priority_fee_list) if priority_fee_list else 0
    
    return min_fee, min_priority_fee, avg_fee, avg_priority_fee, max_fee, max_priority_fee

def avg_net_profit(data, epoch=None):
    profit_list = []

    for entry in data:
        epoch_values = entry.get("bot1", {}).get("Details", {}).get("Epoch", [])
        if epoch is None or epoch == "" or (epoch_values and (epoch == epoch_values[0] or epoch_values[0] == "")):  
            
            bot1 = entry.get("bot1", {})
            bot2 = entry.get("bot2", {})

            token_start = bot1.get("token_start", "")
            token_end = bot2.get("token_end", "")
            
            # Calcola profitto solo se i token sono uguali
            if token_start == token_end and token_start != "":
                try:
                    if token_start == "sol":
                        value_start = parse_number(bot1.get("value_start", 0))
                        value_end = parse_number(bot2.get("value_end", 0))

                        fee1 = clean_fee(bot1.get("Details", {}).get("Fee", "0"))
                        fee2 = clean_fee(bot2.get("Details", {}).get("Fee", "0"))

                        net_profit = value_end - value_start - fee1 - fee2
                        profit_list.append(net_profit)

                except (ValueError, TypeError):
                    continue  # Salta se ci sono problemi nei dati

    avg_profit = sum(profit_list) / len(profit_list) if profit_list else 0
    min_profit = min(profit_list)
    max_profit = max(profit_list)
    
    return  min_profit, avg_profit, max_profit
    

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
            {"label": "All", "value": ""},
            {"label": "Epoca 770", "value": "770"},
            {"label": "Epoca 771", "value": "771"},
            {"label": "Epoca 772", "value": "772"},
        ],
        value="",
        style={"backgroundColor": "#444", "color": "white", "border": "1px solid #555", "borderRadius": "5px"}
    ),

    # Sezione valori medi
    html.Div(id="stats-values", style={
        "display": "flex",
        "justifyContent": "space-around",
        "padding": "20px 0",
        "fontSize": "18px",
        "backgroundColor": "#333",
        "borderRadius": "10px",
        "marginTop": "20px",
        "marginBottom": "10px"
    }),

    dcc.Graph(id="bot-chart"),
    dcc.Graph(id="trade-chart"),
    dcc.Graph(id="heatmap-chart"),
]),
    dcc.Interval(id="interval-component", interval=120*1000, n_intervals=0),
    html.Div("Dati aggiornati ogni 120 secondi", style={"textAlign": "center", "marginTop": "10px", "fontSize": "14px"})
])


def make_stat_block(label, value):
    return html.Div([
        html.Div(label, style={"fontWeight": "bold"}),
        html.Div(f"{value:.6f} SOL")
    ], style={"flex": "1", "textAlign": "center", "padding": "20px"})


# --- Callback aggiornamento grafici ---

@app.callback(
    [Output("bot-chart", "figure"),
     Output("trade-chart", "figure"),
     Output("heatmap-chart", "figure"),
     Output("stats-values", "children")],
    [Input("epoch-dropdown", "value"),
     Input("interval-component", "n_intervals")]
)
    
    
def update_graphs(epoch, n):
    data = load_data()
    fig_bots, fig_trades = generate_figures(data, epoch)
    matrix = prepare_heatmap_data(data, epoch=epoch)
    fig_heatmap = create_heatmap(matrix)

    min_fee, min_priority_fee, avg_fee, avg_priority_fee, max_fee, max_priority_fee = avg_fee_and_priority_fee(data, epoch)
    min_profit, avg_profit, max_profit = avg_net_profit(data, epoch)

    stats_display = html.Div([
    html.Div([
        make_stat_block("Min Fee", min_fee),
        make_stat_block("Average Fee", avg_fee),
        make_stat_block("Max Fee", max_fee),
    ], style={"display": "flex", "width": "100%"}),

    html.Div([
        make_stat_block("Min Priority Fee", min_priority_fee),
        make_stat_block("Average Priority Fee", avg_priority_fee),
        make_stat_block("Max Priority Fee", max_priority_fee),
    ], style={"display": "flex", "width": "100%", "marginTop": "10px"}),

    html.Div([
        make_stat_block("Min Net Profit", min_profit),
        make_stat_block("Average Net Profit", avg_profit),
        make_stat_block("Max Net Profit", max_profit),
    ], style={"display": "flex", "width": "100%", "marginTop": "10px"}),
    ])

    return fig_bots, fig_trades, fig_heatmap, stats_display

# --- Avvio ---

if __name__ == '__main__':
    app.run(debug=True)
