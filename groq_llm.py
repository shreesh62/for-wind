import re
import time
import os
from config import get_settings

try:
    from groq import Groq
except Exception:
    Groq = None  # type: ignore

SETTINGS = get_settings()
_groq_client = None

_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "1536"))
_MAX_CONTINUATIONS = int(os.getenv("GROQ_MAX_CONTINUATIONS", "2"))
_MAX_OUTPUT_CHARS = int(os.getenv("GROQ_MAX_OUTPUT_CHARS", "12000"))

def remove_think_blocks(text):
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

def clean_output(text):
    text = remove_think_blocks(text)
    text = text.replace("Jarvis:", "").replace("JARVIS:", "").strip()
    return text

def _stringify_memory(memory_snippet):
    if not memory_snippet:
        return ""
    if isinstance(memory_snippet, str):
        return memory_snippet
    if isinstance(memory_snippet, (list, tuple)):
        return "\n".join(str(item) for item in memory_snippet if item)
    if isinstance(memory_snippet, dict):
        return "\n".join(f"{key}: {value}" for key, value in memory_snippet.items())
    return str(memory_snippet)


def query_groq(prompt, memory_snippet=""):
    memory_text = _stringify_memory(memory_snippet)
    final_prompt = (memory_text + "\n\n" + prompt).strip()

    api_key = getattr(SETTINGS, "groq_api_key", None)
    if not api_key:
        return "[LLM unavailable] GROQ_API_KEY is not set."

    if Groq is None:
        return "[LLM unavailable] 'groq' package is not installed in this environment. Install it to enable LLM responses."

    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=api_key)

    last_err = None
    for attempt in range(1, 4):  # up to 3 attempts
        try:
            system_msg = {
                "role": "system",
                "content": (
                    "You are JARVIS, a realistic, intelligent voice assistant created by Shreesh. "
                    "You never refer to yourself as a human, boyfriend, or god. Your tone is helpful, witty, and sharp — like a true AI companion. "
                    "Avoid repeating the user's prompt or including random hallucinations."
                ),
            }

            messages = [system_msg, {"role": "user", "content": final_prompt}]
            out_parts = []
            finish_reason = None

            for cont_idx in range(_MAX_CONTINUATIONS + 1):
                response = _groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=messages,
                    temperature=0.7,
                    max_tokens=_MAX_TOKENS,
                )

                try:
                    finish_reason = getattr(response.choices[0], "finish_reason", None)
                except Exception:
                    finish_reason = None

                raw = (response.choices[0].message.content or "").strip()
                cleaned = clean_output(raw)
                piece = cleaned if cleaned else raw
                if piece:
                    out_parts.append(piece)

                combined = "\n".join([p for p in out_parts if p]).strip()
                if combined and len(combined) >= _MAX_OUTPUT_CHARS:
                    return combined[:_MAX_OUTPUT_CHARS].rstrip()

                if finish_reason != "length":
                    break

                if cont_idx >= _MAX_CONTINUATIONS:
                    break

                messages = [
                    system_msg,
                    {"role": "user", "content": final_prompt},
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": "Continue exactly where you left off. Do not repeat earlier content.",
                    },
                ]

            return "\n".join([p for p in out_parts if p]).strip()
        except Exception as e:
            msg = str(e) if e else "Unknown error"
            last_err = msg
            # Reinitialize client on protocol/connection errors once
            if attempt == 1 and ("protocol error" in msg.lower() or "connection" in msg.lower()):
                try:
                    time.sleep(0.6)
                    # recreate client
                    globals()["_groq_client"] = Groq(api_key=api_key)
                except Exception:
                    pass
            # Backoff and retry
            if attempt < 3:
                time.sleep(0.8 * attempt)
                continue
            break

    return f"[ERROR from Groq API]: {last_err or 'Unknown error'}"
