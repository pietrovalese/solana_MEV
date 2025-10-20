import json
from tqdm import tqdm
import os
import csv
import re

# Percorsi file
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
sandwich_path = os.path.join(BASE_DIR, "sandwiches_annotated.jsonl")
meme_list_path = os.path.join(BASE_DIR, "meme_and_shitcoins_list.csv")
arb_path = os.path.join(BASE_DIR, "arbitrages_annotated.jsonl")

# ======================
# Caricamento memecoin
# ======================
def load_memecoins(csv_path):
    memecoin_tickers = set()
    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Tipo'].strip().lower() == 'meme' and row['Ticker']:
                memecoin_tickers.add(row['Ticker'].strip().upper())
    return memecoin_tickers

memecoin_tickers = load_memecoins(meme_list_path)

# ======================
# Carica file JSONL
# ======================
with open(sandwich_path, 'r', encoding="utf-8") as f:
    data_sandwich = [json.loads(line.strip()) for line in f]

data_arb = []
with open(arb_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        # Fix per JSON corrotto: doppie chiavi tipo "bot""bot"
        line = re.sub(r'\{"bot""bot"', '{"bot"', line)
        try:
            record = json.loads(line)
            data_arb.append(record)
        except json.JSONDecodeError as e:
            print("Errore su riga:", line[:100])
            print("Dettagli:", e)

print(f"✅ Record letti correttamente: {len(data_arb)}")

# ======================
# Matching arbitraggio ↔ sandwich
# ======================
tx_arb_list = []
sandwich_hash_map = {}  # hash => lista di match
combined_list = []

# 1. Raccogli arbitraggi con indice riga
for idx, entry_arb in enumerate(tqdm(data_arb, desc="🔄 Arbitraggi")):
    tx_hash = entry_arb.get("tx_id")
    if tx_hash:
        tx_arb_list.append((tx_hash, idx, entry_arb))

# 2. Costruisci mappa hash → lista di sandwich matches
for idx, entry_sandwich in enumerate(tqdm(data_sandwich, desc="🔄 Sandwich")):
    bot1 = entry_sandwich.get("bot1", {})
    bot2 = entry_sandwich.get("bot2", {})
    victims = entry_sandwich.get("victims", [])

    for role, part in (("bot1", bot1), ("bot2", bot2)):
        h = part.get("hash")
        name = part.get("bot")
        if h:
            sandwich_hash_map.setdefault(h, []).append({
                "name": name,
                "role": role,
                "sandwich_idx": idx,
                "entry": part,
                "full_sandwich": entry_sandwich
            })

    for victim in victims:
        h = victim.get("hash")
        name_v = victim.get("victim")
        if h:
            sandwich_hash_map.setdefault(h, []).append({
                "name": name_v,
                "role": "victim",
                "sandwich_idx": idx,
                "entry": victim,
                "full_sandwich": entry_sandwich
            })

# 3. Match con indice e dettagli
for arb_tx, arb_idx, arb_entry in tqdm(tx_arb_list, desc="🔍 Matching"):
    if arb_tx in sandwich_hash_map:
        for match in sandwich_hash_map[arb_tx]:
            combined_list.append({
                "arb_tx": arb_tx,
                "arb_idx": arb_idx,
                "arb_entry": arb_entry,
                "sandwich_idx": match["sandwich_idx"],
                "role": match["role"],
                "sandwich_entry": match["entry"],
                "full_sandwich": match["full_sandwich"],
                "name": match['name']
            })

print(f"\n✅ Trovate {len(combined_list)} corrispondenze tra arbitraggio e sandwich "
      f"su {len(data_arb)} arbitraggi e {len(data_sandwich)} sandwich\n")

# ======================
# Estrazione unici
# ======================
unique_victim = set()
for match in combined_list:
    unique_victim.add(match['name'])
    print(f"- Arb row {match['arb_idx']} (tx {match['arb_tx']}) "
          f"is {match['role']} in sandwich row {match['sandwich_idx']}")

# Pulizia dei nomi vittime (rimozione prefisso "victim: ")
pulite = {v.split(":", 1)[-1].strip() for v in unique_victim}

# Bot unici negli arbitrages
unique_bots = set()
for elem in data_arb:
    for match in combined_list:
        if elem["tx_id"] == match['arb_tx']:  # uguaglianza diretta, no substring
            unique_bots.add(elem['bot'])

# ======================
# Output finale
# ======================
print("="*50)
print("Bot arbitraggi unici:")
print(", ".join(sorted(unique_bots)))
print("\nVittime uniche:")
print(", ".join(sorted(pulite)))

import pandas as pd
from collections import Counter

# Contiamo le occorrenze di tutte le vittime (con prefisso "victim:")
victim_counter = Counter()

for match in combined_list:
    if match["role"] == "victim":
        victim_counter[match["name"]] += 1

# Pulizia prefisso "victim:" come prima
victim_counts_clean = {v.split(":", 1)[-1].strip(): c for v, c in victim_counter.items()}

# Convertiamo in DataFrame ordinato
df_victims = pd.DataFrame(
    list(victim_counts_clean.items()), 
    columns=["victim", "count"]
).sort_values(by="count", ascending=False)

# Mostriamo tabella
print("\n📊 Top vittime per numero di occorrenze:\n")
print(df_victims.head(10))  # prime 20

import pandas as pd
from collections import Counter
import matplotlib.pyplot as plt

# ============================
# 1. Costruzione DataFrame
# ============================
records = []

for match in combined_list:
    role = match["role"]
    entry = match["sandwich_entry"]
    details = entry.get("Details", {})

    records.append({
        "role": role,
        "name": match["name"],
        "sandwich_idx": match["sandwich_idx"],
        "arb_tx": match["arb_tx"],
        "token_start": entry.get("token_start"),
        "token_end": entry.get("token_end"),
        "value_start": entry.get("value_start"),
        "value_end": entry.get("value_end"),
        "priority_fee": details.get("fee", {}).get("priority_fee", 0)/1000000000,
        "total_fee": details.get("fee", {}).get("total_fee", 0),
        "blockTime": details.get("blockTime")
    })

df_matches = pd.DataFrame(records)

# ============================
# 2. Statistiche generali
# ============================
import pandas as pd
import matplotlib.pyplot as plt

# ============================
# 1. Estraggo TUTTI i record da data_sandwich
# ============================
all_records = []

for idx, sandwich in enumerate(data_sandwich):
    # Bot1
    if sandwich.get("bot1"):
        entry = sandwich["bot1"]
        details = entry.get("Details", {})
        all_records.append({
            "role": "bot1",
            "name": entry.get("bot"),
            "sandwich_idx": idx,
            "token_start": entry.get("token_start"),
            "token_end": entry.get("token_end"),
            "priority_fee": details.get("fee", {}).get("priority_fee", 0)/1e9,
            "total_fee": details.get("fee", {}).get("total_fee", 0),
        })

    # Bot2
    if sandwich.get("bot2"):
        entry = sandwich["bot2"]
        details = entry.get("Details", {})
        all_records.append({
            "role": "bot2",
            "name": entry.get("bot"),
            "sandwich_idx": idx,
            "token_start": entry.get("token_start"),
            "token_end": entry.get("token_end"),
            "priority_fee": details.get("fee", {}).get("priority_fee", 0)/1e9,
            "total_fee": details.get("fee", {}).get("total_fee", 0),
        })

    # Victims
    for victim in sandwich.get("victims", []):
        details = victim.get("Details", {})
        all_records.append({
            "role": "victim",
            "name": victim.get("victim"),
            "sandwich_idx": idx,
            "token_start": victim.get("token_start"),
            "token_end": victim.get("token_end"),
            "priority_fee": details.get("fee", {}).get("priority_fee", 0)/1e9,
            "total_fee": details.get("fee", {}).get("total_fee", 0),
        })

df_all_sandwich = pd.DataFrame(all_records)

# ============================
# 2. Rimuovo outlier sulle vittime usando IQR
# ============================
df_victims = df_all_sandwich[df_all_sandwich["role"] == "victim"].copy()

Q1 = df_victims["priority_fee"].quantile(0.25)
Q3 = df_victims["priority_fee"].quantile(0.75)
IQR = Q3 - Q1

lower_bound = Q1 - 1.5 * IQR
upper_bound = Q3 + 1.5 * IQR

df_victims_no_outlier = df_victims[
    (df_victims["priority_fee"] >= lower_bound) &
    (df_victims["priority_fee"] <= upper_bound)
]

# Sostituisco le vittime filtrate nel DataFrame completo
df_all_sandwich_filtered = pd.concat([
    df_all_sandwich[df_all_sandwich["role"] != "victim"],
    df_victims_no_outlier
])

# ============================
# 3. Describe statistiche
# ============================
print("\n📊 Priority Fee - Tutto Sandwich Data (vittime senza outlier)")
print(df_all_sandwich_filtered["priority_fee"].describe())

print("\n📊 Priority Fee per ruolo - Tutto Sandwich Data (vittime senza outlier)")
print(df_all_sandwich_filtered.groupby("role")["priority_fee"].describe())

print("\n📊 Priority Fee - Solo Matchati")
print(df_matches["priority_fee"].describe())

print("\n📊 Priority Fee per ruolo - Solo Matchati")
print(df_matches.groupby("role")["priority_fee"].describe())

# ============================
# 4. Victim che arbitra
# ============================
pulite = {v.split(":", 1)[-1].strip() for v in unique_victim}
victim_as_bot = pulite.intersection(unique_bots)

df_overlap = df_matches[df_matches["name"].isin(victim_as_bot)]

if not df_overlap.empty:
    print("\n📊 Statistiche per Victim che arbitra (overlap):")
    print(df_overlap.groupby("role")["priority_fee"].describe())
    print("\nTop Token usati dagli overlap:")
    print(df_overlap["token_start"].value_counts().head(10))

# ============================
# 5. Boxplot comparativi
# ============================
fig, axes = plt.subplots(1, 2, figsize=(14,6), sharey=True)

df_all_sandwich_filtered.boxplot(column="priority_fee", by="role", ax=axes[0])
axes[0].set_title("Priority Fee per ruolo - Tutto Sandwich Data (vittime senza outlier)")
axes[0].set_ylabel("Priority Fee")
axes[0].set_xlabel("Role")

df_matches.boxplot(column="priority_fee", by="role", ax=axes[1])
axes[1].set_title("Priority Fee per ruolo - Solo Matchati")
axes[1].set_xlabel("Role")

plt.suptitle("")
plt.tight_layout()
plt.show()
