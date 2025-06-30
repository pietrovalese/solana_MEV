import csv
import requests
import os
import time
from tqdm import tqdm
from ratelimit import limits, sleep_and_retry

csv_file_path = "meme_and_shitcoins_list.csv"


# Limite ufficiale CoinGecko: 50 richieste per 60 secondi
RATE_LIMIT_CALLS = 50
RATE_LIMIT_PERIOD = 60  # secondi

@sleep_and_retry
@limits(calls=RATE_LIMIT_CALLS, period=RATE_LIMIT_PERIOD)
def safe_request(url, params):
    return requests.get(url, params=params, timeout=15)

def fetch_coins_by_category(category):
    url = "https://api.coingecko.com/api/v3/coins/markets"
    coins = []
    page = 1
    request_count = 0

    while True:
        params = {
            "vs_currency": "usd",
            "category": category,
            "order": "market_cap_desc",
            "per_page": 50,
            "page": page
        }

        try:
            response = safe_request(url, params=params)
            request_count += 1

            if response.status_code == 429:
                print(f"🚫 Rate limit superato. Attesa 60 secondi prima di riprovare...")
                time.sleep(60)
                continue

            response.raise_for_status()
            page_coins = response.json()
            if not page_coins:
                print(f"✅ Fine dei dati per '{category}' (pagina {page})")
                break

            coins.extend(page_coins)
            print(f"📄 Pagina {page} completata ({len(page_coins)} token)")
            page += 1

        except requests.exceptions.RequestException as e:
            print(f"❌ Errore richiesta categoria '{category}': {e}")
            break

        time.sleep(1.3)  # margine di sicurezza

    print(f"🔁 Richieste totali effettuate per '{category}': {request_count}")
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
        time.sleep(5)
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
