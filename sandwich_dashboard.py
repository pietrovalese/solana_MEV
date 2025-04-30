import json
import pandas as pd
from dash import Dash, dcc, html, callback, Output, Input, MATCH, callback_context, ctx
from dash.dependencies import Output, Input
import plotly.express as px
import plotly.graph_objects as go
import os
import re
import requests
from datetime import datetime
import time
from dotenv import load_dotenv

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

def get_last_sandwich_attacks(data, n=5):
    return data[-n:]

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


def display_sandwich_attacks(epoch, callback_context):
    data = load_data()
    last_attacks = get_last_sandwich_attacks(data)

    attacks = []

    for i, entry in enumerate(last_attacks):
        bot1 = entry.get("bot1", {}).get("bot", "Unknown Bot")
        bot2 = entry.get("bot2", {}).get("bot", "Unknown Bot")
        token_start = entry.get("bot1", {}).get("token_start", "Unknown Token")
        token_end = entry.get("bot1", {}).get("token_end", "Unknown Token")
        bot1_value_start = entry.get("bot1", {}).get("value_start")
        bot1_value_end = entry.get("bot1", {}).get("value_end")
        bot2_value_start = entry.get("bot2", {}).get("value_start")
        bot2_value_end = entry.get("bot2", {}).get("value_end")
        attack_id = entry.get("bot1", {}).get("hash", "Unknown ID")

        victims_divs = []
        for victim in entry.get("victims", []):
            victim_name = victim.get("victim", "Unknown Victim")
            v_token_start = victim.get("token_start", "Unknown Token")
            v_value_start = victim.get("value_start", "Unknown Value")
            v_token_end = victim.get("token_end", "Unknown Token")
            v_value_end = victim.get("value_end", "Unknown Value")

            victims_divs.extend([
                html.Div(f"Victim: {victim_name}", style={"fontWeight": "bold", "fontSize": "18px"}),
                html.Div(f"Token Start: {v_token_start} Value: {v_value_start} <-> Token End: {v_token_end} Value: {v_value_end}", style={"fontSize": "16px"}),
            ])

        attack_div = html.Div(
            children=[
                html.Div(f"Bot: {bot1}", style={"fontWeight": "bold", "fontSize": "18px"}),
                html.Div(f"Token Start: {token_start} Value: {bot1_value_start} <-> Token End: {token_end} Value: {bot1_value_end}", style={"fontSize": "16px"}),
                *victims_divs,
                html.Div(f"Bot: {bot2}", style={"fontWeight": "bold", "fontSize": "18px"}),
                html.Div(f"Token Start: {token_end} Value: {bot2_value_start} <-> Token End: {token_start} Value: {bot2_value_end}", style={"fontSize": "16px"}),
                html.Button(
                    "Visualizza Report",
                    id={"type": "generate-report-btn", "index": attack_id},
                    n_clicks=0,
                    style={"backgroundColor": "#444", "color": "white", "borderRadius": "5px", "marginTop": "10px"}
                ),
                html.Div(id={"type": "report-div", "index": attack_id}, style={"marginTop": "10px"})
            ],
            style={"border": "1px solid #444", "margin": "10px", "padding": "10px", "cursor": "pointer"}
        )

        attacks.append(attack_div)


    return attacks


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

    html.Div(id="sandwich-attack-list", style={"marginTop": "20px"}),  # Qui verranno mostrati gli attacchi
    dcc.Graph(id="bot-chart"),
    dcc.Graph(id="trade-chart"),
    #dcc.Graph(id="heatmap-chart"),

    dcc.Interval(id="interval-component", interval=120*1000, n_intervals=0),
    dcc.Interval(id="price-interval", interval=30*1000, n_intervals=0),
    html.Div("Dati aggiornati ogni 120 secondi", style={"textAlign": "center", "fontSize": "14px", "marginTop": "10px"})
])


@app.callback(
    Output({"type": "report-div", "index": MATCH}, "children"),
    Input({"type": "generate-report-btn", "index": MATCH}, "n_clicks"),
)
def generate_report(n_clicks):
    if not n_clicks:
        return ""
    triggered_id = ctx.triggered_id
    attack_id = triggered_id["index"]

    load_dotenv()
    API_KEY = os.getenv("API_KEY")
    
    data = load_data()
    sandwiches = get_last_sandwich_attacks(data, n=5)
    signatures = []
    
    for entry in sandwiches:
        if entry.get("bot1", {}).get("hash", {}) == attack_id:
            signatures.append(entry.get("bot1", {}).get("hash", ""))
            signatures.append(entry.get("bot2", {}).get("hash", ""))
            
            for victim in entry.get("victims", []):
                hash_val = victim.get("hash", "")
                if hash_val:  
                    signatures.append(hash_val)

    signatures = list(filter(None, set(signatures)))
    
    for signature in signatures:
        url = f"https://api.solanabeach.io/v1/transaction/{signature}"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }

        response = requests.get(url, headers=headers)

        if response.ok:
            tx_details = response.json()
            flat_line = json.dumps(tx_details, separators=(',', ':'), ensure_ascii=False).replace("\n", "")
            with open("sandwich_details.jsonl", 'a', encoding='utf-8') as out:
                out.write(flat_line + '\n')
        else:
            print(f"Errore: {response.status_code} - {response.text}")
        time.sleep(2.5)
    
    
    from report import create_report_sandwich
    final_report = create_report_sandwich("sandwich_details.jsonl")
    
    return html.Div([
        html.H4("📄 Report Finale"),
        html.Pre(final_report)  # Usa html.Pre per mantenere formattazione testo
    ])


@app.callback(
    [
        Output("bot-chart", "figure"),
        Output("trade-chart", "figure"),
        Output("stats-values", "children"),
        Output("sandwich-attack-list", "children"),
    ],
    [
        Input("epoch-dropdown", "value"),
        Input("interval-component", "n_intervals")
    ]
)
def update_dashboard(epoch, callback_context):
    
    ctx = callback_context
    
    data = load_data()
    last_attacks = get_last_sandwich_attacks(data)

    # Generazione dei grafici
    fig_bots, fig_trades = generate_figures(data, epoch)

    # Calcolo delle statistiche
    min_fee, min_priority_fee, avg_fee, avg_priority_fee, max_fee, max_priority_fee = avg_fee_and_priority_fee(data, epoch)
    min_profit, avg_profit, max_profit = avg_net_profit(data, epoch)

    # Statistiche da visualizzare
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

    # Visualizzazione degli attacchi
    attacks = []

    for i, entry in enumerate(last_attacks):
        bot1 = entry.get("bot1", {}).get("bot", "Unknown Bot")
        bot2 = entry.get("bot2", {}).get("bot", "Unknown Bot")
        token_start = entry.get("bot1", {}).get("token_start", "Unknown Token")
        token_end = entry.get("bot1", {}).get("token_end", "Unknown Token")
        bot1_value_start = entry.get("bot1", {}).get("value_start")
        bot1_value_end = entry.get("bot1", {}).get("value_end")
        bot2_value_start = entry.get("bot2", {}).get("value_start")
        bot2_value_end = entry.get("bot2", {}).get("value_end")
        attack_id = entry.get("bot1", {}).get("hash", "Unknown ID")

        victims_divs = []
        for victim in entry.get("victims", []):
            victim_name = victim.get("victim", "Unknown Victim")
            v_token_start = victim.get("token_start", "Unknown Token")
            v_value_start = victim.get("value_start", "Unknown Value")
            v_token_end = victim.get("token_end", "Unknown Token")
            v_value_end = victim.get("value_end", "Unknown Value")

            victims_divs.extend([
                html.Div(f"{victim_name}", style={"fontWeight": "bold", "fontSize": "18px", "color": "#ffffff"}),
                html.Div(f"Token Start: {v_token_start} Value: {v_value_start} <-> Token End: {v_token_end} Value: {v_value_end}", style={"fontSize": "16px", "color": "#dddddd"}),
            ])


        attack_div = html.Div(
            children=[
                # BOT 1
                html.Div([
                    html.Div(f"{bot1}", style={"fontWeight": "bold", "fontSize": "18px", "color": "#ffffff"}),
                    html.Div(f"Token Start: {token_start} Value: {bot1_value_start} <-> Token End: {token_end} Value: {bot1_value_end}", style={"fontSize": "16px", "color": "#dddddd"}),
                ], style={"backgroundColor": "#2c3e50", "padding": "10px", "borderRadius": "8px"}),

                html.Hr(style={"borderColor": "#555"}),

                # VITTIME
                html.Div([
                    html.Div("Victims:", style={"fontWeight": "bold", "fontSize": "17px", "color": "#e74c3c", "marginBottom": "5px"}),
                    *victims_divs
                ], style={"backgroundColor": "#3b3b3b", "padding": "10px", "borderRadius": "8px"}),

                html.Hr(style={"borderColor": "#555"}),

                # BOT 2
                html.Div([
                    html.Div(f"{bot2}", style={"fontWeight": "bold", "fontSize": "18px", "color": "#ffffff"}),
                    html.Div(f"Token Start: {token_end} Value: {bot2_value_start} <-> Token End: {token_start} Value: {bot2_value_end}", style={"fontSize": "16px", "color": "#dddddd"}),
                ], style={"backgroundColor": "#2c3e50", "padding": "10px", "borderRadius": "8px"}),

                html.Hr(style={"borderColor": "#555"}),

                html.Button(
                    "Visualizza Report",
                    id={"type": "generate-report-btn", "index": attack_id},
                    n_clicks=0,
                    style={"backgroundColor": "#8e44ad", "color": "white", "borderRadius": "5px", "marginTop": "10px", "padding": "10px 20px", "border": "none"}
                ),

                html.Div(id={"type": "report-div", "index": attack_id}, style={"marginTop": "10px"})
            ],
            style={
                "backgroundColor": "#1e1e1e",  # ✅ sfondo scuro del contenitore
                "border": "1px solid #444",
                "margin": "15px",
                "padding": "20px",
                "borderRadius": "12px",
                "boxShadow": "2px 2px 10px rgba(0,0,0,0.3)"
            }
        )

        attacks.append(attack_div)

    return fig_bots, fig_trades, stats, attacks


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
    app.run(host='0.0.0.0', port=8050, debug=True)
