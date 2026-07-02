"""Secure credential vault using Windows DPAPI encryption.

This module provides encrypted storage for sensitive credentials.
NO credentials are ever exposed to LLM prompts or logs.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Optional

try:
    import win32crypt
    DPAPI_AVAILABLE = True
except ImportError:
    DPAPI_AVAILABLE = False


_VAULT_PATH = Path(__file__).parent / "credentials.dat"
_LOCK = threading.Lock()


def _load() -> dict:
    """Load and decrypt vault data using Windows DPAPI."""
    if not _VAULT_PATH.exists():
        return {}
    
    if not DPAPI_AVAILABLE:
        raise RuntimeError("Windows DPAPI (pywin32) is required for credential vault")
    
    try:
        with open(_VAULT_PATH, "rb") as f:
            encrypted_data = f.read()
        
        if not encrypted_data:
            return {}
        
        decrypted_bytes = win32crypt.CryptUnprotectData(
            encrypted_data,
            None,
            None,
            None,
            0
        )[1]
        
        return json.loads(decrypted_bytes.decode('utf-8'))
    except Exception as e:
        raise RuntimeError(f"Failed to decrypt vault: {e}")


def _save(data: dict) -> None:
    """Encrypt and save vault data using Windows DPAPI."""
    if not DPAPI_AVAILABLE:
        raise RuntimeError("Windows DPAPI (pywin32) is required for credential vault")
    
    try:
        raw_json = json.dumps(data, indent=2)
        raw_bytes = raw_json.encode('utf-8')
        
        # CryptProtectData returns encrypted bytes directly
        encrypted_data = win32crypt.CryptProtectData(
            raw_bytes,
            None,
            None,
            None,
            None,
            0
        )
        
        _VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        with open(_VAULT_PATH, "wb") as f:
            f.write(encrypted_data)
    except Exception as e:
        raise RuntimeError(f"Failed to encrypt vault: {e}")


class CredentialVault:
    """Thread-safe encrypted credential storage using Windows DPAPI.
    
    This vault ensures:
    - All credentials are encrypted at rest
    - Thread-safe access via lock
    - No credential values exposed to logs or LLM
    """
    
    def get(self, key: str) -> Optional[str]:
        """Retrieve a credential from the vault.
        
        Args:
            key: Credential identifier (e.g., "chrome_password", "whatsapp_pin")
            
        Returns:
            Credential value or None if not found
        """
        with _LOCK:
            data = _load()
            return data.get(key)
    
    def set(self, key: str, value: str) -> None:
        """Store a credential in the vault.
        
        Args:
            key: Credential identifier
            value: Credential value (will be encrypted)
        """
        with _LOCK:
            data = _load()
            data[key] = value
            _save(data)
    
    def delete(self, key: str) -> bool:
        """Delete a credential from the vault.
        
        Args:
            key: Credential identifier
            
        Returns:
            True if deleted, False if not found
        """
        with _LOCK:
            data = _load()
            if key in data:
                del data[key]
                _save(data)
                return True
            return False
    
    def list_keys(self) -> list[str]:
        """List all credential keys (NOT values).
        
        Returns:
            List of credential identifiers
        """
        with _LOCK:
            data = _load()
            return list(data.keys())
    
    def exists(self, key: str) -> bool:
        """Check if a credential exists.
        
        Args:
            key: Credential identifier
            
        Returns:
            True if credential exists
        """
        with _LOCK:
            data = _load()
            return key in data
    
    def clear(self) -> None:
        """Clear all credentials from vault."""
        with _LOCK:
            _save({})


_vault_instance: Optional[CredentialVault] = None


def get_vault() -> CredentialVault:
    """Get the global credential vault instance.
    
    Returns:
        Singleton CredentialVault instance
    """
    global _vault_instance
    if _vault_instance is None:
        _vault_instance = CredentialVault()
    return _vault_instance
