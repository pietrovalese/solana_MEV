from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import json
import time
import hashlib

def is_valid_float(value):
    try:
        float(str(value).replace(',', ''))  
        return True
    except (ValueError, TypeError):
        return False


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

    return True


def calculate_id(bot1,victims,bot2):
    
    id=""
    victims_string=""
    bot1_string=bot1["hash"]
    bot2_string=bot2["hash"]
    
    for victim in victims:
        victim_string=victim["hash"]
        victims_string+=victim_string
          
    id=bot1_string+bot2_string+victims_string
    hash_object = hashlib.sha256(id.encode('utf-8'))
    hashed = hash_object.hexdigest()
    return hashed

def get_transaction_solanaFM(tx_block, driver_solanaFM):
    url_solanaFM = f"https://solana.fm/block/{tx_block}?cluster=mainnet-alpha"
    driver_solanaFM.get(url_solanaFM)
    
    print(f"Richiesta a {url_solanaFM}")
    res=""

    try:
        WebDriverWait(driver_solanaFM, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.w-full'))
        )
        time.sleep(10)

        details_block = driver_solanaFM.find_elements(By.CSS_SELECTOR, '.text-sm')

        refined_list_block = []
        for el in details_block:
            text = el.text.strip().lower()
            if text:
                refined_list_block.append(text)
            else:
                link = el.get_attribute("href")
                refined_list_block.append(link)

        refined_list_block = [x for x in refined_list_block if x and isinstance(x, str) and x.isdigit()]
        res = refined_list_block[0] if len(refined_list_block) >= 1 else "",

    except Exception as e:
        print(f"Errore durante l'estrazione (get_transactions_solanaFM)")

    print(f"Epoch trovata: {res}")
    return res

def get_transaction_info(tx_hash, driver_solscan):
    url_solscan = f"https://solscan.io/tx/{tx_hash}"
    driver_solscan.get(url_solscan)
    
    print(f"Richiesta a {url_solscan}")
    
    info = {}

    try:
        # Attendere che la pagina si carichi e che l'elemento venga trovato
        WebDriverWait(driver_solscan, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'textLink'))
        )
        time.sleep(5)

        # Prendere gli elementi con il selettore CSS che identificano i dettagli della transazione
        details_block = driver_solscan.find_elements(By.CSS_SELECTOR, 'a.textLink') 
        details_timestamp = driver_solscan.find_elements(By.CSS_SELECTOR, '.text-neutral5')
        details_fee = driver_solscan.find_elements(By.CSS_SELECTOR, '.text-neutral7')  
        details_result = driver_solscan.find_elements(By.CSS_SELECTOR, '.flex-wrap')  #

        # Elenco delle informazioni estratte (da adattare ai dati effettivi)
        refined_list_block = []
        for el in details_block:
            text = el.text.strip().lower()
            if text:
                refined_list_block.append(text)
            else:
                link = el.get_attribute("href")
                refined_list_block.append(link)
        
        refined_list_ts = []
        for el in details_timestamp:
            text = el.text.strip().lower()
            if text:
                refined_list_ts.append(text)
            else:
                link = el.get_attribute("href")
                refined_list_ts.append(link)
            
        refined_list_fee = []
        for el in details_fee:
            text = el.text.strip().lower()
            if text:
                refined_list_fee.append(text)
            else:
                link = el.get_attribute("href")
                refined_list_fee.append(link)
        refined_list_fee = [x for x in refined_list_fee if x != None]
        refined_list_fee = [x for x in refined_list_fee if "sol" in x.lower() and "$" in x]
        
        refined_list_result = []
        index=-1
        for el in details_result:
            text = el.text.strip().lower()
            if text:
                refined_list_result.append(text)
            else:
                link = el.get_attribute("href")
                refined_list_result.append(link)
        refined_list_result = [x for x in refined_list_result if x != None]
        for i in range(0, len(refined_list_result)):
            if refined_list_result[i] == "result":
                index=i
        result = refined_list_result[index+1].replace("\n", " --> ")
        
        # Estrazione dei dettagli: assicurati di selezionare gli indici corretti
         
        info = {"Block": refined_list_block[1] if len(refined_list_block) > 1 else "" , 
                "Timestamp": refined_list_ts[0] if len(refined_list_ts) > 1 else "", 
                "Fee": refined_list_fee[0], "Priority Fee": refined_list_fee[1] if len(refined_list_fee) > 1 else "", 
                "Result": result if index!=-1 else "",
                "Epoch": get_transaction_solanaFM(refined_list_block[1], driver_solanaFM)
                }

    except Exception as e:
        print(f"Errore durante l'estrazione (get_transaction_info)")

    return info

def extract_tx_id(url):
    """Rimuove la parte del link per ottenere solo l'ID della transazione."""
    tx_id = url.replace("https://solscan.io/tx/", "")
    return tx_id


def create_bot_info(refined_list, i):
    """Funzione per creare un dizionario bot."""
    bot = {
        "bot": refined_list[i],
        "value_start": refined_list[i + 1] if i + 1 < len(refined_list) else "",
        "token_start": refined_list[i + 2] if i + 2 < len(refined_list) else "",
        "value_end": refined_list[i + 3] if i + 3 < len(refined_list) else "",
        "token_end": refined_list[i + 4] if i + 4 < len(refined_list) else "",
        "hash": extract_tx_id(refined_list[i + 5] if i + 5 < len(refined_list) else ""),
        "Details": get_transaction_info(extract_tx_id(refined_list[i + 5] if i + 5 < len(refined_list) else ""), driver_solscan)
    }
    return bot

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
    
    victims = []
    sandwich_array = []
    bot_counter = 0
    
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.css-vooagt'))
        )
        time.sleep(1.5)

        # Prende tutti gli elementi desiderati
        combined_elements = driver.find_elements(By.CSS_SELECTOR, ".css-c8crdy, .css-j4hctk, .css-1d4aeae, .css-1dtafdp, .css-14fj6r6")
        refined_list = []
        
        for i, el in enumerate(combined_elements):
            text = el.text.strip().lower()
            if text == "":
                link = el.get_attribute("href")
                refined_list.append(link)
            else:
                refined_list.append(text)
            
        for i in range(0,len(refined_list)): 
            text = refined_list[i]   
            if "bot" in text:
                if bot_counter == 2:
                    sandwich = {
                        "Id": calculate_id(bot1,victims,bot2),
                        "bot1": bot1,
                        "victims": victims,
                        "bot2": bot2
                    }
                    if sandwich_integrity_check(sandwich):
                        print("\n-------------------------------------------------------\nValid sandwich\n-------------------------------------------------------\n")
                        sandwich_array.append(sandwich)
                        json_write(sandwich_array)
                        sandwich_array.remove(sandwich)
                    victims = []
                    bot_counter = 0

                if bot_counter == 0:
                    print(f"Making bot1 nr. {i}")
                    bot1 = create_bot_info(refined_list, i)
                elif bot_counter == 1:
                    print(f"Making bot2 nr. {i}")
                    bot2 = create_bot_info(refined_list, i)
                
                bot_counter += 1

            elif "victim" in text:
                print(f"making victim nr. {i}")
                victim = {
                    "victim": refined_list[i],
                    "value_start": refined_list[i + 1] if i + 1 < len(refined_list) else "",
                    "token_start": refined_list[i + 2] if i + 2 < len(refined_list) else "",
                    "value_end": refined_list[i + 3] if i + 3 < len(refined_list) else "",
                    "token_end": refined_list[i + 4] if i + 4 < len(refined_list) else "",
                    "hash": extract_tx_id(refined_list[i + 5] if i + 5 < len(refined_list) else ""),
                    "Details": get_transaction_info(extract_tx_id(refined_list[i + 5] if i + 5 < len(refined_list) else ""), driver_solscan)
                }
                victims.append(victim)
        

    except Exception as e:
        print(f"Errore durante l'estrazione (get_import): {e}")


if __name__ == "__main__":
    
    while True:
        start = time.perf_counter()

        url_sandwich = 'https://sandwiched.me'
        driver_sandwich = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
        driver_solscan = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
        driver_solanaFM = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

        driver_sandwich.get(url_sandwich)
        get_import(driver_sandwich)

        end = time.perf_counter()
        print(f"Tempo di esecuzione: {end - start:.4f} secondi")

        time.sleep(5)
        driver_sandwich.quit()
        driver_solscan.quit()
        driver_solanaFM.quit()
        time.sleep(5)
