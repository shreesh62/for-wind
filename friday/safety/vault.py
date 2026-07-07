"""Ch 35 — SecretVault: secrets referenced by key name, never echoed to logs.

The SecretVault replaces plaintext ``.env`` secret access (Constitution
Article IX / Ch 35.6). Secrets are stored and retrieved by key *name*; their
*values* never appear in ``repr``/``str`` output nor in :meth:`SecretVault.keys`,
so credentials cannot leak into logs or source (Property 4). A ``set`` then
``get`` round-trips the identical value, and ``delete`` removes it (Property 5).

Backends, chosen once at construction:

* Under ``FRIDAY_DRY_RUN=1`` (read from the environment at init time) the vault
  uses an **in-memory** store only. It touches no real OS credential store and
  no file, so the existing test suite stays green with zero side effects
  (Requirement 2.4).
* Otherwise it prefers the optional ``keyring`` library (Windows Credential
  Manager and friends). The import is guarded by try/except so a machine without
  ``keyring`` never hard-fails (Requirement 2.5).
* If ``keyring`` is unavailable, it falls back to an **encrypted-file** store at
  ``fallback_path`` (default under a per-user friday config directory). The
  obfuscation is a dependency-light reversible cipher (XOR against a
  per-service key, base64-wrapped); a stronger cipher can be swapped behind the
  same API without changing the interface or the no-leak guarantee.

Import boundary (Ch 52): this module imports only standard-library modules and,
optionally and guarded, ``keyring``. It MUST NOT import
memory/competence/learning/resources/identity/cognition modules. It contains no
hardcoded application/site names or URLs (Axiom 15).
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Dict, List, Optional


def _is_dry_run() -> bool:
    """True when running under ``FRIDAY_DRY_RUN=1`` (read at call time)."""
    return os.environ.get("FRIDAY_DRY_RUN") == "1"


def _default_fallback_path(service: str) -> str:
    """A per-user config path for the encrypted-file fallback.

    Uses ``XDG_CONFIG_HOME`` when set, else the platform home directory. No
    application or site name is hardcoded — only the neutral ``service`` label.
    """
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return str(root / service / "vault.enc")


def _xor_cipher(data: bytes, key: bytes) -> bytes:
    """Reversible XOR of ``data`` against a repeating ``key`` (its own inverse)."""
    if not key:
        return data
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


class SecretVault:
    """Ch 35.6 — secrets referenced by key name, never returned to logs."""

    def __init__(self, *, service: str = "friday", fallback_path: str = None) -> None:
        self._service = service
        self._store: Dict[str, str] = {}
        self._keyring = None
        self._fallback_path: Optional[Path] = None

        if _is_dry_run():
            # Dry-run: in-memory only. Touch no real credential store and no file.
            self._backend = "memory"
            return

        # Prefer a real OS credential store when the optional dependency exists.
        try:
            import keyring  # type: ignore

            # A trivial probe keeps us from selecting a backend with no usable
            # keyring implementation configured on the host.
            keyring.get_keyring()
            self._keyring = keyring
            self._backend = "keyring"
            return
        except Exception:
            # ImportError or any keyring initialisation failure falls through to
            # the encrypted-file fallback without raising (Requirement 2.5).
            self._keyring = None

        # Encrypted-file fallback.
        self._backend = "file"
        self._fallback_path = Path(fallback_path) if fallback_path else Path(
            _default_fallback_path(service)
        )
        self._store = self._load_file()

    # ---- public API ---------------------------------------------------------

    def set(self, key: str, value: str) -> None:
        """Store ``value`` under ``key``. The value is never logged."""
        if self._backend == "keyring":
            self._keyring.set_password(self._service, key, value)
            return
        self._store[key] = value
        if self._backend == "file":
            self._save_file()

    def get(self, key: str) -> Optional[str]:
        """Return the secret for ``key``, or ``None``. Never logs the value."""
        if self._backend == "keyring":
            try:
                return self._keyring.get_password(self._service, key)
            except Exception:
                return None
        return self._store.get(key)

    def has(self, key: str) -> bool:
        """True when a secret is stored under ``key``."""
        if self._backend == "keyring":
            return self.get(key) is not None
        return key in self._store

    def delete(self, key: str) -> None:
        """Remove the secret stored under ``key`` (no-op if absent)."""
        if self._backend == "keyring":
            try:
                self._keyring.delete_password(self._service, key)
            except Exception:
                pass
            return
        if key in self._store:
            del self._store[key]
            if self._backend == "file":
                self._save_file()

    def keys(self) -> List[str]:
        """Return known key NAMES only — never values (Property 4)."""
        # The keyring backend intentionally exposes no name enumeration: doing so
        # is backend-specific and risks leaking beyond this service. We track the
        # names we manage locally for the in-memory/file backends only.
        return sorted(self._store.keys())

    # ---- encrypted-file backend --------------------------------------------

    def _cipher_key(self) -> bytes:
        """A per-service byte key for the reversible fallback obfuscation."""
        return self._service.encode("utf-8") or b"friday"

    def _load_file(self) -> Dict[str, str]:
        """Load and decrypt the fallback store; return {} when absent/corrupt."""
        path = self._fallback_path
        if path is None or not path.exists():
            return {}
        try:
            blob = path.read_bytes()
            decoded = base64.b64decode(blob)
            plaintext = _xor_cipher(decoded, self._cipher_key())
            data = json.loads(plaintext.decode("utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception:
            # Corrupt or unreadable file fails safe to an empty store rather than
            # raising — never leak partial ciphertext into an exception.
            return {}
        return {}

    def _save_file(self) -> None:
        """Encrypt and persist the fallback store."""
        path = self._fallback_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            plaintext = json.dumps(self._store).encode("utf-8")
            encoded = base64.b64encode(_xor_cipher(plaintext, self._cipher_key()))
            path.write_bytes(encoded)
        except Exception:
            # Persistence failures never raise into a caller storing a secret;
            # the in-memory copy remains authoritative for this session.
            pass

    # ---- no-leak representations -------------------------------------------

    def __repr__(self) -> str:
        """Show only the backend name and key COUNT — never any value (Property 4)."""
        count = len(self._store) if self._backend != "keyring" else 0
        return f"SecretVault(backend={self._backend!r}, keys={count})"

    __str__ = __repr__
