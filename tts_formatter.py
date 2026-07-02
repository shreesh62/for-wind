# tts_formatter.py
import re
from urllib.parse import urlparse
from personality import PersonalityManager

class TTSFormatter:
    def __init__(self, personality_manager: PersonalityManager):
        """
        Handles text formatting for TTS output, including
        personality-driven enhancements like pauses, tone, and style.
        """
        self.pm = personality_manager

    def format_text(self, text: str) -> str:
        """
        Format the text for TTS output by applying personality-driven
        rules (e.g., tone, pauses, JARVIS-like style).
        """
        def humanize_urls(s: str) -> str:
            def _map(url: str) -> str:
                try:
                    host = urlparse(url).netloc.lower()
                except Exception:
                    host = ""
                mapping = {
                    "www.youtube.com": "YouTube",
                    "youtube.com": "YouTube",
                    "open.spotify.com": "Spotify",
                    "www.google.com": "Google",
                    "calendar.google.com": "Google Calendar",
                    "mail.google.com": "Gmail",
                    "github.com": "GitHub",
                    "www.netflix.com": "Netflix",
                    "www.linkedin.com": "LinkedIn",
                }
                if host in mapping:
                    return mapping[host]
                if host:
                    parts = host.split(".")
                    if len(parts) >= 2:
                        return parts[-2].capitalize()
                    return host
                return "the site"

            return re.sub(r"https?://\S+", lambda m: _map(m.group(0)), s)

        text = humanize_urls(text)
        personality = self.pm.get_personality()
        tone = personality.get("tone", "default")
        pause_style = personality.get("pause_style", "short")
        style = personality.get("style", "neutral")

        # Apply pause formatting
        if pause_style == "short":
            pause = " ... "
        elif pause_style == "medium":
            pause = " ... (pause) ... "
        elif pause_style == "long":
            pause = " ... (long pause) ... "
        else:
            pause = " "

        # Tone adjustments (very basic for now, can expand later)
        if tone == "formal":
            text = text.replace("okay", "certainly").replace("yeah", "affirmative")
        elif tone == "casual":
            text = text.replace("hello", "hey").replace("yes", "yep")
        elif tone == "sarcastic":
            text = f"Oh, really? {pause}{text}"
        elif tone == "jarvis":
            text = f"{text}{pause}Sir."

        # Style adjustments
        if style == "energetic":
            text = text.upper()
        elif style == "calm":
            text = text.capitalize()
        elif style == "neutral":
            text = text  # no change

        return text
