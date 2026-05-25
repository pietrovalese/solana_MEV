import json
import asyncio
import aiohttp
import pandas as pd
from pathlib import Path

# =========================
# CONFIG
# =========================
RPC_ENDPOINT = "https://mainnet.helius-rpc.com/?api-key=API_KEY"

SANDWICHES_JSONL = "dataset/sandwiches_annotated.jsonl"
OUTPUT_SLOT_MAP = "slot_to_validator.csv"

RATE_LIMIT = 5
CONCURRENCY = 3
BATCH_SIZE = 100

# =========================
# LOAD SANDWICH SLOTS FROM JSONL
# =========================
def load_sandwich_slots(jsonl_path: str) -> pd.DataFrame:
    """Parses the annotated JSONL file and extracts sandwich events with slot, epoch, and block_time.
    Returns a DataFrame with one row per sandwich event that has a valid slot."""
    records = []
    with open(jsonl_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            bot1 = obj.get("bot1") or {}
            details = bot1.get("Details") or {}
            slot = details.get("slot")
            epoch = details.get("epoch")
            block_time = details.get("blockTime")
            if slot is not None:
                records.append({
                    "sandwich_id": obj.get("Id"),
                    "slot": int(slot),
                    "epoch": epoch,
                    "block_time": block_time,
                })

    df = pd.DataFrame(records)
    print(f"Sandwich events with slot: {len(df)}")
    print(f"   Unique slots: {df['slot'].nunique()}")
    print(f"   Epochs: {sorted(df['epoch'].dropna().unique().astype(int).tolist())}")
    return df


# =========================
# CSV RESUME
# =========================
def load_already_resolved(output_path: str) -> set[int]:
    """Reads the output CSV (if it exists) and returns the set of already-resolved slots.
    Used to skip RPC calls on restart and resume progress."""
    p = Path(output_path)
    if not p.exists():
        return set()
    df = pd.read_csv(p, usecols=["slot"])
    resolved = set(df["slot"].dropna().astype(int).tolist())
    print(f"Existing CSV found: {len(resolved)} slots already saved, resuming...")
    return resolved


def append_batch_to_csv(rows: list[dict], output_path: str) -> None:
    """Appends a batch of rows to the output CSV file.
    Writes the header only if the file does not exist yet."""
    if not rows:
        return
    p = Path(output_path)
    df_batch = pd.DataFrame(rows)
    df_batch.to_csv(output_path, mode="a", header=not p.exists(), index=False)


# =========================
# ASYNC RPC
# =========================
async def get_block_leader(
    session: aiohttp.ClientSession,
    slot: int,
    semaphore: asyncio.Semaphore,
    rate_limiter: asyncio.Queue,
) -> tuple[int, str | None]:
    """Calls getBlock for a given slot and returns (slot, leader_vote_account).
    The block leader is identified via the Fee-type reward entry."""
    async with semaphore:
        await rate_limiter.get()

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getBlock",
            "params": [
                slot,
                {
                    "encoding": "base64",
                    "transactionDetails": "none",   # transactions not needed
                    "rewards": True,                 # only rewards (leader is here)
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        }

        for attempt in range(3):
            try:
                async with session.post(
                    RPC_ENDPOINT,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    data = await resp.json()

                    if "error" in data:
                        err = data["error"]
                        code = err.get("code", 0)
                        # 429 rate limit — wait and retry
                        if code == 429 or "rate" in str(err).lower():
                            wait = 2 ** attempt
                            print(f"  Rate limit on slot {slot}, waiting {wait}s...")
                            await asyncio.sleep(wait)
                            continue
                        # Slot skipped by the chain (normal for some slots)
                        if code in (-32009, -32004):
                            return slot, None
                        print(f"  RPC error slot {slot}: {err}")
                        return slot, None

                    result = data.get("result")
                    if not result:
                        return slot, None

                    # The leader is in rewards with rewardType "Fee"
                    for reward in result.get("rewards", []):
                        if reward.get("rewardType") == "Fee":
                            return slot, reward.get("pubkey")

                    return slot, None

            except asyncio.TimeoutError:
                print(f"  Timeout slot {slot}, attempt {attempt + 1}/3")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"  Error slot {slot}: {e}")
                return slot, None

        return slot, None


async def rate_limiter_producer(queue: asyncio.Queue, rate: int) -> None:
    """Continuously releases `rate` tokens per second into the queue for rate limiting.
    Runs indefinitely until cancelled."""
    while True:
        for _ in range(rate):
            await queue.put(1)
        await asyncio.sleep(1.0)


# =========================
# MAIN ASYNC
# =========================
async def resolve_all(
    df_all: pd.DataFrame,
    already_resolved: set[int],
    output_path: str,
) -> None:
    """Resolves all unresolved slots by querying the RPC for the block leader.
    Saves results to CSV in batches; already-resolved slots are skipped."""
    # Unique slots to resolve (excluding those already in the CSV)
    unique_slots = [
        s for s in df_all["slot"].unique().tolist()
        if s not in already_resolved
    ]
    total = len(unique_slots)

    print(f"\nSlots to resolve: {total} (already resolved: {len(already_resolved)})")

    if total == 0:
        print("All slots already resolved.")
        return

    eta_hours = total / RATE_LIMIT / 3600
    print(f"Estimated time: {eta_hours:.1f} hours at {RATE_LIMIT} req/s")
    print(f"   Press Ctrl+C to stop — progress is saved every {BATCH_SIZE} slots\n")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    rate_queue: asyncio.Queue = asyncio.Queue(maxsize=RATE_LIMIT * 2)

    # Map slot -> list of sandwich rows (to enrich CSV with sandwich_id, epoch, etc.)
    slot_to_rows: dict[int, list[dict]] = {}
    unique_slots_set = set(unique_slots)
    for _, row in df_all[df_all["slot"].isin(unique_slots_set)].iterrows():
        s = int(row["slot"])
        slot_to_rows.setdefault(s, []).append(row.to_dict())

    async with aiohttp.ClientSession() as session:
        producer_task = asyncio.create_task(rate_limiter_producer(rate_queue, RATE_LIMIT))

        done = 0
        found = 0

        for i in range(0, total, BATCH_SIZE):
            batch_slots = unique_slots[i: i + BATCH_SIZE]

            tasks = [
                get_block_leader(session, slot, semaphore, rate_queue)
                for slot in batch_slots
            ]
            results = await asyncio.gather(*tasks)

            # Build rows to append to CSV
            rows_to_save = []
            for slot, leader in results:
                done += 1
                if leader:
                    found += 1
                    # One row per sandwich in this slot
                    for row in slot_to_rows.get(slot, [{"slot": slot}]):
                        rows_to_save.append({**row, "vote_account": leader})
                else:
                    # Save slots with no leader too (vote_account=None)
                    # so they are skipped on resume and not re-requested
                    for row in slot_to_rows.get(slot, [{"slot": slot}]):
                        rows_to_save.append({**row, "vote_account": None})

            # Append to CSV immediately — data is safe after each batch
            append_batch_to_csv(rows_to_save, output_path)

            # Short pause between batches to avoid bursts
            await asyncio.sleep(0.5)

            pct = done / total * 100
            print(
                f"  [{pct:.1f}%] {done}/{total} slots | "
                f"leaders found: {found} | "
                f"rows saved to CSV: {found}"
            )

        producer_task.cancel()

    print(f"\nDone! {found}/{total} slots resolved -> {output_path}")


# =========================
# ENTRY POINT
# =========================
def main() -> None:
    # Load all sandwiches from the JSONL file
    df = load_sandwich_slots(SANDWICHES_JSONL)

    # Filter only epochs of interest
    df = df[df["epoch"].between(814, 848)].copy()
    print(f"   After filtering epochs 814-848: {len(df)} events, {df['slot'].nunique()} unique slots")

    # Load already-resolved slots to skip
    already_resolved = load_already_resolved(OUTPUT_SLOT_MAP)

    # Resolve remaining slots
    asyncio.run(resolve_all(df, already_resolved, OUTPUT_SLOT_MAP))

    # Print top validators from the final CSV
    print("\nTOP VALIDATORS BY SANDWICH COUNT (from CSV):")
    df_out = pd.read_csv(OUTPUT_SLOT_MAP)
    top = (
        df_out[df_out["vote_account"].notna()]
        .groupby("vote_account")
        .agg(n_sandwiches=("sandwich_id", "count"))
        .sort_values("n_sandwiches", ascending=False)
        .head(15)
    )
    print(top.to_string())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        print(f"   Progress saved to {OUTPUT_SLOT_MAP}")
        print("   Re-run the script to resume from where you left off.")