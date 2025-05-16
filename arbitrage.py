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

def parse_arbitrage_block(text_block):
    lines = [line.strip() for line in text_block.strip().splitlines() if line.strip()]
    
    arb = {}
    steps = []
    
    # Extract header
    header_match = re.match(r"arb\s+#(\d+)\s+\|\s+bot:\s+(\w+)", lines[0], re.IGNORECASE)
    if header_match:
        arb["arb_id"] = (header_match.group(1))
        arb["bot"] = header_match.group(2)

    # Extract revenue
    revenue_match = re.match(r"revenue:\s*\+?([\d.]+)\s*sol", lines[1], re.IGNORECASE)
    if revenue_match:
        arb["revenue_sol"] = (revenue_match.group(1))

    # Parse steps
    i = 2
    while i < len(lines):
        platform = lines[i]
        amount = (lines[i + 1].replace(',', ''))
        token = lines[i + 2].upper()
        steps.append({
            "platform": platform,
            "amount": amount,
            "token": token
        })
        i += 3

    arb["steps"] = steps
    return arb

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

        # Group lines into arbitrage blocks
        arbs = []
        block = []
        for line in refined_list:
            if re.match(r"arb\s+#\d+\s+\|\s+bot:", line.lower()):
                if block:  # If previous block exists, parse it
                    try:
                        arb_json = parse_arbitrage_block("\n".join(block))
                        arbs.append(arb_json)
                    except Exception as parse_error:
                        logging.warning(f"Failed to parse arbitrage block: {parse_error}")
                block = [line]  # Start new block
            else:
                block.append(line)

        # Don't forget the last block
        if block:
            try:
                arb_json = parse_arbitrage_block("\n".join(block))
                arbs.append(arb_json)
            except Exception as parse_error:
                logging.warning(f"Failed to parse final arbitrage block: {parse_error}")

        # Append results to a .jsonl file
        with open("arbitrages.jsonl", "a", encoding="utf-8") as f:
            for arb in arbs:
                f.write(json.dumps(arb) + "\n")
                
    except Exception as e:
        logging.error("Errore durante get_arbs", exc_info=e)




if __name__ == "__main__":
    
    while True:
        start = time.perf_counter()

        url = 'https://sandwiched.me/arbitrages'
        driver = init_driver()
        driver.get(url)

        get_arbs(driver)

        driver.quit()

        end = time.perf_counter()
        logging.info(f"Execution time: {end - start:.2f} seconds")

        time.sleep(10)