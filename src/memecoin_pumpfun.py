import requests
from datetime import datetime, timezone
import csv
import os
import time
from collections import defaultdict

CSV_FILE = "memecoin_pumpfun.csv"
POLL_INTERVAL = 30  

# Dizionari di conteggio
tokens_per_minute = defaultdict(int)
tokens_per_hour = defaultdict(int)

# Contatore totale token raccolti
total_tokens_saved = 0


def fetch_latest_pumpfun_token():
    url = "https://api.pumpfunapi.org/pumpfun/new/tokens"
    response = requests.get(url)

    if response.status_code != 200:
        print("❌ Errore nel recupero dati:", response.status_code)
        return None

    token = response.json()

    name = token.get("name", "")
    symbol = token.get("symbol", "")
    mint = token.get("mint", "")
    created_at = token.get("createdAt")

    if created_at:
        launched_at = created_at.replace("T", " ").split(".")[0]
    else:
        launched_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") + " (stimato)"

    return {
        "Nome": name,
        "Ticker": symbol,
        "Tipo": "Meme",
        "Blockchain/Note": "Pump.fun",
        "mint": mint,
        "launched_at": launched_at,
        "pumpfun_link": f"https://pump.fun/{mint}"
    }


def load_existing_mints(filename):
    if not os.path.isfile(filename):
        return set()
    
    with open(filename, mode="r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        return set(row.get("mint", "") for row in reader if "mint" in row)


def save_token_to_csv(token, filename):
    file_exists = os.path.isfile(filename)

    fieldnames = ["Nome", "Ticker", "Tipo", "Blockchain/Note", "mint", "launched_at", "pumpfun_link"]

    with open(filename, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerow(token)


def update_stats():
    """Mostra statistiche di quanti token sono stati salvati per minuto e per ora"""
    print("\n📊 Statistiche memecoin raccolte:\n")

    # --- Per minuto
    print("⏱️  Dettaglio per minuto:")
    for minute, count in sorted(tokens_per_minute.items()):
        print(f"   {minute}: {count} token")

    # --- Per ora
    print("\n🕒 Riepilogo per ora:")
    total = 0
    for hour, count in sorted(tokens_per_hour.items()):
        print(f"   {hour}: {count} token")
        total += count

    if tokens_per_hour:
        avg_per_hour = total / len(tokens_per_hour)
        print(f"\n📈 Media stimata: ~{avg_per_hour:.2f} token/ora")
    print("")


if __name__ == "__main__":
    print("📡 Avvio monitoraggio token Pump.fun...\n")

    known_mints = load_existing_mints(CSV_FILE)

    try:
        while True:
            token = fetch_latest_pumpfun_token()
            if token:
                mint = token["mint"]
                if mint and mint not in known_mints:
                    print(f"🆕 Nuovo token trovato: {token['Nome']} ({token['Ticker']})")
                    print(f"   Mint: {mint}")
                    print(f"   Launched at: {token['launched_at']}")
                    print(f"   Link: {token['pumpfun_link']}\n")

                    save_token_to_csv(token, CSV_FILE)
                    known_mints.add(mint)

                    # ➕ Aggiorna contatori
                    current_minute = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
                    current_hour = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:00")
                    tokens_per_minute[current_minute] += 1
                    tokens_per_hour[current_hour] += 1

                    total_tokens_saved += 1

                    # ✅ Mostra statistiche ogni 100 token raccolti
                    if total_tokens_saved % 100 == 0:
                        update_stats()
                else:
                    print(f"⏩ Nessun nuovo token. Ultimo visto: {token['Nome']} ({token['Ticker']})")

            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n🛑 Monitoraggio interrotto manualmente.")
        update_stats()
