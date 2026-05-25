import logging
import json
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import re


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def init_driver():
    options = Options()
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def is_valid_float(value):
    try:
        float(str(value).replace(',', ''))  
        return True
    except (ValueError, TypeError):
        return False
    
def clean_fee(fee_str):
    """Estrae il primo numero decimale valido da una stringa, oppure 0.0 se non trovato."""
    if not fee_str:
        return 0.0
    matches = re.findall(r"\d*\.?\d+", fee_str)
    return float(matches[0]) if matches else 0.0



def sandwich_integrity_check(sandwich):
    def check_value_path(path):
        try:
            val = path
            return is_valid_float(val)
        except (KeyError, TypeError, IndexError):
            return False

    # -------- VALUE START --------
    if not check_value_path(sandwich["bot1"]["value_start"]):
        return False
    if not check_value_path(sandwich["bot2"]["value_start"]):
        return False
    for victim in sandwich.get("victims", []):
        if not check_value_path(victim["value_start"]):
            return False

    # -------- VALUE END --------
    if not check_value_path(sandwich["bot1"]["value_end"]):
        return False
    if not check_value_path(sandwich["bot2"]["value_end"]):
        return False
    for victim in sandwich.get("victims", []):
        if not check_value_path(victim["value_end"]):
            return False

    # -------- BLOCK --------
    for bot in ["bot1", "bot2"]:
        block = sandwich[bot]["Details"].get("Block")
        if block is None or not is_valid_float(block):
            return False
    for victim in sandwich.get("victims", []):
        block = victim["Details"].get("Block")
        if block is None or not is_valid_float(block):
            return False

    # -------- EPOCH --------
    for bot in ["bot1", "bot2"]:
        epoch = sandwich[bot]["Details"].get("Epoch")
        if epoch and len(epoch) > 0:
            if not is_valid_float(epoch[0]):
                return False
    for victim in sandwich.get("victims", []):
        epoch = victim["Details"].get("Epoch")
        if epoch and len(epoch) > 0:
            if not is_valid_float(epoch[0]):
                return False
            
    # -------- FEE --------
    
    error_string="sponsored:   solaxy: the first-ever solana layer 2 presale, solaxy, explodes, raising over $26m! buy $solx!"
    
    for bot in ["bot1", "bot2"]:
        fee = sandwich[bot]["Details"].get("Fee")
        if fee and len(fee) > 0:
            if not is_valid_float(clean_fee(fee)) or error_string in fee:
                return False
    for victim in sandwich.get("victims", []):
        fee = victim["Details"].get("Fee")
        if fee and len(fee) > 0:
            if not is_valid_float(clean_fee(fee)) or error_string in fee:
                return False

    return True


def calculate_id(bot1, victims, bot2):
    id_str = bot1["hash"] + bot2["hash"] + ''.join(v["hash"] for v in victims)
    return hashlib.sha256(id_str.encode('utf-8')).hexdigest()

def extract_tx_id(url):
    """Rimuove la parte del link per ottenere solo l'ID della transazione."""
    tx_id = url.replace("https://solscan.io/tx/", "")
    return tx_id


def create_bot_info(refined_list, i):
    return {
        "bot": refined_list[i],
        "value_start": refined_list[i + 1] if i + 1 < len(refined_list) else "",
        "token_start": refined_list[i + 2] if i + 2 < len(refined_list) else "",
        "value_end": refined_list[i + 3] if i + 3 < len(refined_list) else "",
        "token_end": refined_list[i + 4] if i + 4 < len(refined_list) else "",
        "hash": extract_tx_id(refined_list[i + 5] if i + 5 < len(refined_list) else ""),
    }

def create_victim_info(refined_list, i):
    return {
        "victim": refined_list[i],
        "value_start": refined_list[i + 1] if i + 1 < len(refined_list) else "",
        "token_start": refined_list[i + 2] if i + 2 < len(refined_list) else "",
        "value_end": refined_list[i + 3] if i + 3 < len(refined_list) else "",
        "token_end": refined_list[i + 4] if i + 4 < len(refined_list) else "",
        "hash": extract_tx_id(refined_list[i + 5] if i + 5 < len(refined_list) else ""),
    }

def json_write(sandwich_array):
    
    with open("sandwich.jsonl", "r", encoding="utf-8") as f:
            try:
                existing_data = [json.loads(line) for line in f]
            except json.JSONDecodeError:
                existing_data = []

    print("\n--------------------Sandwich recap:--------------------")
    # Crea un set degli hash già presenti
    existing_Id = {entry["Id"] for entry in existing_data}
    print(f"Hash già presenti ({len(existing_Id)})")
    
    # Filtra i nuovi sandwich che non sono già presenti
    new_sandwiches = [entry for entry in sandwich_array if entry["Id"] not in existing_Id]
    print(f"Nuovi sandwich da aggiungere ({len(new_sandwiches)})")
    
    print("-------------------------------------------------------\n")

    
        # Scrive ogni oggetto su una riga nel file di output
    with open("sandwich.jsonl", 'a', encoding='utf-8') as out:
        flat_line = json.dumps(new_sandwiches[0], separators=(',', ':'))
        out.write(flat_line + '\n')
    

def get_import(driver):
    try:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, '.css-vooagt')))
        time.sleep(3)

        elements = driver.find_elements(By.CSS_SELECTOR, ".css-c8crdy, .css-j4hctk, .css-1d4aeae, .css-1dtafdp, .css-14fj6r6")
        refined_list = [el.text.strip().lower() or el.get_attribute("href") for el in elements]

        i = 0
        while i < len(refined_list):
            if "bot" in refined_list[i]:
                i_bot1 = i
                logging.info(f"Trovato bot1 a index {i_bot1}")
                i += 6  # salta i 6 campi del bot

                # Inizio raccolta victims
                victim_indices = []
                while i < len(refined_list) and "victim" in refined_list[i]:
                    victim_indices.append(i)
                    i += 6  # ogni victim occupa 6 slot

                # Ora cerchiamo bot2
                if i < len(refined_list) and "bot" in refined_list[i]:
                    i_bot2 = i
                    logging.info(f"Trovato bot2 a index {i_bot2}")
                    i += 6  # salta bot2

                    with ThreadPoolExecutor(max_workers=3) as executor:
                        future_bot1 = executor.submit(create_bot_info, refined_list, i_bot1)
                        future_bot2 = executor.submit(create_bot_info, refined_list, i_bot2)
                        future_victims = executor.submit(
                            lambda: [create_victim_info(refined_list, vi) for vi in victim_indices]
                        )

                        bot1 = future_bot1.result()
                        bot2 = future_bot2.result()
                        victims = future_victims.result()

                        sandwich = {
                            "Id": calculate_id(bot1, victims, bot2),
                            "bot1": bot1,
                            "victims": victims,
                            "bot2": bot2
                        }

                        #if sandwich_integrity_check(sandwich):
                        json_write([sandwich])
                        logging.info("✅ Sandwich creato e scritto nel JSON.")

                else:
                    logging.warning("Bot2 non trovato dopo victims.")
            else:
                i += 1  # Avanza se non è un bot (skippa elementi inutili)

    except Exception as e:
        logging.error("Errore durante get_import", exc_info=e)


if __name__ == "__main__":
    
    while True:
        start = time.perf_counter()

        url = 'https://sandwiched.me'
        driver = init_driver()
        driver.get(url)

        get_import(driver)

        driver.quit()

        end = time.perf_counter()
        logging.info(f"Execution time: {end - start:.2f} seconds")

        time.sleep(45)

