#!/usr/bin/env python3
"""
Helius Solana Block Fetcher
Scarica tutte le informazioni raw di un blocco Solana tramite le API di Helius.

Uso:
    python download_block.py <slot_number> [--output output.json]

La API key viene letta dalla variabile d'ambiente HELIUS_API_KEY.
In alternativa può essere passata con --api-key (sconsigliato in produzione).

Esempio:
    HELIUS_API_KEY=abc123 python download_block.py 280000000 --output block.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
load_dotenv()


# ─── Configurazione ───────────────────────────────────────────────────────────

DEFAULT_MAX_SUPPORTED_TRANSACTION_VERSION = 0
REQUEST_TIMEOUT = 60          # secondi
MAX_RETRIES     = 3           # tentativi per ogni chiamata RPC
RETRY_BACKOFF   = 2.0         # secondi di attesa tra un retry e l'altro


# ─── Eccezioni custom ─────────────────────────────────────────────────────────

class HeliusError(RuntimeError):
    """Errore generico delle API Helius."""

class BlockNotFoundError(HeliusError):
    """Il blocco richiesto non esiste o non è disponibile."""

class RateLimitError(HeliusError):
    """Rate limit raggiunto (HTTP 429)."""


# ─── Helius RPC Client ────────────────────────────────────────────────────────

class HeliusClient:
    def __init__(self, api_key: str, network: str = "mainnet"):
        if not api_key:
            raise HeliusError(
                "API key mancante. Imposta la variabile d'ambiente HELIUS_API_KEY "
                "oppure usa --api-key."
            )
        self.api_key = api_key
        self.network = network
        if network == "mainnet":
            self.rpc_url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
        elif network == "devnet":
            self.rpc_url = f"https://devnet.helius-rpc.com/?api-key={api_key}"
        else:
            raise ValueError(f"Network non supportata: {network}. Usa 'mainnet' o 'devnet'.")

    def _rpc_call(self, method: str, params: list) -> dict:
        """
        Esegue una chiamata JSON-RPC all'endpoint Helius con retry automatico
        su errori transitori (timeout, 5xx, 429).
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        headers = {"Content-Type": "application/json"}
        last_exc: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(
                    self.rpc_url,
                    json=payload,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                )

                if response.status_code == 429:
                    wait = RETRY_BACKOFF * attempt
                    print(f"[WARN] Rate limit (429). Attendo {wait:.1f}s… "
                          f"(tentativo {attempt}/{MAX_RETRIES})", file=sys.stderr)
                    time.sleep(wait)
                    last_exc = RateLimitError("HTTP 429 Too Many Requests")
                    continue

                if response.status_code >= 500:
                    wait = RETRY_BACKOFF * attempt
                    print(f"[WARN] Errore server {response.status_code}. "
                          f"Attendo {wait:.1f}s… (tentativo {attempt}/{MAX_RETRIES})",
                          file=sys.stderr)
                    time.sleep(wait)
                    last_exc = HeliusError(f"HTTP {response.status_code}")
                    continue

                response.raise_for_status()
                data = response.json()

                if "error" in data:
                    err = data["error"]
                    # -32009 = slot skipped / not available
                    if isinstance(err, dict) and err.get("code") in (-32009, -32004):
                        raise BlockNotFoundError(
                            f"Slot non disponibile (codice {err.get('code')}): "
                            f"{err.get('message', '')}"
                        )
                    raise HeliusError(f"Errore RPC ({method}): {err}")

                return data.get("result")

            except (requests.Timeout, requests.ConnectionError) as e:
                wait = RETRY_BACKOFF * attempt
                print(f"[WARN] Errore di rete: {e}. "
                      f"Attendo {wait:.1f}s… (tentativo {attempt}/{MAX_RETRIES})",
                      file=sys.stderr)
                time.sleep(wait)
                last_exc = e

            except (BlockNotFoundError, HeliusError):
                raise   # errori non recuperabili, non ha senso riprovare

        raise HeliusError(
            f"Chiamata {method} fallita dopo {MAX_RETRIES} tentativi. "
            f"Ultimo errore: {last_exc}"
        )

    def get_block(self, slot: int) -> dict:
        params = [
            slot,
            {
                "encoding": "jsonParsed",
                "transactionDetails": "full",
                "rewards": True,
                "maxSupportedTransactionVersion": DEFAULT_MAX_SUPPORTED_TRANSACTION_VERSION,
            },
        ]
        return self._rpc_call("getBlock", params)

    def get_block_time(self, slot: int) -> int | None:
        return self._rpc_call("getBlockTime", [slot])

    def get_block_height(self) -> int:
        return self._rpc_call("getBlockHeight", [])

    def get_slot(self) -> int:
        return self._rpc_call("getSlot", [])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def format_timestamp(ts: int | None) -> str:
    if ts is None:
        return "N/A"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def print_summary(slot: int, block: dict, block_time: int | None) -> None:
    transactions = block.get("transactions", [])
    rewards      = block.get("rewards", [])

    print("\n" + "═" * 60)
    print(f"  BLOCCO SOLANA — Slot {slot}")
    print("═" * 60)
    print(f"  Blockhash          : {block.get('blockhash', 'N/A')}")
    print(f"  Parent slot        : {block.get('parentSlot', 'N/A')}")
    print(f"  Previous blockhash : {block.get('previousBlockhash', 'N/A')}")
    print(f"  Timestamp          : {format_timestamp(block_time)}")
    print(f"  Block height       : {block.get('blockHeight', 'N/A')}")
    print(f"  Transazioni        : {len(transactions)}")
    print(f"  Rewards            : {len(rewards)}")

    successes = sum(1 for tx in transactions if tx.get("meta", {}).get("err") is None)
    failures  = len(transactions) - successes
    print(f"    ✓ Successo       : {successes}")
    print(f"    ✗ Fallite        : {failures}")

    total_fee = sum(tx.get("meta", {}).get("fee", 0) for tx in transactions)
    print(f"  Fee totali (lamport): {total_fee:,}  ({total_fee / 1e9:.6f} SOL)")

    if rewards:
        top = max(rewards, key=lambda r: r.get("lamports", 0))
        print(f"  Reward maggiore    : {top.get('lamports', 0):,} lamport → "
              f"{top.get('pubkey', 'N/A')[:20]}…")

    print("═" * 60 + "\n")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scarica un blocco Solana completo tramite le API di Helius."
    )
    parser.add_argument("slot", type=int, help="Numero dello slot da scaricare")
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key Helius (preferibile usare la variabile d'ambiente HELIUS_API_KEY)",
    )
    parser.add_argument(
        "--network",
        choices=["mainnet", "devnet"],
        default="mainnet",
        help="Rete Solana da usare (default: mainnet)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="File JSON dove salvare il blocco raw. Se omesso, stampa su stdout.",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Disabilita il riassunto a console",
    )
    args = parser.parse_args()

    # Risoluzione API key: argomento CLI > variabile d'ambiente
    api_key = args.api_key or os.environ.get("HELIUS_API_KEY", "")
    if not api_key:
        print(
            "ERRORE: API key non trovata.\n"
            "  Imposta HELIUS_API_KEY=<chiave> oppure usa --api-key <chiave>.",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        client = HeliusClient(api_key=api_key, network=args.network)
    except (HeliusError, ValueError) as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        sys.exit(2)

    print(f"[*] Connessione a Helius ({args.network})…")
    try:
        current_slot = client.get_slot()
        print(f"    Slot corrente: {current_slot:,}")
    except HeliusError as e:
        print(f"[WARN] Impossibile recuperare lo slot corrente: {e}", file=sys.stderr)

    print(f"[*] Scaricamento blocco slot {args.slot:,}…")
    t0 = time.time()
    try:
        block = client.get_block(args.slot)
    except BlockNotFoundError as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        sys.exit(1)
    except HeliusError as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.time() - t0
    print(f"    Fatto in {elapsed:.2f}s")

    if block is None:
        print("ERRORE: Blocco non trovato o slot non disponibile.", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Recupero timestamp blocco…")
    try:
        block_time = client.get_block_time(args.slot)
    except HeliusError as e:
        print(f"[WARN] Impossibile recuperare il timestamp: {e}", file=sys.stderr)
        block_time = None

    output_data = {
        "_meta": {
            "slot": args.slot,
            "network": args.network,
            "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
            "block_time_unix": block_time,
            "block_time_human": format_timestamp(block_time),
        },
        "block": block,
    }

    if not args.no_summary:
        print_summary(args.slot, block, block_time)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            size_mb = os.path.getsize(args.output) / 1024 / 1024
            print(f"[✓] Blocco salvato in '{args.output}' ({size_mb:.2f} MB)")
        except OSError as e:
            print(f"ERRORE scrittura file '{args.output}': {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(json.dumps(output_data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()