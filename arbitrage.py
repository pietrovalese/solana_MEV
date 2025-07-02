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

def init_driver():
    options = Options()
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def remove_duplicate_ids(filename):
    seen_ids = set()
    unique_entries = []

    # Leggi tutte le righe e filtra duplicati
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                obj_id = obj.get("ID")
                if obj_id and obj_id not in seen_ids:
                    seen_ids.add(obj_id)
                    unique_entries.append(obj)
                # Se obj_id è duplicato, ignora
            except json.JSONDecodeError:
                # Ignora righe malformate
                continue

    # Riscrivi il file con solo entrate uniche
    with open(filename, "w", encoding="utf-8") as f:
        for entry in unique_entries:
            json.dump(entry, f, ensure_ascii=False)
            f.write("\n")
            
def create_ID(obj):
    result = []

    def extract_strings(item):
        if isinstance(item, dict):
            for value in item.values():
                extract_strings(value)
        elif isinstance(item, list):
            for element in item:
                extract_strings(element)
        elif isinstance(item, str):
            result.append(item)

    extract_strings(obj)
    id= ''.join(result)
    return hashlib.sha256(id.encode('utf-8')).hexdigest()

def parse_arbitrage_block(text_block):

    data = text_block
    results = []
    i = 0

    while i < len(data):
        if data[i].startswith("Arb"):
            arb = {}
            arb_id = data[i]
            bot_id = arb_id.split("| Bot: ")[1]
            arb["bot"] = bot_id
            i += 1

            revenue = data[i].split(": ")[1].split(" ")[0]
            arb["revenue_sol"] = float(revenue)
            i += 1

            arb["trades"] = []
            while i < len(data) and not data[i].startswith("Arb"):
                trade = {
                    "platform": data[i],
                    "from_amount": data[i+1],
                    "from_token": data[i+2],
                    "to_amount": data[i+3],
                    "to_token": data[i+4],
                }
                arb["trades"].append(trade)
                i += 5

            id = create_ID(arb)
            arb["ID"] = id
            
            results.append(arb)

    with open("arbitrages.jsonl", "w") as f:
        for arb in results:
            json.dump(arb, f)
            f.write("\n")

def get_arbs(driver):
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.css-vooagt'))
        )
        time.sleep(1.5)

        bottone = driver.find_element(By.CSS_SELECTOR, ".css-1dowmvd")
        bottone.click()

        elements = driver.find_elements(By.CSS_SELECTOR, ".css-ftzju4, .css-7oju96, .css-dx1stx, .css-1dc18fv, .css-1dv8du6")
        
        refined_list = []
        for i in range(len(elements)):
            try:
                el = driver.find_elements(By.CSS_SELECTOR, ".css-ftzju4, .css-7oju96, .css-dx1stx, .css-1dc18fv, .css-1dv8du6")[i]
                text = el.text.strip()
                refined_list.append(text if text else el.get_attribute("href") or "")
            except Exception as inner_e:
                logging.warning(f"Failed to access element content: {inner_e}")
                continue
        
        print(refined_list)
        parse_arbitrage_block(refined_list)
              
    except Exception as e:
        logging.error("Errore durante get_arbs", exc_info=e)

if __name__ == "__main__":
    
    while True:
        start = time.perf_counter()

        url = 'https://sandwiched.me/arbitrages'
        driver = init_driver()
        driver.get(url)

        get_arbs(driver)
        remove_duplicate_ids("arbitrages.jsonl")
        driver.quit()

        end = time.perf_counter()
        logging.info(f"Execution time: {end - start:.2f} seconds")

        time.sleep(10)