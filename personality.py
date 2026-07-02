# personality.py

"""
Defines the personality and response style of JARVIS.
All AI outputs are passed through this module before being spoken.
"""

class PersonalityManager:
    def __init__(self, persona: str | None = None):
        """
        Controls personality traits and transformation rules for JARVIS.
        Traits can be toggled for different styles of interaction.
        """
        self.available_personas = {
            "classic": {
                "traits": {"calm": True, "formal": True, "concise": True, "witty": True},
                "meta": {"tone": "formal", "pause_style": "short", "style": "neutral"},
                "replacements": {
                    "okay": "Understood",
                    "ok": "Acknowledged",
                    "sure": "Certainly",
                    "yes": "Affirmative",
                    "no": "Negative",
                    "thanks": "Much obliged",
                    "thank you": "You're welcome",
                    "sorry": "My apologies",
                },
            },
            "friendly": {
                "traits": {"calm": True, "formal": False, "concise": False, "witty": True},
                "meta": {"tone": "warm", "pause_style": "medium", "style": "friendly"},
                "replacements": {
                    "okay": "You got it",
                    "ok": "You got it",
                    "sure": "Absolutely",
                    "yes": "Yep",
                    "no": "Not really",
                    "thanks": "Thanks a ton",
                    "thank you": "Happy to help",
                    "sorry": "Oops",
                },
            },
            "deadpan": {
                "traits": {"calm": True, "formal": True, "concise": True, "witty": False},
                "meta": {"tone": "dry", "pause_style": "short", "style": "deadpan"},
                "replacements": {
                    "okay": "Acknowledged",
                    "ok": "Acknowledged",
                    "sure": "Very well",
                    "yes": "Affirmative",
                    "no": "Negative",
                    "thanks": "Noted",
                    "thank you": "No problem",
                    "sorry": "Apologies",
                },
            },
        }

        persona_key = persona or "classic"
        if persona_key not in self.available_personas:
            persona_key = "classic"

        descriptor = self.available_personas[persona_key]
        self.persona = persona_key
        self.traits = descriptor["traits"].copy()
        self.meta = descriptor["meta"].copy()
        self.replacements = descriptor["replacements"].copy()
        self.last_context = None

    def apply(self, ai_response: str) -> str:
        """
        Transforms a raw AI response into JARVIS-style speech.
        """
        if not ai_response or not isinstance(ai_response, str):
            return "I'm here, but I didn’t quite catch that."

        ai_response = ai_response.strip()

        # Apply replacements
        for word, replacement in self.replacements.items():
            ai_response = ai_response.replace(f" {word} ", f" {replacement} ")
            if ai_response.lower().startswith(word):
                ai_response = replacement + ai_response[len(word):]

        # Ensure professional cadence
        if self.traits.get("formal"):
            ai_response = ai_response.replace(" gonna ", " going to ")
            ai_response = ai_response.replace(" wanna ", " want to ")

        # Keep it concise
        if self.traits.get("concise"):
            words = ai_response.split()
            try:
                max_words = int(__import__("os").getenv("JARVIS_PERSONALITY_MAX_WORDS", "220"))
            except Exception:
                max_words = 220
            if len(words) > max_words:
                trimmed = " ".join(words[:max_words])
                last_punct = max(trimmed.rfind("."), trimmed.rfind("!"), trimmed.rfind("?"))
                if last_punct >= 0 and last_punct > max(0, len(trimmed) - 140):
                    trimmed = trimmed[: last_punct + 1]
                else:
                    if not trimmed.endswith((".", "!", "?")):
                        trimmed = trimmed + "."
                ai_response = trimmed + " Say \"more\" if you want a longer explanation."

        # Wit
        if self.traits.get("witty") and ai_response.lower().startswith(("yes", "affirmative", "understood")):
            ai_response += " As always."

        # Allow tense shifts based on last context hint
        if self.last_context == "alert" and self.traits.get("calm"):
            ai_response = ai_response.replace(".", "!", 1)

        # Ensure proper punctuation
        if not ai_response.endswith((".", "!", "?")):
            ai_response += "."

        return ai_response

    def set_persona(self, persona: str) -> None:
        if persona not in self.available_personas:
            return
        descriptor = self.available_personas[persona]
        self.persona = persona
        self.traits = descriptor["traits"].copy()
        self.meta = descriptor["meta"].copy()
        self.replacements = descriptor["replacements"].copy()

    def update_context(self, context_hint: str) -> None:
        self.last_context = context_hint
        if context_hint == "alert":
            self.meta["tone"] = "urgent"
            self.meta["pause_style"] = "short"
        elif context_hint == "briefing":
            self.meta["tone"] = "informative"
            self.meta["pause_style"] = "medium"
        else:
            base_meta = self.available_personas[self.persona]["meta"]
            self.meta = base_meta.copy()

    def get_personality(self) -> dict:
        """
        Returns metadata for TTSFormatter (tone, pause style, etc.)
        """
        return self.meta


# Quick helper
def apply_personality(ai_response: str, manager: PersonalityManager = None) -> str:
    if manager is None:
        manager = PersonalityManager()
    return manager.apply(ai_response)
