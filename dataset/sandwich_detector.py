#!/usr/bin/env python3
"""
Sandwich Attack Detector — Solana Block  (v2)
==============================================
Miglioramenti rispetto alla v1:
  - Verifica condivisione pool/AMM account (non solo coppia di token)
  - Filtro tx di voto validator prima del parsing
  - Stima fee Solana (base + priorità) per validare profitto reale
  - Penalità gap: tx del bot stesso tra front e back invalidano il match
  - Slippage stimato per ogni vittima
  - Supporto cross-DEX (front e back possono usare programmi diversi)
  - Blocco statistiche completo a fine analisi

Uso:
    python sandwich_detector.py block.json
    python sandwich_detector.py block.json --min-profit 0.001 --verbose
"""

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median
from typing import Optional


# ─── Costanti ─────────────────────────────────────────────────────────────────

SOL_MINT = "So11111111111111111111111111111111111111112"

# Programma di voto dei validator — da escludere sempre
VOTE_PROGRAM = "Vote111111111111111111111111111111111111111"

# Fee base per tx Solana in lamport (5000 = ~0.000005 SOL)
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


# ─── Strutture dati ───────────────────────────────────────────────────────────

@dataclass
class SwapInfo:
    tx_index:    int
    signature:   str
    signer:      str
    token_in:    str
    token_out:   str
    amount_in:   float
    amount_out:  float
    program:     str
    failed:      bool
    fee_sol:     float = 0.0          # fee pagata in SOL (base + priorità)
    pool_accounts: frozenset = field(default_factory=frozenset)
                                      # account AMM/pool coinvolti nella tx


@dataclass
class VictimInfo:
    swap:              SwapInfo
    slippage_estimate: float          # % di slippage stimato rispetto al prezzo pre-frontrun


@dataclass
class SandwichResult:
    frontrun:       SwapInfo
    victims:        list[VictimInfo]
    backrun:        SwapInfo
    profit_token:   str
    profit_raw:     float             # delta grezzo (senza fee)
    profit_net:     float             # profit_raw - fee_frontrun - fee_backrun
    shared_pools:   frozenset         # pool in comune tra front e back
    cross_dex:      bool              # True se front e back usano DEX diversi
    confidence:     str               # "HIGH" / "MEDIUM" / "LOW"


# ─── Helpers generici ─────────────────────────────────────────────────────────

def get_signer(tx: dict) -> str:
    try:
        account_keys = tx["transaction"]["message"]["accountKeys"]
        first = account_keys[0]
        return first["pubkey"] if isinstance(first, dict) else first
    except (KeyError, IndexError, TypeError):
        return ""


def get_account_keys_flat(tx: dict) -> list[str]:
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
    """True se la tx è una tx di voto validator (da escludere)."""
    try:
        keys = get_account_keys_flat(tx)
        return VOTE_PROGRAM in keys
    except Exception:
        return False


def extract_token_transfers(tx: dict) -> list[dict]:
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
    fee   = meta.get("fee", 0)
    return (post[idx] - pre[idx] + fee) / 1e9


def get_fee_sol(tx: dict) -> float:
    """Restituisce la fee totale della tx in SOL (base + priority fee)."""
    try:
        return tx["meta"].get("fee", BASE_FEE_LAMPORTS) / 1e9
    except (KeyError, TypeError):
        return BASE_FEE_LAMPORTS / 1e9


def get_pool_accounts(tx: dict) -> frozenset:
    """
    Restituisce gli account writable della tx che appartengono a DEX noti.
    Sono i candidate pool/AMM account condivisi tra front e backrun.
    Usiamo solo i writable perché i pool AMM vengono sempre modificati durante uno swap.
    """
    try:
        account_keys_raw = tx["transaction"]["message"]["accountKeys"]
        writable_keys = set()
        for k in account_keys_raw:
            if isinstance(k, dict):
                if k.get("writable"):
                    writable_keys.add(k["pubkey"])
            # Per tx non-parsed non abbiamo info su writable, skip
        # Aggiungi writable da loadedAddresses
        loaded = tx.get("meta", {}).get("loadedAddresses", {})
        writable_keys.update(loaded.get("writable", []))
        return frozenset(writable_keys)
    except (KeyError, TypeError):
        return frozenset()


# ─── Parser swap ──────────────────────────────────────────────────────────────

def infer_swap_from_transfers(
    tx_index: int,
    tx: dict,
    verbose: bool = False,
) -> Optional[SwapInfo]:
    """
    Ricostruisce lo swap principale di una tx dai balance delta.
    Include fee SOL e pool accounts nel risultato.
    """
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
            tx_index     = tx_index,
            signature    = sig,
            signer       = signer,
            token_in     = token_in,
            token_out    = token_out,
            amount_in    = amount_in,
            amount_out   = amount_out,
            program      = program,
            failed       = False,
            fee_sol      = get_fee_sol(tx),
            pool_accounts= get_pool_accounts(tx),
        )

    except Exception as e:
        if verbose:
            print(f"[WARN] Errore parsing tx {tx_index}: {e}", file=sys.stderr)
        return None


# ─── Stima slippage vittima ───────────────────────────────────────────────────

def estimate_victim_slippage(
    victim: SwapInfo,
    frontrun: SwapInfo,
) -> float:
    """
    Stima lo slippage subito dalla vittima confrontando il suo price_impact
    con il prezzo implicito del frontrun (che ha spostato il pool prima di lei).

    price_fr    = amount_out_fr / amount_in_fr   (prezzo ottenuto dal bot)
    price_vic   = amount_out_vic / amount_in_vic (prezzo ottenuto dalla vittima)

    Se front e vittima vanno nella stessa direzione (token_in uguale):
        slippage = (price_fr - price_vic) / price_fr  * 100
    Altrimenti (direzioni opposte) non ha senso confrontarli → restituisce 0.
    """
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


# ─── Classificazione confidenza ──────────────────────────────────────────────

def classify_confidence(
    fr: SwapInfo,
    br: SwapInfo,
    victims: list[SwapInfo],
    shared_pools: frozenset,
    profit_net: float,
    gap: int,
) -> str:
    """
    Assegna una confidenza al sandwich rilevato.

    HIGH:   pool condivisi + profitto netto > 0 + gap <= 3
    MEDIUM: pool condivisi OPPURE profitto netto > 0
    LOW:    nessuno dei criteri forti (possibile falso positivo)
    """
    has_shared_pool  = len(shared_pools) > 0
    has_net_profit   = profit_net > 0
    tight_gap        = gap <= 3

    score = sum([has_shared_pool, has_net_profit, tight_gap])

    if score == 3:
        return "HIGH"
    elif score >= 1:
        return "MEDIUM"
    else:
        return "LOW"


# ─── Algoritmo di detection ───────────────────────────────────────────────────

def is_mirror_swap(a: SwapInfo, b: SwapInfo) -> bool:
    return a.token_in == b.token_out and a.token_out == b.token_in


def detect_sandwiches(
    swaps: list[SwapInfo],
    max_gap: int = 10,
    min_profit_net: Optional[float] = None,
    verbose: bool = False,
) -> list[SandwichResult]:
    """
    Algoritmo di detection migliorato:

    Per ogni coppia (frontrun, backrun) che soddisfa:
      1. stesso signer
      2. swap speculare (A→B / B→A)
      3. almeno una vittima in mezzo sullo stesso token pair
      4. nessuna tx del bot stesso in mezzo (evita falsi positivi)
      5. pool condivisi tra front e back (quando disponibili)
      6. profitto netto > soglia (opzionale)

    Restituisce i risultati ordinati per profitto netto decrescente.
    """
    results: list[SandwichResult] = []
    n = len(swaps)

    for i in range(n):
        fr = swaps[i]

        for j in range(i + 2, min(i + 1 + max_gap, n)):
            br = swaps[j]

            # ── Criteri base ────────────────────────────────────────────────
            if fr.signer != br.signer:
                continue
            if not is_mirror_swap(fr, br):
                continue

            # ── Nessuna tx del bot in mezzo (filtro falsi positivi) ─────────
            # Se il bot fa un'altra operazione tra front e back, probabilmente
            # non è un sandwich ma due trade separati.
            bot_tx_in_between = any(
                swaps[k].signer == fr.signer
                for k in range(i + 1, j)
            )
            if bot_tx_in_between:
                if verbose:
                    print(f"  [skip] bot ha tx intermedie tra {i} e {j}", file=sys.stderr)
                continue

            # ── Vittime: stessa coppia, signer diverso ───────────────────────
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

            # ── Pool condivisi ───────────────────────────────────────────────
            # Intersezione degli account writable: se vuota, front e back
            # non toccano lo stesso pool (probabile falso positivo su token
            # molto liquidi presenti su molti AMM).
            shared_pools = fr.pool_accounts & br.pool_accounts
            if verbose and not shared_pools:
                print(f"  [warn] nessun pool condiviso tra frontrun@{i} e backrun@{j}",
                      file=sys.stderr)

            # ── Calcolo profitto ─────────────────────────────────────────────
            profit_raw = br.amount_out - fr.amount_in
            profit_net = profit_raw - fr.fee_sol - br.fee_sol

            # ── Filtro profitto netto minimo ─────────────────────────────────
            if min_profit_net is not None and profit_net < min_profit_net:
                if verbose:
                    print(f"  [skip] profitto netto {profit_net:.6f} < {min_profit_net}",
                          file=sys.stderr)
                continue

            # ── Slippage vittime ─────────────────────────────────────────────
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
                print(f"  [match {confidence}] frontrun@{fr.tx_index} → "
                      f"backrun@{br.tx_index} signer={fr.signer[:8]}… "
                      f"pool_shared={len(shared_pools)} profit_net={profit_net:.6f}",
                      file=sys.stderr)
            break

    # Ordina per profitto netto decrescente
    results.sort(key=lambda s: s.profit_net, reverse=True)
    return results


# ─── Statistiche ─────────────────────────────────────────────────────────────

def compute_stats(
    sandwiches: list[SandwichResult],
    total_txs: int,
    total_swaps: int,
) -> dict:
    """Calcola statistiche aggregate sui sandwich trovati."""
    if not sandwiches:
        return {}

    profits_net = [s.profit_net for s in sandwiches]
    profits_raw = [s.profit_raw for s in sandwiches]

    # Bot più attivi
    bot_count: dict[str, int] = {}
    bot_profit: dict[str, float] = {}
    for s in sandwiches:
        bot = s.frontrun.signer
        bot_count[bot]  = bot_count.get(bot, 0) + 1
        bot_profit[bot] = bot_profit.get(bot, 0.0) + s.profit_net

    top_bots = sorted(bot_count.items(), key=lambda x: x[1], reverse=True)[:5]

    # DEX più colpiti (conteggio vittime per DEX del frontrun)
    dex_count: dict[str, int] = {}
    for s in sandwiches:
        dex = s.frontrun.program
        dex_count[dex] = dex_count.get(dex, 0) + len(s.victims)

    # Slippage medio vittime
    all_slippages = [
        v.slippage_estimate
        for s in sandwiches
        for v in s.victims
        if v.slippage_estimate != 0
    ]

    # Distribuzione confidenza
    conf_dist: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for s in sandwiches:
        conf_dist[s.confidence] += 1

    return {
        "total_sandwiches":      len(sandwiches),
        "total_txs_in_block":    total_txs,
        "total_swaps_parsed":    total_swaps,
        "sandwich_rate_pct":     round(len(sandwiches) / max(total_swaps, 1) * 100, 2),
        "cross_dex_count":       sum(1 for s in sandwiches if s.cross_dex),
        "confidence_distribution": conf_dist,
        "profit_net": {
            "min":    round(min(profits_net), 6),
            "max":    round(max(profits_net), 6),
            "mean":   round(mean(profits_net), 6),
            "median": round(median(profits_net), 6),
            "total":  round(sum(profits_net), 6),
        },
        "profit_raw": {
            "min":    round(min(profits_raw), 6),
            "max":    round(max(profits_raw), 6),
            "mean":   round(mean(profits_raw), 6),
            "total":  round(sum(profits_raw), 6),
        },
        "victim_slippage_pct": {
            "mean":   round(mean(all_slippages), 4) if all_slippages else None,
            "max":    round(max(all_slippages), 4)  if all_slippages else None,
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
    if not stats:
        return

    W = 68
    print(f"\n{'═'*W}")
    print(f"  STATISTICHE BLOCCO")
    print(f"{'═'*W}")
    print(f"  Tx totali nel blocco      : {stats['total_txs_in_block']}")
    print(f"  Swap identificati         : {stats['total_swaps_parsed']}")
    print(f"  Sandwich rilevati         : {stats['total_sandwiches']}")
    print(f"  Tasso sandwich/swap       : {stats['sandwich_rate_pct']}%")
    print(f"  Cross-DEX                 : {stats['cross_dex_count']}")

    cd = stats["confidence_distribution"]
    print(f"\n  Confidenza:")
    print(f"    HIGH   : {cd['HIGH']}")
    print(f"    MEDIUM : {cd['MEDIUM']}")
    print(f"    LOW    : {cd['LOW']}")

    pn = stats["profit_net"]
    pr = stats["profit_raw"]
    token_label = "SOL"   # il profitto è quasi sempre in SOL
    print(f"\n  Profitto netto (fee dedotte) [{token_label}]:")
    print(f"    Totale  : {pn['total']:+.6f}")
    print(f"    Media   : {pn['mean']:+.6f}")
    print(f"    Mediana : {pn['median']:+.6f}")
    print(f"    Min/Max : {pn['min']:+.6f} / {pn['max']:+.6f}")

    print(f"\n  Profitto grezzo (senza fee) [{token_label}]:")
    print(f"    Totale  : {pr['total']:+.6f}")
    print(f"    Media   : {pr['mean']:+.6f}")

    vs = stats["victim_slippage_pct"]
    if vs["mean"] is not None:
        print(f"\n  Slippage stimato vittime:")
        print(f"    Media   : {vs['mean']:.4f}%")
        print(f"    Massimo : {vs['max']:.4f}%")

    if stats["top_bots"]:
        print(f"\n  Top bot:")
        for b in stats["top_bots"]:
            print(f"    {b['signer'][:20]}…  "
                  f"sandwich: {b['sandwiches']}  "
                  f"profit_net: {b['profit_net']:+.6f} {token_label}")

    if stats["dex_victims"]:
        print(f"\n  Vittime per DEX (frontrun):")
        for dex, cnt in sorted(stats["dex_victims"].items(), key=lambda x: -x[1]):
            print(f"    {dex:<30} : {cnt} vittime")

    print(f"{'═'*W}\n")


# ─── Output dettaglio ─────────────────────────────────────────────────────────

MINT_LABELS = {SOL_MINT: "SOL"}

def label(mint: str) -> str:
    return MINT_LABELS.get(mint, mint[:8] + "…")


def print_sandwich(idx: int, s: SandwichResult) -> None:
    fr = s.frontrun
    br = s.backrun
    W  = 68
    conf_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(s.confidence, "")
    print(f"\n{'─'*W}")
    print(f"  SANDWICH #{idx+1}  [{s.confidence} {conf_icon}]"
          + ("  ⚡ CROSS-DEX" if s.cross_dex else ""))
    print(f"{'─'*W}")
    print(f"  Bot         : {fr.signer}")
    print(f"  DEX front   : {fr.program}")
    print(f"  DEX back    : {br.program}")
    print(f"  Pool comuni : {len(s.shared_pools)}")
    print()
    print(f"  FRONTRUN  [tx #{fr.tx_index}]")
    print(f"    sig       : {fr.signature}")
    print(f"    swap      : {fr.amount_in:.6f} {label(fr.token_in)}"
          f"  →  {fr.amount_out:.6f} {label(fr.token_out)}")
    print(f"    fee       : {fr.fee_sol:.6f} SOL")
    print()
    for vi, v in enumerate(s.victims):
        slip_str = (f"  slippage stimato: {v.slippage_estimate:+.4f}%"
                    if v.slippage_estimate != 0 else "")
        print(f"  VICTIM {vi+1}  [tx #{v.swap.tx_index}]{slip_str}")
        print(f"    sig       : {v.swap.signature}")
        print(f"    signer    : {v.swap.signer}")
        print(f"    swap      : {v.swap.amount_in:.6f} {label(v.swap.token_in)}"
              f"  →  {v.swap.amount_out:.6f} {label(v.swap.token_out)}")
    print()
    print(f"  BACKRUN   [tx #{br.tx_index}]")
    print(f"    sig       : {br.signature}")
    print(f"    swap      : {br.amount_in:.6f} {label(br.token_in)}"
          f"  →  {br.amount_out:.6f} {label(br.token_out)}")
    print(f"    fee       : {br.fee_sol:.6f} SOL")
    print()
    profit_label = label(s.profit_token)
    sign_raw = "+" if s.profit_raw >= 0 else ""
    sign_net = "+" if s.profit_net >= 0 else ""
    print(f"  PROFITTO GREZZO : {sign_raw}{s.profit_raw:.6f} {profit_label}")
    print(f"  PROFITTO NETTO  : {sign_net}{s.profit_net:.6f} {profit_label}", end="")
    if s.profit_net > 0:
        print("  ✓ PROFIT")
    elif s.profit_net < 0:
        print("  ✗ LOSS")
    else:
        print("  ~ BREAKEVEN")
    print(f"{'─'*W}")


def print_summary_table(sandwiches: list[SandwichResult]) -> None:
    if not sandwiches:
        print("\n[✓] Nessun sandwich attack rilevato nel blocco.")
        return
    W = 68
    print(f"\n{'═'*W}")
    print(f"  RIEPILOGO — {len(sandwiches)} sandwich (ordinati per profitto netto)")
    print(f"{'═'*W}")
    print(f"  {'#':<4} {'Conf':<7} {'Bot':<18} {'Pair':<20} {'Vit':<5} {'Net profit'}")
    print(f"  {'─'*4} {'─'*7} {'─'*18} {'─'*20} {'─'*5} {'─'*14}")
    for i, s in enumerate(sandwiches):
        pair       = f"{label(s.frontrun.token_in)}→{label(s.frontrun.token_out)}"
        sign       = "+" if s.profit_net >= 0 else ""
        profit_str = f"{sign}{s.profit_net:.4f} {label(s.profit_token)}"
        print(f"  {i+1:<4} {s.confidence:<7} {s.frontrun.signer[:16]:<18} "
              f"{pair:<20} {len(s.victims):<5} {profit_str}")
    print(f"{'═'*W}\n")


# ─── Serializzazione ──────────────────────────────────────────────────────────

def swap_to_dict(x: SwapInfo) -> dict:
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


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rileva sandwich attack in un blocco Solana (v2 — euristica avanzata)."
    )
    parser.add_argument("block_file", help="Percorso del file JSON del blocco")
    parser.add_argument("--min-profit", type=float, default=None,
                        help="Mostra solo sandwich con profitto NETTO >= X SOL")
    parser.add_argument("--max-gap", type=int, default=10,
                        help="Numero massimo di tx tra frontrun e backrun (default: 10)")
    parser.add_argument("--confidence", choices=["HIGH", "MEDIUM", "LOW"], default=None,
                        help="Filtra per livello minimo di confidenza")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Output di debug durante il parsing")
    parser.add_argument("--output-json", default=None,
                        help="Salva i risultati (array JSON) in un file")
    parser.add_argument("--output-stats", default=None,
                        help="Salva le statistiche in un file JSON separato")
    args = parser.parse_args()

    # ── Caricamento blocco ───────────────────────────────────────────────────
    block_path = Path(args.block_file)
    if not block_path.exists():
        print(f"ERRORE: File non trovato: {block_path}", file=sys.stderr)
        sys.exit(1)
    if block_path.stat().st_size == 0:
        print(f"ERRORE: File vuoto: {block_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Caricamento {block_path} …")
    try:
        with block_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERRORE: JSON non valido in '{block_path}': {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"ERRORE: Impossibile leggere '{block_path}': {e}", file=sys.stderr)
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
        print("ERRORE: Formato blocco non valido: 'transactions' non è una lista.",
              file=sys.stderr)
        sys.exit(1)
    print(f"    Transazioni nel blocco: {len(transactions)}")

    # ── Filtro tx di voto + estrazione swap ──────────────────────────────────
    print(f"\n[*] Parsing swap (filtro tx di voto attivo)…")
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

    print(f"    Tx di voto filtrate : {vote_count}")
    print(f"    Swap estratti       : {len(swaps)}")
    print(f"    Non-swap / errori   : {failed_parse}")

    if not swaps:
        print("\n[!] Nessuno swap identificabile nel blocco. "
              "Verifica che il JSON sia in formato jsonParsed.")
        sys.exit(0)

    # ── Rilevamento sandwich ─────────────────────────────────────────────────
    print(f"\n[*] Ricerca pattern sandwich (max_gap={args.max_gap})…")
    sandwiches = detect_sandwiches(
        swaps,
        max_gap=args.max_gap,
        min_profit_net=args.min_profit,
        verbose=args.verbose,
    )
    print(f"    Sandwich trovati: {len(sandwiches)}")

    # Filtro confidenza
    if args.confidence:
        conf_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        min_conf   = conf_order[args.confidence]
        before     = len(sandwiches)
        sandwiches = [s for s in sandwiches if conf_order[s.confidence] >= min_conf]
        print(f"    Dopo filtro confidenza >= {args.confidence}: {len(sandwiches)} "
              f"(esclusi {before - len(sandwiches)})")

    # ── Stampa dettagli ──────────────────────────────────────────────────────
    for i, s in enumerate(sandwiches):
        print_sandwich(i, s)
    print_summary_table(sandwiches)

    # ── Statistiche ──────────────────────────────────────────────────────────
    stats = compute_stats(sandwiches, len(transactions), len(swaps))
    print_stats(stats)

    # ── Salvataggio JSON risultati ───────────────────────────────────────────
    if args.output_json:
        output_path = Path(args.output_json)
        try:
            with output_path.open("w", encoding="utf-8") as f:
                json.dump([sandwich_to_dict(s) for s in sandwiches], f, indent=2)
            print(f"[✓] Risultati salvati in '{output_path}'")
        except OSError as e:
            print(f"ERRORE scrittura '{output_path}': {e}", file=sys.stderr)
            sys.exit(1)

    # ── Salvataggio JSON statistiche ─────────────────────────────────────────
    if args.output_stats and stats:
        stats_path = Path(args.output_stats)
        try:
            with stats_path.open("w", encoding="utf-8") as f:
                json.dump(stats, f, indent=2)
            print(f"[✓] Statistiche salvate in '{stats_path}'")
        except OSError as e:
            print(f"ERRORE scrittura '{stats_path}': {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()