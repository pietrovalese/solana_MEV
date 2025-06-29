import csv
import requests
import os
import time
from tqdm import tqdm

csv_file_path = "meme_and_shitcoins_list.csv"

def fetch_coins_by_category(category):
    url = "https://api.coingecko.com/api/v3/coins/markets"
    coins = []
    page = 1

    while True:
        params = {
            "vs_currency": "usd",
            "category": category,
            "order": "market_cap_desc",
            "per_page": 250,
            "page": page
        }

        try:
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 429:
                print(f"⏳ Rate limit per categoria '{category}' — attendo 15 secondi...")
                time.sleep(15)
                continue  # riprova la stessa pagina

            response.raise_for_status()
            page_coins = response.json()
            if not page_coins:
                break
            coins.extend(page_coins)
            page += 1
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore richiesta categoria '{category}': {e}")
            break
        finally:
            time.sleep(2)  # attesa *dopo ogni richiesta*, sempre

    return coins

if __name__ == "__main__":
    # === Step 1: Leggi token esistenti dal CSV ===
    existing_tickers = set()
    if os.path.exists(csv_file_path):
        with open(csv_file_path, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                ticker = row.get("Ticker")
                if ticker:
                    existing_tickers.add(ticker.strip().upper())

    # === Step 2: Fetch da entrambe le categorie ===
    categories = {
        "meme-token": "Meme",
        "solana-meme-coins": "Solana Meme"
    }

    all_new_entries = []

    for i, (category, tipo) in enumerate(categories.items()):
        if i > 0:
            time.sleep(6)  # attesa prima della seconda categoria

        print(f"\n🔍 Scaricamento token per categoria: {tipo} ({category})...")
        coins = fetch_coins_by_category(category)
        print(f"📦 Trovati {len(coins)} token nella categoria '{category}'.")

        for coin in tqdm(coins, desc=f"⏳ Processamento {tipo}", unit="token"):
            ticker = coin["symbol"].strip().upper()
            if ticker not in existing_tickers:
                name = coin["name"]
                platforms = coin.get("platforms") or {}
                platforms_str = ", ".join(f"{k}:{v}" for k, v in platforms.items()) if platforms else "N/A"
                all_new_entries.append([name, ticker, tipo, platforms_str])
                existing_tickers.add(ticker)
                tqdm.write(f"✅ Aggiunto nuovo token: {name} ({ticker}) [{tipo}]")
            else:
                tqdm.write(f"⏩ Già presente: {ticker}")

    # === Step 3: Scrittura CSV ===
    file_exists = os.path.exists(csv_file_path)
    with open(csv_file_path, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Nome", "Ticker", "Tipo", "Blockchain/Note"])
        writer.writerows(all_new_entries)

    print(f"\n✅ Completato! {len(all_new_entries)} nuovi token aggiunti al file.")
