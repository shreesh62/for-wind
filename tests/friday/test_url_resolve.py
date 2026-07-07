"""TD-1 fix — tests for the generic target→URL resolver (Axiom 15 / Ch 39).

Guards the removal of the hardcoded application/site → URL map. A real URL or
bare host resolves; a bare app/site word never does (it is discovered
generically instead).
"""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import ast
from pathlib import Path

import pytest

from friday.actions.url_resolve import resolve_target_url

_FRIDAY_ROOT = Path(__file__).resolve().parent.parent.parent / "friday"
_BANNED_SITE_NAMES = ("instagram", "whatsapp", "gmail", "youtube", "reddit")


@pytest.mark.parametrize(
    "target,expected",
    [
        ("https://example.com/path", "https://example.com/path"),
        ("http://example.org", "http://example.org"),
        ("www.example.net", "https://www.example.net"),
        ("example.com", "https://example.com"),
        ("docs.example.co.uk", "https://docs.example.co.uk"),
    ],
)
def test_real_urls_and_hosts_resolve(target, expected):
    assert resolve_target_url(target) == expected


@pytest.mark.parametrize(
    "target",
    ["instagram", "gmail", "notepad", "open my mail", "send a message", "", "   "],
)
def test_bare_names_and_phrases_do_not_resolve(target):
    """Bare app/site words and phrases resolve to None (no hardcoded map)."""
    assert resolve_target_url(target) is None


def test_no_hardcoded_site_names_in_resolver_or_callers():
    """executor.py, bridge.py, and url_resolve.py contain no banned site-name
    string literals in code (Axiom 15). Docstrings are excluded."""
    files = [
        _FRIDAY_ROOT / "actions" / "url_resolve.py",
        _FRIDAY_ROOT / "executor.py",
        _FRIDAY_ROOT / "bridge.py",
    ]
    violations = []
    for path in files:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
        # Collect docstring constant node ids to exclude them.
        docstring_ids = set()
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    docstring_ids.add(id(node.body[0].value))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstring_ids
            ):
                low = node.value.lower()
                for banned in _BANNED_SITE_NAMES:
                    if banned in low:
                        violations.append(f"{path.name}:{node.lineno}: '{banned}'")

    assert violations == [], (
        "hardcoded site-name literals remain (TD-1 not fully removed):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
