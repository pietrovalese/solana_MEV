#!/usr/bin/env python3
"""
Helius Solana Block Fetcher
Downloads all raw information for a Solana block via the Helius API.

Usage:
    python download_block.py <slot_number> [--output output.json]

The API key is read from the HELIUS_API_KEY environment variable.
It can also be passed via --api-key (not recommended in production).

Example:
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


# --- Configuration ---

DEFAULT_MAX_SUPPORTED_TRANSACTION_VERSION = 0
REQUEST_TIMEOUT = 60      # seconds
MAX_RETRIES     = 3       # attempts per RPC call
RETRY_BACKOFF   = 2.0     # seconds to wait between retries


# --- Custom exceptions ---

class HeliusError(RuntimeError):
    """Generic Helius API error."""

class BlockNotFoundError(HeliusError):
    """The requested block does not exist or is not available."""

class RateLimitError(HeliusError):
    """Rate limit reached (HTTP 429)."""


# --- Helius RPC Client ---

class HeliusClient:
    def __init__(self, api_key: str, network: str = "mainnet"):
        """Initializes the client with the given API key and target network.
        Raises HeliusError if the key is missing, or ValueError for unsupported networks."""
        if not api_key:
            raise HeliusError(
                "API key missing. Set the HELIUS_API_KEY environment variable "
                "or use --api-key."
            )
        self.api_key = api_key
        self.network = network
        if network == "mainnet":
            self.rpc_url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
        elif network == "devnet":
            self.rpc_url = f"https://devnet.helius-rpc.com/?api-key={api_key}"
        else:
            raise ValueError(f"Unsupported network: {network}. Use 'mainnet' or 'devnet'.")

    def _rpc_call(self, method: str, params: list) -> dict:
        """Executes a JSON-RPC call to the Helius endpoint with automatic retry on transient errors.
        Retries on timeout, 5xx responses, and 429 rate limits; raises immediately on non-recoverable errors."""
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
                    print(f"[WARN] Rate limit (429). Waiting {wait:.1f}s... "
                          f"(attempt {attempt}/{MAX_RETRIES})", file=sys.stderr)
                    time.sleep(wait)
                    last_exc = RateLimitError("HTTP 429 Too Many Requests")
                    continue

                if response.status_code >= 500:
                    wait = RETRY_BACKOFF * attempt
                    print(f"[WARN] Server error {response.status_code}. "
                          f"Waiting {wait:.1f}s... (attempt {attempt}/{MAX_RETRIES})",
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
                            f"Slot not available (code {err.get('code')}): "
                            f"{err.get('message', '')}"
                        )
                    raise HeliusError(f"RPC error ({method}): {err}")

                return data.get("result")

            except (requests.Timeout, requests.ConnectionError) as e:
                wait = RETRY_BACKOFF * attempt
                print(f"[WARN] Network error: {e}. "
                      f"Waiting {wait:.1f}s... (attempt {attempt}/{MAX_RETRIES})",
                      file=sys.stderr)
                time.sleep(wait)
                last_exc = e

            except (BlockNotFoundError, HeliusError):
                raise   # non-recoverable errors, no point retrying

        raise HeliusError(
            f"Call {method} failed after {MAX_RETRIES} attempts. "
            f"Last error: {last_exc}"
        )

    def get_block(self, slot: int) -> dict:
        """Fetches the full block data for the given slot.
        Returns the raw block dict from the RPC result."""
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
        """Returns the estimated Unix timestamp for the given slot, or None if unavailable."""
        return self._rpc_call("getBlockTime", [slot])

    def get_block_height(self) -> int:
        """Returns the current block height of the node."""
        return self._rpc_call("getBlockHeight", [])

    def get_slot(self) -> int:
        """Returns the current slot as reported by the node."""
        return self._rpc_call("getSlot", [])


# --- Helpers ---

def format_timestamp(ts: int | None) -> str:
    """Converts a Unix timestamp to a human-readable UTC string.
    Returns 'N/A' if the timestamp is None."""
    if ts is None:
        return "N/A"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def print_summary(slot: int, block: dict, block_time: int | None) -> None:
    """Prints a human-readable summary of a Solana block to stdout.
    Includes transaction counts, fees, and top reward."""
    transactions = block.get("transactions", [])
    rewards      = block.get("rewards", [])

    print("\n" + "=" * 60)
    print(f"  SOLANA BLOCK -- Slot {slot}")
    print("=" * 60)
    print(f"  Blockhash          : {block.get('blockhash', 'N/A')}")
    print(f"  Parent slot        : {block.get('parentSlot', 'N/A')}")
    print(f"  Previous blockhash : {block.get('previousBlockhash', 'N/A')}")
    print(f"  Timestamp          : {format_timestamp(block_time)}")
    print(f"  Block height       : {block.get('blockHeight', 'N/A')}")
    print(f"  Transactions       : {len(transactions)}")
    print(f"  Rewards            : {len(rewards)}")

    successes = sum(1 for tx in transactions if tx.get("meta", {}).get("err") is None)
    failures  = len(transactions) - successes
    print(f"    Success          : {successes}")
    print(f"    Failed           : {failures}")

    total_fee = sum(tx.get("meta", {}).get("fee", 0) for tx in transactions)
    print(f"  Total fees (lamport): {total_fee:,}  ({total_fee / 1e9:.6f} SOL)")

    if rewards:
        top = max(rewards, key=lambda r: r.get("lamports", 0))
        print(f"  Top reward         : {top.get('lamports', 0):,} lamport -> "
              f"{top.get('pubkey', 'N/A')[:20]}...")

    print("=" * 60 + "\n")


# --- Main ---

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download a complete Solana block via the Helius API."
    )
    parser.add_argument("slot", type=int, help="Slot number to download")
    parser.add_argument(
        "--api-key",
        default=None,
        help="Helius API key (prefer using the HELIUS_API_KEY environment variable)",
    )
    parser.add_argument(
        "--network",
        choices=["mainnet", "devnet"],
        default="mainnet",
        help="Solana network to use (default: mainnet)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="JSON file to save the raw block. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Disable the console summary",
    )
    args = parser.parse_args()

    # API key resolution: CLI argument > environment variable
    api_key = args.api_key or os.environ.get("HELIUS_API_KEY", "")
    if not api_key:
        print(
            "ERROR: API key not found.\n"
            "  Set HELIUS_API_KEY=<key> or use --api-key <key>.",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        client = HeliusClient(api_key=api_key, network=args.network)
    except (HeliusError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    print(f"[*] Connecting to Helius ({args.network})...")
    try:
        current_slot = client.get_slot()
        print(f"    Current slot: {current_slot:,}")
    except HeliusError as e:
        print(f"[WARN] Could not retrieve current slot: {e}", file=sys.stderr)

    print(f"[*] Downloading block slot {args.slot:,}...")
    t0 = time.time()
    try:
        block = client.get_block(args.slot)
    except BlockNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except HeliusError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.time() - t0
    print(f"    Done in {elapsed:.2f}s")

    if block is None:
        print("ERROR: Block not found or slot not available.", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Fetching block timestamp...")
    try:
        block_time = client.get_block_time(args.slot)
    except HeliusError as e:
        print(f"[WARN] Could not retrieve timestamp: {e}", file=sys.stderr)
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
            print(f"[OK] Block saved to '{args.output}' ({size_mb:.2f} MB)")
        except OSError as e:
            print(f"ERROR writing file '{args.output}': {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(json.dumps(output_data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()