"""LLM input sanitizer to prevent credential leakage.

This module strips sensitive information from all text before it reaches the LLM.
NO credentials, passwords, or vault keys are ever exposed to the LLM.
"""

from __future__ import annotations

import re
from typing import Dict, List


# Sensitive field patterns to strip
SENSITIVE_PATTERNS = [
    r'password["\']?\s*[:=]\s*["\']?[^"\'\s]+',
    r'credential["\']?\s*[:=]\s*["\']?[^"\'\s]+',
    r'secret["\']?\s*[:=]\s*["\']?[^"\'\s]+',
    r'api_key["\']?\s*[:=]\s*["\']?[^"\'\s]+',
    r'access_token["\']?\s*[:=]\s*["\']?[^"\'\s]+',
    r'auth_token["\']?\s*[:=]\s*["\']?[^"\'\s]+',
    r'pin["\']?\s*[:=]\s*["\']?\d+',
]

# Sensitive field names in dicts/snapshots
SENSITIVE_FIELDS = {
    "password",
    "credential",
    "secret",
    "api_key",
    "access_token",
    "auth_token",
    "pin",
    "vault_key",
    "chrome_password",
    "whatsapp_password",
    "chrome_pass",
    "whatsapp_pass",
}


def strip_credentials_from_text(text: str) -> str:
    """Strip credential patterns from text.
    
    Args:
        text: Input text that may contain credentials
        
    Returns:
        Sanitized text with credentials replaced by [REDACTED]
    """
    if not text:
        return text
    
    sanitized = text
    
    for pattern in SENSITIVE_PATTERNS:
        sanitized = re.sub(pattern, "[CREDENTIAL_REDACTED]", sanitized, flags=re.IGNORECASE)
    
    return sanitized


def strip_credentials_from_dict(data: Dict, recursive: bool = True) -> Dict:
    """Strip sensitive fields from dictionary.
    
    Args:
        data: Dictionary that may contain sensitive fields
        recursive: Whether to recursively sanitize nested dicts
        
    Returns:
        Sanitized dictionary with sensitive values replaced
    """
    if not isinstance(data, dict):
        return data
    
    sanitized = {}
    
    for key, value in data.items():
        key_lower = str(key).lower()
        
        # Check if key is sensitive
        if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
            sanitized[key] = "[REDACTED]"
        elif recursive and isinstance(value, dict):
            sanitized[key] = strip_credentials_from_dict(value, recursive=True)
        elif recursive and isinstance(value, list):
            sanitized[key] = [
                strip_credentials_from_dict(item, recursive=True) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value
    
    return sanitized


def strip_credentials_from_snapshot(snapshot: str) -> str:
    """Strip credentials from perception snapshot text.
    
    Args:
        snapshot: Snapshot text (redacted format)
        
    Returns:
        Sanitized snapshot with credentials removed
    """
    if not snapshot:
        return snapshot
    
    # Strip credential patterns
    sanitized = strip_credentials_from_text(snapshot)
    
    # Additional snapshot-specific patterns
    # Remove lines that mention passwords/credentials
    lines = sanitized.split('\n')
    safe_lines = []
    
    for line in lines:
        line_lower = line.lower()
        if any(word in line_lower for word in ["password", "credential", "secret", "vault_key"]):
            # Skip lines mentioning credentials
            continue
        safe_lines.append(line)
    
    return '\n'.join(safe_lines)


def strip_credentials_from_memory(memory_text: str) -> str:
    """Strip credentials from memory text before storage.
    
    Args:
        memory_text: Memory text that may contain credentials
        
    Returns:
        Sanitized memory text
    """
    return strip_credentials_from_text(memory_text)


def strip_credentials_from_tool_trace(tool_trace: List[str]) -> List[str]:
    """Strip credentials from tool trace entries.
    
    Args:
        tool_trace: List of tool trace strings
        
    Returns:
        Sanitized tool trace
    """
    if not tool_trace:
        return tool_trace
    
    sanitized = []
    
    for entry in tool_trace:
        if not isinstance(entry, str):
            sanitized.append(entry)
            continue
        
        # Strip credentials from entry
        clean_entry = strip_credentials_from_text(entry)
        
        # Skip entries that are entirely about credentials
        entry_lower = entry.lower()
        if any(word in entry_lower for word in ["vault.get", "vault.set", "password", "credential"]):
            clean_entry = "[Tool trace redacted: credential operation]"
        
        sanitized.append(clean_entry)
    
    return sanitized


def sanitize_for_llm(
    text: str = None,
    snapshot: str = None,
    tool_trace: List[str] = None,
    memory: str = None
) -> Dict[str, any]:
    """Sanitize all inputs before sending to LLM.
    
    Args:
        text: User command or text
        snapshot: Perception snapshot
        tool_trace: Tool execution trace
        memory: Memory context
        
    Returns:
        Dictionary with sanitized versions of all inputs
    """
    return {
        "text": strip_credentials_from_text(text) if text else text,
        "snapshot": strip_credentials_from_snapshot(snapshot) if snapshot else snapshot,
        "tool_trace": strip_credentials_from_tool_trace(tool_trace) if tool_trace else tool_trace,
        "memory": strip_credentials_from_memory(memory) if memory else memory,
    }
