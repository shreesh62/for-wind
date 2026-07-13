import json
import os
import difflib


def _memory_file() -> str:
    """Resolve the memory store path at call time.

    Honors FRIDAY_STATE_DIR so runtime state can be redirected out of the repo
    tree (tests point it at a temp dir for hermeticity). Unset => "memory.json"
    in the CWD, i.e. production behavior is unchanged.
    """
    state_dir = os.getenv("FRIDAY_STATE_DIR", "")
    return os.path.join(state_dir, "memory.json") if state_dir else "memory.json"


# Backward-compatible module constant (resolved at import; functions below use
# _memory_file() so a later env change / redirect is always honored).
MEMORY_FILE = _memory_file()

def ensure_memory_file():
    path = _memory_file()
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump({}, f)

def load_memory():
    ensure_memory_file()
    with open(_memory_file(), "r") as f:
        return json.load(f)

def save_to_memory(key: str, value: str):
    data = load_memory()
    data[key] = value
    with open(_memory_file(), "w") as f:
        json.dump(data, f, indent=4)

def delete_from_memory(keyword: str):
    data = load_memory()
    keys_to_delete = [k for k, v in data.items() if keyword.lower() in k.lower() or keyword.lower() in str(v).lower()]
    for key in keys_to_delete:
        del data[key]
    with open(_memory_file(), "w") as f:
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

    # Coerce to str: memory.json is shared with vector_memory, which stores
    # structured (dict) entries, so values are not guaranteed to be strings.
    # Never TypeError on a legitimately-shaped store.
    return "\n".join(str(r) for r in relevant)[:max_chars]
