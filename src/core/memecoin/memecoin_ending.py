import csv
import requests
import time
import os
from datetime import datetime
from tqdm import tqdm

HELIUS_RPC_ENDPOINT = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"
INPUT_CSV  = "memecoin_appoggio.csv"
OUTPUT_CSV = "memecoin_with_last_activity.csv"


def get_last_activity(mint_address):
    """Return the ISO timestamp of the most recent transaction for the given
    mint address using getSignaturesForAddress (Helius RPC), or None on failure."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [mint_address, {"limit": 1}],
    }
    try:
        response = requests.post(
            HELIUS_RPC_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        if response.status_code != 200:
            print(f"\nAPI error for {mint_address}: {response.status_code} - {response.text}")
            return None
        result = response.json().get("result")
        if isinstance(result, list) and result:
            block_time = result[0].get("blockTime")
            if block_time:
                return datetime.fromtimestamp(block_time).isoformat()
    except Exception as e:
        print(f"\nException for {mint_address}: {e}")
    return None


def main():
    print(f"Starting processing of {INPUT_CSV}...")

    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        input_rows = list(csv.DictReader(f))

    existing_mints = set()
    file_exists = os.path.exists(OUTPUT_CSV)
    if file_exists:
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            existing_mints = {row["mint"] for row in csv.DictReader(f)}
        print(f"Found {len(existing_mints)} existing entries in {OUTPUT_CSV}.")
    else:
        print("Output file not found — creating a new one.")

    missing_rows = [row for row in input_rows if row["mint"] not in existing_mints]
    print(f"Found {len(missing_rows)} missing mints to process.")

    if not missing_rows:
        print("No missing mints found. Everything is up to date.")
        return

    fieldnames = list(input_rows[0].keys()) + ["last_activity"]
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        for row in tqdm(missing_rows, desc="Processing mints", unit="mint"):
            last_date = get_last_activity(row["mint"])
            row["last_activity"] = last_date or ""
            writer.writerow(row)
            time.sleep(0.6)  # Helius free tier: ~100 req/min

    print(f"Completed. Added {len(missing_rows)} new rows to {OUTPUT_CSV}.")


if __name__ == "__main__":
    main()