import requests
import csv
import time
import pandas as pd

API_KEY = "ec0b3aa9-2e83-48fc-95eb-71b52f0d424a"
HEADERS = {
    "Accepts": "application/json",
    "X-CMC_PRO_API_KEY": API_KEY,
}

def get_categories():
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/categories"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json().get("data", [])

def find_meme_category_ids(categories):
    return [
        cat["id"]
        for cat in categories
        if "meme" in cat["name"].lower() or "memes" in cat["name"].lower()
    ]

def get_all_coins_by_category_id(category_id):
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/category"
    all_coins = []
    start = 1
    limit = 100

    while True:
        params = {"id": category_id, "start": start, "limit": limit}
        resp = requests.get(url, headers=HEADERS, params=params)

        if resp.status_code == 429:
            print("⚠️ Rate limit raggiunto, attendo 10 secondi...")
            time.sleep(10)
            continue

        resp.raise_for_status()
        coins = resp.json().get("data", {}).get("coins", [])
        if not coins:
            break
        all_coins.extend(coins)
        start += limit

        time.sleep(2.5)  # ⏱️ attende per rispettare il rate limit
    return all_coins

def save_coins_to_csv(coins, filename="meme_coins.csv", write_header=False):
    with open(filename, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["id", "name", "symbol", "slug", "rank"])
        for c in coins:
            writer.writerow([c["id"], c["name"], c["symbol"], c["slug"]])

def main():
    print("📦 Fetching categories...")
    categories = get_categories()
    meme_ids = find_meme_category_ids(categories)

    if not meme_ids:
        print("❌ Nessuna categoria 'meme' trovata.")
        return

    for i, cat_id in enumerate(meme_ids):
        print(f"\n🔍 Categoria 'meme' trovata con ID: {cat_id}")
        print("⏳ Fetching all coins in this meme category...")

        coins = get_all_coins_by_category_id(cat_id)
        print(f"✅ Trovate {len(coins)} meme coin nella categoria.")

        save_coins_to_csv(coins, write_header=(i == 0))

    print("\n📁 File salvato come `meme_coins.csv`")

    # File in input
    file1 = "meme_and_shitcoins_list.csv" 
    file2 = "meme_coins.csv"  
    # Carica il primo file
    df1 = pd.read_csv(file1)
    df1 = df1.rename(columns={"Ticker": "symbol"})
    df1["symbol"] = df1["symbol"].str.upper()

    # Carica il secondo file
    df2 = pd.read_csv(file2)
    df2 = df2.rename(columns={"name": "Nome", "symbol": "symbol"})
    df2["symbol"] = df2["symbol"].str.upper()
    df2["Tipo"] = "Meme"
    df2["Blockchain/Note"] = "N/A"

    # Mantieni solo le colonne coerenti con il primo file
    df2 = df2[["Nome", "symbol", "Tipo", "Blockchain/Note"]]

    # Unione rimuovendo duplicati (basato sul symbol)
    merged_df = pd.concat([df1, df2], ignore_index=True)
    merged_df = merged_df.drop_duplicates(subset="symbol", keep="first")

    # Rinomina per riportare "symbol" a "Ticker"
    merged_df = merged_df.rename(columns={"symbol": "Ticker"})

    # Salva nel nuovo file
    merged_df.to_csv("memecoin_unificato.csv", index=False)

    print("✅ Unione completata: salvato come 'memecoin_unificato.csv'")


if __name__ == "__main__":
    main()
    
