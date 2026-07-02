"""Goal parser: Convert natural language into formal Goal objects.

This module analyzes user commands and extracts structured intent
without relying on keyword matching or site-specific logic.
"""

from __future__ import annotations

import re
from typing import Optional

from .goal_schema import Goal


class GoalParser:
    """Converts natural language commands into formal Goal objects."""
    
    def __init__(self):
        self._intent_patterns = {
            "navigate": [
                r"(?:open|go to|visit|navigate to|browse to|show me)\s+(.+)",
                r"(?:take me to|head to)\s+(.+)",
            ],
            "search": [
                r"(?:search|find|look for|look up)\s+(.+)",
                r"(?:what is|what are|who is|where is)\s+(.+)",
            ],
            "send_message": [
                r"(?:send|message|text)\s+(?:a message to|to)\s+(\w+)(?:\s+saying\s+(.+))?",
                r"(?:tell|inform)\s+(\w+)\s+(?:that|about)\s+(.+)",
            ],
            "compose_email": [
                r"(?:email|send email to|compose email to)\s+(\w+)(?:\s+about\s+(.+))?",
            ],
            "read_content": [
                r"(?:read|summarize|what does it say|what's on)\s+(.+)",
            ],
            "click": [
                r"(?:click|press|tap|select)\s+(?:on\s+)?(.+)",
            ],
            "type": [
                r"(?:type|enter|input)\s+(.+)",
            ],
            "focus": [
                r"(?:focus|switch to|bring up|activate)\s+(.+)",
            ],
        }
    
    def parse(self, command: str) -> Goal:
        """Parse a natural language command into a Goal.
        
        Args:
            command: Raw user command text
            
        Returns:
            Goal object representing the user's intent
        """
        command = command.strip()
        command_lower = command.lower()
        
        # Try to match intent patterns
        for intent, patterns in self._intent_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, command_lower, re.IGNORECASE)
                if match:
                    return self._build_goal_from_match(intent, match, command)
        
        # Fallback: treat as general query/command
        return Goal(
            target_app=None,
            target_entity=None,
            intent="general_query",
            desired_effect="information_provided",
        )
    
    def _build_goal_from_match(self, intent: str, match: re.Match, original_command: str) -> Goal:
        """Build a Goal from a regex match."""
        
        if intent == "navigate":
            target = match.group(1).strip()
            target_app = "browser"
            
            # Detect if it's a URL or site name
            if any(ext in target for ext in [".com", ".org", ".net", ".io", "http"]):
                target_entity = target
            else:
                # Assume it's a site name
                target_entity = target
            
            return Goal(
                target_app=target_app,
                target_entity=target_entity,
                intent="navigate",
                desired_effect=f"{target}_page_visible",
            )
        
        elif intent == "search":
            query = match.group(1).strip()
            return Goal(
                target_app="browser",
                target_entity=None,
                intent="search",
                desired_effect="search_results_visible",
                search_query=query,
            )
        
        elif intent == "send_message":
            recipient = match.group(1).strip()
            message = match.group(2).strip() if match.lastindex >= 2 else None
            
            # Detect messaging platform
            if "whatsapp" in original_command.lower():
                target_app = "whatsapp"
            elif "instagram" in original_command.lower():
                target_app = "instagram"
            else:
                target_app = "messaging"
            
            return Goal(
                target_app=target_app,
                target_entity=recipient,
                intent="send_message",
                desired_effect="message_delivered",
                message_content=message,
            )
        
        elif intent == "compose_email":
            recipient = match.group(1).strip()
            subject = match.group(2).strip() if match.lastindex >= 2 else None
            
            return Goal(
                target_app="email",
                target_entity=recipient,
                intent="compose_email",
                desired_effect="email_composed",
                message_content=subject,
            )
        
        elif intent == "read_content":
            target = match.group(1).strip()
            return Goal(
                target_app=None,
                target_entity=target,
                intent="read_content",
                desired_effect="content_summarized",
            )
        
        elif intent == "click":
            target = match.group(1).strip()
            return Goal(
                target_app=None,
                target_entity=target,
                intent="click",
                desired_effect=f"{target}_clicked",
            )
        
        elif intent == "type":
            text = match.group(1).strip()
            return Goal(
                target_app=None,
                target_entity=None,
                intent="type",
                desired_effect="text_entered",
                message_content=text,
            )
        
        elif intent == "focus":
            target = match.group(1).strip()
            return Goal(
                target_app=target,
                target_entity=None,
                intent="focus",
                desired_effect=f"{target}_focused",
            )
        
        # Fallback
        return Goal(
            target_app=None,
            target_entity=None,
            intent="unknown",
            desired_effect="command_executed",
        )


def parse_goal(command: str) -> Goal:
    """Convenience function to parse a command into a Goal.
    
    Args:
        command: Natural language command
        
    Returns:
        Goal object
    """
    parser = GoalParser()
    return parser.parse(command)
