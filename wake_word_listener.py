import os
import pvporcupine
import pyaudio
import struct

ACCESS_KEY = "tj/UFvSf4ytpYZ0ZNqHGngvBp2HPyWbYspXK+MQooAzp6DYW+9z+MQ=="  # Replace with your actual Porcupine Access Key

def wait_for_wake_word():
    keyword_path = r"C:\Users\Shreesh\OneDrive\Desktop\JARVIS_AI\wake_words\jarvis_en_windows_v3_0_0.ppn"


    porcupine = pvporcupine.create(
        access_key=ACCESS_KEY,
        keyword_paths=[keyword_path]
    )

    pa = pyaudio.PyAudio()
    audio_stream = pa.open(
        rate=porcupine.sample_rate,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=porcupine.frame_length
    )

    print("🛎️ Say 'Jarvis' to wake me up...")

    try:
        while True:
            pcm = audio_stream.read(porcupine.frame_length, exception_on_overflow=False)
            pcm = struct.unpack_from("h" * porcupine.frame_length, pcm)

            keyword_index = porcupine.process(pcm)
            if keyword_index >= 0:
                print("🔊 Wake word detected!")
                break
    finally:
        audio_stream.stop_stream()
        audio_stream.close()
        pa.terminate()
        porcupine.delete()
