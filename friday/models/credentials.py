"""Ch 35.6 — vault-first credential resolution (retires plaintext .env reads).

Providers previously read API keys directly from ``os.getenv`` (the plaintext
``.env`` anti-pattern, Constitution Article IX / TD-9). This module centralises
credential access behind a :class:`~friday.safety.vault.SecretVault`:

- :func:`resolve_secret` returns a secret by key NAME, preferring the vault and
  falling back to the process environment for backward compatibility. The value
  is never logged.
- :func:`seed_vault_from_env` copies known keys from the environment into the
  vault once at startup so the running process reads them from the vault rather
  than re-reading plaintext ``.env`` on every call.

A module-level default vault is used so providers need no constructor changes.
Under ``FRIDAY_DRY_RUN=1`` the vault is in-memory and empty, so resolution
transparently falls back to the environment and the existing test suite is
unaffected.
"""

from __future__ import annotations

import os
import threading
from typing import Iterable, Optional

from friday.safety.vault import SecretVault

_lock = threading.RLock()
_default_vault: Optional[SecretVault] = None


def default_vault() -> SecretVault:
    """Return the process-wide default vault, constructing it once on first use."""
    global _default_vault
    with _lock:
        if _default_vault is None:
            _default_vault = SecretVault(service="friday")
        return _default_vault


def set_default_vault(vault: SecretVault) -> None:
    """Override the default vault (primarily for tests / explicit wiring)."""
    global _default_vault
    with _lock:
        _default_vault = vault


def resolve_secret(key: str, *, vault: Optional[SecretVault] = None) -> str:
    """Resolve a secret by key name: vault first, then environment fallback.

    Returns an empty string when the key is unknown in both. The value is never
    logged or echoed by this function.
    """
    if not key:
        return ""
    store = vault if vault is not None else default_vault()
    try:
        value = store.get(key)
    except Exception:  # noqa: BLE001 — a vault read must never break a provider
        value = None
    if value:
        return value
    return os.getenv(key, "")


def seed_vault_from_env(
    keys: Iterable[str], *, vault: Optional[SecretVault] = None
) -> int:
    """Copy any present environment values for ``keys`` into the vault.

    Returns the number of keys seeded. Missing/empty env values are skipped. This
    lets a process migrate off repeated plaintext ``.env`` reads: after seeding,
    :func:`resolve_secret` returns the vault-held copy. Never logs the values.
    """
    store = vault if vault is not None else default_vault()
    seeded = 0
    for key in keys:
        env_value = os.getenv(key, "")
        if env_value and not store.has(key):
            try:
                store.set(key, env_value)
                seeded += 1
            except Exception:  # noqa: BLE001 — seeding is best-effort
                continue
    return seeded
