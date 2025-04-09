from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
from webdriver_manager.chrome import ChromeDriverManager
import time
import hashlib


def calculate_hash(bot1,victims,bot2):
    string_to_hash=""
    victims_string=""
    bot1_string=bot1["bot"]+bot1["value_start"]+bot1["currency_start"]+bot1["value_end"]+bot1["currency_end"]
    bot2_string=bot2["bot"]+bot2["value_start"]+bot2["currency_start"]+bot2["value_end"]+bot2["currency_end"]
    for victim in victims:
        victim_string=victim["victim"]+victim["value_start"]+victim["currency_start"]+victim["value_end"]+victim["currency_end"]
        victims_string+=victim_string  
    string_to_hash=bot1_string+bot2_string+victims_string
    hash_object = hashlib.sha256(string_to_hash.encode('utf-8'))
    hashed = hash_object.hexdigest()
    return hashed


def get_import(url):
    driver.get(url)
    victims = []
    sandwich_array = []
    bot_counter = 0

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.css-vooagt'))
        )
        time.sleep(0.8)
        combined_elements = driver.find_elements(By.CSS_SELECTOR, ".css-c8crdy, .css-1d4aeae, .css-1dtafdp, .css-14fj6r6")
        
        for i in range(0,len(combined_elements)):
            text = combined_elements[i].text.strip().lower()

            if "bot" in text:
                if bot_counter == 2:
                    hashed=calculate_hash(bot1,victims,bot2)
                    sandwich = {
                        "hash": hashed,
                        "bot1": bot1,
                        "victims": victims,
                        "bot2": bot2
                    }
                    sandwich_array.append(sandwich)
                    victims = []
                    bot_counter = 0

                if bot_counter == 0:
                    bot1 = {
                        "bot": combined_elements[i].text,
                        "value_start": combined_elements[i+1].text,
                        "currency_start": combined_elements[i+2].text,
                        "value_end": combined_elements[i+3].text,
                        "currency_end": combined_elements[i+4].text
                    }
                elif bot_counter == 1:
                    bot2 = {
                        "bot": combined_elements[i].text,
                        "value_start": combined_elements[i+1].text,
                        "currency_start": combined_elements[i+2].text,
                        "value_end": combined_elements[i+3].text,
                        "currency_end": combined_elements[i+4].text
                    }
                bot_counter += 1

            elif "victim" in text:
                victim = {
                    "victim": combined_elements[i].text,
                    "value_start": combined_elements[i+1].text,
                    "currency_start": combined_elements[i+2].text,
                    "value_end": combined_elements[i+3].text,
                    "currency_end": combined_elements[i+4].text
                }
                victims.append(victim)

        with open("sandwich.json", "r", encoding="utf-8") as f:
            try:
                existing_data = json.load(f)
            except json.JSONDecodeError:
                existing_data = []

        print("\n--------------------Sandwich recap:--------------------")
        # Crea un set degli hash già presenti
        existing_hashes = {entry["hash"] for entry in existing_data}
        print(f"Hash già presenti ({len(existing_hashes)})")
        
        # Filtra i nuovi sandwich che non sono già presenti
        new_sandwiches = [entry for entry in sandwich_array if entry["hash"] not in existing_hashes]
        print(f"Nuovi sandwich da aggiungere ({len(new_sandwiches)})")
        
        print("-------------------------------------------------------\n")

        # Unisci i dati esistenti con i nuovi
        updated_data = existing_data + new_sandwiches
        
        with open("sandwich.json", "w", encoding="utf-8") as f:
            json.dump(updated_data, f, indent=4, ensure_ascii=False)
            print("JSON aggiornato con nuovi sandwich")
            print("Dati estratti correttamente\n")

    except Exception as e:
        print(f"Errore durante l'estrazione\n")
        return sandwich_array

    return sandwich_array


if __name__ == "__main__":
    url = 'https://sandwiched.me'
    for i in range(0,50):
        print(f"--------------------Iterazione: {i+1}--------------------")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
        sand = get_import(url)
        driver.quit()
        time.sleep(20)