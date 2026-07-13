# vector_memory.py

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None  # type: ignore
import math
import os
import json
try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore
from datetime import datetime
from datetime import timezone
from typing import Dict, Any, Iterable, List

# Enable heavy embedding pipeline only if explicitly requested via env var
_ENABLE_EMBEDDINGS = os.getenv("MEMORY_EMBEDDINGS", "0").strip().lower() in {"1", "true", "yes", "on"}
if _ENABLE_EMBEDDINGS:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception:  # pragma: no cover
        SentenceTransformer = None  # type: ignore
else:
    SentenceTransformer = None  # type: ignore

# Path to store memory index and logs.
# Honor FRIDAY_STATE_DIR so runtime state can be redirected out of the repo tree
# (e.g. tests point it at a temp dir for hermeticity). Unset => current behavior
# (bare names in the CWD), so production defaults are unchanged.
def _state_path(name: str) -> str:
    state_dir = os.getenv("FRIDAY_STATE_DIR", "")
    return os.path.join(state_dir, name) if state_dir else name


INDEX_FILE = _state_path("memory.index")
MEMORY_JSON = _state_path("memory.json")
LOG_FILE = _state_path("interaction_log.json")

embedding_model = None
EMBED_DIM = 0
if SentenceTransformer is not None:
    try:
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        EMBED_DIM = embedding_model.get_sentence_embedding_dimension()
    except Exception:
        embedding_model = None
        EMBED_DIM = 0

if faiss is not None and embedding_model is not None and EMBED_DIM > 0 and np is not None:
    if os.path.exists(INDEX_FILE):
        index = faiss.read_index(INDEX_FILE)
    else:
        index = faiss.IndexFlatL2(EMBED_DIM)
else:
    index = None

# Store mapping between vector IDs and entries
# Entry format (new): {"text": str, "salience": "low|medium|high", "ts": ISO8601}
# Backward compat: values may be plain strings.
if os.path.exists(MEMORY_JSON):
    with open(MEMORY_JSON, "r", encoding="utf-8") as f:
        memory_data: Dict[str, Any] = json.load(f)
else:
    memory_data = {}


def save_index():
    """Save FAISS index and memory mapping."""
    if index is not None and faiss is not None:
        faiss.write_index(index, INDEX_FILE)
    with open(MEMORY_JSON, "w", encoding="utf-8") as f:
        json.dump(memory_data, f, ensure_ascii=False, indent=2)


def embed_text(text: str) -> Any:
    """Convert text into embedding vector."""
    if embedding_model is None or np is None:
        # Keep shape compatible with FAISS-less fallback usage.
        return [[0.0]]  # type: ignore[return-value]
    return np.array(embedding_model.encode([text]), dtype="float32")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_entry(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        # Ensure required fields
        return {
            "text": value.get("text", ""),
            "salience": value.get("salience", "low"),
            "ts": value.get("ts") or _now_iso(),
        }
    return {"text": str(value), "salience": "low", "ts": _now_iso()}


def _iter_entries() -> Iterable[Dict[str, Any]]:
    for k in sorted(memory_data.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
        yield _as_entry(memory_data[k])


def save_to_memory(text: str, *, salience: str = "low"):
    """Save text into vector memory with metadata."""
    new_id = str(len(memory_data))  # unique ID
    entry = {"text": text, "salience": salience or "low", "ts": _now_iso()}
    memory_data[new_id] = entry
    if index is not None and embedding_model is not None:
        vector = embed_text(text)
        try:
            index.add(vector)
        except Exception:
            pass
    save_index()
    return new_id


def delete_from_memory(text: str):
    """Remove memory entry if text matches."""
    global index
    to_delete = None
    target = (text or "").strip()
    if not target:
        return False
    target_norm = target.lower()
    for k, v in memory_data.items():
        try:
            entry = _as_entry(v)
            candidate = entry.get("text")
        except Exception:
            candidate = None
        if isinstance(candidate, str) and candidate.strip().lower() == target_norm:
            to_delete = k
            break

    if to_delete is not None:
        del memory_data[to_delete]
        if index is not None and faiss is not None and embedding_model is not None and EMBED_DIM > 0:
            try:
                index = faiss.IndexFlatL2(EMBED_DIM)
                for v in memory_data.values():
                    entry = _as_entry(v)
                    candidate = entry.get("text")
                    if not isinstance(candidate, str) or not candidate.strip():
                        continue
                    index.add(embed_text(candidate))
            except Exception:
                index = None
        save_index()
        return True
    return False


def parse_remember_command(command: str):
    """Extract memory text from a 'remember' command."""
    command = command.lower().strip()
    if "remember" in command:
        return command.replace("remember", "").strip()
    return None


def parse_forget_command(command: str):
    """Extract memory text from a 'forget' command."""
    command = command.lower().strip()
    if "forget" in command:
        return command.replace("forget", "").strip()
    return None


def _recency_weight(ts_iso: str) -> float:
    try:
        ts = datetime.fromisoformat(ts_iso)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - ts).days
        # Half-life ~90 days
        return float(math.exp(-days / 90.0))
    except Exception:
        return 0.9


def _similarity_fallback(a: str, b: str) -> float:
    a, b = a.lower(), b.lower()
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    # Token overlap
    sa, sb = set(a.split()), set(b.split())
    inter = len(sa & sb)
    union = len(sa | sb) or 1
    return inter / union


def get_relevant_memory_snippets(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Retrieve ranked memory entries with fields: text, score, salience, ts."""
    if len(memory_data) == 0:
        return []

    ranked: List[Dict[str, Any]] = []

    if index is not None and embedding_model is not None and EMBED_DIM > 0 and np is not None:
        try:
            vector = embed_text(query)
            # Search over all known vectors if possible
            k = min(top_k * 5, len(memory_data)) or top_k
            distances, indices = index.search(vector, k)
            keys = list(memory_data.keys())
            for i, idx in enumerate(indices[0]):
                if idx == -1 or idx >= len(keys):
                    continue
                entry = _as_entry(memory_data[keys[idx]])
                # Convert L2 distance to rough similarity in [0,1]
                d = float(distances[0][i]) if isinstance(distances, np.ndarray) else 0.0
                sim = 1.0 / (1.0 + d)
                score = 0.7 * sim + 0.3 * _recency_weight(entry.get("ts", _now_iso()))
                ranked.append({"text": entry["text"], "salience": entry.get("salience", "low"), "ts": entry.get("ts", _now_iso()), "score": float(score)})
        except Exception:
            ranked = []

    # Fallback: simple matching with token overlap + recency
    if not ranked:
        q = (query or "").strip().lower()
        for entry in _iter_entries():
            sim = _similarity_fallback(q, entry["text"].lower()) if q else 0.2
            score = 0.7 * sim + 0.3 * _recency_weight(entry.get("ts", _now_iso()))
            ranked.append({"text": entry["text"], "salience": entry.get("salience", "low"), "ts": entry.get("ts", _now_iso()), "score": float(score)})

    ranked.sort(key=lambda e: e["score"], reverse=True)
    return ranked[:top_k]


def log_interaction(user_input: str, assistant_response: str):
    """Log each interaction to a JSON file with timestamp."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user_input": user_input,
        "assistant_response": assistant_response
    }

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
    else:
        logs = []

    logs.append(entry)

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)
