import json

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


if __name__ == "__main__":
    
    lines=[]
    
    with open("sandwich.jsonl", 'r', encoding='utf-8') as f:
        data_flat = [json.loads(line) for line in f]

    for i in range(0,len(data_flat)):
        if not sandwich_integrity_check(data_flat[i]):
            lines.append(i+1)

    print(f"Numero di righe da controllare: {len(lines)}\nRighe da controllare: {lines}")
    print(f"Valid sandwich: {len(data_flat)-len(lines)}")
    print(f"Percentuale di sandwich da eliminare: {round((len(lines)/len(data_flat))*100,2)}%")