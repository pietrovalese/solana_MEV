/// sandwich_detector — Rust core for MEV sandwich detection on Solana.
///
/// Exposed to Python via PyO3 as the `sandwich_detector` extension module.
/// The three public functions replace the hot-path Python equivalents:
///
///   parse_swaps(transactions, verbose)  →  list[SwapInfo]
///   detect_sandwiches(swaps, max_gap, min_profit_net, verbose)  →  list[SandwichResult]
///   parse_and_detect(transactions, max_gap, min_profit_net, verbose)  →  list[SandwichResult]
///
/// All input is passed as plain Python dicts/lists; output is plain Python dicts/lists
/// so the Python layer needs zero Rust-specific types.
use std::collections::{HashMap, HashSet};

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SOL_MINT: &str = "So11111111111111111111111111111111111111112";
const VOTE_PROGRAM: &str = "Vote111111111111111111111111111111111111111";
const BASE_FEE_LAMPORTS: u64 = 5_000;

/// Known DEX program addresses → human-readable label.
fn known_dex_programs() -> HashMap<&'static str, &'static str> {
    let mut m = HashMap::new();
    m.insert("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", "Raydium AMM v4");
    m.insert("9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP", "Orca v1");
    m.insert("whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",  "Orca Whirlpool");
    m.insert("JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",  "Jupiter v6");
    m.insert("JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB",  "Jupiter v4");
    m.insert("srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX",  "Serum/OpenBook");
    m.insert("CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", "Raydium CLMM");
    m.insert("CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C", "Raydium CPMM");
    m
}

// ---------------------------------------------------------------------------
// Internal data structures
// ---------------------------------------------------------------------------

/// Internal representation of a single swap extracted from a transaction.
/// All fields use owned types so instances can be stored in a Vec and shared
/// across threads without lifetime constraints.
#[derive(Clone, Debug)]
struct SwapInfo {
    tx_index:      usize,
    signature:     String,
    signer:        String,
    token_in:      String,
    token_out:     String,
    amount_in:     f64,
    amount_out:    f64,
    program:       String,
    fee_sol:       f64,
    pool_accounts: HashSet<String>,
}

/// A victim transaction together with its estimated slippage.
#[derive(Clone, Debug)]
struct VictimInfo {
    swap:              SwapInfo,
    slippage_estimate: f64,
}

/// A fully resolved sandwich: frontrun, one or more victims, and backrun.
#[derive(Clone, Debug)]
struct SandwichResult {
    frontrun:     SwapInfo,
    victims:      Vec<VictimInfo>,
    backrun:      SwapInfo,
    profit_token: String,
    profit_raw:   f64,
    profit_net:   f64,
    shared_pools: HashSet<String>,
    cross_dex:    bool,
    confidence:   String,
}

// ---------------------------------------------------------------------------
// Transaction helpers
// ---------------------------------------------------------------------------

/// Extract the public key of the first account (fee payer) from a transaction dict.
fn get_signer(tx: &PyDict) -> Option<String> {
    let msg = tx
        .get_item("transaction").ok()??
        .downcast::<PyDict>().ok()?
        .get_item("message").ok()??
        .downcast::<PyDict>().ok()?;

    let keys = msg.get_item("accountKeys").ok()??
        .downcast::<PyList>().ok()?;

    let first = keys.get_item(0).ok()?;

    // accountKeys entries can be plain strings or dicts with a "pubkey" field.
    if let Ok(d) = first.downcast::<PyDict>() {
        d.get_item("pubkey").ok()??
            .extract::<String>().ok()
    } else {
        first.extract::<String>().ok()
    }
}

/// Return a flat Vec of all account key strings in a transaction,
/// including writable and readonly loaded addresses.
fn get_account_keys_flat(tx: &PyDict) -> Vec<String> {
    let mut keys = Vec::new();

    // Static account keys
    if let Ok(Some(msg)) = tx
        .get_item("transaction")
        .and_then(|t| t.map(|v| v.downcast::<PyDict>().ok().map(|d| d.get_item("message"))).transpose())
        .and_then(|r| r.map(|o| o.and_then(|v| v.downcast::<PyDict>().ok())).transpose())
    {
        if let Ok(Some(ak)) = msg.get_item("accountKeys") {
            if let Ok(list) = ak.downcast::<PyList>() {
                for item in list.iter() {
                    if let Ok(d) = item.downcast::<PyDict>() {
                        if let Ok(Some(pk)) = d.get_item("pubkey") {
                            if let Ok(s) = pk.extract::<String>() {
                                keys.push(s);
                            }
                        }
                    } else if let Ok(s) = item.extract::<String>() {
                        keys.push(s);
                    }
                }
            }
        }
    }

    // Loaded addresses (writable + readonly)
    if let Ok(Some(meta)) = tx.get_item("meta") {
        if let Ok(m) = meta.downcast::<PyDict>() {
            if let Ok(Some(la)) = m.get_item("loadedAddresses") {
                if let Ok(la_dict) = la.downcast::<PyDict>() {
                    for field in &["writable", "readonly"] {
                        if let Ok(Some(arr)) = la_dict.get_item(*field) {
                            if let Ok(list) = arr.downcast::<PyList>() {
                                for item in list.iter() {
                                    if let Ok(s) = item.extract::<String>() {
                                        keys.push(s);
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    keys
}

/// Return true if the transaction is a validator vote transaction (should be excluded).
fn is_vote_tx(tx: &PyDict) -> bool {
    get_account_keys_flat(tx).contains(&VOTE_PROGRAM.to_string())
}

/// Extract a list of (mint, owner, delta) token balance changes from a transaction.
fn extract_token_transfers(tx: &PyDict) -> Vec<(String, String, f64)> {
    let meta = match tx.get_item("meta") {
        Ok(Some(m)) => match m.downcast::<PyDict>() {
            Ok(d) => d.to_owned(),
            _ => return vec![],
        },
        _ => return vec![],
    };

    // Build pre/post maps: account_index → balance entry
    let mut pre: HashMap<i64, &PyDict>  = HashMap::new();
    let mut post: HashMap<i64, &PyDict> = HashMap::new();

    for (map, field) in [(&mut pre, "preTokenBalances"), (&mut post, "postTokenBalances")] {
        if let Ok(Some(arr)) = meta.get_item(field) {
            if let Ok(list) = arr.downcast::<PyList>() {
                for item in list.iter() {
                    if let Ok(d) = item.downcast::<PyDict>() {
                        if let Ok(Some(idx)) = d.get_item("accountIndex") {
                            if let Ok(i) = idx.extract::<i64>() {
                                map.insert(i, d);
                            }
                        }
                    }
                }
            }
        }
    }

    let all_indices: HashSet<i64> = pre.keys().chain(post.keys()).copied().collect();
    let mut transfers = Vec::new();

    for idx in all_indices {
        let pre_b  = pre.get(&idx);
        let post_b = post.get(&idx);

        let representative = post_b.or(pre_b);
        let mint  = representative.and_then(|d| d.get_item("mint").ok().flatten())
            .and_then(|v| v.extract::<String>().ok())
            .unwrap_or_default();
        let owner = representative.and_then(|d| d.get_item("owner").ok().flatten())
            .and_then(|v| v.extract::<String>().ok())
            .unwrap_or_default();

        let extract_ui_amount = |d_opt: Option<&&PyDict>| -> f64 {
            d_opt
                .and_then(|d| d.get_item("uiTokenAmount").ok().flatten())
                .and_then(|v| v.downcast::<PyDict>().ok())
                .and_then(|d| d.get_item("uiAmount").ok().flatten())
                .and_then(|v| v.extract::<f64>().ok())
                .unwrap_or(0.0)
        };

        let pre_amt  = extract_ui_amount(pre_b);
        let post_amt = extract_ui_amount(post_b);
        let delta    = post_amt - pre_amt;

        if delta.abs() > 1e-9 {
            transfers.push((mint, owner, delta));
        }
    }

    transfers
}

/// Return the net SOL balance change (excluding fees) for the signer of a transaction.
fn sol_delta_for_signer(tx: &PyDict, signer: &str) -> f64 {
    let meta = match tx.get_item("meta") {
        Ok(Some(m)) => match m.downcast::<PyDict>() {
            Ok(d) => d.to_owned(),
            _ => return 0.0,
        },
        _ => return 0.0,
    };

    let keys = get_account_keys_flat(tx);
    let idx  = match keys.iter().position(|k| k == signer) {
        Some(i) => i,
        None    => return 0.0,
    };

    let get_balance = |field: &str| -> Option<i64> {
        meta.get_item(field).ok()??
            .downcast::<PyList>().ok()?
            .get_item(idx).ok()?
            .extract::<i64>().ok()
    };

    let pre  = get_balance("preBalances").unwrap_or(0);
    let post = get_balance("postBalances").unwrap_or(0);
    let fee  = meta.get_item("fee").ok()
        .flatten()
        .and_then(|v| v.extract::<i64>().ok())
        .unwrap_or(0);

    (post - pre + fee) as f64 / 1e9
}

/// Return the total fee paid for a transaction in SOL.
fn get_fee_sol(tx: &PyDict) -> f64 {
    tx.get_item("meta").ok()
        .flatten()
        .and_then(|m| m.downcast::<PyDict>().ok())
        .and_then(|m| m.get_item("fee").ok().flatten())
        .and_then(|v| v.extract::<u64>().ok())
        .unwrap_or(BASE_FEE_LAMPORTS) as f64
        / 1e9
}

/// Return the set of writable account keys in a transaction.
/// Only writable accounts are considered because AMM pool state is always modified.
fn get_pool_accounts(tx: &PyDict) -> HashSet<String> {
    let mut writable = HashSet::new();

    if let Ok(Some(msg)) = tx
        .get_item("transaction")
        .ok()
        .flatten()
        .and_then(|t| t.downcast::<PyDict>().ok())
        .map(|d| d.get_item("message"))
        .transpose()
    {
        if let Some(m) = msg {
            if let Ok(d) = m.downcast::<PyDict>() {
                if let Ok(Some(ak)) = d.get_item("accountKeys") {
                    if let Ok(list) = ak.downcast::<PyList>() {
                        for item in list.iter() {
                            if let Ok(entry) = item.downcast::<PyDict>() {
                                let is_writable = entry.get_item("writable").ok()
                                    .flatten()
                                    .and_then(|v| v.extract::<bool>().ok())
                                    .unwrap_or(false);
                                if is_writable {
                                    if let Ok(Some(pk)) = entry.get_item("pubkey") {
                                        if let Ok(s) = pk.extract::<String>() {
                                            writable.insert(s);
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Also include writable loaded addresses
    if let Ok(Some(meta)) = tx.get_item("meta") {
        if let Ok(m) = meta.downcast::<PyDict>() {
            if let Ok(Some(la)) = m.get_item("loadedAddresses") {
                if let Ok(la_dict) = la.downcast::<PyDict>() {
                    if let Ok(Some(arr)) = la_dict.get_item("writable") {
                        if let Ok(list) = arr.downcast::<PyList>() {
                            for item in list.iter() {
                                if let Ok(s) = item.extract::<String>() {
                                    writable.insert(s);
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    writable
}

// ---------------------------------------------------------------------------
// Swap inference
// ---------------------------------------------------------------------------

/// Try to reconstruct the primary swap from a transaction's balance deltas.
/// Returns None if the transaction is not a swap or cannot be parsed.
fn infer_swap(tx_index: usize, tx: &PyDict, verbose: bool) -> Option<SwapInfo> {
    let meta = tx.get_item("meta").ok()??;
    let meta = meta.downcast::<PyDict>().ok()?;

    // Skip failed transactions
    if let Ok(Some(err)) = meta.get_item("err") {
        if !err.is_none() {
            return None;
        }
    }

    let signer = get_signer(tx)?;
    if signer.is_empty() {
        return None;
    }

    let transfers   = extract_token_transfers(tx);
    let signer_xfers: Vec<_> = transfers.iter().filter(|(_, o, _)| o == &signer).collect();

    // Aggregate per-mint deltas for the signer
    let mut mint_deltas: HashMap<String, f64> = HashMap::new();
    for (mint, _, delta) in &signer_xfers {
        *mint_deltas.entry(mint.clone()).or_insert(0.0) += delta;
    }
    mint_deltas.retain(|_, d| d.abs() > 1e-9);

    let sol_d = sol_delta_for_signer(tx, &signer);

    let sold:   HashMap<String, f64> = mint_deltas.iter().filter(|(_, d)| **d < 0.0).map(|(m, d)| (m.clone(), d.abs())).collect();
    let bought: HashMap<String, f64> = mint_deltas.iter().filter(|(_, d)| **d > 0.0).map(|(m, d)| (m.clone(), *d)).collect();

    let (token_in, token_out, amount_in, amount_out) = if !sold.is_empty() && !bought.is_empty() {
        let ti = sold.iter().max_by(|a, b| a.1.partial_cmp(b.1).unwrap()).map(|(m, _)| m.clone())?;
        let to = bought.iter().max_by(|a, b| a.1.partial_cmp(b.1).unwrap()).map(|(m, _)| m.clone())?;
        let ai = sold[&ti];
        let ao = bought[&to];
        (ti, to, ai, ao)
    } else if sol_d < -0.000_001 && !bought.is_empty() && sold.is_empty() {
        let to = bought.iter().max_by(|a, b| a.1.partial_cmp(b.1).unwrap()).map(|(m, _)| m.clone())?;
        let ao = bought[&to];
        (SOL_MINT.to_string(), to, sol_d.abs(), ao)
    } else if sol_d > 0.000_001 && !sold.is_empty() && bought.is_empty() {
        let ti = sold.iter().max_by(|a, b| a.1.partial_cmp(b.1).unwrap()).map(|(m, _)| m.clone())?;
        let ai = sold[&ti];
        (ti, SOL_MINT.to_string(), ai, sol_d)
    } else {
        if verbose {
            eprintln!("[WARN] tx {tx_index}: ambiguous balance deltas, skipping");
        }
        return None;
    };

    let dex_map   = known_dex_programs();
    let acct_keys = get_account_keys_flat(tx);
    let program   = acct_keys.iter()
        .find_map(|k| dex_map.get(k.as_str()).copied())
        .unwrap_or("unknown")
        .to_string();

    let signature = tx
        .get_item("transaction").ok().flatten()
        .and_then(|t| t.downcast::<PyDict>().ok())
        .and_then(|d| d.get_item("signatures").ok().flatten())
        .and_then(|s| s.downcast::<PyList>().ok())
        .and_then(|l| l.get_item(0).ok())
        .and_then(|v| v.extract::<String>().ok())
        .unwrap_or_default();

    Some(SwapInfo {
        tx_index,
        signature,
        signer,
        token_in,
        token_out,
        amount_in,
        amount_out,
        program,
        fee_sol:       get_fee_sol(tx),
        pool_accounts: get_pool_accounts(tx),
    })
}

// ---------------------------------------------------------------------------
// Sandwich detection
// ---------------------------------------------------------------------------

/// Return true if swaps a and b are mirror operations (A→B and B→A).
#[inline]
fn is_mirror_swap(a: &SwapInfo, b: &SwapInfo) -> bool {
    a.token_in == b.token_out && a.token_out == b.token_in
}

/// Estimate the slippage suffered by a victim relative to the frontrun price.
fn estimate_victim_slippage(victim: &SwapInfo, frontrun: &SwapInfo) -> f64 {
    if victim.token_in != frontrun.token_in || victim.token_out != frontrun.token_out {
        return 0.0;
    }
    if frontrun.amount_in == 0.0 || victim.amount_in == 0.0 || frontrun.amount_out == 0.0 {
        return 0.0;
    }
    let price_fr  = frontrun.amount_out / frontrun.amount_in;
    let price_vic = victim.amount_out   / victim.amount_in;
    let slippage  = (price_fr - price_vic) / price_fr * 100.0;
    (slippage * 10_000.0).round() / 10_000.0
}

/// Assign a confidence level ("HIGH" / "MEDIUM" / "LOW") to a sandwich candidate.
fn classify_confidence(
    shared_pools: &HashSet<String>,
    profit_net: f64,
    gap: usize,
) -> String {
    let score = [
        !shared_pools.is_empty(),
        profit_net > 0.0,
        gap <= 3,
    ]
    .iter()
    .filter(|&&b| b)
    .count();

    match score {
        3 => "HIGH",
        1 | 2 => "MEDIUM",
        _ => "LOW",
    }
    .to_string()
}

/// Core O(n * max_gap) detection loop.
/// Returns sandwiches sorted by descending net profit.
fn detect_sandwiches_inner(
    swaps: &[SwapInfo],
    max_gap: usize,
    min_profit_net: Option<f64>,
    verbose: bool,
) -> Vec<SandwichResult> {
    let n = swaps.len();
    let mut results = Vec::new();

    for i in 0..n {
        let fr = &swaps[i];
        let upper = (i + 1 + max_gap).min(n);

        for j in (i + 2)..upper {
            let br = &swaps[j];

            if fr.signer != br.signer {
                continue;
            }
            if !is_mirror_swap(fr, br) {
                continue;
            }

            // Reject if the bot has any other swap between frontrun and backrun.
            let bot_in_between = swaps[i + 1..j].iter().any(|s| s.signer == fr.signer);
            if bot_in_between {
                if verbose {
                    eprintln!("[skip] bot has intermediate txs between {i} and {j}");
                }
                continue;
            }

            // Collect victims: same token pair, different signer.
            let victim_swaps: Vec<&SwapInfo> = swaps[i + 1..j]
                .iter()
                .filter(|s| {
                    s.signer != fr.signer
                        && ((s.token_in == fr.token_in  && s.token_out == fr.token_out)
                         || (s.token_in == fr.token_out && s.token_out == fr.token_in))
                })
                .collect();

            if victim_swaps.is_empty() {
                continue;
            }

            // Shared pool accounts: empty set → likely false positive.
            let shared_pools: HashSet<String> =
                fr.pool_accounts.intersection(&br.pool_accounts).cloned().collect();
            if verbose && shared_pools.is_empty() {
                eprintln!("[warn] no shared pool between frontrun@{i} and backrun@{j}");
            }

            let profit_raw = br.amount_out - fr.amount_in;
            let profit_net = profit_raw - fr.fee_sol - br.fee_sol;

            if let Some(min_p) = min_profit_net {
                if profit_net < min_p {
                    if verbose {
                        eprintln!("[skip] net profit {profit_net:.6f} < {min_p}");
                    }
                    continue;
                }
            }

            let gap        = j - i;
            let confidence = classify_confidence(&shared_pools, profit_net, gap);
            let cross_dex  = fr.program != br.program;

            let victims: Vec<VictimInfo> = victim_swaps
                .iter()
                .map(|v| VictimInfo {
                    swap:              (*v).clone(),
                    slippage_estimate: estimate_victim_slippage(v, fr),
                })
                .collect();

            if verbose {
                eprintln!(
                    "  [match {confidence}] frontrun@{} -> backrun@{} signer={}... \
                     pool_shared={} profit_net={profit_net:.6f}",
                    fr.tx_index,
                    br.tx_index,
                    &fr.signer[..8.min(fr.signer.len())],
                    shared_pools.len(),
                );
            }

            results.push(SandwichResult {
                frontrun:     fr.clone(),
                victims,
                backrun:      br.clone(),
                profit_token: br.token_out.clone(),
                profit_raw,
                profit_net,
                shared_pools,
                cross_dex,
                confidence,
            });

            // One backrun per frontrun: stop searching for this i.
            break;
        }
    }

    results.sort_by(|a, b| b.profit_net.partial_cmp(&a.profit_net).unwrap());
    results
}

// ---------------------------------------------------------------------------
// Conversion to Python dicts (output layer)
// ---------------------------------------------------------------------------

/// Serialize a SwapInfo to a Python dict.
fn swap_to_pydict(py: Python<'_>, s: &SwapInfo) -> PyResult<PyObject> {
    let d = PyDict::new(py);
    d.set_item("tx_index",   s.tx_index)?;
    d.set_item("signature",  &s.signature)?;
    d.set_item("signer",     &s.signer)?;
    d.set_item("token_in",   &s.token_in)?;
    d.set_item("token_out",  &s.token_out)?;
    d.set_item("amount_in",  s.amount_in)?;
    d.set_item("amount_out", s.amount_out)?;
    d.set_item("program",    &s.program)?;
    d.set_item("fee_sol",    s.fee_sol)?;
    Ok(d.into())
}

/// Serialize a SandwichResult to a Python dict.
fn sandwich_to_pydict(py: Python<'_>, s: &SandwichResult) -> PyResult<PyObject> {
    let d = PyDict::new(py);
    d.set_item("frontrun", swap_to_pydict(py, &s.frontrun)?)?;

    let victims_list = PyList::empty(py);
    for v in &s.victims {
        let vd = PyDict::new(py);
        vd.set_item("swap",              swap_to_pydict(py, &v.swap)?)?;
        vd.set_item("slippage_estimate", v.slippage_estimate)?;
        victims_list.append(vd)?;
    }
    d.set_item("victims", victims_list)?;

    d.set_item("backrun",      swap_to_pydict(py, &s.backrun)?)?;
    d.set_item("profit_token", &s.profit_token)?;
    d.set_item("profit_raw",   s.profit_raw)?;
    d.set_item("profit_net",   s.profit_net)?;

    let pools: Vec<&String> = s.shared_pools.iter().collect();
    d.set_item("shared_pools", pools)?;
    d.set_item("cross_dex",    s.cross_dex)?;
    d.set_item("confidence",   &s.confidence)?;
    Ok(d.into())
}

// ---------------------------------------------------------------------------
// PyO3 public API
// ---------------------------------------------------------------------------

/// Parse all swap transactions in a block.
///
/// Args:
///     transactions: Python list of transaction dicts as returned by
///                   ``getBlock`` with ``encoding="jsonParsed"``.
///     verbose:      If True, print warnings to stderr.
///
/// Returns:
///     A Python list of dicts, one per detected swap.
///     Each dict has the same keys as the Python ``SwapInfo`` dataclass:
///     tx_index, signature, signer, token_in, token_out, amount_in,
///     amount_out, program, fee_sol.
#[pyfunction]
#[pyo3(signature = (transactions, verbose = false))]
fn parse_swaps(
    py: Python<'_>,
    transactions: &PyList,
    verbose: bool,
) -> PyResult<PyObject> {
    let dex = known_dex_programs(); // eagerly build once per call
    let _ = dex; // used inside infer_swap via module-level fn

    let result = PyList::empty(py);
    let mut vote_count = 0usize;

    for (i, tx_obj) in transactions.iter().enumerate() {
        let tx = match tx_obj.downcast::<PyDict>() {
            Ok(d) => d,
            Err(_) => continue,
        };

        if is_vote_tx(tx) {
            vote_count += 1;
            continue;
        }

        if let Some(swap) = infer_swap(i, tx, verbose) {
            let d = PyDict::new(py);
            d.set_item("tx_index",   swap.tx_index)?;
            d.set_item("signature",  &swap.signature)?;
            d.set_item("signer",     &swap.signer)?;
            d.set_item("token_in",   &swap.token_in)?;
            d.set_item("token_out",  &swap.token_out)?;
            d.set_item("amount_in",  swap.amount_in)?;
            d.set_item("amount_out", swap.amount_out)?;
            d.set_item("program",    &swap.program)?;
            d.set_item("fee_sol",    swap.fee_sol)?;
            result.append(d)?;
        }
    }

    if verbose {
        eprintln!("[rust] vote txs filtered: {vote_count}");
        eprintln!("[rust] swaps extracted:   {}", result.len());
    }

    Ok(result.into())
}

/// Detect sandwich attacks in an ordered list of swaps.
///
/// Args:
///     swaps:          Python list of swap dicts (output of :func:`parse_swaps`).
///     max_gap:        Maximum number of transactions between frontrun and backrun.
///     min_profit_net: Minimum net SOL profit; sandwiches below this are discarded.
///     verbose:        If True, print debug output to stderr.
///
/// Returns:
///     A Python list of sandwich dicts, sorted by descending net profit.
#[pyfunction]
#[pyo3(signature = (swaps, max_gap = 10, min_profit_net = None, verbose = false))]
fn detect_sandwiches(
    py: Python<'_>,
    swaps: &PyList,
    max_gap: usize,
    min_profit_net: Option<f64>,
    verbose: bool,
) -> PyResult<PyObject> {
    // Re-hydrate SwapInfo from Python dicts.
    let mut swap_vec: Vec<SwapInfo> = Vec::with_capacity(swaps.len());
    for item in swaps.iter() {
        let d = match item.downcast::<PyDict>() {
            Ok(d) => d,
            Err(_) => continue,
        };
        let get_str = |key: &str| -> String {
            d.get_item(key).ok().flatten()
                .and_then(|v| v.extract::<String>().ok())
                .unwrap_or_default()
        };
        let get_f64 = |key: &str| -> f64 {
            d.get_item(key).ok().flatten()
                .and_then(|v| v.extract::<f64>().ok())
                .unwrap_or(0.0)
        };
        let get_usize = |key: &str| -> usize {
            d.get_item(key).ok().flatten()
                .and_then(|v| v.extract::<usize>().ok())
                .unwrap_or(0)
        };

        swap_vec.push(SwapInfo {
            tx_index:      get_usize("tx_index"),
            signature:     get_str("signature"),
            signer:        get_str("signer"),
            token_in:      get_str("token_in"),
            token_out:     get_str("token_out"),
            amount_in:     get_f64("amount_in"),
            amount_out:    get_f64("amount_out"),
            program:       get_str("program"),
            fee_sol:       get_f64("fee_sol"),
            pool_accounts: HashSet::new(), // not round-tripped; recomputed in parse_swaps
        });
    }

    let results = detect_sandwiches_inner(&swap_vec, max_gap, min_profit_net, verbose);

    let out = PyList::empty(py);
    for s in &results {
        out.append(sandwich_to_pydict(py, s)?)?;
    }
    Ok(out.into())
}

/// Parse swaps and detect sandwiches in a single call (avoids Python round-trip overhead).
///
/// This is the recommended entry point when processing a single block: the
/// intermediate SwapInfo vec never crosses the Python/Rust boundary.
///
/// Args:
///     transactions:   Python list of transaction dicts (jsonParsed format).
///     max_gap:        Maximum tx gap between frontrun and backrun.
///     min_profit_net: Minimum net SOL profit filter.
///     verbose:        Verbose stderr output.
///
/// Returns:
///     A Python list of sandwich dicts, sorted by descending net profit.
#[pyfunction]
#[pyo3(signature = (transactions, max_gap = 10, min_profit_net = None, verbose = false))]
fn parse_and_detect(
    py: Python<'_>,
    transactions: &PyList,
    max_gap: usize,
    min_profit_net: Option<f64>,
    verbose: bool,
) -> PyResult<PyObject> {
    let mut swaps: Vec<SwapInfo> = Vec::new();

    for (i, tx_obj) in transactions.iter().enumerate() {
        let tx = match tx_obj.downcast::<PyDict>() {
            Ok(d) => d,
            Err(_) => continue,
        };
        if is_vote_tx(tx) {
            continue;
        }
        if let Some(swap) = infer_swap(i, tx, verbose) {
            swaps.push(swap);
        }
    }

    let results = detect_sandwiches_inner(&swaps, max_gap, min_profit_net, verbose);

    let out = PyList::empty(py);
    for s in &results {
        out.append(sandwich_to_pydict(py, s)?)?;
    }
    Ok(out.into())
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

#[pymodule]
fn sandwich_detector(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_swaps,      m)?)?;
    m.add_function(wrap_pyfunction!(detect_sandwiches, m)?)?;
    m.add_function(wrap_pyfunction!(parse_and_detect,  m)?)?;
    Ok(())
}