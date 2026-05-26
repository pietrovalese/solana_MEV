import json
import logging
import os
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# --- Configuration ---

STARTING_BLOCK = 349_354_252
ENDING_BLOCK   = 350_610_119
NUM_BLOCKS     = 1
MAX_GAP        = 10          
MIN_PROFIT     = None        
OUTPUT_DIR     = Path("output")
RESULTS_FILE   = OUTPUT_DIR / "results.jsonl"

# --- Logging ---

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# --- Helpers ---

def gen_block_list(n: int = NUM_BLOCKS) -> list[int]:
    """Generates a list of n random slot numbers within the configured range.
    Returns a list of integers."""
    return [random.randint(STARTING_BLOCK, ENDING_BLOCK) for _ in range(n)]


def append_sandwiches(results_path: Path, slot: int, sandwiches: list[dict]) -> int:
    """Appends each sandwich as a JSONL line, enriched with slot and detection timestamp.
    Returns the number of lines written."""
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
    """Runs a subprocess, logs stdout/stderr, and returns the result.
    Returns None on timeout or unexpected error."""
    log.debug("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        log.error("[%s] Timeout expired.", label)
        return None
    except Exception as e:
        log.error("[%s] Unexpected error: %s", label, e)
        return None

    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            log.debug("[%s stdout] %s", label, line)
    if result.stderr.strip():
        for line in result.stderr.strip().splitlines():
            log.warning("[%s stderr] %s", label, line)

    if result.returncode != 0:
        log.error("[%s] Exited with code %d.", label, result.returncode)
        return None

    return result


# --- Single-slot pipeline ---

def process_slot(slot: int, results_path: Path) -> bool:
    """Downloads the block and runs sandwich detection for a single slot.
    Returns True if detection completed successfully, False otherwise."""
    log.info("-- Slot %d --", slot)

    # Temporary file for the block (avoids collisions between parallel runs
    # and prevents reading a stale block on failure)
    with tempfile.NamedTemporaryFile(
        dir=OUTPUT_DIR, suffix=".json", delete=False, prefix=f"block_{slot}_"
    ) as tmp:
        block_path = Path(tmp.name)

    try:
        # Step 1: download
        log.info("  [1/2] Downloading block...")
        dl = run_subprocess(
            ["python3", "download_block.py", str(slot), "--output", str(block_path)],
            label=f"download:{slot}",
        )
        if dl is None:
            log.error("  Download failed for slot %d, skipping.", slot)
            return False

        if not block_path.exists() or block_path.stat().st_size == 0:
            log.error("  Block file missing or empty for slot %d, skipping.", slot)
            return False

        # Step 2: detection
        log.info("  [2/2] Detecting sandwiches...")

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
            log.error("  Detection failed for slot %d, skipping.", slot)
            return False

        # Step 3: append JSONL
        sandwiches: list[dict] = []
        if sw_path.exists() and sw_path.stat().st_size > 0:
            try:
                with sw_path.open("r", encoding="utf-8") as f:
                    sandwiches = json.load(f)
            except json.JSONDecodeError as e:
                log.error("  Invalid results JSON for slot %d: %s", slot, e)

        written = append_sandwiches(results_path, slot, sandwiches)
        if written:
            log.info("  %d sandwich(es) written to %s", written, results_path)
        else:
            log.info("  No sandwiches detected for slot %d.", slot)

        return True

    finally:
        # Clean up temporary files
        for p in [block_path, sw_path if "sw_path" in dir() else None]:
            if p and p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass


# --- Main ---

def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    block_list = gen_block_list()
    block_list.append(350605114)
    log.info("Selected slots: %s", block_list)
    log.info("Results -> %s (append JSONL)", RESULTS_FILE)

    ok = 0
    failed = 0

    for slot in block_list:
        try:
            success = process_slot(slot, RESULTS_FILE)
        except Exception as e:
            log.exception("  Unexpected error for slot %d: %s", slot, e)
            success = False

        if success:
            ok += 1
        else:
            failed += 1

    log.info("-- Done --  OK: %d  |  Failed: %d  |  Total: %d", ok, failed, ok + failed)

    # Count total sandwiches in the output file
    if RESULTS_FILE.exists():
        total_lines = sum(1 for _ in RESULTS_FILE.open(encoding="utf-8"))
        log.info("Total sandwiches in %s: %d", RESULTS_FILE, total_lines)


if __name__ == "__main__":
    main()