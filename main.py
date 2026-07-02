# main.py
import threading
import struct
import re
import asyncio
import time
import os
import importlib
import traceback
import socket
from pathlib import Path
import queue
from collections import deque

# ---------------------------------------------------------------------------
# HARD STARTUP GUARD (anti-phantom-actions)
# The legacy JARVIS entry point runs a forever loop that can open Chrome,
# Notepad, and execute commands. To stop accidental/background launches that
# the owner observed, this file refuses to run unless explicitly authorized
# with FRIDAY_ALLOW_LEGACY_MAIN=1. Tests and the new friday/ package never
# import main at module top in a way that triggers this.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if os.getenv("FRIDAY_ALLOW_LEGACY_MAIN", "").strip().lower() not in ("1", "true", "yes"):
        print(
            "[BLOCKED] Legacy main.py will not start.\n"
            "This is the old JARVIS loop that can auto-open Chrome/Notepad.\n"
            "The new system is friday/ (operator/bridge). If you really intend\n"
            "to run the legacy entry point, set FRIDAY_ALLOW_LEGACY_MAIN=1."
        )
        raise SystemExit(0)

pvporcupine = None  # type: ignore
pyaudio = None  # type: ignore
# Load environment variables (API keys in .env)
from config import get_settings

from edge_tts_voice import speak_edge, speak_edge_async, interrupt_tts
from groq_llm import query_groq
from personality import PersonalityManager
from tts_formatter import TTSFormatter
from capabilities import CapabilityRegistry
from memory.memory_controller import MemoryController
from core.capability_dispatcher import CapabilityDispatcher
from core.assistant import AssistantOrchestrator
from automation.services import AutomationServices
from automation.browser_state_tracker import BrowserStateTracker
from awareness.windows_accessibility import WindowsAccessibilityMonitor, WindowsAccessibilityUnavailable
from awareness.system_monitor import SystemMonitor
from awareness.controller import AwarenessController
from ui.ipc_server import UISocketServer, WebsocketUnavailable, UIEvent
from plugins import PluginLoader, PluginContext
from server.app import RemoteServer, RemoteServerUnavailable
from core.telemetry import TelemetryLogger

# Import services
from services.weather_service import get_weather, get_last_weather_report
from core.routine_scheduler import RoutineScheduler
from services.maps_service import get_distance_and_time

# Wake word setup
JARVIS_KEYWORD_PATH = "wake_words/jarvis_en_windows.ppn"
FRIDAY_KEYWORD_PATH = "wake_words/friday_en_windows.ppn"  # Future wake word
SETTINGS = get_settings()
ACCESS_KEY = SETTINGS.porcupine_access_key
DISABLE_WAKE_WORD = os.getenv("DISABLE_WAKE_WORD", "").strip().lower() in ("1", "true", "yes")
DISABLE_MIC = os.getenv("DISABLE_MIC", "").strip().lower() in ("1", "true", "yes")
DISABLE_TTS = os.getenv("DISABLE_TTS", "").strip().lower() in ("1", "true", "yes")
DISABLE_REMOTE_SERVER = os.getenv("DISABLE_REMOTE_SERVER", "").strip().lower() in ("1", "true", "yes")
DISABLE_BROWSER_TRACKER = os.getenv("DISABLE_BROWSER_TRACKER", "").strip().lower() in ("1", "true", "yes")
DISABLE_UI_AUTOMATION_MONITOR = os.getenv("DISABLE_UI_AUTOMATION_MONITOR", "").strip().lower() in ("1", "true", "yes")
DISABLE_CPU_ALERTS = os.getenv("DISABLE_CPU_ALERTS", "").strip().lower() in ("1", "true", "yes")
AUTO_LAUNCH_CHROME = os.getenv("AUTO_LAUNCH_CHROME", "").strip().lower() in ("1", "true", "yes")
CHROME_REMOTE_DEBUG_PORT = int(os.getenv("CHROME_REMOTE_DEBUG_PORT", "9222"))
BROWSER_DOM_STATUS_MAX_CHARS = int(os.getenv("BROWSER_DOM_STATUS_MAX_CHARS", "4000"))

# FRIDAY Bridge flag — when enabled, routes through new friday/ architecture
USE_FRIDAY_BRIDGE = os.getenv("USE_FRIDAY_BRIDGE", "").strip().lower() in ("1", "true", "yes")

BROWSER_TRACKER_AUTO_LAUNCH = os.getenv("BROWSER_TRACKER_AUTO_LAUNCH", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

FORCE_POWERSHELL_TTS = os.getenv("FORCE_POWERSHELL_TTS", "").strip().lower() in ("1", "true", "yes")

# Common phrases
END_KEYWORDS = ["that's all", "done", "thank you", "bye", "you can stop now"]
QUESTION_HINTS = ["what", "how", "why", "can you", "could you", "should i", "do you", "tell me", "explain", "?"]


def clean_text_for_tts(text: str) -> str:
    """Removes unsupported characters and prepares text for speech."""
    if not text:
        return ""
    text = re.sub(r"[^\w\s,.!?']", '', text)
    return text.strip()


class JarvisAssistant:
    def __init__(self):
        self.interrupt_event = threading.Event()
        self._command_lock = threading.Lock()
        self.awaiting_wake_word = True
        if DISABLE_MIC:
            class _NoMicIO:
                def listen(self, *args, **kwargs):
                    return ""

                def shutdown(self):
                    return

            self.io = _NoMicIO()
        else:
            try:
                from jarvis_io import JarvisIO
                self.io = JarvisIO()
            except Exception as exc:
                print(f"[⚠️] Microphone input unavailable ({exc}). Running without mic.")
                class _NoMicIO:
                    def listen(self, *args, **kwargs):
                        return ""

                    def shutdown(self):
                        return

                self.io = _NoMicIO()

        self.porcupine = None
        self.pa = None
        self.stream = None
        if DISABLE_WAKE_WORD:
            self.awaiting_wake_word = False
        elif not ACCESS_KEY or ACCESS_KEY.strip() == "":
            print(
                "[⚠️] PORCUPINE_ACCESS_KEY is missing. Running without wake word. "
                "Set PORCUPINE_ACCESS_KEY in .env to enable wake word detection."
            )
            self.awaiting_wake_word = False
        else:
            try:
                pv = importlib.import_module("pvporcupine")
            except Exception:
                pv = None
            try:
                pa_mod = importlib.import_module("pyaudio")
            except Exception:
                pa_mod = None

            if pv is None or pa_mod is None:
                print(
                    "[⚠️] Wake word dependencies are not installed. Running without wake word. "
                    "Install pvporcupine and pyaudio to enable wake word detection."
                )
                self.awaiting_wake_word = False
            else:
                try:
                    try:
                        self.porcupine = pv.create(
                            access_key=ACCESS_KEY,
                            keyword_paths=[JARVIS_KEYWORD_PATH],
                            sensitivities=[0.65]
                        )
                    except Exception:
                        keywords = getattr(pv, "KEYWORDS", None)
                        if keywords and "jarvis" in keywords:
                            self.porcupine = pv.create(
                                access_key=ACCESS_KEY,
                                keywords=["jarvis"],
                                sensitivities=[0.65]
                            )
                        else:
                            raise

                    self.pa = pa_mod.PyAudio()
                    self.stream = self.pa.open(
                        rate=self.porcupine.sample_rate,
                        channels=1,
                        format=pa_mod.paInt16,
                        input=True,
                        frames_per_buffer=self.porcupine.frame_length
                    )
                except Exception as exc:
                    print(
                        "[⚠️] Wake word initialization failed. Running without wake word. "
                        f"({exc})"
                    )
                    self.porcupine = None
                    self.stream = None
                    if self.pa is not None:
                        try:
                            self.pa.terminate()
                        except Exception:
                            pass
                    self.pa = None
                    self.awaiting_wake_word = False

        # Personality, Formatter, Capabilities
        self.personality_manager = PersonalityManager()
        self.tts_formatter = TTSFormatter(self.personality_manager)
        self.capabilities = CapabilityRegistry()
        self.awareness_controller = AwarenessController(
            enable_ui_monitor=not DISABLE_UI_AUTOMATION_MONITOR,
        )
        self.awareness_controller.start()
        if DISABLE_BROWSER_TRACKER:
            self.browser_tracker = None
        else:
            try:
                self.browser_tracker = BrowserStateTracker(
                    self.awareness_controller.dispatcher,
                    state_cache=self.awareness_controller.state_cache,
                    auto_launch=BROWSER_TRACKER_AUTO_LAUNCH,
                    remote_debug_port=CHROME_REMOTE_DEBUG_PORT,
                )
                self.browser_tracker.start()
            except Exception:
                self.browser_tracker = None
        # Telemetry before services so we can pass it in
        self.telemetry = TelemetryLogger(buffer_size=300, file_path="logs/telemetry.log")
        self.automation_services = AutomationServices(
            headless=True,
            use_chrome_profile=True,
            chrome_profile="Default",
            remote_debug_port=CHROME_REMOTE_DEBUG_PORT,
            auto_launch=AUTO_LAUNCH_CHROME,
            awareness_state=self.awareness_controller.state_cache,
            telemetry=self.telemetry,
        )
        self.dispatcher = CapabilityDispatcher(
            registry=self.capabilities,
            weather_handler=get_weather,
            distance_handler=get_distance_and_time,
            automation_services=self.automation_services,
            telemetry=self.telemetry,
        )
        self.fixed_responses = {
            "fuck you": "Respectfully, fuck you too.",
            "who are you": "I’m JARVIS, your AI assistant.",
            "who made you": "I was created by Shreesh.",
        }
        self.memory = MemoryController()
        # Ensure the Final Product Vision is seeded once for planning context
        try:
            self.memory.ensure_vision_memory()
        except Exception:
            pass
        self.orchestrator = AssistantOrchestrator(
            memory=self.memory,
            dispatcher=self.dispatcher,
            personality_manager=self.personality_manager,
            llm_callable=query_groq,
            fixed_responses=self.fixed_responses,
            automation=self.automation_services,
            awareness_state=self.awareness_controller.state_cache,
        )
        
        # HARD ASSERTION: CognitiveLoop must be initialized when COGNITIVE_MODE=1
        if os.getenv("COGNITIVE_MODE") == "1" and self.orchestrator._cognitive_loop is None:
            raise RuntimeError("COGNITIVE_MODE enabled but CognitiveLoop is not initialized")

        # FRIDAY Bridge — new architecture (USE_FRIDAY_BRIDGE=1 to activate)
        self.friday_bridge = None
        if USE_FRIDAY_BRIDGE:
            try:
                from friday.bridge import FridayBridge
                from friday.memory import FridayMemory
                from friday.models.router import ModelRouter
                from friday.models.providers.nvidia_provider import NvidiaProvider
                from friday.models.providers.groq_provider import GroqProvider

                # Initialize model router (NVIDIA primary, Groq fallback)
                model_router = ModelRouter()
                nvidia = NvidiaProvider()
                groq = GroqProvider()
                if nvidia.available:
                    model_router.register_provider(nvidia)
                if groq.available:
                    model_router.register_provider(groq)

                # Initialize FRIDAY memory (bridges legacy memory + NVIDIA embeddings)
                friday_memory = FridayMemory(
                    data_dir="friday_data",
                    legacy_memory=self.memory,
                    embedding_provider=nvidia if nvidia.available else None,
                )

                # Initialize the bridge
                self.friday_bridge = FridayBridge(
                    automation_services=self.automation_services,
                    state_cache=self.awareness_controller.state_cache,
                    llm_callable=query_groq,
                    model_router=model_router,
                )
                self.friday_memory = friday_memory
                print("[🧠] FRIDAY Bridge active (NVIDIA-primary routing)")
            except Exception as exc:
                print(f"[⚠️] FRIDAY Bridge failed to initialize: {exc}")
                self.friday_bridge = None

        # Awareness & UI bridges (optional)
        try:
            self.accessibility_monitor = WindowsAccessibilityMonitor()
        except WindowsAccessibilityUnavailable:
            self.accessibility_monitor = None

        try:
            self.ui_socket = UISocketServer()
            self.ui_loop = asyncio.new_event_loop()
            threading.Thread(target=self._start_ui_server, daemon=True).start()
            self.ui_socket.register_handler(self._handle_ui_message)
        except WebsocketUnavailable:
            self.ui_socket = None
            self.ui_loop = None

        self.manual_commands: "queue.Queue[str]" = queue.Queue()
        self._recent_conversation: deque = deque(maxlen=10)
        self._alert_history: deque = deque(maxlen=5)
        self.system_monitor = SystemMonitor()
        self.shutdown_event = threading.Event()
        self._last_alerts = {"cpu": 0.0, "battery": 0.0}
        self._current_browser_summary: dict = {}
        self._last_browser_error: str | None = None
        self.status_thread = threading.Thread(
            target=self._broadcast_system_status_loop,
            daemon=True,
        )
        self.status_thread.start()
        self._current_window_state: dict = {}
        self.window_thread = None
        if self.accessibility_monitor:
            self.window_thread = threading.Thread(
                target=self._window_monitor_loop,
                daemon=True,
            )
            self.window_thread.start()
        else:
            # Fallback: use awareness controller state if available
            self.window_thread = threading.Thread(
                target=self._awareness_window_loop,
                daemon=True,
            )
            self.window_thread.start()

        self.browser_summary_thread = threading.Thread(
            target=self._browser_awareness_loop,
            daemon=True,
        )
        self.browser_summary_thread.start()

        self.scheduler = RoutineScheduler()
        self.scheduler.add_daily_task("morning_briefing", 9, 0, self._run_morning_briefing)
        self.scheduler.add_interval_task("battery_check", 300, self._check_battery_reminder)
        self.scheduler.start()
        self._last_persona_change = time.time()
        self.telemetry.log("startup", {"personas": list(self.personality_manager.available_personas.keys())})

        # Remote HTTP server (optional dependency)
        if DISABLE_REMOTE_SERVER:
            self.remote_server = None
        else:
            try:
                host = os.getenv("REMOTE_HOST", "127.0.0.1")
                port = int(os.getenv("REMOTE_PORT", "8801"))
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    # On Windows, SO_REUSEADDR can mask that the port is already in use.
                    sock.bind((host, port))
                    sock.close()
                except Exception:
                    try:
                        sock.close()
                    except Exception:
                        pass
                    raise RemoteServerUnavailable(f"Remote port {host}:{port} is already in use")

                self.remote_server = RemoteServer(
                    self.manual_commands,
                    host=host,
                    port=port,
                    status_provider=self._remote_status_payload,
                    api_key=SETTINGS.remote_api_key,
                    persona_setter=self._handle_persona_change,
                    execute_handler=self.execute_text_command,
                )
                self.remote_server.start()
                print(
                    f"[🌐] Remote control server running at http://{host}:{port}"
                )
            except RemoteServerUnavailable:
                self.remote_server = None

        # Plugin loader
        self.plugin_loader = PluginLoader(Path(__file__).resolve().parent / "plugins")
        self.plugin_loader.load_plugins(
            PluginContext(
                registry=self.capabilities,
                dispatcher=self.dispatcher,
            )
        )

    def listen_for_jarvis(self):
        if not self.porcupine or not self.stream:
            # Wake-word disabled/unavailable; proceed immediately.
            self.awaiting_wake_word = False
            return True

        print("[🔊] Waiting for wake word 'Jarvis'...")
        while self.awaiting_wake_word:
            pcm = self.stream.read(self.porcupine.frame_length, exception_on_overflow=False)
            pcm_unpacked = struct.unpack_from("h" * self.porcupine.frame_length, pcm)
            result = self.porcupine.process(pcm_unpacked)
            if result >= 0:
                print("[✅] Wake word 'Jarvis' detected!")
                try:
                    interrupt_tts()
                except Exception:
                    pass
                self.awaiting_wake_word = False
                return True
        return False

    def is_question(self, text: str) -> bool:
        text = text.strip().lower()
        return text.endswith("?") or any(text.startswith(hint) for hint in QUESTION_HINTS)

    def handle_command(self, command: str):
        pending = command

        while True:
            if not pending or not pending.strip():
                try:
                    self._speak_text("Can you please repeat that?")
                except Exception:
                    pass
                self.awaiting_wake_word = not DISABLE_WAKE_WORD
                return

            command_lower = pending.lower().strip()
            print(f"[🎤] User: {command_lower}")
            self.telemetry.log("command_received", {"text": command_lower[:120]})

            # Stop phrases handled locally
            if any(phrase in command_lower for phrase in END_KEYWORDS):
                final_response = "Alright. Standing by."
                self._speak_and_emit(pending, final_response)
                self.awaiting_wake_word = not DISABLE_WAKE_WORD
                self.telemetry.log("command_completed", {"handled": True, "category": "stop"})
                return

            with self._command_lock:
                try:
                    result = self.orchestrator.process_command(pending)
                except KeyboardInterrupt as exc:
                    msg = "Okay. Cancelled that." 
                    print(f"[⚠️] Command processing interrupted: {exc}")
                    try:
                        traceback.print_exc()
                    except Exception:
                        pass
                    try:
                        self.telemetry.log("command_interrupted", {"error": str(exc)[:200]})
                    except Exception:
                        pass
                    self._speak_and_emit(pending, msg)
                    self.awaiting_wake_word = not DISABLE_WAKE_WORD
                    return
                except Exception as exc:
                    msg = f"Sorry, I hit an error while processing that. ({exc})"
                    print(f"[⚠️] Command processing failed: {exc}")
                    try:
                        self.telemetry.log("command_error", {"error": str(exc)[:200]})
                    except Exception:
                        pass
                    self._speak_and_emit(pending, msg)
                    self.awaiting_wake_word = not DISABLE_WAKE_WORD
                    return
            final_response = result.final_response
            print(f"[🎭] JARVIS Final: {final_response}")

            self._speak_and_emit(pending, final_response)
            self.telemetry.log(
                "command_completed",
                {
                    "handled": result.handled,
                    "response_length": len(final_response),
                },
            )

            if self.is_question(final_response):
                try:
                    interrupt_tts()
                except Exception:
                    pass
                if DISABLE_MIC:
                    self.awaiting_wake_word = not DISABLE_WAKE_WORD
                    return
                follow_up = self.io.listen()
                if not follow_up:
                    self.awaiting_wake_word = not DISABLE_WAKE_WORD
                    return
                pending = follow_up
                continue

            self.awaiting_wake_word = not DISABLE_WAKE_WORD
            return

    def _extract_screenshot_path(self, text: str) -> str | None:
        try:
            m = re.search(r"(?:saved to|saved at)\s+(.+?)(?:\.|$)", text, flags=re.IGNORECASE)
            if not m:
                return None
            candidate = (m.group(1) or "").strip().strip('"')
            if not candidate:
                return None
            lower = candidate.lower()
            if not lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                return None
            return candidate
        except Exception:
            return None

    def execute_text_command(self, text: str, metadata: dict | None = None) -> dict:
        command = (text or "").strip()
        if not command:
            return {"ok": False, "error": "Command text cannot be empty."}

        meta = metadata or {}
        command_lower = command.lower().strip()

        if any(phrase in command_lower for phrase in END_KEYWORDS):
            final_response = "Alright. Standing by."
            if bool(meta.get("speak")):
                try:
                    self._speak_text(final_response)
                except Exception:
                    pass
            try:
                self.telemetry.log("remote_execute_completed", {"handled": True, "category": "stop"})
            except Exception:
                pass
            return {
                "ok": True,
                "text": final_response,
                "handled": True,
                "screenshot_path": None,
                "meta": {"source": meta.get("source")},
            }

        try:
            try:
                self.telemetry.log(
                    "remote_execute_received",
                    {
                        "text": command_lower[:120],
                        "source": meta.get("source"),
                    },
                )
            except Exception:
                pass

            # --- FRIDAY Bridge routing (new architecture) ---
            if self.friday_bridge:
                try:
                    wake_word = meta.get("wake_word")  # "jarvis" or "friday" if detected
                    bridge_result = self.friday_bridge.process(command, wake_word=wake_word)
                    final_response = bridge_result.response

                    # Record in FRIDAY memory
                    if hasattr(self, 'friday_memory'):
                        self.friday_memory.record_turn(
                            user_text=command,
                            assistant_response=final_response,
                            mode=bridge_result.mode.value,
                            complexity=int(bridge_result.complexity),
                        )

                    if bool(meta.get("speak")):
                        try:
                            self._speak_text(final_response)
                        except Exception:
                            pass

                    self.telemetry.log(
                        "friday_bridge_completed",
                        {
                            "mode": bridge_result.mode.value,
                            "complexity": int(bridge_result.complexity),
                            "handled": bridge_result.handled,
                        },
                    )

                    return {
                        "ok": True,
                        "text": final_response,
                        "handled": bridge_result.handled,
                        "screenshot_path": None,
                        "meta": {
                            "source": meta.get("source"),
                            "mode": bridge_result.mode.value,
                            "complexity": int(bridge_result.complexity),
                        },
                    }
                except Exception as exc:
                    # Bridge failed — fall through to legacy orchestrator
                    self.telemetry.log("friday_bridge_error", {"error": str(exc)[:200]})

            # --- Legacy orchestrator path ---
            with self._command_lock:
                try:
                    result = self.orchestrator.process_command(command)
                except KeyboardInterrupt as exc:
                    try:
                        traceback.print_exc()
                    except Exception:
                        pass
                    try:
                        self.telemetry.log("remote_execute_interrupted", {"error": str(exc)[:200]})
                    except Exception:
                        pass
                    return {"ok": False, "error": "Command cancelled."}
            final_response = result.final_response
            screenshot_path = self._extract_screenshot_path(final_response)

            if bool(meta.get("speak")):
                try:
                    self._speak_text(final_response)
                except Exception:
                    pass

            try:
                self._emit_ui_event(
                    "conversation",
                    {
                        "user": command,
                        "assistant": final_response,
                        "window": self._current_window_info(),
                        "weather": get_last_weather_report(),
                        "remote": True,
                        "metadata": meta,
                    },
                )
                self._emit_system_status()
            except Exception:
                pass

            self._recent_conversation.append(
                {
                    "user": command,
                    "assistant": final_response,
                    "timestamp": time.time(),
                }
            )

            try:
                self.telemetry.log(
                    "remote_execute_completed",
                    {
                        "handled": bool(result.handled),
                        "response_length": len(final_response),
                    },
                )
            except Exception:
                pass

            return {
                "ok": True,
                "text": final_response,
                "handled": bool(result.handled),
                "screenshot_path": screenshot_path,
                "meta": {"source": meta.get("source")},
            }
        except Exception as exc:
            try:
                self.telemetry.log("remote_execute_error", {"error": str(exc)[:200]})
            except Exception:
                pass
            return {"ok": False, "error": str(exc)}

    def _speak_text(self, assistant_text: str) -> None:
        tts_ready = self.tts_formatter.format_text(assistant_text)
        tts_ready = clean_text_for_tts(tts_ready)

        spoke = False
        try:
            if not FORCE_POWERSHELL_TTS:
                spoke = bool(speak_edge_async(tts_ready))
        except Exception:
            spoke = False

        if not DISABLE_TTS and not spoke and hasattr(self.io, "speak"):
            try:
                print("[🔊] Speaking via pyttsx3 (fallback)")
                self.io.speak(tts_ready)
            except Exception:
                pass

    def _speak_and_emit(self, user_text: str, assistant_text: str) -> None:
        # First apply formatter (humanize URLs, tone), then clean for TTS
        # Awareness hint injection (short and optional)
        awareness_hints = {}
        try:
            if self.awareness_controller:
                summary = self.awareness_controller.state_cache.get_browser_summary()
                if summary and isinstance(summary, dict):
                    hints = summary.get("hints") or {}
                    if isinstance(hints, dict):
                        awareness_hints = {
                            k: bool(v) for k, v in hints.items() if k in {
                                "has_login", "has_form", "has_consent", "has_error_modal"
                            }
                        }
        except Exception:
            awareness_hints = {}

        spoken_suffix = ""
        if awareness_hints:
            parts = []
            if awareness_hints.get("has_login"):
                parts.append("a login form")
            if awareness_hints.get("has_consent"):
                parts.append("a consent dialog")
            if awareness_hints.get("has_error_modal"):
                parts.append("a modal dialog")
            if parts:
                spoken_suffix = " Also, I can see " + ", ".join(parts) + "."

        tts_ready = self.tts_formatter.format_text(assistant_text + spoken_suffix)
        tts_ready = clean_text_for_tts(tts_ready)
        spoke = False
        try:
            if not FORCE_POWERSHELL_TTS:
                spoke = bool(speak_edge_async(tts_ready))
        except Exception:
            pass

        # Fallback to local pyttsx3 (JarvisIO.speak) if Edge TTS is unavailable/fails.
        # Respect DISABLE_TTS (do not speak at all if explicitly disabled).
        if not DISABLE_TTS and not spoke and hasattr(self.io, "speak"):
            try:
                print("[🔊] Speaking via pyttsx3 (fallback)")
                self.io.speak(tts_ready)
            except Exception:
                pass

        self._emit_ui_event(
            "conversation",
            {
                "user": user_text,
                "assistant": assistant_text,
                "window": self._current_window_info(),
                "weather": get_last_weather_report(),
                "awareness_hints": awareness_hints,
            },
        )
        self._emit_system_status()
        self._recent_conversation.append(
            {
                "user": user_text,
                "assistant": assistant_text,
                "timestamp": time.time(),
            }
        )
        self.telemetry.log(
            "conversation_turn",
            {
                "user_text": user_text[:160],
                "assistant_text": assistant_text[:160],
            },
        )

    def _handle_ui_message(self, message: dict) -> None:
        if not isinstance(message, dict):
            return
        if message.get("type") != "manual_command":
            return
        payload = message.get("payload", {})
        if not isinstance(payload, dict):
            return
        text = payload.get("text", "")
        if not text:
            return
        self.manual_commands.put(text)
        self.telemetry.log("manual_command_received", {"text": text[:160]})
        self._emit_ui_event(
            "manual_received",
            {
                "user": text,
            },
        )

    def _get_manual_command(self) -> str | None:
        try:
            return self.manual_commands.get_nowait()
        except queue.Empty:
            return None

    def _start_ui_server(self) -> None:
        if not self.ui_socket or not self.ui_loop:
            return
        asyncio.set_event_loop(self.ui_loop)
        self.ui_loop.run_until_complete(self.ui_socket.start())
        self.ui_loop.run_forever()

    def _emit_ui_event(self, event_type: str, payload: dict) -> None:
        if not self.ui_socket or not self.ui_loop:
            return
        event = UIEvent(type=event_type, payload=payload)
        asyncio.run_coroutine_threadsafe(self.ui_socket.broadcast(event), self.ui_loop)

    def _current_window_info(self) -> dict:
        return dict(self._current_window_state)

    def _emit_system_status(self) -> None:
        if not self.system_monitor or not self.ui_socket:
            return
        snapshot = self.system_monitor.snapshot()
        self._emit_ui_event("system_status", snapshot.as_dict())
        self._maybe_emit_alert(snapshot)

    def _broadcast_system_status_loop(self) -> None:
        while not self.shutdown_event.is_set():
            self._emit_system_status()
            if self.shutdown_event.wait(15):
                break

    def _window_monitor_loop(self) -> None:
        if not self.accessibility_monitor:
            return
        last_payload = None
        while not self.shutdown_event.is_set():
            payload = self.accessibility_monitor.to_dict()
            if payload != last_payload:
                self._current_window_state = payload or {}
                self._emit_ui_event("window_update", self._current_window_state)
                last_payload = payload
            if self.shutdown_event.wait(5):
                break

    def _awareness_window_loop(self) -> None:
        if not self.awareness_controller:
            return
        last_handle = None
        while not self.shutdown_event.is_set():
            context = self.awareness_controller.state_cache.get_window()
            if context and context.handle != last_handle:
                payload = {
                    "title": context.title,
                    "handle": context.handle,
                    "class_name": context.app_exe,
                }
                self._current_window_state = payload
                self._emit_ui_event("window_update", payload)
                last_handle = context.handle
            if self.shutdown_event.wait(2):
                break

    def _browser_awareness_loop(self) -> None:
        if not self.awareness_controller:
            return
        last_summary = None
        last_error = None
        while not self.shutdown_event.is_set():
            summary = self.awareness_controller.state_cache.get_browser_summary()
            if summary and summary != last_summary:
                self._current_browser_summary = summary
                self._emit_ui_event("browser_summary", summary)
                last_summary = summary

            error = self.awareness_controller.state_cache.get_browser_error()
            if error and error != last_error:
                self._last_browser_error = error
                self._emit_alert(f"Browser tracker: {error}")
                last_error = error

            if self.shutdown_event.wait(2):
                break

    def _maybe_emit_alert(self, snapshot) -> None:
        now = time.time()
        if (not DISABLE_CPU_ALERTS) and snapshot.cpu_percent is not None and snapshot.cpu_percent >= 85:
            if now - self._last_alerts["cpu"] > 120:
                self._emit_alert(f"CPU usage is high at {snapshot.cpu_percent:.0f}%.")
                self._last_alerts["cpu"] = now

        if (
            snapshot.battery_percent is not None
            and snapshot.battery_percent <= 20
            and (snapshot.power_plugged is False or snapshot.power_plugged is None)
        ):
            if now - self._last_alerts["battery"] > 180:
                self._emit_alert(
                    f"Battery is low at {snapshot.battery_percent:.0f}%. Consider plugging in."
                )
                self._last_alerts["battery"] = now

    def _emit_alert(self, message: str) -> None:
        print(f"[⚠️] {message}")
        self._emit_ui_event("alert", {"message": message})
        self._alert_history.append({"message": message, "timestamp": time.time()})

    def _sanitize_browser_summary_for_status(self, summary: dict | None) -> dict:
        if not summary or not isinstance(summary, dict):
            return {}
        sanitized = dict(summary)
        dom = sanitized.get("dom")
        if isinstance(dom, str):
            sanitized["dom_len"] = len(dom)
            if len(dom) > BROWSER_DOM_STATUS_MAX_CHARS:
                sanitized["dom"] = dom[:BROWSER_DOM_STATUS_MAX_CHARS]
                sanitized["dom_truncated"] = True
            else:
                sanitized["dom_truncated"] = False
        return sanitized

    def _remote_status_payload(self) -> dict:
        browser_payload = self._sanitize_browser_summary_for_status(self._current_browser_summary)
        payload = {
            "pending_manual_commands": list(self.manual_commands.queue),
            "recent_conversation": list(self._recent_conversation),
            "system": self.system_monitor.snapshot().as_dict() if self.system_monitor else {},
            "window": self._current_window_state,
            "browser": browser_payload,
            "awareness": self._awareness_snapshot(),
            "ocr": {
                "text": self.awareness_controller.state_cache.get_ocr_text() if self.awareness_controller else None,
                "error": self.awareness_controller.state_cache.get_ocr_error() if self.awareness_controller else None,
                "confidence": self.awareness_controller.state_cache.get_ocr_confidence() if self.awareness_controller else None,
                "updated_at": self.awareness_controller.state_cache.ocr_last_updated() if self.awareness_controller else None,
            },
            "alerts": list(self._alert_history),
            "weather": get_last_weather_report(),
            "persona": {
                "current": self.personality_manager.persona,
                "tone": self.personality_manager.get_personality().get("tone"),
                "pause": self.personality_manager.get_personality().get("pause_style"),
                "last_changed": self._last_persona_change,
            },
            "telemetry": self.telemetry.snapshot(limit=15),
        }
        return payload

    def _awareness_snapshot(self) -> dict:
        if not self.awareness_controller:
            return {}
        context = self.awareness_controller.state_cache.get_window()
        event = self.awareness_controller.state_cache.get_last_event()
        process = self.awareness_controller.state_cache.get_last_process()
        browser = self._sanitize_browser_summary_for_status(
            self.awareness_controller.state_cache.get_browser_summary()
        )
        return {
            "window": {
                "title": context.title if context else None,
                "app": context.app_exe if context else None,
                "pid": context.process_id if context else None,
            },
            "last_event_type": event.event_type.value if event else None,
            "last_process": process.as_dict() if process else None,
            "browser": browser or {},
            "ocr": {
                "text": self.awareness_controller.state_cache.get_ocr_text(),
                "error": self.awareness_controller.state_cache.get_ocr_error(),
                "confidence": self.awareness_controller.state_cache.get_ocr_confidence(),
                "updated_at": self.awareness_controller.state_cache.ocr_last_updated(),
            },
        }

    def _run_morning_briefing(self) -> None:
        weather_report = get_last_weather_report()
        weather_message = weather_report["message"] if weather_report else "Weather data is not available yet."
        system_snapshot = self.system_monitor.snapshot().describe() if self.system_monitor else "System telemetry unavailable."
        message = f"Good morning. {weather_message} Current system status: {system_snapshot}."
        self._emit_alert("Morning briefing triggered.")
        try:
            speak_edge(message)
        except Exception:
            if not DISABLE_TTS and hasattr(self.io, "speak"):
                try:
                    self.io.speak(message)
                except Exception:
                    pass

    def _check_battery_reminder(self) -> None:
        if not self.system_monitor:
            return
        snapshot = self.system_monitor.snapshot()
        if snapshot.battery_percent is None:
            return
        if snapshot.battery_percent <= 30 and not snapshot.power_plugged:
            reminder = f"Battery reminder: charge is at {snapshot.battery_percent:.0f} percent."
            self._emit_alert(reminder)
            try:
                speak_edge(reminder)
            except Exception:
                if not DISABLE_TTS and hasattr(self.io, "speak"):
                    try:
                        self.io.speak(reminder)
                    except Exception:
                        pass
            self.telemetry.log("alert", {"type": "battery", "level": snapshot.battery_percent})

    def _handle_persona_change(self, persona: str) -> None:
        if persona not in self.personality_manager.available_personas:
            raise ValueError(f"Unknown persona '{persona}'.")
        self.personality_manager.set_persona(persona)
        self._last_persona_change = time.time()
        self.personality_manager.update_context("idle")
        self._emit_alert(f"Persona set to {persona.title()}.")
        self.telemetry.log("persona_changed", {"persona": persona})

    def run(self):
        print("🤖 JARVIS is online.")
        try:
            while True:
                if DISABLE_MIC:
                    # Server-only mode: keep process alive for remote /execute and UI/manual commands.
                    manual_command = self._get_manual_command()
                    if manual_command:
                        self.awaiting_wake_word = False
                        self.handle_command(manual_command)
                        continue
                    if self.shutdown_event.wait(0.25):
                        break
                    continue

                manual_command = self._get_manual_command()
                if manual_command:
                    self.awaiting_wake_word = False
                    self.handle_command(manual_command)
                    continue

                if self.awaiting_wake_word and not DISABLE_WAKE_WORD:
                    self.listen_for_jarvis()

                try:
                    interrupt_tts()
                except Exception:
                    pass
                try:
                    command = self.io.listen()
                except Exception as exc:
                    print(f"[⚠️] Microphone listen failed: {exc}")
                    try:
                        self.telemetry.log("mic_error", {"error": str(exc)[:200]})
                    except Exception:
                        pass
                    self.awaiting_wake_word = not DISABLE_WAKE_WORD
                    continue
                if not command:
                    try:
                        self._speak_text("Apologies, I didn’t catch that.")
                    except Exception:
                        pass
                    self.awaiting_wake_word = not DISABLE_WAKE_WORD
                    continue

                try:
                    self.handle_command(command)
                except Exception as exc:
                    print(f"[⚠️] Unexpected runtime error: {exc}")
                    try:
                        self.telemetry.log("runtime_error", {"error": str(exc)[:200]})
                    except Exception:
                        pass
                    self.awaiting_wake_word = not DISABLE_WAKE_WORD

        except KeyboardInterrupt:
            print("👋 Exiting Jarvis...")

        finally:
            if self.ui_socket and self.ui_loop:
                future = asyncio.run_coroutine_threadsafe(self.ui_socket.stop(), self.ui_loop)
                try:
                    future.result(timeout=2)
                except Exception:
                    pass
                self.ui_loop.call_soon_threadsafe(self.ui_loop.stop)

            self.shutdown_event.set()
            if hasattr(self, "status_thread") and self.status_thread.is_alive():
                self.status_thread.join(timeout=3)
            if self.window_thread and self.window_thread.is_alive():
                self.window_thread.join(timeout=3)
            if self.browser_tracker:
                self.browser_tracker.stop()
            if self.awareness_controller:
                self.awareness_controller.stop()
            if self.remote_server:
                self.remote_server.stop()

            if self.stream is not None:
                try:
                    self.stream.stop_stream()
                except Exception:
                    pass
                try:
                    self.stream.close()
                except Exception:
                    pass
            if self.pa is not None:
                try:
                    self.pa.terminate()
                except Exception:
                    pass
            self.io.shutdown()
if __name__ == "__main__":
    assistant = JarvisAssistant()
    assistant.run()
