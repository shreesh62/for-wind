import speech_recognition as sr

def listen_command(timeout=5, phrase_time_limit=10):
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 200
    recognizer.dynamic_energy_threshold = True

    with sr.Microphone() as source:
        print("🎤 Listening... Speak now.")
        recognizer.adjust_for_ambient_noise(source, duration=1.2)

        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except sr.WaitTimeoutError:
            print("🕒 No speech detected.")
            return ""

    try:
        command = recognizer.recognize_google(audio)
        print(f"🗣️ You said: {command}")
        return command
    except sr.UnknownValueError:
        print("❌ Didn't catch that.")
        return ""
    except sr.RequestError:
        print("🌐 Speech recognition API down.")
        return "[Speech service error]"
