import asyncio
try:
    import edge_tts  # type: ignore
except Exception:
    edge_tts = None  # type: ignore
import os
import re
import time
import tempfile
try:
    from playsound import playsound  # type: ignore
except Exception:
    playsound = None  # type: ignore
import subprocess
import sys

# Track running playback subprocess for interrupt support
_PLAY_PROC = None  # type: ignore

VOICE = "en-GB-RyanNeural"
RATE = "+10%"
VOLUME = "+0%"
PITCH = "+0Hz"

DISABLE_TTS = os.getenv("DISABLE_TTS", "").strip().lower() in ("1", "true", "yes")
DISABLE_EDGE_TTS = os.getenv("DISABLE_EDGE_TTS", "").strip().lower() in ("1", "true", "yes")

# If Edge TTS fails repeatedly (network/service issues), back off to avoid spam/CPU.
_EDGE_TTS_DISABLED_UNTIL = 0.0


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def _edge_tts_available_now() -> bool:
    global _EDGE_TTS_DISABLED_UNTIL
    if _env_flag("DISABLE_TTS"):
        return False
    if _env_flag("DISABLE_EDGE_TTS"):
        return False
    if time.time() < _EDGE_TTS_DISABLED_UNTIL:
        return False
    return True


def _edge_tts_cooldown(seconds: float = 300.0) -> None:
    global _EDGE_TTS_DISABLED_UNTIL
    _EDGE_TTS_DISABLED_UNTIL = max(_EDGE_TTS_DISABLED_UNTIL, time.time() + float(seconds))

def clean_text(text):
    # Remove emojis
    text = re.sub(r'[^\w\s.,!?\'\"-]', '', text)

    # Optional: Remove multiple spaces caused by cleanup
    text = re.sub(r'\s+', ' ', text).strip()
    return text

async def generate_tts(text, filename="voice.mp3"):
    if edge_tts is None:
        raise RuntimeError("edge-tts is not installed")
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE, volume=VOLUME, pitch=PITCH)
    await communicate.save(filename)

def speak_edge(text):
    print(f"[🔊 Edge TTS] Speaking: {text}")
    if not _edge_tts_available_now():
        return
    if edge_tts is None or playsound is None:
        print("[⚠️] Edge TTS is not available. Install edge-tts and playsound to enable speech.")
        return
    clean = clean_text(text)

    tmp = tempfile.NamedTemporaryFile(prefix="edge_tts_", suffix=".mp3", delete=False)
    filename = tmp.name
    tmp.close()

    try:
        try:
            asyncio.run(generate_tts(clean, filename))
        except Exception as e:
            print(f"[⚠️] Edge TTS generation failed: {e}")
            _edge_tts_cooldown()
            return

        try:
            playsound(filename)
        except Exception:
            # Retry once after a short delay for transient MCI init errors
            time.sleep(0.25)
            try:
                playsound(filename)
            except Exception as e:
                print(f"[⚠️] Edge TTS playback failed: {e}")
                _edge_tts_cooldown()
    finally:
        try:
            if os.path.exists(filename):
                os.remove(filename)
        except Exception:
            pass


def speak_edge_async(text: str):
    """Non-blocking TTS playback using a subprocess. Use interrupt_tts() to stop.

    Spawns a Python subprocess that calls playsound on a generated MP3.
    The subprocess will exit when playback completes.
    """
    global _PLAY_PROC
    # If something is already playing, stop it first
    interrupt_tts()

    if not _edge_tts_available_now():
        return False

    if edge_tts is None:
        return False

    clean = clean_text(text)
    tmp = tempfile.NamedTemporaryFile(prefix="edge_tts_", suffix=".mp3", delete=False)
    filename = tmp.name
    tmp.close()

    async def _gen():
        communicate = edge_tts.Communicate(clean, VOICE, rate=RATE, volume=VOLUME, pitch=PITCH)
        await communicate.save(filename)

    try:
        asyncio.run(_gen())
    except Exception as e:
        try:
            if os.path.exists(filename):
                os.remove(filename)
        except Exception:
            pass
        print(f"[⚠️] Edge TTS generation failed: {e}")
        _edge_tts_cooldown()
        return False

    # Launch a subprocess that plays the file and deletes it afterwards
    player_code = (
        "import time,os,sys; "
        "from playsound import playsound; "
        "f=sys.argv[1]; "
        "try:\n playsound(f)\n finally:\n  time.sleep(0.05); "
        "\n  "+"try:\n   os.remove(f)\n  except Exception: pass"
    )
    _PLAY_PROC = subprocess.Popen([sys.executable, "-c", player_code, filename])
    return True


def interrupt_tts():
    """Stop current non-blocking TTS playback if any."""
    global _PLAY_PROC
    if _PLAY_PROC is not None:
        try:
            _PLAY_PROC.terminate()
        except Exception:
            pass
        try:
            _PLAY_PROC.wait(timeout=1)
        except Exception:
            pass
        _PLAY_PROC = None
