import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median
from typing import Optional


# --- Constants ---
SOL_MINT = "So11111111111111111111111111111111111111112"
# Validator vote program -- always excluded
VOTE_PROGRAM = "Vote111111111111111111111111111111111111111"
# Base fee per Solana transaction in lamports (5000 = ~0.000005 SOL)
BASE_FEE_LAMPORTS = 5_000

KNOWN_DEX_PROGRAMS = {
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM v4",
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP": "Orca v1",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc":  "Orca Whirlpool",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4":  "Jupiter v6",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB":  "Jupiter v4",
    "srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX":  "Serum/OpenBook",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium CLMM",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "Raydium CPMM",
}

# --- Data structures ---
@dataclass
class SwapInfo:
    tx_index:      int
    signature:     str
    signer:        str
    token_in:      str
    token_out:     str
    amount_in:     float
    amount_out:    float
    program:       str
    failed:        bool
    fee_sol:       float = 0.0            # fee paid in SOL (base + priority)
    pool_accounts: frozenset = field(default_factory=frozenset)
                                          # AMM/pool accounts involved in the tx
@dataclass
class VictimInfo:
    swap:              SwapInfo
    slippage_estimate: float              # estimated slippage % vs pre-frontrun price


@dataclass
class SandwichResult:
    frontrun:       SwapInfo
    victims:        list[VictimInfo]
    backrun:        SwapInfo
    profit_token:   str
    profit_raw:     float                 # raw delta (before fees)
    profit_net:     float                 # profit_raw - fee_frontrun - fee_backrun
    shared_pools:   frozenset             # pool accounts shared between front and back
    cross_dex:      bool                  # True if front and back use different DEXes
    confidence:     str                   # "HIGH" / "MEDIUM" / "LOW"


# --- Generic helpers ---

def get_signer(tx: dict) -> str:
    """Returns the public key of the first account (fee payer / signer) in a transaction.
    Returns an empty string if the key cannot be extracted."""
    try:
        account_keys = tx["transaction"]["message"]["accountKeys"]
        first = account_keys[0]
        return first["pubkey"] if isinstance(first, dict) else first
    except (KeyError, IndexError, TypeError):
        return ""


def get_account_keys_flat(tx: dict) -> list[str]:
    """Returns a flat list of all account keys in a transaction, including loaded addresses.
    Combines static keys with writable and readonly loaded addresses."""
    keys = []
    try:
        for k in tx["transaction"]["message"]["accountKeys"]:
            keys.append(k["pubkey"] if isinstance(k, dict) else k)
    except (KeyError, TypeError):
        pass
    try:
        loaded = tx["meta"].get("loadedAddresses", {})
        keys += loaded.get("writable", [])
        keys += loaded.get("readonly", [])
    except (AttributeError, KeyError):
        pass
    return keys


def is_vote_tx(tx: dict) -> bool:
    """Returns True if the transaction is a validator vote transaction (to be excluded).
    Detection is based on the presence of the vote program in the account keys."""
    try:
        keys = get_account_keys_flat(tx)
        return VOTE_PROGRAM in keys
    except Exception:
        return False


def extract_token_transfers(tx: dict) -> list[dict]:
    """Extracts token balance changes from a transaction's pre/post token balances.
    Returns a list of dicts with mint, owner, and delta amount."""
    meta = tx.get("meta", {})
    pre  = {b["accountIndex"]: b for b in meta.get("preTokenBalances", [])}
    post = {b["accountIndex"]: b for b in meta.get("postTokenBalances", [])}
    transfers = []
    for idx in set(pre) | set(post):
        pre_b  = pre.get(idx, {})
        post_b = post.get(idx, {})
        mint   = (post_b or pre_b).get("mint", "")
        owner  = (post_b or pre_b).get("owner", "")
        pre_amt  = float((pre_b.get("uiTokenAmount") or {}).get("uiAmount") or 0)
        post_amt = float((post_b.get("uiTokenAmount") or {}).get("uiAmount") or 0)
        delta    = post_amt - pre_amt
        if delta != 0:
            transfers.append({"mint": mint, "owner": owner, "delta": delta})
    return transfers


def sol_delta_for_signer(tx: dict, signer: str) -> float:
    """Computes the net SOL balance change for the signer of a transaction, excluding fees.
    Returns 0.0 if the signer is not found in the account keys."""
    meta = tx.get("meta", {})
    keys = get_account_keys_flat(tx)
    try:
        idx = keys.index(signer)
    except ValueError:
        return 0.0
    pre  = meta.get("preBalances", [])
    post = meta.get("postBalances", [])
    if idx >= len(pre) or idx >= len(post):
        return 0.0
    fee = meta.get("fee", 0)
    return (post[idx] - pre[idx] + fee) / 1e9


def get_fee_sol(tx: dict) -> float:
    """Returns the total fee paid for a transaction in SOL (base + priority).
    Falls back to BASE_FEE_LAMPORTS if the fee field is missing."""
    try:
        return tx["meta"].get("fee", BASE_FEE_LAMPORTS) / 1e9
    except (KeyError, TypeError):
        return BASE_FEE_LAMPORTS / 1e9


def get_pool_accounts(tx: dict) -> frozenset:
    """Returns the writable account keys of a transaction that belong to known DEX programs.
    Only writable accounts are included since AMM pools are always modified during a swap."""
    try:
        account_keys_raw = tx["transaction"]["message"]["accountKeys"]
        writable_keys = set()
        for k in account_keys_raw:
            if isinstance(k, dict):
                if k.get("writable"):
                    writable_keys.add(k["pubkey"])
            # For non-parsed transactions, writable info is unavailable -- skip
        # Add writable keys from loadedAddresses
        loaded = tx.get("meta", {}).get("loadedAddresses", {})
        writable_keys.update(loaded.get("writable", []))
        return frozenset(writable_keys)
    except (KeyError, TypeError):
        return frozenset()


# --- Swap parser ---

def infer_swap_from_transfers(
    tx_index: int,
    tx: dict,
    verbose: bool = False,
) -> Optional[SwapInfo]:
    """Reconstructs the main swap of a transaction from balance deltas.
    Returns a SwapInfo with fee and pool accounts, or None if the transaction is not a swap."""
    try:
        meta = tx.get("meta", {})
        if meta.get("err") is not None:
            return None

        signer = get_signer(tx)
        if not signer:
            return None

        transfers    = extract_token_transfers(tx)
        signer_xfers = [t for t in transfers if t["owner"] == signer]

        mint_deltas: dict[str, float] = {}
        for t in signer_xfers:
            mint_deltas[t["mint"]] = mint_deltas.get(t["mint"], 0) + t["delta"]
        mint_deltas = {m: d for m, d in mint_deltas.items() if abs(d) > 1e-9}

        sol_d  = sol_delta_for_signer(tx, signer)
        sold   = {m: abs(d) for m, d in mint_deltas.items() if d < 0}
        bought = {m: d       for m, d in mint_deltas.items() if d > 0}

        if sold and bought:
            token_in   = max(sold,   key=sold.get)
            token_out  = max(bought, key=bought.get)
            amount_in  = sold[token_in]
            amount_out = bought[token_out]
        elif sol_d < -0.000_001 and bought and not sold:
            token_in   = SOL_MINT
            token_out  = max(bought, key=bought.get)
            amount_in  = abs(sol_d)
            amount_out = bought[token_out]
        elif sol_d > 0.000_001 and sold and not bought:
            token_in   = max(sold, key=sold.get)
            token_out  = SOL_MINT
            amount_in  = sold[token_in]
            amount_out = sol_d
        else:
            return None

        account_keys = get_account_keys_flat(tx)
        program = next(
            (KNOWN_DEX_PROGRAMS[pk] for pk in account_keys if pk in KNOWN_DEX_PROGRAMS),
            "unknown",
        )

        sig = ""
        try:
            sig = tx["transaction"]["signatures"][0]
        except (KeyError, IndexError):
            pass

        return SwapInfo(
            tx_index      = tx_index,
            signature     = sig,
            signer        = signer,
            token_in      = token_in,
            token_out     = token_out,
            amount_in     = amount_in,
            amount_out    = amount_out,
            program       = program,
            failed        = False,
            fee_sol       = get_fee_sol(tx),
            pool_accounts = get_pool_accounts(tx),
        )

    except Exception as e:
        if verbose:
            print(f"[WARN] Error parsing tx {tx_index}: {e}", file=sys.stderr)
        return None


# --- Victim slippage estimation ---

def estimate_victim_slippage(
    victim: SwapInfo,
    frontrun: SwapInfo,
) -> float:
    """Estimates the slippage suffered by a victim by comparing its implicit price to the frontrun price.
    Returns 0.0 if the two swaps are in opposite directions or if amounts are zero."""
    if victim.token_in != frontrun.token_in or victim.token_out != frontrun.token_out:
        return 0.0
    if frontrun.amount_in == 0 or victim.amount_in == 0:
        return 0.0
    price_fr  = frontrun.amount_out / frontrun.amount_in
    price_vic = victim.amount_out   / victim.amount_in
    if price_fr == 0:
        return 0.0
    slippage = (price_fr - price_vic) / price_fr * 100
    return round(slippage, 4)


# --- Confidence classification ---

def classify_confidence(
    fr: SwapInfo,
    br: SwapInfo,
    victims: list[SwapInfo],
    shared_pools: frozenset,
    profit_net: float,
    gap: int,
) -> str:
    """Assigns a confidence level to a detected sandwich based on shared pools, net profit, and gap size.
    Returns 'HIGH' if all three criteria are met, 'MEDIUM' if at least one is, 'LOW' otherwise."""
    has_shared_pool = len(shared_pools) > 0
    has_net_profit  = profit_net > 0
    tight_gap       = gap <= 3

    score = sum([has_shared_pool, has_net_profit, tight_gap])

    if score == 3:
        return "HIGH"
    elif score >= 1:
        return "MEDIUM"
    else:
        return "LOW"


# --- Detection algorithm ---

def is_mirror_swap(a: SwapInfo, b: SwapInfo) -> bool:
    """Returns True if two swaps are mirror operations (A->B and B->A).
    Used to identify matching frontrun/backrun pairs."""
    return a.token_in == b.token_out and a.token_out == b.token_in


def detect_sandwiches(
    swaps: list[SwapInfo],
    max_gap: int = 10,
    min_profit_net: Optional[float] = None,
    verbose: bool = False,
) -> list[SandwichResult]:
    """Detects sandwich attacks in a list of ordered swaps using an advanced heuristic.
    Returns results sorted by descending net profit, optionally filtered by minimum profit."""
    results: list[SandwichResult] = []
    n = len(swaps)

    for i in range(n):
        fr = swaps[i]

        for j in range(i + 2, min(i + 1 + max_gap, n)):
            br = swaps[j]

            # Basic criteria
            if fr.signer != br.signer:
                continue
            if not is_mirror_swap(fr, br):
                continue

            # No bot transactions between front and back (avoids false positives)
            # If the bot makes another operation between front and back, it is likely
            # two separate trades rather than a sandwich.
            bot_tx_in_between = any(
                swaps[k].signer == fr.signer
                for k in range(i + 1, j)
            )
            if bot_tx_in_between:
                if verbose:
                    print(f"  [skip] bot has intermediate txs between {i} and {j}", file=sys.stderr)
                continue

            # Victims: same token pair, different signer
            victim_swaps = [
                swaps[k]
                for k in range(i + 1, j)
                if swaps[k].signer != fr.signer and (
                    (swaps[k].token_in == fr.token_in  and swaps[k].token_out == fr.token_out) or
                    (swaps[k].token_in == fr.token_out and swaps[k].token_out == fr.token_in)
                )
            ]
            if not victim_swaps:
                continue

            # Shared pool accounts: intersection of writable accounts.
            # If empty, front and back do not touch the same pool
            # (likely a false positive on highly liquid tokens across many AMMs).
            shared_pools = fr.pool_accounts & br.pool_accounts
            if verbose and not shared_pools:
                print(f"  [warn] no shared pool between frontrun@{i} and backrun@{j}",
                      file=sys.stderr)

            # Profit calculation
            profit_raw = br.amount_out - fr.amount_in
            profit_net = profit_raw - fr.fee_sol - br.fee_sol

            # Minimum net profit filter
            if min_profit_net is not None and profit_net < min_profit_net:
                if verbose:
                    print(f"  [skip] net profit {profit_net:.6f} < {min_profit_net}",
                          file=sys.stderr)
                continue

            # Victim slippage
            victims = [
                VictimInfo(
                    swap=v,
                    slippage_estimate=estimate_victim_slippage(v, fr),
                )
                for v in victim_swaps
            ]

            gap        = j - i
            cross_dex  = fr.program != br.program
            confidence = classify_confidence(
                fr, br, victim_swaps, shared_pools, profit_net, gap
            )

            results.append(SandwichResult(
                frontrun     = fr,
                victims      = victims,
                backrun      = br,
                profit_token = br.token_out,
                profit_raw   = profit_raw,
                profit_net   = profit_net,
                shared_pools = shared_pools,
                cross_dex    = cross_dex,
                confidence   = confidence,
            ))

            if verbose:
                print(f"  [match {confidence}] frontrun@{fr.tx_index} -> "
                      f"backrun@{br.tx_index} signer={fr.signer[:8]}... "
                      f"pool_shared={len(shared_pools)} profit_net={profit_net:.6f}",
                      file=sys.stderr)
            break

    # Sort by descending net profit
    results.sort(key=lambda s: s.profit_net, reverse=True)
    return results


# --- Statistics ---

def compute_stats(
    sandwiches: list[SandwichResult],
    total_txs: int,
    total_swaps: int,
) -> dict:
    """Computes aggregate statistics over the detected sandwiches.
    Returns a dict with profit summaries, top bots, DEX breakdown, and confidence distribution."""
    if not sandwiches:
        return {}

    profits_net = [s.profit_net for s in sandwiches]
    profits_raw = [s.profit_raw for s in sandwiches]

    # Most active bots
    bot_count: dict[str, int] = {}
    bot_profit: dict[str, float] = {}
    for s in sandwiches:
        bot = s.frontrun.signer
        bot_count[bot]  = bot_count.get(bot, 0) + 1
        bot_profit[bot] = bot_profit.get(bot, 0.0) + s.profit_net

    top_bots = sorted(bot_count.items(), key=lambda x: x[1], reverse=True)[:5]

    # Most targeted DEXes (victim count per frontrun DEX)
    dex_count: dict[str, int] = {}
    for s in sandwiches:
        dex = s.frontrun.program
        dex_count[dex] = dex_count.get(dex, 0) + len(s.victims)

    # Average victim slippage
    all_slippages = [
        v.slippage_estimate
        for s in sandwiches
        for v in s.victims
        if v.slippage_estimate != 0
    ]

    # Confidence distribution
    conf_dist: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for s in sandwiches:
        conf_dist[s.confidence] += 1

    return {
        "total_sandwiches":        len(sandwiches),
        "total_txs_in_block":      total_txs,
        "total_swaps_parsed":      total_swaps,
        "sandwich_rate_pct":       round(len(sandwiches) / max(total_swaps, 1) * 100, 2),
        "cross_dex_count":         sum(1 for s in sandwiches if s.cross_dex),
        "confidence_distribution": conf_dist,
        "profit_net": {
            "min":    round(min(profits_net), 6),
            "max":    round(max(profits_net), 6),
            "mean":   round(mean(profits_net), 6),
            "median": round(median(profits_net), 6),
            "total":  round(sum(profits_net), 6),
        },
        "profit_raw": {
            "min":   round(min(profits_raw), 6),
            "max":   round(max(profits_raw), 6),
            "mean":  round(mean(profits_raw), 6),
            "total": round(sum(profits_raw), 6),
        },
        "victim_slippage_pct": {
            "mean": round(mean(all_slippages), 4) if all_slippages else None,
            "max":  round(max(all_slippages), 4)  if all_slippages else None,
        },
        "top_bots": [
            {
                "signer":     bot,
                "sandwiches": count,
                "profit_net": round(bot_profit[bot], 6),
            }
            for bot, count in top_bots
        ],
        "dex_victims": dex_count,
    }


def print_stats(stats: dict) -> None:
    """Prints a formatted block statistics summary to stdout.
    Does nothing if stats is empty."""
    if not stats:
        return

    W = 68
    print(f"\n{'='*W}")
    print(f"  BLOCK STATISTICS")
    print(f"{'='*W}")
    print(f"  Total txs in block        : {stats['total_txs_in_block']}")
    print(f"  Swaps identified          : {stats['total_swaps_parsed']}")
    print(f"  Sandwiches detected       : {stats['total_sandwiches']}")
    print(f"  Sandwich/swap rate        : {stats['sandwich_rate_pct']}%")
    print(f"  Cross-DEX                 : {stats['cross_dex_count']}")

    cd = stats["confidence_distribution"]
    print(f"\n  Confidence:")
    print(f"    HIGH   : {cd['HIGH']}")
    print(f"    MEDIUM : {cd['MEDIUM']}")
    print(f"    LOW    : {cd['LOW']}")

    pn = stats["profit_net"]
    pr = stats["profit_raw"]
    token_label = "SOL"   # profit is almost always denominated in SOL
    print(f"\n  Net profit (fees deducted) [{token_label}]:")
    print(f"    Total  : {pn['total']:+.6f}")
    print(f"    Mean   : {pn['mean']:+.6f}")
    print(f"    Median : {pn['median']:+.6f}")
    print(f"    Min/Max: {pn['min']:+.6f} / {pn['max']:+.6f}")

    print(f"\n  Raw profit (before fees) [{token_label}]:")
    print(f"    Total  : {pr['total']:+.6f}")
    print(f"    Mean   : {pr['mean']:+.6f}")

    vs = stats["victim_slippage_pct"]
    if vs["mean"] is not None:
        print(f"\n  Estimated victim slippage:")
        print(f"    Mean   : {vs['mean']:.4f}%")
        print(f"    Max    : {vs['max']:.4f}%")

    if stats["top_bots"]:
        print(f"\n  Top bots:")
        for b in stats["top_bots"]:
            print(f"    {b['signer'][:20]}...  "
                  f"sandwiches: {b['sandwiches']}  "
                  f"profit_net: {b['profit_net']:+.6f} {token_label}")

    if stats["dex_victims"]:
        print(f"\n  Victims by DEX (frontrun):")
        for dex, cnt in sorted(stats["dex_victims"].items(), key=lambda x: -x[1]):
            print(f"    {dex:<30} : {cnt} victim(s)")

    print(f"{'='*W}\n")


# --- Detail output ---

MINT_LABELS = {SOL_MINT: "SOL"}


def label(mint: str) -> str:
    """Returns a short human-readable label for a mint address.
    Falls back to the first 8 characters of the address if the mint is unknown."""
    return MINT_LABELS.get(mint, mint[:8] + "...")


def print_sandwich(idx: int, s: SandwichResult) -> None:
    """Prints a detailed formatted view of a single sandwich result to stdout.
    Includes frontrun, victims, backrun, and profit information."""
    fr = s.frontrun
    br = s.backrun
    W  = 68
    print(f"\n{'-'*W}")
    print(f"  SANDWICH #{idx+1}  [{s.confidence}]"
          + ("  CROSS-DEX" if s.cross_dex else ""))
    print(f"{'-'*W}")
    print(f"  Bot          : {fr.signer}")
    print(f"  DEX front    : {fr.program}")
    print(f"  DEX back     : {br.program}")
    print(f"  Shared pools : {len(s.shared_pools)}")
    print()
    print(f"  FRONTRUN  [tx #{fr.tx_index}]")
    print(f"    sig        : {fr.signature}")
    print(f"    swap       : {fr.amount_in:.6f} {label(fr.token_in)}"
          f"  ->  {fr.amount_out:.6f} {label(fr.token_out)}")
    print(f"    fee        : {fr.fee_sol:.6f} SOL")
    print()
    for vi, v in enumerate(s.victims):
        slip_str = (f"  estimated slippage: {v.slippage_estimate:+.4f}%"
                    if v.slippage_estimate != 0 else "")
        print(f"  VICTIM {vi+1}  [tx #{v.swap.tx_index}]{slip_str}")
        print(f"    sig        : {v.swap.signature}")
        print(f"    signer     : {v.swap.signer}")
        print(f"    swap       : {v.swap.amount_in:.6f} {label(v.swap.token_in)}"
              f"  ->  {v.swap.amount_out:.6f} {label(v.swap.token_out)}")
    print()
    print(f"  BACKRUN   [tx #{br.tx_index}]")
    print(f"    sig        : {br.signature}")
    print(f"    swap       : {br.amount_in:.6f} {label(br.token_in)}"
          f"  ->  {br.amount_out:.6f} {label(br.token_out)}")
    print(f"    fee        : {br.fee_sol:.6f} SOL")
    print()
    profit_label = label(s.profit_token)
    sign_raw = "+" if s.profit_raw >= 0 else ""
    sign_net = "+" if s.profit_net >= 0 else ""
    print(f"  RAW PROFIT  : {sign_raw}{s.profit_raw:.6f} {profit_label}")
    print(f"  NET PROFIT  : {sign_net}{s.profit_net:.6f} {profit_label}", end="")
    if s.profit_net > 0:
        print("  PROFIT")
    elif s.profit_net < 0:
        print("  LOSS")
    else:
        print("  BREAKEVEN")
    print(f"{'-'*W}")


def print_summary_table(sandwiches: list[SandwichResult]) -> None:
    """Prints a compact summary table of all detected sandwiches, sorted by net profit.
    Prints a 'none found' message if the list is empty."""
    if not sandwiches:
        print("\nNo sandwich attacks detected in the block.")
        return
    W = 68
    print(f"\n{'='*W}")
    print(f"  SUMMARY -- {len(sandwiches)} sandwich(es) (sorted by net profit)")
    print(f"{'='*W}")
    print(f"  {'#':<4} {'Conf':<7} {'Bot':<18} {'Pair':<20} {'Vic':<5} {'Net profit'}")
    print(f"  {'─'*4} {'─'*7} {'─'*18} {'─'*20} {'─'*5} {'─'*14}")
    for i, s in enumerate(sandwiches):
        pair       = f"{label(s.frontrun.token_in)}->{label(s.frontrun.token_out)}"
        sign       = "+" if s.profit_net >= 0 else ""
        profit_str = f"{sign}{s.profit_net:.4f} {label(s.profit_token)}"
        print(f"  {i+1:<4} {s.confidence:<7} {s.frontrun.signer[:16]:<18} "
              f"{pair:<20} {len(s.victims):<5} {profit_str}")
    print(f"{'='*W}\n")


# --- Serialization ---

def swap_to_dict(x: SwapInfo) -> dict:
    """Converts a SwapInfo dataclass to a JSON-serializable dictionary.
    Excludes pool_accounts (frozenset) as it is not needed in output."""
    return {
        "tx_index":  x.tx_index,
        "signature": x.signature,
        "signer":    x.signer,
        "token_in":  x.token_in,
        "token_out": x.token_out,
        "amount_in": x.amount_in,
        "amount_out":x.amount_out,
        "program":   x.program,
        "fee_sol":   x.fee_sol,
    }


def sandwich_to_dict(s: SandwichResult) -> dict:
    """Converts a SandwichResult dataclass to a JSON-serializable dictionary.
    Shared pools are converted from frozenset to a sorted list."""
    return {
        "frontrun":     swap_to_dict(s.frontrun),
        "victims":      [
            {"swap": swap_to_dict(v.swap), "slippage_estimate": v.slippage_estimate}
            for v in s.victims
        ],
        "backrun":      swap_to_dict(s.backrun),
        "profit_token": s.profit_token,
        "profit_raw":   s.profit_raw,
        "profit_net":   s.profit_net,
        "shared_pools": list(s.shared_pools),
        "cross_dex":    s.cross_dex,
        "confidence":   s.confidence,
    }


# --- Main ---

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect sandwich attacks in a Solana block (v2 -- advanced heuristics)."
    )
    parser.add_argument("block_file", help="Path to the block JSON file")
    parser.add_argument("--min-profit", type=float, default=None,
                        help="Show only sandwiches with NET profit >= X SOL")
    parser.add_argument("--max-gap", type=int, default=10,
                        help="Maximum number of txs between frontrun and backrun (default: 10)")
    parser.add_argument("--confidence", choices=["HIGH", "MEDIUM", "LOW"], default=None,
                        help="Filter by minimum confidence level")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug output during parsing")
    parser.add_argument("--output-json", default=None,
                        help="Save results (JSON array) to a file")
    parser.add_argument("--output-stats", default=None,
                        help="Save statistics to a separate JSON file")
    args = parser.parse_args()

    # Block loading
    block_path = Path(args.block_file)
    if not block_path.exists():
        print(f"ERROR: File not found: {block_path}", file=sys.stderr)
        sys.exit(1)
    if block_path.stat().st_size == 0:
        print(f"ERROR: Empty file: {block_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Loading {block_path}...")
    try:
        with block_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in '{block_path}': {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"ERROR: Cannot read '{block_path}': {e}", file=sys.stderr)
        sys.exit(1)

    if "block" in raw and "_meta" in raw:
        block_data = raw["block"]
        meta_info  = raw["_meta"]
        print(f"    Slot     : {meta_info.get('slot', 'N/A')}")
        print(f"    Network  : {meta_info.get('network', 'N/A')}")
        print(f"    Timestamp: {meta_info.get('block_time_human', 'N/A')}")
    else:
        block_data = raw
        meta_info  = {}

    transactions = block_data.get("transactions", [])
    if not isinstance(transactions, list):
        print("ERROR: Invalid block format: 'transactions' is not a list.",
              file=sys.stderr)
        sys.exit(1)
    print(f"    Transactions in block: {len(transactions)}")

    # Vote tx filter + swap extraction
    print(f"\n[*] Parsing swaps (vote tx filter enabled)...")
    swaps: list[SwapInfo] = []
    vote_count   = 0
    failed_parse = 0

    for i, tx in enumerate(transactions):
        if not isinstance(tx, dict):
            failed_parse += 1
            continue
        if is_vote_tx(tx):
            vote_count += 1
            continue
        swap = infer_swap_from_transfers(i, tx, verbose=args.verbose)
        if swap:
            swaps.append(swap)
        else:
            failed_parse += 1

    print(f"    Vote txs filtered : {vote_count}")
    print(f"    Swaps extracted   : {len(swaps)}")
    print(f"    Non-swap / errors : {failed_parse}")

    if not swaps:
        print("\n[!] No identifiable swaps in the block. "
              "Make sure the JSON is in jsonParsed format.")
        sys.exit(0)

    # Sandwich detection
    print(f"\n[*] Searching for sandwich patterns (max_gap={args.max_gap})...")
    sandwiches = detect_sandwiches(
        swaps,
        max_gap=args.max_gap,
        min_profit_net=args.min_profit,
        verbose=args.verbose,
    )
    print(f"    Sandwiches found: {len(sandwiches)}")

    # Confidence filter
    if args.confidence:
        conf_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        min_conf   = conf_order[args.confidence]
        before     = len(sandwiches)
        sandwiches = [s for s in sandwiches if conf_order[s.confidence] >= min_conf]
        print(f"    After confidence filter >= {args.confidence}: {len(sandwiches)} "
              f"(excluded {before - len(sandwiches)})")

    # Print detailed results
    for i, s in enumerate(sandwiches):
        print_sandwich(i, s)
    print_summary_table(sandwiches)

    # Statistics
    stats = compute_stats(sandwiches, len(transactions), len(swaps))
    print_stats(stats)

    # Save results JSON
    if args.output_json:
        output_path = Path(args.output_json)
        try:
            with output_path.open("w", encoding="utf-8") as f:
                json.dump([sandwich_to_dict(s) for s in sandwiches], f, indent=2)
            print(f"[OK] Results saved to '{output_path}'")
        except OSError as e:
            print(f"ERROR writing '{output_path}': {e}", file=sys.stderr)
            sys.exit(1)

    # Save statistics JSON
    if args.output_stats and stats:
        stats_path = Path(args.output_stats)
        try:
            with stats_path.open("w", encoding="utf-8") as f:
                json.dump(stats, f, indent=2)
            print(f"[OK] Statistics saved to '{stats_path}'")
        except OSError as e:
            print(f"ERROR writing '{stats_path}': {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()