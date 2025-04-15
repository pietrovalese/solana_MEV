import json
import re

#\u00ea


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
    for bot in ["bot1", "bot2"]:
        fee = sandwich[bot]["Details"].get("Fee")
        if fee and len(fee) > 0:
            if not is_valid_float(clean_fee(fee)) or "sponsored:   solaxy: the first-ever solana layer 2 presale, solaxy, explodes, raising over $26m! buy $solx!" in fee:
                return False
    for victim in sandwich.get("victims", []):
        fee = victim["Details"].get("Fee")
        if fee and len(fee) > 0:
            if not is_valid_float(clean_fee(fee)) or "sponsored:   solaxy: the first-ever solana layer 2 presale, solaxy, explodes, raising over $26m! buy $solx!" in fee:
                return False
            
    return True

if __name__ == "__main__":
    
    lines_to_eliminate=[]
    lines_good=[]
    
    with open("sandwich.jsonl", 'r', encoding='utf-8') as f:
        data_flat = [json.loads(line) for line in f]

    for i in range(0,len(data_flat)):
        if not sandwich_integrity_check(data_flat[i]):
            lines_to_eliminate.append(i+1)
        else:
            lines_good.append(data_flat[i])
    
    
    with open("sandwich_corretti.jsonl", 'a', encoding='utf-8') as out:
        for i in range(0, len(lines_good)):
            flat_line = json.dumps(lines_good[i], separators=(',', ':'))
            out.write(flat_line + '\n')
        
    print(f"Numero di righe da controllare: {len(lines_to_eliminate)}\nRighe da controllare: {lines_to_eliminate}")
    print(f"Valid sandwich: {len(data_flat)-len(lines_to_eliminate)}")
    print(f"Percentuale di sandwich da eliminare: {round((len(lines_to_eliminate)/len(data_flat))*100,2)}%")