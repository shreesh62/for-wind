import sys
import types
import threading
import queue
import os
import subprocess

import pyttsx3

try:
    import winsound
except Exception:  # pragma: no cover
    winsound = None  # type: ignore

try:
    import distutils.version  # type: ignore
except Exception:
    try:
        from setuptools._distutils.version import LooseVersion  # type: ignore
        distutils_mod = types.ModuleType("distutils")
        distutils_mod.__path__ = []  # type: ignore[attr-defined]
        version_mod = types.ModuleType("distutils.version")
        version_mod.LooseVersion = LooseVersion  # type: ignore[attr-defined]
        distutils_mod.version = version_mod  # type: ignore[attr-defined]
        sys.modules.setdefault("distutils", distutils_mod)
        sys.modules.setdefault("distutils.version", version_mod)
    except Exception:
        try:
            from packaging.version import parse as _parse_version  # type: ignore

            class LooseVersion:  # type: ignore[no-redef]
                def __init__(self, v: object) -> None:
                    self._v = _parse_version(str(v))

                def __str__(self) -> str:
                    return str(self._v)

                def __repr__(self) -> str:
                    return f"LooseVersion({self._v!s})"

                def __lt__(self, other: object) -> bool:
                    return self._v < _parse_version(str(other))

                def __le__(self, other: object) -> bool:
                    return self._v <= _parse_version(str(other))

                def __gt__(self, other: object) -> bool:
                    return self._v > _parse_version(str(other))

                def __ge__(self, other: object) -> bool:
                    return self._v >= _parse_version(str(other))

                def __eq__(self, other: object) -> bool:
                    return self._v == _parse_version(str(other))

                def __ne__(self, other: object) -> bool:
                    return self._v != _parse_version(str(other))

            distutils_mod = types.ModuleType("distutils")
            distutils_mod.__path__ = []  # type: ignore[attr-defined]
            version_mod = types.ModuleType("distutils.version")
            version_mod.LooseVersion = LooseVersion  # type: ignore[attr-defined]
            distutils_mod.version = version_mod  # type: ignore[attr-defined]
            sys.modules.setdefault("distutils", distutils_mod)
            sys.modules.setdefault("distutils.version", version_mod)
        except Exception:
            pass

import speech_recognition as sr

class JarvisIO:
    def __init__(self):
        self.debug_tts = os.getenv("DEBUG_TTS", "").strip().lower() in ("1", "true", "yes")
        self.force_powershell_tts = os.getenv("FORCE_POWERSHELL_TTS", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        try:
            self.engine = pyttsx3.init(driverName="sapi5")
        except Exception:
            self.engine = pyttsx3.init()
        try:
            self.engine.setProperty("volume", 1.0)
        except Exception:
            pass
        try:
            rate = self.engine.getProperty("rate")
            if isinstance(rate, int) and rate < 120:
                self.engine.setProperty("rate", 180)
        except Exception:
            pass
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.is_speaking = False
        self._lock = threading.Lock()

        self._tts_queue: "queue.Queue[str]" = queue.Queue()
        self._tts_stop = threading.Event()
        self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self._tts_thread.start()

        if self.debug_tts:
            try:
                voice = self.engine.getProperty("voice")
                rate = self.engine.getProperty("rate")
                volume = self.engine.getProperty("volume")
                voices = self.engine.getProperty("voices") or []
                print(
                    f"[🔊][TTS debug] driver=pyttsx3 voice={voice!r} rate={rate!r} volume={volume!r} voices={len(voices)} force_powershell={self.force_powershell_tts}"
                )
            except Exception as e:
                print(f"[🔊][TTS debug] init inspection failed: {e}")

    def _speak_powershell(self, text: str) -> None:
        safe = str(text).replace("`", "").replace('"', "'")
        safe = safe.replace("\r", " ").replace("\n", " ")
        cmd = (
            "Add-Type -AssemblyName System.Speech; "
            "$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$speak.Speak(\"" + safe + "\")"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=False)

    def _tts_worker(self) -> None:
        while not self._tts_stop.is_set():
            try:
                text = self._tts_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if not text:
                continue
            with self._lock:
                self.is_speaking = True
                try:
                    if self.debug_tts and winsound is not None:
                        try:
                            winsound.MessageBeep()
                        except Exception:
                            pass

                    if self.force_powershell_tts:
                        self._speak_powershell(text)
                    else:
                        self.engine.say(text)
                        self.engine.runAndWait()
                except Exception as e:
                    print(f"[ERROR] speak: {e}")
                    try:
                        self._speak_powershell(text)
                    except Exception:
                        pass
                finally:
                    self.is_speaking = False

    def speak(self, text):
        try:
            self._tts_queue.put_nowait(str(text))
        except Exception:
            pass

    def stop_speaking(self):
        with self._lock:
            try:
                self.engine.stop()
            except Exception as e:
                print(f"[ERROR] stop_speaking: {e}")
            self.is_speaking = False

    def listen(self, timeout=5, phrase_time_limit=8):
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
            try:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                return self.recognizer.recognize_google(audio)
            except sr.WaitTimeoutError:
                return ""
            except sr.UnknownValueError:
                return ""
            except sr.RequestError:
                return "Speech service is down."

    def listen_non_blocking(self, timeout=2, phrase_time_limit=2):
        try:
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                return self.recognizer.recognize_google(audio)
        except Exception:
            return ""

    def shutdown(self):
        self.stop_speaking()
        try:
            self._tts_stop.set()
        except Exception:
            pass
        try:
            self.engine.stop()
        except Exception:
            pass
