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
    """Extract all sandwich events with their slot, epoch, block_time."""
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
    print(f"Sandwich events con slot: {len(df)}")
    print(f"   Unique slots: {df['slot'].nunique()}")
    print(f"   Epochs: {sorted(df['epoch'].dropna().unique().astype(int).tolist())}")
    return df


# =========================
# CSV RESUME LOGIC
# =========================
def load_already_resolved(output_path: str) -> set[int]:
    """
    Legge il CSV di output (se esiste) e restituisce i slot già risolti.
    Usato per skippare le chiamate già fatte al riavvio.
    """
    p = Path(output_path)
    if not p.exists():
        return set()
    df = pd.read_csv(p, usecols=["slot"])
    resolved = set(df["slot"].dropna().astype(int).tolist())
    print(f"♻️  CSV esistente trovato: {len(resolved)} slot già salvati, riprendo da lì...")
    return resolved


def append_batch_to_csv(rows: list[dict], output_path: str) -> None:
    """
    Appende un batch di righe al CSV di output.
    Scrive l'header solo se il file non esiste ancora.
    """
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
    """
    Chiama getBlock per uno slot e restituisce (slot, vote_account_leader).
    Il leader è nel campo rewards con rewardType == "Fee".
    """
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
                    "transactionDetails": "none",   # non ci servono le tx
                    "rewards": True,                 # solo i reward (leader qui)
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
                        # 429 rate limit — aspetta e riprova
                        if code == 429 or "rate" in str(err).lower():
                            wait = 2 ** attempt
                            print(f"  ⚠️  Rate limit su slot {slot}, aspetto {wait}s...")
                            await asyncio.sleep(wait)
                            continue
                        # Slot skippato dalla chain (normale per alcuni slot)
                        if code in (-32009, -32004):
                            return slot, None
                        print(f"  RPC error slot {slot}: {err}")
                        return slot, None

                    result = data.get("result")
                    if not result:
                        return slot, None

                    # Il leader è nei rewards con rewardType "Fee"
                    for reward in result.get("rewards", []):
                        if reward.get("rewardType") == "Fee":
                            return slot, reward.get("pubkey")

                    return slot, None

            except asyncio.TimeoutError:
                print(f"  ⏱️  Timeout slot {slot}, tentativo {attempt+1}/3")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"  ❌ Errore slot {slot}: {e}")
                return slot, None

        return slot, None



async def rate_limiter_producer(queue: asyncio.Queue, rate: int) -> None:
    """Rilascia `rate` token al secondo nel queue per il rate limiting."""
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
    # Slot unici da risolvere (esclusi quelli già nel CSV)
    unique_slots = [
        s for s in df_all["slot"].unique().tolist()
        if s not in already_resolved
    ]
    total = len(unique_slots)

    print(f"\n🌐 Slots da risolvere: {total} (già risolti: {len(already_resolved)})")

    if total == 0:
        print("✅ Tutti gli slot già risolti!")
        return

    eta_hours = total / RATE_LIMIT / 3600
    print(f"⏱️  Tempo stimato: {eta_hours:.1f} ore a {RATE_LIMIT} req/s")
    print(f"   Ctrl+C per interrompere — i progressi vengono salvati ogni {BATCH_SIZE} slot\n")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    rate_queue: asyncio.Queue = asyncio.Queue(maxsize=RATE_LIMIT * 2)

    # Mappa slot → lista di sandwich rows (per arricchire il CSV con sandwich_id, epoch, ecc.)
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
            batch_slots = unique_slots[i : i + BATCH_SIZE]

            tasks = [
                get_block_leader(session, slot, semaphore, rate_queue)
                for slot in batch_slots
            ]
            results = await asyncio.gather(*tasks)

            # Costruisci le righe da appendere al CSV
            rows_to_save = []
            for slot, leader in results:
                done += 1
                if leader:
                    found += 1
                    # Una riga per ogni sandwich in questo slot
                    for row in slot_to_rows.get(slot, [{"slot": slot}]):
                        rows_to_save.append({**row, "vote_account": leader})
                else:
                    # Salviamo anche slot senza leader (vote_account vuoto)
                    # così al resume vengono skippati e non richiesti di nuovo
                    for row in slot_to_rows.get(slot, [{"slot": slot}]):
                        rows_to_save.append({**row, "vote_account": None})

            # Appende subito al CSV — dati al sicuro dopo ogni batch
            append_batch_to_csv(rows_to_save, output_path)

            # Pausa tra batch per evitare burst
            await asyncio.sleep(0.5)

            pct = done / total * 100
            print(
                f"  [{pct:.1f}%] {done}/{total} slots | "
                f"leader trovati: {found} | "
                f"righe salvate nel CSV: {found}"
            )

        producer_task.cancel()

    print(f"\n✅ Completato! {found}/{total} slot risolti → {output_path}")


# =========================
# ENTRY POINT
# =========================
def main() -> None:
    # Carica tutti i sandwich dal JSONL
    df = load_sandwich_slots(SANDWICHES_JSONL)

    # Filtra solo le epoche di interesse
    df = df[df["epoch"].between(814, 848)].copy()
    print(f"   Dopo filtro epoche 814-848: {len(df)} eventi, {df['slot'].nunique()} slot unici")

    # Leggi il CSV di output per sapere cosa skippare
    already_resolved = load_already_resolved(OUTPUT_SLOT_MAP)

    # Risolvi i restanti
    asyncio.run(resolve_all(df, already_resolved, OUTPUT_SLOT_MAP))

    # Stampa top validatori dal CSV finale
    print("\n🏆 TOP VALIDATORI PER NUMERO DI SANDWICH (dal CSV):")
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
        print("\n\n⏸️  Interrotto!")
        print(f"   I progressi sono salvati in {OUTPUT_SLOT_MAP}")
        print("   Riesegui lo script per riprendere da dove hai lasciato.")