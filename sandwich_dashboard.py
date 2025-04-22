import json
import pandas as pd
from dash import Dash, dcc, html
from dash.dependencies import Output, Input
import plotly.express as px
import plotly.graph_objects as go
import os
import re
import requests
from datetime import datetime

# --- Funzioni di utilità ---

def clean_token(token):
    return token.replace("bot: ", "").replace("victim: ", "").strip()

def clean_fee(fee_str):
    if not fee_str:
        return 0.0
    matches = re.findall(r"\d*\.?\d+", fee_str)
    return float(matches[0]) if matches else 0.0

def parse_number(value):
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
        epoch_values = entry.get("bot1", {}).get("Details", {}).get("Epoch", [])
        if epoch is None or epoch == "" or (epoch_values and (epoch == epoch_values[0] or epoch_values[0] == "")):
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

    top_tokens = set([token for token, _ in sorted(token_freq.items(), key=lambda x: x[1], reverse=True)[:top_n_tokens]])
    filtered_trade_count = {pair: count for pair, count in trade_count.items() if pair[0] in top_tokens and pair[1] in top_tokens}
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
        margin=dict(l=80, r=40, t=80, b=50),  
        xaxis=dict(tickangle=45, tickfont=dict(size=12)),
        yaxis=dict(tickfont=dict(size=12), ticks="outside", ticklen=10)
    )
    return fig

# --- Analisi statistiche ---

def top_bot(data, n, epoch=None):
    bot_name_dict = {}
    for entry in data:
        epoch_values = entry.get("bot1", {}).get("Details", {}).get("Epoch", [])
        if epoch is None or epoch == "" or (epoch_values and (epoch == epoch_values[0] or epoch_values[0] == "")):
            raw_bot_name = entry.get("bot1", {}).get("bot", "")
            bot_name = clean_token(raw_bot_name)
            if bot_name:
                bot_name_dict[bot_name] = bot_name_dict.get(bot_name, 0) + 1
    return sorted(bot_name_dict.items(), key=lambda x: x[1], reverse=True)[:n]

def top_trades(data, n, epoch=None):
    trade_count = {}
    for entry in data:
        epoch_values = entry.get("bot1", {}).get("Details", {}).get("Epoch", [])
        if epoch is None or epoch == "" or (epoch_values and (epoch == epoch_values[0] or epoch_values[0] == "")):
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
    return sorted(trade_count.items(), key=lambda x: x[1], reverse=True)[:n]

def avg_fee_and_priority_fee(data, epoch=None):
    fee_list, priority_fee_list = [], []
    for entry in data:
        epoch_values = entry.get("bot1", {}).get("Details", {}).get("Epoch", [])
        if epoch is None or epoch == "" or (epoch_values and (epoch == epoch_values[0] or epoch_values[0] == "")):
            for bot_key in ["bot1", "bot2"]:
                fee_list.append(clean_fee(entry.get(bot_key, {}).get("Details", {}).get("Fee", "")))
            for victim in entry.get("victims", []):
                fee_list.append(clean_fee(victim.get("Details", {}).get("Fee", "")))
                priority_fee_list.append(clean_fee(victim.get("Details", {}).get("Priority Fee", "")))

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
            bot1, bot2 = entry.get("bot1", {}), entry.get("bot2", {})
            if bot1.get("token_start") == bot2.get("token_end") and bot1.get("token_start") == "sol":
                try:
                    start = parse_number(bot1.get("value_start", 0))
                    end = parse_number(bot2.get("value_end", 0))
                    fee1 = clean_fee(bot1.get("Details", {}).get("Fee", "0"))
                    fee2 = clean_fee(bot2.get("Details", {}).get("Fee", "0"))
                    profit_list.append(end - start - fee1 - fee2)
                except:
                    continue
    if not profit_list:
        return 0, 0, 0
    return min(profit_list), sum(profit_list) / len(profit_list), max(profit_list)

# --- Caricamento dati ---

def load_data():
    if not os.path.exists("sandwich.jsonl"):
        return []
    with open("sandwich.jsonl", "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]

# --- Generazione grafici ---

def generate_figures(data, epoch):
    df_bots = pd.DataFrame(top_bot(data, 8, epoch), columns=["Bot", "Frequenza"])
    df_trades = pd.DataFrame(top_trades(data, 8, epoch), columns=["Trade", "Frequenza"])

    fig_bots = px.bar(df_bots, x="Bot", y="Frequenza", title="Top 8 Bot per Frequenza", color="Bot")
    fig_trades = px.bar(df_trades, x="Trade", y="Frequenza", title="Top 8 Trade Pairs", color="Trade")

    for fig in [fig_bots, fig_trades]:
        fig.update_layout(plot_bgcolor="#222", paper_bgcolor="#222", font_color="white", xaxis_tickangle=45)

    return fig_bots, fig_trades

# --- Dash App ---

app = Dash(__name__)
app.title = "Sandwich Attack Dashboard"

def make_stat_block(label, value):
    return html.Div([
        html.Div(label, style={"fontWeight": "bold", "fontSize": "18px"}),
        html.Div(f"{value:.6f} SOL", style={"fontSize": "16px"})
    ], style={"flex": "1", "textAlign": "center", "padding": "10px"})

app.layout = html.Div(style={"backgroundColor": "#222", "color": "white", "padding": "20px"}, children=[
    html.H1("Sandwich Attack Dashboard", style={"textAlign": "center"}),

    dcc.Dropdown(
        id="epoch-dropdown",
        options=[{"label": f"Epoca {i}", "value": str(i)} for i in range(770, 775)] + [{"label": "All", "value": ""}],
        value="",
        style={"backgroundColor": "#444", "color": "white", "borderRadius": "5px"}
    ),

    html.Div(style={"display": "flex", "marginTop": "20px"}, children=[
        html.Div(id="stats-values", style={"flex": "1", "marginRight": "20px"}),
        html.Div([
            html.H3("Prezzo SOL (Real Time)", style={"textAlign": "center"}),
            dcc.Graph(id="sol-price-chart")
        ], style={"flex": "1"})
    ]),

    dcc.Graph(id="bot-chart"),
    dcc.Graph(id="trade-chart"),
    dcc.Graph(id="heatmap-chart"),

    dcc.Interval(id="interval-component", interval=120*1000, n_intervals=0),
    dcc.Interval(id="price-interval", interval=30*1000, n_intervals=0),
    html.Div("Dati aggiornati ogni 120 secondi", style={"textAlign": "center", "fontSize": "14px", "marginTop": "10px"})
])

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

    stats = html.Div([
    html.Div([
        html.Div([make_stat_block("Min Fee", min_fee),
                  make_stat_block("Average Fee", avg_fee),
                  make_stat_block("Max Fee", max_fee)],
                 style={"display": "flex", "justifyContent": "center", "marginTop": "50px"}),

        html.Div([make_stat_block("Min Priority Fee", min_priority_fee),
                  make_stat_block("Average Priority Fee", avg_priority_fee),
                  make_stat_block("Max Priority Fee", max_priority_fee)],
                 style={"display": "flex", "justifyContent": "center", "marginTop": "100px"}),

        html.Div([make_stat_block("Min Net Profit", min_profit),
                  make_stat_block("Average Net Profit", avg_profit),
                  make_stat_block("Max Net Profit", max_profit)],
                 style={"display": "flex", "justifyContent": "center", "marginTop": "100px"})
    ], style={"textAlign": "center", "marginTop": "20px"})
])

    return fig_bots, fig_trades, fig_heatmap, stats

@app.callback(
    Output("sol-price-chart", "figure"),
    Input("price-interval", "n_intervals")
)
def update_sol_price_chart(n):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": "SOLUSDT", "interval": "1h", "limit": 24}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        raw_data = response.json()

        df = pd.DataFrame(raw_data, columns=[
            "timestamp", "open", "high", "low", "close",
            "volume", "close_time", "quote_asset_volume",
            "number_of_trades", "taker_buy_base", "taker_buy_quote", "ignore"
        ])

        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["close"] = df["close"].astype(float)

        fig = px.line(
            df,
            x="timestamp",
            y="close",
            title="Prezzo di SOL (USD - Ultime 24h)",
            labels={"close": "USD", "timestamp": "Orario"}
        )
        fig.update_layout(plot_bgcolor="#222", paper_bgcolor="#222", font_color="white")
        return fig

    except Exception as e:
        fig = go.Figure()
        fig.add_annotation(
            text="⚠️ Errore nel caricamento del prezzo di SOL.",
            xref="paper", yref="paper", showarrow=False,
            font=dict(color="red", size=16),
            x=0.5, y=0.5
        )
        fig.update_layout(title="Prezzo di SOL non disponibile", plot_bgcolor="#222", paper_bgcolor="#222", font_color="white")
        print("Errore Binance:", e)
        return fig


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
