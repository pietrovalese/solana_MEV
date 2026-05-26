"""
sandwich_detector.py — CLI wrapper for the Rust sandwich_detector extension.

Build the Rust extension first:
    pip install maturin
    maturin develop --release        # development (installs into current venv)
    # or
    maturin build --release          # produces a wheel in target/wheels/

Then run:
    python sandwich_detector.py block.json
    python sandwich_detector.py block.json --min-profit 0.001 --confidence HIGH
    python sandwich_detector.py block.json --output-json results.json --output-stats stats.json
"""

import argparse
import json
import sys
from pathlib import Path
from statistics import mean, median

# The Rust extension module.  Built with `maturin develop --release`.
try:
    import sandwich_detector as _rust
except ImportError:
    print(
        "ERROR: Rust extension not found.\n"
        "Build it with:  pip install maturin && maturin develop --release",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants (presentation layer only)
# ---------------------------------------------------------------------------

SOL_MINT = "So11111111111111111111111111111111111111112"
MINT_LABELS = {SOL_MINT: "SOL"}


def label(mint: str) -> str:
    """Return a short human-readable label for a mint address."""
    return MINT_LABELS.get(mint, mint[:8] + "...")


# ---------------------------------------------------------------------------
# Statistics  (pure Python — runs on small result lists, not a hot path)
# ---------------------------------------------------------------------------

def compute_stats(sandwiches: list[dict], total_txs: int, total_swaps: int) -> dict:
    """
    Compute aggregate statistics over the detected sandwiches.

    Args:
        sandwiches:   List of sandwich dicts returned by the Rust extension.
        total_txs:    Total number of transactions in the block.
        total_swaps:  Number of swaps extracted from the block.

    Returns:
        Dict with profit summaries, top bots, DEX breakdown, and confidence distribution.
    """
    if not sandwiches:
        return {}

    profits_net = [s["profit_net"] for s in sandwiches]
    profits_raw = [s["profit_raw"] for s in sandwiches]

    bot_count:  dict[str, int]   = {}
    bot_profit: dict[str, float] = {}
    for s in sandwiches:
        bot = s["frontrun"]["signer"]
        bot_count[bot]  = bot_count.get(bot, 0) + 1
        bot_profit[bot] = bot_profit.get(bot, 0.0) + s["profit_net"]

    top_bots = sorted(bot_count.items(), key=lambda x: x[1], reverse=True)[:5]

    dex_count: dict[str, int] = {}
    for s in sandwiches:
        dex = s["frontrun"]["program"]
        dex_count[dex] = dex_count.get(dex, 0) + len(s["victims"])

    all_slippages = [
        v["slippage_estimate"]
        for s in sandwiches
        for v in s["victims"]
        if v["slippage_estimate"] != 0
    ]

    conf_dist = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for s in sandwiches:
        conf_dist[s["confidence"]] += 1

    return {
        "total_sandwiches":        len(sandwiches),
        "total_txs_in_block":      total_txs,
        "total_swaps_parsed":      total_swaps,
        "sandwich_rate_pct":       round(len(sandwiches) / max(total_swaps, 1) * 100, 2),
        "cross_dex_count":         sum(1 for s in sandwiches if s["cross_dex"]),
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


# ---------------------------------------------------------------------------
# Output formatters  (pure Python — I/O, not a hot path)
# ---------------------------------------------------------------------------

def print_stats(stats: dict) -> None:
    """Print a formatted block statistics summary to stdout."""
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
    print(f"\n  Net profit (fees deducted) [SOL]:")
    print(f"    Total  : {pn['total']:+.6f}")
    print(f"    Mean   : {pn['mean']:+.6f}")
    print(f"    Median : {pn['median']:+.6f}")
    print(f"    Min/Max: {pn['min']:+.6f} / {pn['max']:+.6f}")
    print(f"\n  Raw profit (before fees) [SOL]:")
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
                  f"profit_net: {b['profit_net']:+.6f} SOL")

    if stats["dex_victims"]:
        print(f"\n  Victims by DEX (frontrun):")
        for dex, cnt in sorted(stats["dex_victims"].items(), key=lambda x: -x[1]):
            print(f"    {dex:<30} : {cnt} victim(s)")

    print(f"{'='*W}\n")


def print_sandwich(idx: int, s: dict) -> None:
    """Print a detailed formatted view of a single sandwich result."""
    fr = s["frontrun"]
    br = s["backrun"]
    W  = 68
    print(f"\n{'-'*W}")
    print(f"  SANDWICH #{idx+1}  [{s['confidence']}]"
          + ("  CROSS-DEX" if s["cross_dex"] else ""))
    print(f"{'-'*W}")
    print(f"  Bot          : {fr['signer']}")
    print(f"  DEX front    : {fr['program']}")
    print(f"  DEX back     : {br['program']}")
    print(f"  Shared pools : {len(s['shared_pools'])}")
    print()
    print(f"  FRONTRUN  [tx #{fr['tx_index']}]")
    print(f"    sig        : {fr['signature']}")
    print(f"    swap       : {fr['amount_in']:.6f} {label(fr['token_in'])}"
          f"  ->  {fr['amount_out']:.6f} {label(fr['token_out'])}")
    print(f"    fee        : {fr['fee_sol']:.6f} SOL")
    print()
    for vi, v in enumerate(s["victims"]):
        sv       = v["swap"]
        slip_str = (f"  estimated slippage: {v['slippage_estimate']:+.4f}%"
                    if v["slippage_estimate"] != 0 else "")
        print(f"  VICTIM {vi+1}  [tx #{sv['tx_index']}]{slip_str}")
        print(f"    sig        : {sv['signature']}")
        print(f"    signer     : {sv['signer']}")
        print(f"    swap       : {sv['amount_in']:.6f} {label(sv['token_in'])}"
              f"  ->  {sv['amount_out']:.6f} {label(sv['token_out'])}")
    print()
    print(f"  BACKRUN   [tx #{br['tx_index']}]")
    print(f"    sig        : {br['signature']}")
    print(f"    swap       : {br['amount_in']:.6f} {label(br['token_in'])}"
          f"  ->  {br['amount_out']:.6f} {label(br['token_out'])}")
    print(f"    fee        : {br['fee_sol']:.6f} SOL")
    print()
    profit_label = label(s["profit_token"])
    sign_raw = "+" if s["profit_raw"] >= 0 else ""
    sign_net = "+" if s["profit_net"] >= 0 else ""
    print(f"  RAW PROFIT  : {sign_raw}{s['profit_raw']:.6f} {profit_label}")
    print(f"  NET PROFIT  : {sign_net}{s['profit_net']:.6f} {profit_label}", end="")
    if s["profit_net"] > 0:
        print("  PROFIT")
    elif s["profit_net"] < 0:
        print("  LOSS")
    else:
        print("  BREAKEVEN")
    print(f"{'-'*W}")


def print_summary_table(sandwiches: list[dict]) -> None:
    """Print a compact summary table of all detected sandwiches."""
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
        fr         = s["frontrun"]
        pair       = f"{label(fr['token_in'])}->{label(fr['token_out'])}"
        sign       = "+" if s["profit_net"] >= 0 else ""
        profit_str = f"{sign}{s['profit_net']:.4f} {label(s['profit_token'])}"
        print(f"  {i+1:<4} {s['confidence']:<7} {fr['signer'][:16]:<18} "
              f"{pair:<20} {len(s['victims']):<5} {profit_str}")
    print(f"{'='*W}\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect sandwich attacks in a Solana block (Rust-accelerated)."
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
                        help="Save sandwich results (JSON array) to a file")
    parser.add_argument("--output-stats", default=None,
                        help="Save statistics to a separate JSON file")
    args = parser.parse_args()

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

    transactions = block_data.get("transactions", [])
    if not isinstance(transactions, list):
        print("ERROR: Invalid block format: 'transactions' is not a list.", file=sys.stderr)
        sys.exit(1)
    print(f"    Transactions in block: {len(transactions)}")

    # --- Hot path: delegated entirely to Rust ---
    print(f"\n[*] Parsing and detecting sandwiches (Rust, max_gap={args.max_gap})...")
    sandwiches = _rust.parse_and_detect(
        transactions,
        max_gap        = args.max_gap,
        min_profit_net = args.min_profit,
        verbose        = args.verbose,
    )
    print(f"    Sandwiches found: {len(sandwiches)}")

    # Confidence filter (post-detection; Rust returns all, we slice here)
    if args.confidence:
        conf_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        min_conf   = conf_order[args.confidence]
        before     = len(sandwiches)
        sandwiches = [s for s in sandwiches if conf_order[s["confidence"]] >= min_conf]
        print(f"    After confidence filter >= {args.confidence}: {len(sandwiches)} "
              f"(excluded {before - len(sandwiches)})")

    # --- Presentation (Python) ---
    # We need the swap count for statistics; re-parse only swap count via Rust.
    swaps_only = _rust.parse_swaps(transactions, verbose=False)
    total_swaps = len(swaps_only)

    for i, s in enumerate(sandwiches):
        print_sandwich(i, s)
    print_summary_table(sandwiches)

    stats = compute_stats(sandwiches, len(transactions), total_swaps)
    print_stats(stats)

    if args.output_json:
        output_path = Path(args.output_json)
        try:
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(sandwiches, f, indent=2)
            print(f"[OK] Results saved to '{output_path}'")
        except OSError as e:
            print(f"ERROR writing '{output_path}': {e}", file=sys.stderr)
            sys.exit(1)

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