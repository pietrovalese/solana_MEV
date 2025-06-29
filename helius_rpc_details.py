import requests
import json
import time

def transaction_parsing(tx_hash):
    RPC_URL = "https://mainnet.helius-rpc.com/?api-key=7a49b0b5-1b22-4872-b13f-2e50d689778c"
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

    # Effettua la richiesta
    response = requests.post(RPC_URL, json=payload)

    # Parsing del contenuto JSON della risposta
    response_data = response.json()

    return response_data 

def get_epoch_from_slot(slot, slots_per_epoch=432000):
    """
    Calcola l'epoch dato uno slot, basandosi su slots_per_epoch.

    :param slot: int, numero di slot
    :param slots_per_epoch: int, numero di slot per epoch (default 432000)
    :return: int, numero di epoch
    """
    return slot // slots_per_epoch


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
            "Epoch": get_epoch_from_slot(tx.get("slot")),
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


def process_jsonl_file(input_path, output_path):
    with open(input_path, 'r') as infile, open(output_path, 'w') as outfile:
        for line in infile:
            try:
                data = json.loads(line)
                rpc_response = data.get("response", {})
                simplified = simplify_rpc_response(rpc_response)
                outfile.write(json.dumps(simplified) + "\n")
            except json.JSONDecodeError:
                print("Errore nel parsing JSON di una riga.")

def process_sandwich_file(input_path, output_path):

    def enrich_with_details(obj, key="hash"):
        tx_hash = obj.get(key)
        if tx_hash:
            try:
                rpc = transaction_parsing(tx_hash)
                details = simplify_rpc_response(rpc)
                obj["details"] = details
            except Exception as e:
                obj["details"] = {"error": str(e)}
        return obj

    with open(input_path, "r") as infile, open(output_path, "w") as outfile:
        for line in infile:
            time.sleep(2)
            try:
                data = json.loads(line)

                if "bot1" in data:
                    data["bot1"] = enrich_with_details(data["bot1"])

                if "bot2" in data:
                    data["bot2"] = enrich_with_details(data["bot2"])

                if "victims" in data:
                    data["victims"] = [enrich_with_details(v) for v in data["victims"]]

                outfile.write(json.dumps(data) + "\n")

            except json.JSONDecodeError:
                continue

if __name__ == "__main__":
    process_sandwich_file("sandwich_ristretto.jsonl", "sandwich_dettagliato.jsonl")
    
