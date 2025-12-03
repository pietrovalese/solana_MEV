import requests
import json
import logging
import time
from collections import defaultdict

# -------------------------
# CONFIGURAZIONE LOGGING
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# -------------------------
# CONFIGURAZIONE
# -------------------------
API_KEY = "7a49b0b5-1b22-4872-b13f-2e50d689778c"
HELIUS_RPC = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"
DELAY = 0.15  # secondi tra le richieste

INPUT_FILE = "creator_attackers.json"
OUTPUT_VERIFIED = "verified_attacks_complete.json"

# -------------------------
# FUNZIONE: Ottieni dettagli transazione
# -------------------------
def get_transaction_details(signature):
    """
    Recupera i dettagli completi di una transazione usando getTransaction.
    
    Args:
        signature: Hash della transazione
        
    Returns:
        dict: Dettagli della transazione o None se errore
    """
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "json",
                    "maxSupportedTransactionVersion": 0
                }
            ]
        }
        
        response = requests.post(HELIUS_RPC, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if "error" in result:
            logging.error(f"Errore RPC per {signature[:16]}...: {result['error']}")
            return None
        
        tx_data = result.get("result")
        return tx_data
        
    except Exception as e:
        logging.error(f"Errore nel recupero transazione {signature[:16]}...: {e}")
        return None

# -------------------------
# FUNZIONE: Estrai mint dai token transfers
# -------------------------
def extract_mints_from_transaction(tx_data):
    """
    Estrae tutti i mint address coinvolti nei token transfers di una transazione.
    
    Args:
        tx_data: Dati della transazione
        
    Returns:
        set: Set di mint addresses trovati
    """
    mints = set()
    
    if not tx_data:
        return mints
    
    try:
        # Controlla in meta.postTokenBalances e preTokenBalances
        meta = tx_data.get("meta", {})
        
        # Post token balances
        post_balances = meta.get("postTokenBalances", [])
        for balance in post_balances:
            mint = balance.get("mint")
            if mint:
                mints.add(mint)
        
        # Pre token balances
        pre_balances = meta.get("preTokenBalances", [])
        for balance in pre_balances:
            mint = balance.get("mint")
            if mint:
                mints.add(mint)
        
        # Controlla anche in innerInstructions per essere sicuri
        inner_instructions = meta.get("innerInstructions", [])
        for inner in inner_instructions:
            instructions = inner.get("instructions", [])
            for instruction in instructions:
                # Se è un token program instruction, potrebbe avere parsed info
                if "parsed" in instruction:
                    parsed = instruction.get("parsed", {})
                    info = parsed.get("info", {})
                    if "mint" in info:
                        mints.add(info["mint"])
        
    except Exception as e:
        logging.error(f"Errore nell'estrazione mint: {e}")
    
    return mints

# -------------------------
# FUNZIONE: Verifica singolo attacco
# -------------------------
def verify_single_attack(match):
    """
    Verifica un singolo attacco controllando se il mint appare nelle transazioni bot1/bot2.
    
    Args:
        match: Dizionario con i dati dell'attacco
        
    Returns:
        dict: Match aggiornato con verification dettagliata
    """
    mint = match["memecoin"]["mint"]
    bot1_hash = match.get("bot1_transaction_hash")
    bot2_hash = match.get("bot2_transaction_hash")
    
    logging.info(f"\nVerifica attacco su {match['memecoin']['ticker']} ({mint[:16]}...)")
    logging.info(f"  Sandwich ID: {match['sandwich_id']}")
    
    verification = {
        "bot1_contains_mint": False,
        "bot2_contains_mint": False,
        "bot1_mints_found": [],
        "bot2_mints_found": [],
        "verified": False,
        "verification_method": "transaction_analysis"
    }
    
    # Verifica Bot1
    if bot1_hash:
        logging.info(f"  Analizzando Bot1 TX: {bot1_hash[:16]}...")
        time.sleep(DELAY)
        
        bot1_tx = get_transaction_details(bot1_hash)
        if bot1_tx:
            bot1_mints = extract_mints_from_transaction(bot1_tx)
            verification["bot1_mints_found"] = list(bot1_mints)
            verification["bot1_contains_mint"] = mint in bot1_mints
            
            if verification["bot1_contains_mint"]:
                logging.info(f"    ✓ Mint TROVATO in Bot1!")
            else:
                logging.info(f"    ✗ Mint NON trovato in Bot1 (trovati {len(bot1_mints)} altri mint)")
        else:
            logging.warning(f"    ⚠ Impossibile recuperare Bot1 TX")
    
    # Verifica Bot2
    if bot2_hash:
        logging.info(f"  Analizzando Bot2 TX: {bot2_hash[:16]}...")
        time.sleep(DELAY)
        
        bot2_tx = get_transaction_details(bot2_hash)
        if bot2_tx:
            bot2_mints = extract_mints_from_transaction(bot2_tx)
            verification["bot2_mints_found"] = list(bot2_mints)
            verification["bot2_contains_mint"] = mint in bot2_mints
            
            if verification["bot2_contains_mint"]:
                logging.info(f"    ✓ Mint TROVATO in Bot2!")
            else:
                logging.info(f"    ✗ Mint NON trovato in Bot2 (trovati {len(bot2_mints)} altri mint)")
        else:
            logging.warning(f"    ⚠ Impossibile recuperare Bot2 TX")
    
    # Verifica globale
    verification["verified"] = (
        verification["bot1_contains_mint"] and 
        verification["bot2_contains_mint"]
    )
    
    # Log risultato
    if verification["verified"]:
        logging.info(f"  🎯 ATTACCO VERIFICATO!")
    else:
        logging.info(f"  ❌ Attacco NON verificato")
    
    # Aggiungi verification al match
    verified_match = match.copy()
    verified_match["verification"] = verification
    
    return verified_match

# -------------------------
# FUNZIONE: Verifica tutti gli attacchi
# -------------------------
def verify_all_attacks(matches_file, output_file):
    """
    Verifica tutti gli attacchi analizzando le transazioni bot1/bot2.
    
    Returns:
        tuple: (verified_matches, statistics)
    """
    logging.info(f"Caricamento match da {matches_file}...")
    
    # Carica i match
    with open(matches_file, 'r') as f:
        matches = json.load(f)
    
    total = len(matches)
    logging.info(f"Trovati {total} attacchi da verificare\n")
    logging.info(f"{'='*80}")
    logging.info(f"INIZIO VERIFICA DETTAGLIATA")
    logging.info(f"{'='*80}\n")
    
    verified_matches = []
    stats = {
        "total": total,
        "fully_verified": 0,
        "bot1_only": 0,
        "bot2_only": 0,
        "none_verified": 0,
        "verification_failed": 0
    }
    
    # Verifica ogni attacco
    for i, match in enumerate(matches, 1):
        logging.info(f"[{i}/{total}] " + "="*70)
        
        try:
            verified_match = verify_single_attack(match)
            verified_matches.append(verified_match)
            
            # Update stats
            verification = verified_match["verification"]
            if verification["verified"]:
                stats["fully_verified"] += 1
            elif verification["bot1_contains_mint"] and not verification["bot2_contains_mint"]:
                stats["bot1_only"] += 1
            elif verification["bot2_contains_mint"] and not verification["bot1_contains_mint"]:
                stats["bot2_only"] += 1
            else:
                stats["none_verified"] += 1
            
            # Salvataggio progressivo ogni 10 attacchi
            if i % 10 == 0:
                with open(output_file, 'w') as f:
                    json.dump({
                        "statistics": stats,
                        "verified_matches": verified_matches
                    }, f, indent=2)
                logging.info(f"\n💾 Progresso salvato: {i}/{total}\n")
        
        except Exception as e:
            logging.error(f"Errore nella verifica dell'attacco: {e}")
            stats["verification_failed"] += 1
            continue
    
    # Salvataggio finale
    with open(output_file, 'w') as f:
        json.dump({
            "statistics": stats,
            "verified_matches": verified_matches
        }, f, indent=2)
    
    return verified_matches, stats

# -------------------------
# FUNZIONE: Genera report dettagliato
# -------------------------
def generate_detailed_report(stats, verified_matches):
    """
    Genera un report dettagliato dei risultati.
    """
    logging.info(f"\n\n{'='*80}")
    logging.info(f"REPORT FINALE: VERIFICA COMPLETA ATTACCHI")
    logging.info(f"{'='*80}\n")
    
    # Statistiche generali
    total = stats["total"]
    verified = stats["fully_verified"]
    bot1_only = stats["bot1_only"]
    bot2_only = stats["bot2_only"]
    none = stats["none_verified"]
    failed = stats["verification_failed"]
    
    logging.info(f"📊 STATISTICHE GENERALI:")
    logging.info(f"  Attacchi totali analizzati: {total}")
    logging.info(f"  ✅ Completamente verificati (Bot1 + Bot2): {verified} ({verified/total*100:.1f}%)")
    logging.info(f"  ⚠️  Solo Bot1 verificata: {bot1_only} ({bot1_only/total*100:.1f}%)")
    logging.info(f"  ⚠️  Solo Bot2 verificata: {bot2_only} ({bot2_only/total*100:.1f}%)")
    logging.info(f"  ❌ Nessuna verificata: {none} ({none/total*100:.1f}%)")
    if failed > 0:
        logging.info(f"  ⚠️  Verifiche fallite: {failed} ({failed/total*100:.1f}%)")
    
    # Analisi per creatore
    logging.info(f"\n{'─'*80}")
    logging.info(f"📈 ANALISI PER CREATORE:\n")
    
    by_creator = defaultdict(lambda: {
        "total": 0,
        "verified": 0,
        "tokens": [],
        "total_profit": 0.0
    })
    
    for match in verified_matches:
        creator = match["creator_attacker_pubkey"]
        by_creator[creator]["total"] += 1
        
        if match["verification"]["verified"]:
            by_creator[creator]["verified"] += 1
        
        by_creator[creator]["tokens"].append(match["memecoin"]["ticker"])
        
        if match["profit"]["profit_sol"]:
            by_creator[creator]["total_profit"] += match["profit"]["profit_sol"]
    
    # Ordina per numero di attacchi verificati
    sorted_creators = sorted(
        by_creator.items(), 
        key=lambda x: x[1]["verified"], 
        reverse=True
    )[:10]
    
    logging.info(f"Top 10 creatori per attacchi VERIFICATI:\n")
    for i, (creator, data) in enumerate(sorted_creators, 1):
        verification_rate = (data["verified"] / data["total"] * 100) if data["total"] > 0 else 0
        logging.info(f"  {i}. {creator[:16]}...")
        logging.info(f"     Attacchi totali: {data['total']}")
        logging.info(f"     Attacchi verificati: {data['verified']} ({verification_rate:.1f}%)")
        logging.info(f"     Profitto totale: {data['total_profit']:.4f} SOL")
        logging.info(f"     Token: {', '.join(data['tokens'][:3])}{'...' if len(data['tokens']) > 3 else ''}")
        logging.info("")
    
    # Esempi di attacchi verificati
    logging.info(f"\n{'─'*80}")
    logging.info(f"🎯 ESEMPI DI ATTACCHI VERIFICATI:\n")
    
    verified_examples = [m for m in verified_matches if m["verification"]["verified"]][:5]
    
    for i, match in enumerate(verified_examples, 1):
        mc = match["memecoin"]
        logging.info(f"  {i}. {mc['nome']} ({mc['ticker']})")
        logging.info(f"     Mint: {mc['mint']}")
        logging.info(f"     Creatore: {match['creator_attacker_pubkey'][:16]}...")
        logging.info(f"     Sandwich ID: {match['sandwich_id']}")
        logging.info(f"     Profitto: {match['profit']['profit_sol']:.4f} SOL")
        logging.info(f"     Bot1 TX: {match['bot1_transaction_hash'][:16]}...")
        logging.info(f"     Bot2 TX: {match['bot2_transaction_hash'][:16]}...")
        logging.info(f"     Pump.fun: {mc['pumpfun_link']}")
        logging.info("")
    
    # Calcolo profitto verificato
    verified_profit = sum(
        m["profit"]["profit_sol"] 
        for m in verified_matches 
        if m["verification"]["verified"] and m["profit"]["profit_sol"]
    )
    
    total_claimed_profit = sum(
        m["profit"]["profit_sol"] 
        for m in verified_matches 
        if m["profit"]["profit_sol"]
    )
    
    logging.info(f"\n{'─'*80}")
    logging.info(f"💰 ANALISI PROFITTI:\n")
    logging.info(f"  Profitto dichiarato totale: {total_claimed_profit:.4f} SOL")
    logging.info(f"  Profitto VERIFICATO: {verified_profit:.4f} SOL")
    logging.info(f"  Percentuale verificata: {(verified_profit/total_claimed_profit*100):.1f}%")
    
    logging.info(f"\n{'='*80}")
    logging.info(f"✅ Verifica completata!")
    logging.info(f"{'='*80}\n")

# -------------------------
# MAIN
# -------------------------
def main():
    """Funzione principale."""
    
    logging.info("="*80)
    logging.info("VERIFICA COMPLETA ATTACCHI SANDWICH")
    logging.info("="*80)
    logging.info("Metodo: Analisi diretta delle transazioni bot1/bot2")
    logging.info("Controlla se il mint del token appare nei token transfers")
    logging.info("="*80 + "\n")
    
    # Verifica tutti gli attacchi
    verified_matches, stats = verify_all_attacks(INPUT_FILE, OUTPUT_VERIFIED)
    
    # Genera report dettagliato
    generate_detailed_report(stats, verified_matches)
    
    logging.info(f"📄 Risultati completi salvati in: {OUTPUT_VERIFIED}")
    logging.info("\n✓ Analisi completata!")

if __name__ == "__main__":
    main()