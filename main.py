import threading
import struct
import time
import pvporcupine
import pyaudio

from jarvis_io import JarvisIO
from groq_llm import query_qwen
from memory_core import load_memory

JARVIS_KEYWORD_PATH = "wake_words/jarvis_en_windows.ppn"
ACCESS_KEY = "tj/UFvSf4ytpYZ0ZNqHGngvBp2HPyWbYspXK+MQooAzp6DYW+9z+MQ=="

class JarvisAssistant:
    def __init__(self):
        self.jarvis_io = JarvisIO()
        self.interrupt_event = threading.Event()
        self.awaiting_wake_word = True

        self.porcupine = pvporcupine.create(
            access_key=ACCESS_KEY,
            keyword_paths=[JARVIS_KEYWORD_PATH],
            sensitivities=[0.65]
        )

        self.pa = pyaudio.PyAudio()
        self.stream = self.pa.open(
            rate=self.porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self.porcupine.frame_length
        )

    def listen_for_jarvis(self):
        print("[🔊] Waiting for wake word 'Jarvis'...")
        while self.awaiting_wake_word:
            pcm = self.stream.read(self.porcupine.frame_length, exception_on_overflow=False)
            pcm_unpacked = struct.unpack_from("h" * self.porcupine.frame_length, pcm)
            result = self.porcupine.process(pcm_unpacked)
            if result >= 0:
                print("[✅] Wake word 'Jarvis' detected!")
                self.awaiting_wake_word = False
                return True
        return False

    def interrupt_listener(self):
        print("[⏱️] Interrupt listener active: Say 'listen' to interrupt.")
        while self.jarvis_io.is_speaking:
            said = self.jarvis_io.listen(timeout=2, phrase_time_limit=2)
            if said and "listen" in said.lower():
                print("[⚠️] 'listen' detected - interrupting")
                self.interrupt_event.set()
                self.jarvis_io.stop_speaking()
                break

    def handle_command(self, command):
        print(f"[🎤] User command: {command}")

        if not command.strip():
            self.jarvis_io.speak("Can you please repeat that?")
            self.awaiting_wake_word = True
            return

        personal_keywords = ["who am i", "my birthday", "my name", "about me", "family", "friends"]
        memory_text = load_memory() if any(kw in command.lower() for kw in personal_keywords) else ""

        response = query_qwen(command, memory_snippet=memory_text)
        print(f"[💡] AI response: {response}")

        interrupt_thread = threading.Thread(target=self.interrupt_listener, daemon=True)
        interrupt_thread.start()

        self.jarvis_io.speak(response)

        while self.jarvis_io.is_speaking:
            if self.interrupt_event.is_set():
                self.interrupt_event.clear()
                print("[🛑] Interrupted - listening immediately...")
                new_command = self.jarvis_io.listen()
                self.handle_command(new_command)
                return
            time.sleep(0.1)

        if response.strip().endswith("?"):
            print("[🔁] Response ended with a question — auto-listening again.")
            next_command = self.jarvis_io.listen()
            if next_command:
                self.handle_command(next_command)
            else:
                self.jarvis_io.speak("Sorry, I didn’t catch that.")
                self.awaiting_wake_word = True
        else:
            print("[🔄] Response was not a question — waiting for wake word again.")
            self.awaiting_wake_word = True

    def run(self):
        print("🤖 Jarvis is online.")
        try:
            while True:
                if self.awaiting_wake_word:
                    self.listen_for_jarvis()

                command = self.jarvis_io.listen()
                if not command:
                    self.jarvis_io.speak("Sorry, I didn’t catch that.")
                    self.awaiting_wake_word = True
                    continue

                self.handle_command(command)

        except KeyboardInterrupt:
            print("👋 Exiting Jarvis...")

        finally:
            self.stream.stop_stream()
            self.stream.close()
            self.pa.terminate()
            self.jarvis_io.shutdown()

if __name__ == "__main__":
    assistant = JarvisAssistant()
    assistant.run()
