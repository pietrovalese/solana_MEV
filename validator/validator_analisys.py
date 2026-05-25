import pandas as pd

# =========================
# CONFIG
# =========================
CSV_EPOCH_831 = "epoch_831.csv"
CSV_EPOCH_846 = "epoch_846.csv"
OUTPUT_CSV = "validators_aggregated.csv"

EPOCHS_IN_60D = 30  # ~60 giorni / 2 giorni per epoca


# =========================
# FUNCTIONS
# =========================
def parse_ids(id_string: str) -> set:
    """
    Convert "{id1,id2,...}" → set(ids)
    """
    if pd.isna(id_string):
        return set()

    # Rimuove graffe {}
    cleaned = id_string.strip("{}")

    if not cleaned:
        return set()

    return set(x.strip() for x in cleaned.split(","))

def round_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Round metrics for readability.
    """
    df["blocks_1e"] = df["blocks_1e"].round(0)  # 1 cifra
    df["sandwich_blocks_1e"] = df["sandwich_blocks_1e"].round(0)  # 1 cifra
    df["sandwich_rate_1e"] = df["sandwich_rate_1e"].round(4)  # 4 decimali ≈ 0.01%
    df["SII"] = df["SII"].round(2)
    df["avg_stake"] = df["avg_stake"].round(2)
    return df

def load_and_prepare(csv_path: str, epoch_label: str) -> pd.DataFrame:
    """
    Load a CSV and rename columns with epoch suffix.
    """
    cols = [
        "validator_name",
        "vote_account",
         "validator_ids", 
        "30d_blocks_produced",
        "30d_blocks_with_sandwiches",
        "total_stake",
    ]

    df = pd.read_csv(csv_path)[cols].copy()

    df = df.rename(
        columns={
            "30d_blocks_produced": f"blocks_{epoch_label}",
            "validator_ids": f"validator_ids_{epoch_label}",
            "30d_blocks_with_sandwiches": f"sandwich_blocks_{epoch_label}",
            "total_stake": f"stake_{epoch_label}",
        }
    )

    return df


def aggregate_epochs(df_831: pd.DataFrame, df_846: pd.DataFrame) -> pd.DataFrame:
    """
    Merge the two epochs and aggregate metrics over ~60 days.
    """
    df = pd.merge(
        df_831,
        df_846,
        on="vote_account",
        how="inner",
        suffixes=("_831", "_846"),
    )
    
    # Merge validator IDs
    df["all_validator_ids"] = df.apply(
        lambda row: parse_ids(row["validator_ids_831"]) |
                    parse_ids(row["validator_ids_846"]),
        axis=1
    )
    df["all_validator_ids"] = df["all_validator_ids"].apply(
    lambda s: "{" + ",".join(sorted(s)) + "}"
    )

    # Aggregate over ~60 days
    df["blocks_60d"] = df["blocks_831"] + df["blocks_846"]
    df["sandwich_blocks_60d"] = (
        df["sandwich_blocks_831"] + df["sandwich_blocks_846"]
    )

    df["sandwich_rate_60d"] = (
        df["sandwich_blocks_60d"] / df["blocks_60d"]
    ).fillna(0)

    df["avg_stake"] = (df["stake_831"] + df["stake_846"]) / 2

    return df


def rescale_to_epoch(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rescale absolute metrics to 1 epoch (~2 days).
    """
    df["blocks_1e"] = df["blocks_60d"] / EPOCHS_IN_60D
    df["sandwich_blocks_1e"] = df["sandwich_blocks_60d"] / EPOCHS_IN_60D

    # Rate does NOT change
    df["sandwich_rate_1e"] = df["sandwich_rate_60d"]

    return df


def compute_sii(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute Sandwich Impact Index (SII).
    """
    max_sandwich_blocks = df["sandwich_blocks_60d"].max()

    df["SII"] = (
        df["sandwich_blocks_60d"] / max_sandwich_blocks
    ).fillna(0)

    return df


def print_top10(df: pd.DataFrame) -> None:
    """
    Print Top 10 validators by SII.
    """
    top10 = df.sort_values(by="SII", ascending=False).head(10)

    print("\n🚨 TOP 10 VALIDATORS BY SANDWICH IMPACT (PER EPOCA)\n")
    print(
        top10[
            [
                "validator_name_831",
                "vote_account",
                "blocks_1e",
                "sandwich_blocks_1e",
                "sandwich_rate_1e",
                "SII",
            ]
        ]
    )


# =========================
# MAIN
# =========================
def main() -> None:
    # Load data
    df_831 = load_and_prepare(CSV_EPOCH_831, "831")
    df_846 = load_and_prepare(CSV_EPOCH_846, "846")

    # Aggregate
    df = aggregate_epochs(df_831, df_846)

    # Rescale to 1 epoch
    df = rescale_to_epoch(df)

    # Compute SII
    df = compute_sii(df)

    # Sort by impact
    df = df.sort_values(
        by=["sandwich_blocks_60d", "sandwich_rate_60d"],
        ascending=False,
    )

    # Save final CSV
    final_cols = [
        "validator_name_831",
        "vote_account",
        "all_validator_ids",
        "blocks_1e",
        "sandwich_blocks_1e",
        "sandwich_rate_1e",
        "SII",
        "avg_stake",
    ]

    df[final_cols].to_csv(OUTPUT_CSV, index=False)
    print(f"✅ File generato: {OUTPUT_CSV}")

    # Print Top 10
    print_top10(round_metrics(df))
    
    # Totale sandwich blocks su tutta la rete
    network_sandwich_blocks = df["sandwich_blocks_60d"].sum()
    network_blocks = df["blocks_60d"].sum()

    # Media sandwich rate su tutta la rete (pesata per numero di blocchi prodotti)
    network_sandwich_rate = (
        df["sandwich_blocks_60d"].sum() / df["blocks_60d"].sum()
    )
    print("\n🌐 NETWORK SUMMARY:")
    print(f"Totale blocchi: {network_blocks:.0f}")
    print(f"Totale blocchi sandwichati: {network_sandwich_blocks:.0f}")
    print(f"Sandwich rate medio rete: {network_sandwich_rate*100:.4f}")
    
    # --- Calcolo sandwich rate separati per epoca ---
    df["sandwich_rate_831"] = (
        df["sandwich_blocks_831"] / df["blocks_831"]
    ).fillna(0)
    
    df["sandwich_rate_846"] = (
        df["sandwich_blocks_846"] / df["blocks_846"]
    ).fillna(0)
    
    # Stampare il sandwich rate medio per epoca
    print(f"Sandwich rate medio prima: {df['sandwich_rate_831'].mean() * 100:.4f}%")
    print(f"Sandwich rate medio dopo: {df['sandwich_rate_846'].mean() * 100:.4f}%")




if __name__ == "__main__":
    main()
