import copy
import json
import re
from pathlib import Path
from typing import Dict, Tuple, Optional, Any, List, NamedTuple


class IntentMatch(NamedTuple):
    intent_type: str
    entities: Dict[str, Any]


PROJECT_ROOT = Path(__file__).resolve().parent
CAPABILITIES_PATH = PROJECT_ROOT / "config" / "capabilities.json"


DEFAULT_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "qa_general": {
        "name": "General Q&A",
        "description": "Answer questions and explain things clearly.",
        "status": "available",
        "patterns": [r"\b(what|how|why|explain|tell me|could you|should i|can you)\b"],
    },
    "personal_memory": {
        "name": "Personal Memory",
        "description": "Remember and forget facts on request.",
        "status": "available",
        "patterns": [r"\bremember\b", r"\bsave this\b", r"\bstore this\b", r"\bforget\b"],
    },
    "self_describe": {
        "name": "Self Description",
        "description": "Describe exactly what I can do right now.",
        "status": "available",
        "patterns": [r"\b(what can you do|your capabilities|how can you help|what are you capable)\b"],
    },
    "weather_check": {
        "name": "Weather",
        "description": "Tell current weather for a place.",
        "status": "available",
        "patterns": [r"\b(weather|forecast|temperature|rain|sunny|cloudy)\b"],
    },
    "maps_distance": {
        "name": "Maps: Distance",
        "description": "Estimate distance between two places.",
        "status": "available",
        "patterns": [
            r"\b(distance|how far)\b.*\b(from|between|to)\b",
            r"\bhow far (?:is|from)\b",
        ],
    },
    "maps_travel_time": {
        "name": "Maps: Travel Time",
        "description": "Estimated travel time between two places.",
        "status": "available",
        "patterns": [
            r"\b(travel time|time to|get to|how long).*(from|between|to)\b",
            r"\bhow long (?:will it take|does it take)\b",
        ],
    },
    "send_email": {
        "name": "Email",
        "description": "Draft and send emails.",
        "status": "planned",
        "patterns": [r"\bsend (an )?email\b", r"\bemail (to|someone)\b"],
    },
    "open_browser": {
        "name": "Open Browser / Websites",
        "description": "Open sites or urls.",
        "status": "planned",
        "patterns": [r"\bopen\b.*\b(browser|website|url|link)\b"],
    },
    "play_music": {
        "name": "Play Music",
        "description": "Play songs or playlists.",
        "status": "planned",
        "patterns": [r"\b(play|start)\b.*\b(music|song|songs|playlist)\b"],
    },
    "whatsapp_message": {
        "name": "WhatsApp Messaging",
        "description": "Send a WhatsApp message via automation.",
        "status": "available",
        "patterns": [r"\b(send|message)\b.*\bwhatsapp\b"],
    },
    "instagram_dm": {
        "name": "Instagram DM",
        "description": "Send an Instagram direct message via automation.",
        "status": "available",
        "patterns": [r"\b(send|message)\b.*\binstagram\b", r"\bdm\b.*\binstagram\b"],
    },
    "amazon_shopping": {
        "name": "Amazon Shopping",
        "description": "Search for products on Amazon using the desktop browser.",
        "status": "available",
        "patterns": [
            r"\bsearch\b.*\bamazon\b",
            r"\bfind\b.*\b(on amazon|amazon)\b",
            r"\bbuy\b.*\b(on amazon|amazon)\b",
        ],
    },
    "browser_summarize": {
        "name": "Browser Summary",
        "description": "Summarize the active Chrome tab via DevTools.",
        "status": "available",
        "patterns": [
            r"\b(what|describe|summarize|tell me)\b.*\b(browser|tab|chrome|web page|webpage)\b",
        ],
    },
    "desktop_ocr": {
        "name": "Desktop OCR",
        "description": "Read text from a region of the screen using OCR.",
        "status": "available",
        "patterns": [r"\b(ocr|read)\b.*\b(region|screen)\b", r"\bocr\s+region\b", r"\bread\s+region\b"],
    },
    "desktop_screenshot": {
        "name": "Desktop Screenshot",
        "description": "Capture a screenshot of the current desktop view.",
        "status": "available",
        "patterns": [
            r"\b(take|grab|capture)\b.*\b(screen ?shot|screenshot|screen)\b",
        ],
    },
    "desktop_focus": {
        "name": "Focus Window",
        "description": "Bring a specified application window to the foreground.",
        "status": "available",
        "patterns": [
            r"\b(focus|switch to|bring up|activate)\b.*\b(window|app|application|chrome|browser)\b",
        ],
    },
    "desktop_click": {
        "name": "Desktop Click",
        "description": "Click on the desktop using coordinates or a perceived element.",
        "status": "available",
        "patterns": [
            r"\bclick\s+\d+\s+\d+\b",
            r"\bdouble\s+click\s+\d+\s+\d+\b",
            r"\bclick\s+element\b",
            r"\bclick\s+text\b",
        ],
    },
    "desktop_scroll": {
        "name": "Desktop Scroll",
        "description": "Scroll the active window up/down by a specified amount.",
        "status": "available",
        "patterns": [
            r"\bscroll\s+(up|down)\s+\d+\b",
        ],
    },
    "desktop_type": {
        "name": "Type Text",
        "description": "Type provided text into the active window.",
        "status": "available",
        "patterns": [
            r"\b(type|enter)\b.*",
        ],
    },
    "news_brief": {
        "name": "News Brief",
        "description": "Fetch recent headlines for a topic.",
        "status": "available",
        "patterns": [
            r"\b(news|headlines|updates)\b",
        ],
    },
    "app_launch": {
        "name": "Launch Application",
        "description": "Open a desktop application like Spotify or Chrome.",
        "status": "available",
        "patterns": [
            r"\b(open|launch|start|play)\b.*\b(app|application|spotify|chrome|notepad|calculator|terminal)\b",
        ],
    },
    "web_navigate": {
        "name": "Open Website",
        "description": "Navigate to a website or URL in the browser.",
        "status": "available",
        "patterns": [
            r"\b(open|launch|go to|navigate to|visit)\b.*\b(youtube|gmail|netflix|google|github|linkedin)\b",
            r"\bhttps?://\S+",
            r"\bwww\.\S+",
            r"\b(open|launch|go to|navigate to|visit)\b.*\b\w+\.(com|in|org|net|io|co)\b",
        ],
    },
    "remote_command": {
        "name": "Remote Command Relay",
        "description": "Receive commands via Telegram or authenticated HTTP webhook.",
        "status": "planned",
        "patterns": [
            r"\b(telegram|webhook|remote)\b.*\b(command|control|relay)\b",
        ],
    },
}


def _deepcopy_capabilities(data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return copy.deepcopy(data)


def _load_capabilities(path: Path) -> Dict[str, Dict[str, Any]]:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, dict):
                return payload
        except (json.JSONDecodeError, OSError):
            pass
    return _deepcopy_capabilities(DEFAULT_CAPABILITIES)


class CapabilityRegistry:
    """Central registry of what JARVIS can and cannot do."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._path = config_path or CAPABILITIES_PATH
        self.capabilities: Dict[str, Dict[str, Any]] = {}
        self._compiled_patterns: Dict[str, List[re.Pattern[str]]] = {}
        self._dynamic_capabilities: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        """Reload capability definitions from disk."""

        data = _load_capabilities(self._path)
        self.capabilities = data
        # Re-apply dynamic capabilities registered by plugins
        self.capabilities.update(self._dynamic_capabilities)
        self._compiled_patterns = {
            key: [re.compile(pat, flags=re.IGNORECASE) for pat in cfg.get("patterns", [])]
            for key, cfg in self.capabilities.items()
        }

    def describe_capabilities(self) -> str:
        items = [
            f"• {cfg['name']}: {cfg['description']}"
            for cfg in self.capabilities.values()
            if cfg.get("status") == "available"
        ]
        return "Here’s what I can do right now:\n" + "\n".join(items)

    def match_intent(self, text: str) -> Tuple[Optional[str], Optional[dict]]:
        t = text.strip()
        matches: List[str] = []
        for key, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(t):
                    matches.append(key)
                    break
        if not matches:
            return None, None
        # Prefer specific domain capabilities over generic QA
        priority = [
            "amazon_shopping",
            "weather_check",
            "maps_distance",
            "maps_travel_time",
            "news_brief",
            "browser_summarize",
            "whatsapp_message",
            "instagram_dm",
            "youtube_search",
            "desktop_screenshot",
            "desktop_ocr",
            "desktop_click",
            "desktop_scroll",
            "desktop_focus",
            "desktop_type",
            "web_navigate",
            "open_browser",
            "app_launch",
            "personal_memory",
            "self_describe",
            "qa_general",
        ]
        for p in priority:
            if p in matches:
                return p, {}
        # Fallback to first match
        return matches[0], {}

    def classify(self, text: str) -> IntentMatch:
        capability, _ = self.match_intent(text)
        if capability == "send_email":
            return IntentMatch(intent_type="email", entities={"query": text})
        return IntentMatch(intent_type="none", entities={})

    def is_available(self, key: str) -> bool:
        cap = self.capabilities.get(key)
        return bool(cap and cap.get("status") == "available")

    def explain_unavailable(self, key: str) -> str:
        cap = self.capabilities.get(key)
        if not cap:
            return "That capability isn’t recognized."
        return f"{cap['name']} isn’t enabled yet. We’ll add this soon."

    def list_all(self) -> Dict[str, Dict[str, Any]]:
        return _deepcopy_capabilities(self.capabilities)

    def register_dynamic_capability(self, key: str, definition: Dict[str, Any]) -> None:
        """Register or override a capability definition supplied at runtime."""

        if "patterns" not in definition:
            definition = {**definition, "patterns": []}

        self._dynamic_capabilities[key] = definition
        self.capabilities[key] = definition
        self._compiled_patterns[key] = [
            re.compile(pattern, flags=re.IGNORECASE) for pattern in definition.get("patterns", [])
        ]

    def unregister_dynamic_capability(self, key: str) -> None:
        """Remove a previously registered dynamic capability."""

        self._dynamic_capabilities.pop(key, None)
        self.capabilities.pop(key, None)
        self._compiled_patterns.pop(key, None)
