"""Security module for credential management and vault operations."""

from .credential_vault import CredentialVault, get_vault

__all__ = ["CredentialVault", "get_vault"]
