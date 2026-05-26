import json
import re
import os
import csv
from collections import Counter

import pandas as pd
import matplotlib.pyplot as plt
from tqdm import tqdm

# =======================
# === CONFIGURATION ===
# =======================
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SANDWICH_PATH = os.path.join(BASE_DIR, "sandwiches_annotated.jsonl")
MEME_LIST_PATH = os.path.join(BASE_DIR, "memecoin.csv")
ARB_PATH = os.path.join(BASE_DIR, "arbitrages_annotated.jsonl")

# =======================
# === DATA LOADING ===
# =======================

def load_memecoins(csv_path):
    """
    Load memecoin tickers from a CSV file.

    Reads the CSV at the given path and returns a set of uppercase ticker symbols
    for all rows where the 'Tipo' column equals 'meme'.

    Args:
        csv_path (str): Path to the CSV file containing coin data.

    Returns:
        set: A set of uppercase memecoin ticker strings.
    """
    memecoin_tickers = set()
    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Tipo'].strip().lower() == 'meme' and row['Ticker']:
                memecoin_tickers.add(row['Ticker'].strip().upper())
    return memecoin_tickers


def load_sandwich_data(path):
    """
    Load sandwich records from a JSONL file.

    Args:
        path (str): Path to the JSONL file.

    Returns:
        list[dict]: List of parsed sandwich records.
    """
    with open(path, 'r', encoding='utf-8') as f:
        return [json.loads(line.strip()) for line in f]


def load_arbitrage_data(path):
    """
    Load arbitrage records from a JSONL file, fixing known malformed JSON patterns.

    The function repairs lines where duplicate keys appear as ``{"bot""bot"``
    before parsing.

    Args:
        path (str): Path to the JSONL file.

    Returns:
        list[dict]: List of successfully parsed arbitrage records.
    """
    records = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Fix malformed keys such as duplicate {"bot""bot" → {"bot"
            line = re.sub(r'\{"bot""bot"', '{"bot"', line)
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print("Error on line:", line[:100])
                print("Details:", e)
    return records


memecoin_tickers = load_memecoins(MEME_LIST_PATH)
data_sandwich = load_sandwich_data(SANDWICH_PATH)
data_arb = load_arbitrage_data(ARB_PATH)

print(f"Records loaded successfully: {len(data_arb)}")

# ==================================
# === ARBITRAGE ↔ SANDWICH MATCHING ===
# ==================================

def build_sandwich_hash_map(data_sandwich):
    """
    Build a lookup map from transaction hash to sandwich participation details.

    For each sandwich record, indexes bot1, bot2, and all victim hashes so that
    any transaction hash can be quickly resolved to its role and sandwich index.

    Args:
        data_sandwich (list[dict]): List of sandwich records.

    Returns:
        dict: Mapping ``{tx_hash: [match_dict, ...]}``, where each match_dict
              contains keys: name, role, sandwich_idx, entry, full_sandwich.
    """
    hash_map = {}
    for idx, entry_sandwich in enumerate(tqdm(data_sandwich, desc="Building sandwich map")):
        bot1 = entry_sandwich.get("bot1", {})
        bot2 = entry_sandwich.get("bot2", {})
        victims = entry_sandwich.get("victims", [])

        for role, part in (("bot1", bot1), ("bot2", bot2)):
            h = part.get("hash")
            if h:
                hash_map.setdefault(h, []).append({
                    "name": part.get("bot"),
                    "role": role,
                    "sandwich_idx": idx,
                    "entry": part,
                    "full_sandwich": entry_sandwich
                })

        for victim in victims:
            h = victim.get("hash")
            if h:
                hash_map.setdefault(h, []).append({
                    "name": victim.get("victim"),
                    "role": "victim",
                    "sandwich_idx": idx,
                    "entry": victim,
                    "full_sandwich": entry_sandwich
                })
    return hash_map


def match_arbitrages_to_sandwiches(data_arb, sandwich_hash_map):
    """
    Match arbitrage transaction hashes against the sandwich hash map.

    Args:
        data_arb (list[dict]): Parsed arbitrage records.
        sandwich_hash_map (dict): Output of :func:`build_sandwich_hash_map`.

    Returns:
        list[dict]: Combined records with keys: arb_tx, arb_idx, arb_entry,
                    sandwich_idx, role, sandwich_entry, full_sandwich, name.
    """
    combined = []
    tx_arb_list = [
        (entry.get("tx_id"), idx, entry)
        for idx, entry in enumerate(tqdm(data_arb, desc="Indexing arbitrages"))
        if entry.get("tx_id")
    ]

    for arb_tx, arb_idx, arb_entry in tqdm(tx_arb_list, desc="Matching"):
        if arb_tx in sandwich_hash_map:
            for match in sandwich_hash_map[arb_tx]:
                combined.append({
                    "arb_tx": arb_tx,
                    "arb_idx": arb_idx,
                    "arb_entry": arb_entry,
                    "sandwich_idx": match["sandwich_idx"],
                    "role": match["role"],
                    "sandwich_entry": match["entry"],
                    "full_sandwich": match["full_sandwich"],
                    "name": match["name"]
                })
    return combined


sandwich_hash_map = build_sandwich_hash_map(data_sandwich)
combined_list = match_arbitrages_to_sandwiches(data_arb, sandwich_hash_map)

print(f"\nFound {len(combined_list)} matches between arbitrages and sandwiches "
      f"({len(data_arb)} arbitrages, {len(data_sandwich)} sandwiches)\n")

# =======================
# === UNIQUE ENTITY EXTRACTION ===
# =======================

unique_victim = set()
for match in combined_list:
    unique_victim.add(match['name'])
    print(f"- Arb row {match['arb_idx']} (tx {match['arb_tx']}) "
          f"is {match['role']} in sandwich row {match['sandwich_idx']}")

# Strip "victim: " prefix that may be present in victim name strings
unique_victim_clean = {v.split(":", 1)[-1].strip() for v in unique_victim}

# Collect unique bot addresses from arbitrages whose tx_id appears in combined_list
matched_tx_ids = {m['arb_tx'] for m in combined_list}
unique_bots = {elem['bot'] for elem in data_arb if elem.get("tx_id") in matched_tx_ids}

print("=" * 50)
print("Unique arbitrage bots:")
print(", ".join(sorted(unique_bots)))
print("\nUnique victims:")
print(", ".join(sorted(unique_victim_clean)))

# =======================
# === VICTIM FREQUENCY TABLE ===
# =======================

victim_counter = Counter(
    match["name"]
    for match in combined_list
    if match["role"] == "victim"
)

victim_counts_clean = {v.split(":", 1)[-1].strip(): c for v, c in victim_counter.items()}

df_victims_freq = pd.DataFrame(
    list(victim_counts_clean.items()),
    columns=["victim", "count"]
).sort_values(by="count", ascending=False)

print("\nTop victims by number of occurrences:\n")
print(df_victims_freq.head(10))

# ==================================
# === BUILD MATCHED RECORDS DATAFRAME ===
# ==================================

def build_matches_dataframe(combined_list):
    """
    Build a DataFrame from the matched arbitrage–sandwich records.

    Each row represents one matched transaction and contains role, name,
    token pair, fee information, and block time.

    Args:
        combined_list (list[dict]): Output of :func:`match_arbitrages_to_sandwiches`.

    Returns:
        pd.DataFrame: One row per match with columns: role, name, sandwich_idx,
                      arb_tx, token_start, token_end, value_start, value_end,
                      priority_fee, total_fee, blockTime.
    """
    records = []
    for match in combined_list:
        entry = match["sandwich_entry"]
        details = entry.get("Details", {})
        records.append({
            "role": match["role"],
            "name": match["name"],
            "sandwich_idx": match["sandwich_idx"],
            "arb_tx": match["arb_tx"],
            "token_start": entry.get("token_start"),
            "token_end": entry.get("token_end"),
            "value_start": entry.get("value_start"),
            "value_end": entry.get("value_end"),
            "priority_fee": details.get("fee", {}).get("priority_fee", 0) / 1_000_000_000,
            "total_fee": details.get("fee", {}).get("total_fee", 0),
            "blockTime": details.get("blockTime")
        })
    return pd.DataFrame(records)


df_matches = build_matches_dataframe(combined_list)

# =====================================
# === BUILD FULL SANDWICH DATAFRAME ===
# =====================================

def build_all_sandwich_dataframe(data_sandwich):
    """
    Build a flat DataFrame from all sandwich records (bot1, bot2, victims).

    Args:
        data_sandwich (list[dict]): List of raw sandwich records.

    Returns:
        pd.DataFrame: One row per participant (bot1/bot2/victim) with columns:
                      role, name, sandwich_idx, token_start, token_end,
                      priority_fee, total_fee.
    """
    all_records = []
    for idx, sandwich in enumerate(data_sandwich):
        for role in ("bot1", "bot2"):
            entry = sandwich.get(role)
            if entry:
                details = entry.get("Details", {})
                all_records.append({
                    "role": role,
                    "name": entry.get("bot"),
                    "sandwich_idx": idx,
                    "token_start": entry.get("token_start"),
                    "token_end": entry.get("token_end"),
                    "priority_fee": details.get("fee", {}).get("priority_fee", 0) / 1e9,
                    "total_fee": details.get("fee", {}).get("total_fee", 0),
                })

        for victim in sandwich.get("victims", []):
            details = victim.get("Details", {})
            all_records.append({
                "role": "victim",
                "name": victim.get("victim"),
                "sandwich_idx": idx,
                "token_start": victim.get("token_start"),
                "token_end": victim.get("token_end"),
                "priority_fee": details.get("fee", {}).get("priority_fee", 0) / 1e9,
                "total_fee": details.get("fee", {}).get("total_fee", 0),
            })
    return pd.DataFrame(all_records)


df_all_sandwich = build_all_sandwich_dataframe(data_sandwich)

# ============================
# === OUTLIER REMOVAL (IQR) ===
# ============================

def remove_victim_outliers(df):
    """
    Remove priority_fee outliers from victim rows using the IQR method.

    Non-victim rows are kept unchanged. Victim rows outside
    [Q1 - 1.5*IQR, Q3 + 1.5*IQR] are dropped.

    Args:
        df (pd.DataFrame): Full sandwich DataFrame with a 'role' column.

    Returns:
        pd.DataFrame: DataFrame with victim outliers removed.
    """
    df_v = df[df["role"] == "victim"].copy()
    Q1 = df_v["priority_fee"].quantile(0.25)
    Q3 = df_v["priority_fee"].quantile(0.75)
    IQR = Q3 - Q1
    df_v_clean = df_v[
        (df_v["priority_fee"] >= Q1 - 1.5 * IQR) &
        (df_v["priority_fee"] <= Q3 + 1.5 * IQR)
    ]
    return pd.concat([df[df["role"] != "victim"], df_v_clean])


df_all_sandwich_filtered = remove_victim_outliers(df_all_sandwich)

# =======================
# === STATISTICS ===
# =======================

print("\nPriority Fee – Full sandwich data (victims without outliers):")
print(df_all_sandwich_filtered["priority_fee"].describe())

print("\nPriority Fee by role – Full sandwich data (victims without outliers):")
print(df_all_sandwich_filtered.groupby("role")["priority_fee"].describe())

print("\nPriority Fee – Matched records only:")
print(df_matches["priority_fee"].describe())

print("\nPriority Fee by role – Matched records only:")
print(df_matches.groupby("role")["priority_fee"].describe())

# =======================
# === OVERLAP ANALYSIS ===
# =======================

victim_as_bot = unique_victim_clean.intersection(unique_bots)
df_overlap = df_matches[df_matches["name"].isin(victim_as_bot)]

if not df_overlap.empty:
    print("\nStatistics for victims who also act as arbitrage bots (overlap):")
    print(df_overlap.groupby("role")["priority_fee"].describe())
    print("\nTop tokens used by overlap addresses:")
    print(df_overlap["token_start"].value_counts().head(10))

# =======================
# === PLOTTING ===
# =======================

fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)

df_all_sandwich_filtered.boxplot(column="priority_fee", by="role", ax=axes[0])
axes[0].set_title("Priority fee by role – Full sandwich data (victims without outliers)")
axes[0].set_ylabel("Priority fee (SOL)")
axes[0].set_xlabel("Role")

df_matches.boxplot(column="priority_fee", by="role", ax=axes[1])
axes[1].set_title("Priority fee by role – Matched records only")
axes[1].set_xlabel("Role")

plt.suptitle("")
plt.tight_layout()
plt.show()