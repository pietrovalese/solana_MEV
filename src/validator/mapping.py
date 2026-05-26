import pandas as pd
import json

df1 = pd.read_csv("validators_aggregated.csv").head(10)
df2 = pd.read_csv("slot_to_validator.csv")


def parse_ids(x):
    """Parses a "{id1,id2,...}" string into a list of stripped ID strings.
    Returns an empty list if the input is blank."""
    x = x.strip("{}")
    return [i.strip() for i in x.split(",")]


df1["validator_id"] = df1["all_validator_ids"].apply(parse_ids)
df1_exploded = df1.explode("validator_id")

merged = df1_exploded.merge(
    df2,
    left_on="validator_id",
    right_on="vote_account",
    how="left"
)

result = merged.groupby("vote_account_x").agg({"sandwich_id": list}).reset_index()
result = result.rename(columns={"vote_account_x": "main_vote_account"})

# --- NEW SECTION: JSONL parsing ---
validator_map = dict(zip(result["main_vote_account"], result["sandwich_id"]))
reverse_map = {}
for validator, ids in validator_map.items():
    for sid in ids:
        if pd.notna(sid):
            reverse_map[sid] = validator

rows = []

with open("dataset/sandwiches_annotated.jsonl", "r") as f:
    for line in f:
        data = json.loads(line)
        sid = data.get("Id")
        if sid not in reverse_map:
            continue

        validator = reverse_map[sid]
        bot1 = data.get("bot1", {})
        bot2 = data.get("bot2", {})

        # Extract bot names and pubkeys
        bot1_name = bot1.get("bot")
        bot2_name = bot2.get("bot")
        bot1_details = bot1.get("Details") or {}
        bot2_details = bot2.get("Details") or {}

        bot1_signer = bot1_details.get("signer") or {}
        bot2_signer = bot2_details.get("signer") or {}

        bot1_pubkey = bot1_signer.get("pubkey")
        bot2_pubkey = bot2_signer.get("pubkey")

        def parse_float(x):
            """Converts a value to float, stripping thousand separators if needed.
            Returns 0.0 on None or conversion failure."""
            if x is None:
                return 0.0
            if isinstance(x, str):
                x = x.replace(",", "") 
            try:
                return float(x)
            except:
                return 0.0

        bot1_token_start = bot1.get("token_start")

        if bot1_token_start != "sol":
            continue

        bot1_value_start = parse_float(bot1.get("value_start"))
        bot2_value_end = parse_float(bot2.get("value_end"))

        bot1_fee_total = (bot1_details.get("fee") or {}).get("total_fee", 0) / 10 ** 9
        bot2_fee_total = (bot2_details.get("fee") or {}).get("total_fee", 0) / 10 ** 9

        sandwich_revenue = (bot2_value_end - bot1_value_start) - (bot1_fee_total + bot2_fee_total)

        if sandwich_revenue > 100:
            continue

        # Collect victim signer pubkeys
        signer_pubkeys = []
        for v in data.get("victims", []):
            details = v.get("Details") or {}
            signer = details.get("signer") or {}
            pubkey = signer.get("pubkey")
            if pubkey:
                signer_pubkeys.append(pubkey)

        # Fees and slots
        bot1_fee = bot1.get("Details", {}).get("fee", {}).get("priority_fee", 0)
        bot2_fee = bot2.get("Details", {}).get("fee", {}).get("priority_fee", 0)
        bot1_slot = bot1.get("Details", {}).get("slot")
        bot2_slot = bot2.get("Details", {}).get("slot")

        rows.append({
            "validator": validator,
            "sandwich_id": sid,
            "token_end": bot1.get("token_end"),
            "bot1_name": bot1_name,
            "bot2_name": bot2_name,
            "bot1_pubkey": bot1_pubkey,
            "bot2_pubkey": bot2_pubkey,
            "bot1_priority_fee": bot1_fee,
            "bot2_priority_fee": bot2_fee,
            "bot1_slot": bot1_slot,
            "bot2_slot": bot2_slot,
            "signer_pubkeys": signer_pubkeys,
            "sandwich_revenue": sandwich_revenue,
        })

df_final = pd.DataFrame(rows)

# --- Jito-like detection ---
df_final["same_slot"] = df_final["bot1_slot"] == df_final["bot2_slot"]
FEE_THRESHOLD = 5000
df_final["jito_like"] = (
    df_final["same_slot"] &
    (df_final["bot1_priority_fee"] < FEE_THRESHOLD) &
    (df_final["bot2_priority_fee"] < FEE_THRESHOLD)
)

jito_stats = df_final.groupby("validator").agg(
    total_sandwich=("sandwich_id", "count"),
    jito_like_count=("jito_like", "sum")
).reset_index()
jito_stats["jito_percent"] = 100 * jito_stats["jito_like_count"] / jito_stats["total_sandwich"]

def concentration(df, col_name):
    """Computes the relative frequency of each value in a column.
    Returns a dict mapping each value to its share of the total."""
    counts = df[col_name].value_counts()
    total = counts.sum()
    return {k: v / total for k, v in counts.items()} if total > 0 else {}


def concentration_numeric(df, col_name):
    """Computes a Herfindahl-like concentration index as the sum of squared frequencies.
    Returns a value between 0 (fully dispersed) and 1 (fully concentrated)."""
    counts = df[col_name].value_counts()
    total = counts.sum()
    if total == 0:
        return 0
    freqs = counts / total
    return (freqs ** 2).sum()


bot1_conc = (
    df_final.groupby("validator", group_keys=False, observed=True)
    .apply(lambda x: concentration_numeric(x, "bot1_name"))
    .reset_index()
    .rename(columns={0: "bot1_concentration"})
)

bot2_conc = (
    df_final.groupby("validator", group_keys=False, observed=True)
    .apply(lambda x: concentration_numeric(x, "bot2_name"))
    .reset_index()
    .rename(columns={0: "bot2_concentration"})
)

signer_conc = (
    df_final.explode("signer_pubkeys")
    .groupby("validator", group_keys=False, observed=True)
    .apply(lambda x: concentration_numeric(x, "signer_pubkeys"))
    .reset_index()
    .rename(columns={0: "signer_concentration"})
)

# --- Main aggregation ---
agg_df = df_final.groupby("validator").agg(
    num_sandwich=("sandwich_id", "count"),
    unique_tokens=("token_end", lambda x: list(set(x))),
    total_revenue=("sandwich_revenue", "sum"),
    avg_revenue=("sandwich_revenue", "mean"),
    max_revenue=("sandwich_revenue", "max"),
    bot1_fee_mean=("bot1_priority_fee", "mean"),
    bot1_fee_sum=("bot1_priority_fee", "sum"),
    bot1_fee_max=("bot1_priority_fee", "max"),
    bot2_fee_mean=("bot2_priority_fee", "mean"),
    bot2_fee_sum=("bot2_priority_fee", "sum"),
    bot2_fee_max=("bot2_priority_fee", "max")
).reset_index()

# --- Memecoin percentage ---
memecoin_df = pd.read_csv("dataset/memecoin.csv")
memecoin_tokens = set(memecoin_df["Nome"].str.lower().dropna())


def memecoin_percentage(token_list):
    """Computes the percentage of tokens in the list that are classified as memecoins.
    Returns 0 if the list is empty."""
    if not token_list:
        return 0
    memecoin_count = sum(1 for t in token_list if str(t).lower() in memecoin_tokens)
    return 100 * memecoin_count / len(token_list)


agg_df["memecoin_percent"] = agg_df["unique_tokens"].apply(memecoin_percentage)
agg_df = agg_df.drop(columns=["unique_tokens"])

# --- Merge all metrics ---
agg_df = agg_df.merge(jito_stats[["validator", "jito_percent"]], on="validator", how="left")
agg_df = agg_df.merge(bot1_conc, on="validator", how="left")
agg_df = agg_df.merge(bot2_conc, on="validator", how="left")
agg_df = agg_df.merge(signer_conc, on="validator", how="left")

agg_df = agg_df.sort_values("num_sandwich", ascending=False)
agg_df.to_csv("validator_aggregated_metrics.csv", index=False)

# --- Print highest-revenue sandwich per validator ---
idx = df_final.groupby("validator")["sandwich_revenue"].idxmax()

max_revenue_df = df_final.loc[idx, ["validator", "sandwich_id", "sandwich_revenue"]]

print("\n=== Max revenue sandwich per validator ===")
for _, row in max_revenue_df.iterrows():
    print(f"Validator: {row['validator']}")
    print(f"  Sandwich ID: {row['sandwich_id']}")
    print(f"  Revenue: {row['sandwich_revenue']}")
    print("-" * 50)

print(agg_df)