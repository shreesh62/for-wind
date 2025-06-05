import pyttsx3
import speech_recognition as sr
import threading

class JarvisIO:
    def __init__(self):
        self.engine = pyttsx3.init()
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.is_speaking = False
        self._lock = threading.Lock()

    def speak(self, text):
        def _speak():
            with self._lock:
                self.is_speaking = True
                try:
                    self.engine.say(text)
                    self.engine.runAndWait()
                finally:
                    self.is_speaking = False
        t = threading.Thread(target=_speak)
        t.daemon = True
        t.start()

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
        self.engine.stop()
