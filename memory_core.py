import json
import os
import difflib

MEMORY_FILE = "memory.json"

def ensure_memory_file():
    if not os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "w") as f:
            json.dump({}, f)

def load_memory():
    ensure_memory_file()
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_to_memory(key: str, value: str):
    data = load_memory()
    data[key] = value
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=4)

def delete_from_memory(keyword: str):
    data = load_memory()
    keys_to_delete = [k for k, v in data.items() if keyword.lower() in k.lower() or keyword.lower() in str(v).lower()]
    for key in keys_to_delete:
        del data[key]
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=4)
    return bool(keys_to_delete)

def parse_remember_command(command: str):
    return command[8:].strip() if command.lower().startswith("remember") else None

def parse_forget_command(command: str):
    return command[6:].strip() if command.lower().startswith("forget") else None

def get_relevant_memory_snippet(command: str, max_chars=1000):
    data = load_memory()
    command = command.lower()

    if not data:
        return ""

    memory_items = list(data.items())
    scored = []

    for key, value in memory_items:
        combined = f"{key}: {value}"
        score = difflib.SequenceMatcher(None, command, combined.lower()).ratio()
        scored.append((score, combined))

    scored.sort(reverse=True)
    relevant = [item[1] for item in scored if item[0] > 0.3]

    if not relevant:
        relevant = list(data.values())[:4]

    return "\n".join(relevant)[:max_chars]
