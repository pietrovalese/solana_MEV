import csv
import requests
import os
import time

csv_file_path = "meme_and_shitcoins_list.csv"


if __name__ == "__main__":
    # === Step 1: Carica ticker già presenti nel file ===
    existing_tickers = set()
    if os.path.exists(csv_file_path):
        with open(csv_file_path, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                existing_tickers.add(row["Ticker"].strip().upper())
    # === Step 2: Chiamata API CoinGecko per meme coin ===
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "category": "meme-token",
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1
    }
    response = requests.get(url, params=params)
    coins = response.json()
    # === Step 3: Apri file in append, scrivi solo nuove ===
    file_exists = os.path.exists(csv_file_path)
    with open(csv_file_path, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Nome", "Ticker", "Tipo", "Blockchain/Note"])
        for coin in coins:
            ticker = coin["symbol"].upper().strip()
            if ticker not in existing_tickers:
                name = coin["name"]
                platforms = coin.get("platforms") or "N/A"
                writer.writerow([name, ticker, "Meme", str(platforms)])
                print(f"✅ Aggiunto nuovo token: {name} ({ticker})")
            else:
                print(f"⏩ Già presente: {ticker}")
