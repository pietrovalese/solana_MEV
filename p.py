import pandas as pd
import json
import logging
from datetime import datetime
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
# CONFIGURAZIONE FILE
# -------------------------
CSV_FILE = "token_list_with_fee_payer.csv"
JSONL_FILE = "sandwiches_annotated.jsonl"
OUTPUT_FILE = "creator_attackers.json"

# -------------------------
# FUNZIONE: Parse timestamp
# -------------------------
def parse_timestamp(ts_string):
    """
    Converte una stringa timestamp in epoch Unix.
    Gestisce formati: 
    - ISO 8601: "2025-08-25T17:43:14"
    - Con note: "2025-08-25 15:37:01 (stimato)"
    """
    try:
        # Rimuovi note tipo "(stimato)"
        clean_ts = ts_string.split("(")[0].strip()
        
        # Prova formato ISO 8601
        if "T" in clean_ts:
            dt = datetime.fromisoformat(clean_ts.replace("Z", "+00:00"))
        else:
            # Formato standard con spazio
            dt = datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S")
        
        return int(dt.timestamp())
    except Exception as e:
        logging.warning(f"Errore nel parsing timestamp '{ts_string}': {e}")
        return None

# -------------------------
# FUNZIONE: Carica memecoin data
# -------------------------
def load_memecoin_data(csv_file):
    """
    Carica i dati delle memecoin dal CSV.
    
    Returns:
        dict: {fee_payer: {nome, ticker, mint, launched_at, last_activity, ...}}
    """
    logging.info(f"Caricamento memecoin da {csv_file}...")
    
    df = pd.read_csv(csv_file)
    
    # Filtra solo memecoin con fee_payer valido
    df = df[df["fee_payer"].notna()].copy()
    
    memecoin_map = {}
    
    for _, row in df.iterrows():
        fee_payer = row["fee_payer"]
        
        # Parse timestamp
        launched_ts = parse_timestamp(str(row["launched_at"]))
        last_activity_ts = parse_timestamp(str(row["last_activity"]))
        
        if not launched_ts or not last_activity_ts:
            logging.warning(f"Timestamp invalido per {row['Nome']} ({row['mint']})")
            continue
        
        memecoin_map[fee_payer] = {
            "nome": row["Nome"],
            "ticker": row["Ticker"],
            "mint": row["mint"],
            "launched_at": launched_ts,
            "last_activity": last_activity_ts,
            "pumpfun_link": row.get("pumpfun_link", "N/A"),
            "tipo": row.get("Tipo", "N/A"),
            "blockchain": row.get("Blockchain/Note", "N/A")
        }
    
    logging.info(f"Caricate {len(memecoin_map)} memecoin con fee_payer valido")
    return memecoin_map

# -------------------------
# FUNZIONE: Estrai bot signer dal sandwich
# -------------------------
def extract_bot_signer(sandwich):
    """
    Estrae il signer del bot da un sandwich attack.
    bot1 e bot2 sono lo stesso bot, quindi prendiamo solo bot1.
    
    Returns:
        tuple: (signer_pubkey, bot1_hash, bot2_hash) o (None, None, None)
    """
    bot_signer = None
    bot1_hash = None
    bot2_hash = None
    
    # Bot 1 (transazione di apertura)
    if "bot1" in sandwich and "Details" in sandwich["bot1"]:
        bot_signer = sandwich["bot1"]["Details"].get("signer", {}).get("pubkey")
        bot1_hash = sandwich["bot1"].get("hash")
    
    # Bot 2 (transazione di chiusura) - stesso bot, ma prendiamo l'hash
    if "bot2" in sandwich and "Details" in sandwich["bot2"]:
        bot2_hash = sandwich["bot2"].get("hash")
    
    return bot_signer, bot1_hash, bot2_hash

# -------------------------
# FUNZIONE: Calcola profitto sandwich
# -------------------------
def calculate_sandwich_profit(sandwich):
    """
    Calcola il profitto del sandwich attack in SOL.
    """
    try:
        bot1_value = sandwich.get("bot1", {}).get("value_start", "0")
        bot2_value = sandwich.get("bot2", {}).get("value_end", "0")
        
        # Rimuovi virgole e converti
        bot1_value = float(bot1_value.replace(",", ""))
        bot2_value = float(bot2_value.replace(",", ""))
        
        profit = bot2_value - bot1_value
        return profit, bot1_value, bot2_value
    except:
        return None, None, None

# -------------------------
# FUNZIONE: Match creator-attackers
# -------------------------
def find_creator_attackers(memecoin_map, jsonl_file):
    """
    Trova i casi in cui il creatore del token (fee_payer) è anche
    il bot che ha eseguito sandwich attack sul proprio token.
    
    Returns:
        list: Lista di match con dettagli completi
    """
    logging.info(f"Analisi sandwich attacks da {jsonl_file}...")
    logging.info("Cercando CREATORI che hanno ATTACCATO il proprio token...\n")
    
    matches = []
    total_sandwiches = 0
    
    with open(jsonl_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            try:
                sandwich = json.loads(line)
                total_sandwiches += 1
                
                sandwich_id = sandwich.get("Id", f"unknown_{line_num}")
                
                # Timestamp del sandwich
                sandwich_time = None
                if "bot1" in sandwich and "Details" in sandwich["bot1"]:
                    sandwich_time = sandwich["bot1"]["Details"].get("blockTime")
                
                if not sandwich_time:
                    continue
                
                # Estrai il bot signer (bot1 e bot2 sono lo stesso bot)
                bot_pubkey, bot1_hash, bot2_hash = extract_bot_signer(sandwich)
                
                if not bot_pubkey:
                    continue
                
                # Cerca match: fee_payer (creatore) == bot signer (attaccante)
                if bot_pubkey in memecoin_map:
                    memecoin = memecoin_map[bot_pubkey]
                    
                    # Verifica che l'attacco sia nel ciclo di vita della memecoin
                    if memecoin["launched_at"] <= sandwich_time <= memecoin["last_activity"]:
                        
                        # Calcola profitto
                        profit, value_in, value_out = calculate_sandwich_profit(sandwich)
                        
                        match = {
                            "sandwich_id": sandwich_id,
                            "creator_attacker_pubkey": bot_pubkey,
                            "bot1_transaction_hash": bot1_hash,
                            "bot2_transaction_hash": bot2_hash,
                            "sandwich_timestamp": sandwich_time,
                            "sandwich_datetime": datetime.fromtimestamp(sandwich_time).isoformat(),
                            "memecoin": {
                                "nome": memecoin["nome"],
                                "ticker": memecoin["ticker"],
                                "mint": memecoin["mint"],
                                "launched_at": datetime.fromtimestamp(memecoin["launched_at"]).isoformat(),
                                "last_activity": datetime.fromtimestamp(memecoin["last_activity"]).isoformat(),
                                "pumpfun_link": memecoin["pumpfun_link"],
                                "tipo": memecoin["tipo"]
                            },
                            "timing": {
                                "launched_timestamp": memecoin["launched_at"],
                                "attack_timestamp": sandwich_time,
                                "last_activity_timestamp": memecoin["last_activity"],
                                "seconds_after_launch": sandwich_time - memecoin["launched_at"],
                                "seconds_before_last_activity": memecoin["last_activity"] - sandwich_time,
                                "hours_after_launch": round((sandwich_time - memecoin["launched_at"]) / 3600, 2)
                            },
                            "profit": {
                                "profit_sol": profit,
                                "value_in": value_in,
                                "value_out": value_out
                            },
                            "victims_count": len(sandwich.get("victims", []))
                        }
                        matches.append(match)
                        
                        # Log dettagliato
                        logging.info(f"{'='*80}")
                        logging.info(f"🚨 CREATORE-ATTACCANTE TROVATO!")
                        logging.info(f"{'='*80}")
                        logging.info(f"Sandwich ID: {sandwich_id}")
                        logging.info(f"Creatore/Attaccante: {bot_pubkey}")
                        logging.info(f"Bot1 TX: {bot1_hash}")
                        logging.info(f"Bot2 TX: {bot2_hash}")
                        logging.info(f"\nMemecoin:")
                        logging.info(f"  Nome: {memecoin['nome']} ({memecoin['ticker']})")
                        logging.info(f"  Mint: {memecoin['mint']}")
                        logging.info(f"  Pump.fun: {memecoin['pumpfun_link']}")
                        logging.info(f"\nTiming:")
                        logging.info(f"  Launch: {match['memecoin']['launched_at']}")
                        logging.info(f"  Attacco: {match['sandwich_datetime']}")
                        logging.info(f"  Tempo dopo launch: {match['timing']['hours_after_launch']} ore")
                        logging.info(f"\nAttacco:")
                        logging.info(f"  Vittime: {match['victims_count']}")
                        if profit:
                            logging.info(f"  SOL in: {value_in:.4f}")
                            logging.info(f"  SOL out: {value_out:.4f}")
                            logging.info(f"  Profitto: {profit:.4f} SOL ({profit*100:.2f}%)" if value_in > 0 else f"  Profitto: {profit:.4f} SOL")
                        logging.info(f"{'='*80}\n")
                
            except json.JSONDecodeError as e:
                logging.error(f"Errore parsing JSON alla riga {line_num}: {e}")
                continue
            except Exception as e:
                logging.error(f"Errore alla riga {line_num}: {e}")
                continue
    
    logging.info(f"\n{'='*80}")
    logging.info(f"Sandwich analizzati: {total_sandwiches:,}")
    logging.info(f"Creatori-Attaccanti trovati: {len(matches)}")
    logging.info(f"{'='*80}\n")
    
    return matches

# -------------------------
# FUNZIONE: Genera report
# -------------------------
def generate_report(matches, output_file):
    """
    Salva i match in un file JSON e genera un report dettagliato.
    """
    if not matches:
        logging.warning("❌ Nessun creatore-attaccante trovato!")
        return
    
    # Salva JSON completo
    with open(output_file, 'w') as f:
        json.dump(matches, f, indent=2)
    
    logging.info(f"\n{'='*80}")
    logging.info(f"REPORT FINALE: CREATORI CHE HANNO ATTACCATO I PROPRI TOKEN")
    logging.info(f"{'='*80}\n")
    
    # Raggruppa per creatore
    by_creator = defaultdict(list)
    for match in matches:
        creator = match["creator_attacker_pubkey"]
        by_creator[creator].append(match)
    
    # Statistiche per creatore
    for creator, creator_matches in sorted(by_creator.items(), key=lambda x: len(x[1]), reverse=True):
        logging.info(f"\n{'─'*80}")
        logging.info(f"👤 CREATORE: {creator}")
        logging.info(f"   Token creati e attaccati: {len(creator_matches)}")
        
        total_profit = sum(m["profit"]["profit_sol"] for m in creator_matches if m["profit"]["profit_sol"])
        if total_profit:
            logging.info(f"   Profitto totale stimato: {total_profit:.4f} SOL")
        
        logging.info(f"\n   Token attaccati:")
        
        for i, match in enumerate(creator_matches, 1):
            mc = match["memecoin"]
            logging.info(f"\n   {i}. {mc['nome']} ({mc['ticker']})")
            logging.info(f"      Mint: {mc['mint']}")
            logging.info(f"      Link: {mc['pumpfun_link']}")
            logging.info(f"      Attacco: {match['sandwich_datetime']}")
            logging.info(f"      Dopo {match['timing']['hours_after_launch']}h dal launch")
            logging.info(f"      Vittime: {match['victims_count']}")
            if match["profit"]["profit_sol"]:
                logging.info(f"      Profitto: {match['profit']['profit_sol']:.4f} SOL")
            logging.info(f"      Sandwich ID: {match['sandwich_id']}")
    
    # Statistiche generali
    logging.info(f"\n{'='*80}")
    logging.info(f"STATISTICHE GENERALI")
    logging.info(f"{'='*80}")
    logging.info(f"Creatori unici trovati: {len(by_creator)}")
    logging.info(f"Attacchi totali: {len(matches)}")
    
    # Media attacchi per creatore
    avg_attacks = len(matches) / len(by_creator) if by_creator else 0
    logging.info(f"Media attacchi per creatore: {avg_attacks:.2f}")
    
    # Top creatori
    top_creators = sorted(by_creator.items(), key=lambda x: len(x[1]), reverse=True)[:5]
    logging.info(f"\nTop 5 creatori per numero di attacchi:")
    for i, (creator, creator_matches) in enumerate(top_creators, 1):
        total_profit = sum(m["profit"]["profit_sol"] for m in creator_matches if m["profit"]["profit_sol"])
        logging.info(f"  {i}. {creator[:16]}... - {len(creator_matches)} attacchi - {total_profit:.4f} SOL")
    
    # Timing statistics
    avg_hours = sum(m["timing"]["hours_after_launch"] for m in matches) / len(matches)
    logging.info(f"\nTempo medio dell'attacco dopo il launch: {avg_hours:.2f} ore")
    
    # Profit statistics
    profits = [m["profit"]["profit_sol"] for m in matches if m["profit"]["profit_sol"]]
    if profits:
        total_profit = sum(profits)
        avg_profit = total_profit / len(profits)
        max_profit = max(profits)
        logging.info(f"\nProfitto totale stimato: {total_profit:.4f} SOL")
        logging.info(f"Profitto medio per attacco: {avg_profit:.4f} SOL")
        logging.info(f"Profitto massimo: {max_profit:.4f} SOL")
    
    logging.info(f"\n{'='*80}")
    logging.info(f"Report completo salvato in: {output_file}")
    logging.info(f"{'='*80}\n")

# -------------------------
# MAIN
# -------------------------
def main():
    """Funzione principale."""
    
    logging.info("="*80)
    logging.info("ANALISI: CREATORI CHE ATTACCANO I PROPRI TOKEN")
    logging.info("="*80)
    logging.info("Obiettivo: Trovare fee_payer (creatore) == bot signer (attaccante)")
    logging.info("="*80 + "\n")
    
    # 1. Carica memecoin data
    memecoin_map = load_memecoin_data(CSV_FILE)
    
    if not memecoin_map:
        logging.error("Nessuna memecoin caricata! Verifica il CSV.")
        return
    
    # 2. Trova creatori-attaccanti
    matches = find_creator_attackers(memecoin_map, JSONL_FILE)
    
    # 3. Genera report
    generate_report(matches, OUTPUT_FILE)
    
    logging.info("✓ Analisi completata!")

if __name__ == "__main__":
    main()