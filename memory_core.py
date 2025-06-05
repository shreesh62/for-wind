import json
import os

MEMORY_FILE = "memory.json"

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return ""
    try:
        with open(MEMORY_FILE, "r") as f:
            data = json.load(f)
            return " | ".join(data.get("facts", []))
    except json.JSONDecodeError:
        return ""

def save_fact(fact):
    if not os.path.exists(MEMORY_FILE):
        data = {"facts": []}
    else:
        try:
            with open(MEMORY_FILE, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            data = {"facts": []}
    
    if fact not in data["facts"]:
        data["facts"].append(fact)
    
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=4)
