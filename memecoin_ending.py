import csv
import requests
import time
from datetime import datetime
import os
from tqdm import tqdm  # <-- Progress bar

# 🔑 Your Helius API key
API_KEY = "7a49b0b5-1b22-4872-b13f-2e50d689778c"

# 🌐 RPC endpoint
HELIUS_RPC_ENDPOINT = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"

# 📁 Input / Output files
INPUT_CSV = "memecoin_appoggio.csv"
OUTPUT_CSV = "memecoin_with_last_activity.csv"

def get_last_activity(mint_address):
    """
    Returns the date of the most recent transaction for the given mint address
    using getSignaturesForAddress (Helius RPC).
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [
            mint_address,
            {"limit": 1}
        ]
    }

    try:
        response = requests.post(HELIUS_RPC_ENDPOINT, json=payload, headers={"Content-Type": "application/json"})
        if response.status_code != 200:
            print(f"\nAPI error for {mint_address}: {response.status_code} - {response.text}")
            return None

        data = response.json()

        if "result" in data and isinstance(data["result"], list) and len(data["result"]) > 0:
            tx = data["result"][0]
            block_time = tx.get("blockTime")
            if block_time:
                return datetime.fromtimestamp(block_time).isoformat()

        return None

    except Exception as e:
        print(f"\nException for {mint_address}: {e}")
        return None

def main():
    print(f"🔍 Starting processing of {INPUT_CSV}...\n")

    # --- Step 1: Read all mints from input CSV ---
    with open(INPUT_CSV, newline='', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        input_rows = list(reader)
        input_mints = [row["mint"] for row in input_rows]

    # --- Step 2: Check existing output (if any) ---
    existing_mints = set()
    file_exists = os.path.exists(OUTPUT_CSV)

    if file_exists:
        with open(OUTPUT_CSV, newline='', encoding='utf-8') as outfile:
            reader = csv.DictReader(outfile)
            existing_mints = {row["mint"] for row in reader}
        print(f"📂 Found {len(existing_mints)} existing entries in {OUTPUT_CSV}.")
    else:
        print("🆕 Output file not found — creating a new one.")

    # --- Step 3: Find missing mints ---
    missing_rows = [row for row in input_rows if row["mint"] not in existing_mints]
    print(f"🪙 Found {len(missing_rows)} missing mints to process.\n")

    if not missing_rows:
        print("✅ No missing mints found. Everything is up to date!")
        return

    # --- Step 4: Open output file in append mode ---
    with open(OUTPUT_CSV, 'a', newline='', encoding='utf-8') as outfile:
        fieldnames = list(input_rows[0].keys()) + ["last_activity"]
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)

        # Write header if creating new file
        if not file_exists:
            writer.writeheader()

        # --- Step 5: Process missing mints with a progress bar ---
        for row in tqdm(missing_rows, desc="Processing mints", unit="mint"):
            mint = row["mint"]
            last_date = get_last_activity(mint)
            row["last_activity"] = last_date if last_date else ""
            writer.writerow(row)

            # Rate limiting (Helius free tier: ~100 req/min)
            time.sleep(0.6)

    print(f"\n✅ Completed! Added {len(missing_rows)} new rows to {OUTPUT_CSV}.")

if __name__ == "__main__":
    main()
