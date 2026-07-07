"""TD-9 — tests for vault-first credential resolution (Ch 35.6).

Guards the migration of provider API keys off direct plaintext ``.env`` reads:
resolution prefers the SecretVault and falls back to the environment, and
seeding copies present env values into the vault. Values are never logged.
"""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import pytest

from friday.models.credentials import (
    resolve_secret,
    seed_vault_from_env,
    set_default_vault,
)
from friday.safety.vault import SecretVault


@pytest.fixture()
def fresh_vault():
    """Install a fresh in-memory vault as the default for each test."""
    vault = SecretVault(service="friday-test")
    set_default_vault(vault)
    yield vault
    set_default_vault(SecretVault(service="friday"))


def test_vault_value_takes_precedence_over_env(fresh_vault, monkeypatch):
    monkeypatch.setenv("SOME_KEY", "from-env")
    fresh_vault.set("SOME_KEY", "from-vault")
    assert resolve_secret("SOME_KEY") == "from-vault"


def test_env_fallback_when_vault_empty(fresh_vault, monkeypatch):
    monkeypatch.setenv("ONLY_ENV_KEY", "env-value")
    assert resolve_secret("ONLY_ENV_KEY") == "env-value"


def test_missing_everywhere_returns_empty(fresh_vault, monkeypatch):
    monkeypatch.delenv("NOT_SET_ANYWHERE", raising=False)
    assert resolve_secret("NOT_SET_ANYWHERE") == ""


def test_empty_key_returns_empty(fresh_vault):
    assert resolve_secret("") == ""


def test_seed_vault_from_env_copies_present_keys(fresh_vault, monkeypatch):
    monkeypatch.setenv("SEED_A", "a-val")
    monkeypatch.setenv("SEED_B", "b-val")
    monkeypatch.delenv("SEED_MISSING", raising=False)

    count = seed_vault_from_env(("SEED_A", "SEED_B", "SEED_MISSING"))

    assert count == 2
    assert fresh_vault.get("SEED_A") == "a-val"
    assert fresh_vault.get("SEED_B") == "b-val"
    # Missing env var is not seeded.
    assert fresh_vault.has("SEED_MISSING") is False


def test_seed_does_not_overwrite_existing_vault_value(fresh_vault, monkeypatch):
    fresh_vault.set("SEED_C", "already-in-vault")
    monkeypatch.setenv("SEED_C", "in-env")

    count = seed_vault_from_env(("SEED_C",))

    # Already present ⇒ not re-seeded, existing value preserved.
    assert count == 0
    assert fresh_vault.get("SEED_C") == "already-in-vault"


def test_seeded_value_resolves_from_vault(fresh_vault, monkeypatch):
    monkeypatch.setenv("SEED_D", "seeded")
    seed_vault_from_env(("SEED_D",))
    # After seeding, even if env changes, the vault copy is authoritative.
    monkeypatch.setenv("SEED_D", "changed-in-env")
    assert resolve_secret("SEED_D") == "seeded"


def test_vault_repr_never_leaks_values(fresh_vault):
    fresh_vault.set("SECRET_TOKEN", "super-secret-value")
    assert "super-secret-value" not in repr(fresh_vault)
    assert "super-secret-value" not in str(fresh_vault)
