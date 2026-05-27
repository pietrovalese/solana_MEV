import requests
from datetime import datetime, timezone
import csv
import os
import time
from collections import defaultdict

CSV_FILE = "memecoin_pumpfun.csv"
POLL_INTERVAL = 30

# Token count dictionaries
tokens_per_minute = defaultdict(int)
tokens_per_hour = defaultdict(int)

# Total number of tokens collected
total_tokens_saved = 0


def fetch_latest_pumpfun_token():
    """Fetches the latest token from the Pump.fun API.
    Returns a dict with token metadata, or None on failure."""
    url = "https://api.pumpfunapi.org/pumpfun/new/tokens"
    response = requests.get(url)
    if response.status_code != 200:
        print("Error fetching data:", response.status_code)
        return None
    token = response.json()
    name = token.get("name", "")
    symbol = token.get("symbol", "")
    mint = token.get("mint", "")
    created_at = token.get("createdAt")
    if created_at:
        launched_at = created_at.replace("T", " ").split(".")[0]
    else:
        launched_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") + " (estimated)"
    return {
        "Name": name,
        "Ticker": symbol,
        "Type": "Meme",
        "Blockchain/Notes": "Pump.fun",
        "mint": mint,
        "launched_at": launched_at,
        "pumpfun_link": f"https://pump.fun/{mint}"
    }


def load_existing_mints(filename):
    """Loads the set of already-saved mint addresses from the CSV file.
    Returns an empty set if the file does not exist."""
    if not os.path.isfile(filename):
        return set()
    with open(filename, mode="r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        return set(row.get("mint", "") for row in reader if "mint" in row)


def save_token_to_csv(token, filename):
    """Appends a token record to the CSV file, writing the header if needed.
    Does not return a value."""
    file_exists = os.path.isfile(filename)
    fieldnames = ["Name", "Ticker", "Type", "Blockchain/Notes", "mint", "launched_at", "pumpfun_link"]
    with open(filename, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(token)


def update_stats():
    """Prints a breakdown of collected tokens per minute and per hour.
    Also shows the estimated average tokens per hour."""
    print("\nCollected memecoin statistics:\n")

    # Per-minute breakdown
    print("Per-minute detail:")
    for minute, count in sorted(tokens_per_minute.items()):
        print(f"   {minute}: {count} token(s)")

    # Per-hour summary
    print("\nPer-hour summary:")
    total = 0
    for hour, count in sorted(tokens_per_hour.items()):
        print(f"   {hour}: {count} token(s)")
        total += count

    if tokens_per_hour:
        avg_per_hour = total / len(tokens_per_hour)
        print(f"\nEstimated average: ~{avg_per_hour:.2f} tokens/hour")
    print("")


if __name__ == "__main__":
    print("Starting Pump.fun token monitor...\n")
    known_mints = load_existing_mints(CSV_FILE)
    try:
        while True:
            token = fetch_latest_pumpfun_token()
            if token:
                mint = token["mint"]
                if mint and mint not in known_mints:
                    print(f"New token found: {token['Name']} ({token['Ticker']})")
                    print(f"   Mint: {mint}")
                    print(f"   Launched at: {token['launched_at']}")
                    print(f"   Link: {token['pumpfun_link']}\n")
                    save_token_to_csv(token, CSV_FILE)
                    known_mints.add(mint)

                    # Update counters
                    current_minute = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
                    current_hour = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:00")
                    tokens_per_minute[current_minute] += 1
                    tokens_per_hour[current_hour] += 1
                    total_tokens_saved += 1

                    # Print stats every 100 tokens collected
                    if total_tokens_saved % 100 == 0:
                        update_stats()
                else:
                    print(f"No new token. Last seen: {token['Name']} ({token['Ticker']})")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\nMonitoring stopped manually.")
        update_stats()