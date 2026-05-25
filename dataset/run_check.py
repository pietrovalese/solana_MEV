#!/usr/bin/env python3
"""
Orchestratore: genera slot casuali, scarica i blocchi e rileva sandwich attack.
I risultati vengono accumulati in append su output/results.jsonl
(un oggetto JSON per riga, un oggetto per ogni sandwich trovato).
"""

import json
import logging
import os
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ─── Configurazione ───────────────────────────────────────────────────────────

STARTING_BLOCK = 349_354_252
ENDING_BLOCK   = 350_610_119
NUM_BLOCKS     = 1
MAX_GAP        = 10          # passato a sandwich_detector
MIN_PROFIT     = None        # es. 0.001 per filtrare; None = nessun filtro

OUTPUT_DIR     = Path("output")
RESULTS_FILE   = OUTPUT_DIR / "results.jsonl"

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def gen_block_list(n: int = NUM_BLOCKS) -> list[int]:
    return [random.randint(STARTING_BLOCK, ENDING_BLOCK) for _ in range(n)]


def append_sandwiches(results_path: Path, slot: int, sandwiches: list[dict]) -> int:
    """
    Aggiunge in append ogni sandwich come riga JSONL.
    Arricchisce ogni record con slot e timestamp di rilevamento.
    Restituisce il numero di righe scritte.
    """
    if not sandwiches:
        return 0
    now = datetime.now(tz=timezone.utc).isoformat()
    written = 0
    with results_path.open("a", encoding="utf-8") as f:
        for s in sandwiches:
            record = {"detected_at": now, "slot": slot, **s}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1
    return written


def run_subprocess(cmd: list[str], label: str) -> subprocess.CompletedProcess | None:
    """
    Esegue un sottoprocesso, logga stdout/stderr e restituisce il risultato.
    In caso di errore restituisce None.
    """
    log.debug("Eseguo: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        log.error("[%s] Timeout scaduto.", label)
        return None
    except Exception as e:
        log.error("[%s] Errore inatteso: %s", label, e)
        return None

    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            log.debug("[%s stdout] %s", label, line)
    if result.stderr.strip():
        for line in result.stderr.strip().splitlines():
            log.warning("[%s stderr] %s", label, line)

    if result.returncode != 0:
        log.error("[%s] Uscito con codice %d.", label, result.returncode)
        return None

    return result


# ─── Pipeline per singolo slot ────────────────────────────────────────────────

def process_slot(slot: int, results_path: Path) -> bool:
    """
    Scarica il blocco e rileva sandwich per un singolo slot.
    Restituisce True se almeno la detection è andata a buon fine.
    """
    log.info("━━ Slot %d ━━", slot)

    # File temporaneo per il blocco (evita collisioni tra esecuzioni parallele
    # e non rischia di leggere un blocco vecchio in caso di fallimento)
    with tempfile.NamedTemporaryFile(
        dir=OUTPUT_DIR, suffix=".json", delete=False, prefix=f"block_{slot}_"
    ) as tmp:
        block_path = Path(tmp.name)

    try:
        # ── Step 1: download ─────────────────────────────────────────────────
        log.info("  [1/2] Scaricamento blocco…")
        dl = run_subprocess(
            ["python3", "download_block.py", str(slot), "--output", str(block_path)],
            label=f"download:{slot}",
        )
        if dl is None:
            log.error("  Scaricamento fallito per slot %d, salto.", slot)
            return False

        if not block_path.exists() or block_path.stat().st_size == 0:
            log.error("  File blocco assente o vuoto per slot %d, salto.", slot)
            return False

        # ── Step 2: detection ────────────────────────────────────────────────
        log.info("  [2/2] Rilevamento sandwich…")

        with tempfile.NamedTemporaryFile(
            dir=OUTPUT_DIR, suffix=".json", delete=False, prefix=f"sw_{slot}_"
        ) as tmp2:
            sw_path = Path(tmp2.name)

        detect_cmd = [
            "python3", "sandwich_detector.py", str(block_path),
            "--output-json", str(sw_path),
            "--max-gap", str(MAX_GAP),
        ]
        if MIN_PROFIT is not None:
            detect_cmd += ["--min-profit", str(MIN_PROFIT)]

        det = run_subprocess(detect_cmd, label=f"detect:{slot}")
        if det is None:
            log.error("  Detection fallita per slot %d, salto.", slot)
            return False

        # ── Step 3: append JSONL ─────────────────────────────────────────────
        sandwiches: list[dict] = []
        if sw_path.exists() and sw_path.stat().st_size > 0:
            try:
                with sw_path.open("r", encoding="utf-8") as f:
                    sandwiches = json.load(f)
            except json.JSONDecodeError as e:
                log.error("  JSON risultati non valido per slot %d: %s", slot, e)

        written = append_sandwiches(results_path, slot, sandwiches)
        if written:
            log.info("  ✓ %d sandwich scritti in %s", written, results_path)
        else:
            log.info("  Nessun sandwich rilevato per slot %d.", slot)

        return True

    finally:
        # Pulizia file temporanei
        for p in [block_path, sw_path if "sw_path" in dir() else None]:
            if p and p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    block_list = gen_block_list()
    block_list.append(350605114)
    log.info("Slot selezionati: %s", block_list)
    log.info("Risultati → %s (append JSONL)", RESULTS_FILE)

    ok = 0
    failed = 0

    for slot in block_list:
        try:
            success = process_slot(slot, RESULTS_FILE)
        except Exception as e:
            log.exception("  Errore imprevisto per slot %d: %s", slot, e)
            success = False

        if success:
            ok += 1
        else:
            failed += 1

    log.info("━━ Fine ━━  OK: %d  |  Falliti: %d  |  Totale: %d", ok, failed, ok + failed)

    # Conta totale sandwich nel file
    if RESULTS_FILE.exists():
        total_lines = sum(1 for _ in RESULTS_FILE.open(encoding="utf-8"))
        log.info("Sandwich totali in %s: %d", RESULTS_FILE, total_lines)


if __name__ == "__main__":
    main()