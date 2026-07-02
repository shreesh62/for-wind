import os
import asyncio
from pathlib import Path
import sys
from typing import Any

import requests

try:
    from telegram import Update  # type: ignore
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters  # type: ignore
except Exception:
    Update = None  # type: ignore

# Allow running as a script: add project root to sys.path
try:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except Exception:
    pass
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_IDS = {s.strip() for s in os.getenv("TELEGRAM_ALLOWED_IDS", "").split(",") if s.strip()}

REMOTE_SERVER_URL = os.getenv("REMOTE_SERVER_URL", "http://127.0.0.1:8801").rstrip("/")
REMOTE_API_KEY = os.getenv("REMOTE_API_KEY", "")
TELEGRAM_SPEAK = os.getenv("TELEGRAM_SPEAK", "").strip().lower() in ("1", "true", "yes")

def _resolve_screenshot_path(path_str: str) -> Path | None:
    try:
        p = Path(path_str)
        if not p.is_absolute():
            p = (PROJECT_ROOT / p).resolve()
        if p.exists() and p.is_file():
            return p
        return None
    except Exception:
        return None


def _call_execute_sync(text: str, metadata: dict[str, Any]) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if REMOTE_API_KEY:
        headers["X-API-Key"] = REMOTE_API_KEY
    payload: dict[str, Any] = {"text": text, "metadata": metadata}
    if TELEGRAM_SPEAK:
        payload["speak"] = True
    resp = requests.post(f"{REMOTE_SERVER_URL}/execute", json=payload, headers=headers, timeout=60)
    try:
        data = resp.json()
    except Exception:
        data = {"ok": False, "error": f"Non-JSON response ({resp.status_code})."}
    if resp.status_code != 200:
        return {"ok": False, "error": data.get("detail") or data.get("error") or f"HTTP {resp.status_code}"}
    return data


async def start(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    if not _is_allowed(update):
        return
    await update.message.reply_text("Jarvis Telegram relay online.")


def _is_allowed(update: "Update") -> bool:
    if not ALLOWED_IDS:
        return True  # if not configured, allow for dev
    try:
        uid = str(update.effective_user.id)
        return uid in ALLOWED_IDS
    except Exception:
        return False


async def handle_message(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    if not _is_allowed(update):
        return
    text = update.message.text or ""
    if not text.strip():
        return

    metadata = {
        "source": "telegram",
        "chat_id": getattr(update.effective_chat, "id", None),
        "user_id": getattr(update.effective_user, "id", None),
        "username": getattr(update.effective_user, "username", None),
    }

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, lambda: _call_execute_sync(text, metadata))

    if not isinstance(result, dict) or not result.get("ok"):
        err = "Remote execute failed."
        if isinstance(result, dict):
            err = result.get("error") or err
        await update.message.reply_text(err)
        return

    response_text = (result.get("text") or "").strip() or "(no response)"
    screenshot_path = result.get("screenshot_path")

    if screenshot_path:
        resolved = _resolve_screenshot_path(str(screenshot_path))
        if resolved:
            try:
                with resolved.open("rb") as f:
                    await update.message.reply_photo(photo=f, caption=response_text[:900])
                return
            except Exception:
                pass

    await update.message.reply_text(response_text)


def main() -> None:
    if Update is None:
        print("python-telegram-bot is not installed. Run: pip install python-telegram-bot==20.6")
        return
    if not BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN is not set. Create a bot and export TELEGRAM_BOT_TOKEN=... in .env")
        return
    if not REMOTE_API_KEY:
        print("REMOTE_API_KEY is not set. Set REMOTE_API_KEY in .env to authenticate against the local Jarvis server.")
        return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("[Telegram] Relay started. Press Ctrl+C to stop.")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
