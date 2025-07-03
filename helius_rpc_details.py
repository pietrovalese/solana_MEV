import requests
import json
import time
from tqdm import tqdm
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("API_KEY")
DELAY_SECONDS = 2  

def transaction_parsing(tx_hash):
    RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            tx_hash,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0
            }
        ]
    }

    try:
        response = requests.post(RPC_URL, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Errore nella richiesta per {tx_hash}: {e}")
        return {}

def get_epoch_from_slot(slot, slots_per_epoch=432000):
    return slot // slots_per_epoch if slot else None

def simplify_rpc_response(rpc_response):
    try:
        tx = rpc_response.get("result", {})
        meta = tx.get("meta", {})
        transaction = tx.get("transaction", {})
        message = transaction.get("message", {})
        account_keys = message.get("accountKeys", [])

        simplified = {
            "blockTime": tx.get("blockTime"),
            "slot": tx.get("slot"),
            "epoch": get_epoch_from_slot(tx.get("slot")),
            "fee": meta.get("fee"),
            "compute_units_consumed": meta.get("computeUnitsConsumed"),
            "status": "success" if meta.get("err") is None else "error",
            "signer": account_keys[0] if account_keys else None,
            "transfers": {
                "sol": [],
                "tokens": []
            }
        }

        for inner in meta.get("innerInstructions", []):
            for inst in inner.get("instructions", []):
                parsed = inst.get("parsed", {}).get("info", {})
                if inst.get("program") == "system" and inst.get("parsed", {}).get("type") == "transfer":
                    simplified["transfers"]["sol"].append({
                        "from": parsed.get("source"),
                        "to": parsed.get("destination"),
                        "lamports": parsed.get("lamports")
                    })
                elif inst.get("program") == "spl-token" and inst.get("parsed", {}).get("type") == "transfer":
                    simplified["transfers"]["tokens"].append({
                        "mint": parsed.get("mint"),
                        "from": parsed.get("source"),
                        "to": parsed.get("destination"),
                        "amount": parsed.get("amount"),
                        "decimals": parsed.get("decimals")
                    })

        return simplified

    except Exception as e:
        print("Errore nella semplificazione:", e)
        return {}

def load_existing_ids(output_path):
    existing_ids = set()
    if os.path.exists(output_path):
        with open(output_path, "r") as exfile:
            for line in exfile:
                try:
                    obj = json.loads(line)
                    if "Id" in obj:
                        existing_ids.add(obj["Id"])
                except json.JSONDecodeError:
                    continue
    return existing_ids

def process_sandwich_file(input_path, output_path):

    def enrich_with_details(obj, key="hash"):
        tx_hash = obj.get(key)
        if tx_hash:
            try:
                rpc = transaction_parsing(tx_hash)
                details = simplify_rpc_response(rpc)
                obj["Details"] = details
            except Exception as e:
                obj["Details"] = {"error": str(e)}
        return obj

    with open(input_path, "r") as infile:
        lines = infile.readlines()
        
    existing_ids = load_existing_ids(output_path)
    total_lines = len(lines)

    with open(output_path, "a") as outfile:
        for line in tqdm(lines, total=total_lines, desc="Enrichment transazioni", unit="tx",
                         bar_format="{l_bar}{bar} | {n_fmt}/{total_fmt} | ETA: {remaining} | {rate_fmt}"):
            try:
                data = json.loads(line)
                if data.get("Id") in existing_ids:
                    print("Sandwich already exist")
                    continue

                if "bot1" in data:
                    data["bot1"] = enrich_with_details(data["bot1"])
                    time.sleep(DELAY_SECONDS)

                if "bot2" in data:
                    data["bot2"] = enrich_with_details(data["bot2"])
                    time.sleep(DELAY_SECONDS)

                if "victims" in data:
                    enriched_victims = []
                    for victim in data["victims"]:
                        enriched_victims.append(enrich_with_details(victim))
                        time.sleep(DELAY_SECONDS)
                    data["victims"] = enriched_victims

                outfile.write(json.dumps(data) + "\n")

            except json.JSONDecodeError:
                continue


if __name__ == "__main__":
    process_sandwich_file("sandwich_appoggio.jsonl", "sandwich_enriched.jsonl")
    
        


