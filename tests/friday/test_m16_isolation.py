"""M16 — Research Competence: static isolation guard (P9).

Mirrors the existing ``test_no_site_names_in_source`` pattern in
``tests/friday/test_web_agent.py``: it proves the M16 module contains NO per-site
conditional branching. Provider hosts (e.g. "duckduckgo") may appear ONLY in
module-level constant assignments — never inside an ``if``/``elif``/``while``
condition or a ternary test expression (Axiom 15).
"""

from __future__ import annotations

import ast
from pathlib import Path

import friday.capabilities.web_search as web_search

# Known site/host tokens that must never drive control flow.
_SITE_TOKENS = ("duckduckgo", "html.duckduckgo", "lite.duckduckgo")


def _source_and_tree():
    src = Path(web_search.__file__).read_text(encoding="utf-8")
    return src, ast.parse(src)


# Feature: m16-research-competence, Property 9: No site/app-specific branching
# (Axiom 15 static guard)
class TestProperty9NoSiteSpecificBranching:
    """Validates: Requirements 1.6, 7.3"""

    def test_module_parses(self):
        """The M16 source must be valid, parseable Python."""
        src, tree = _source_and_tree()
        assert isinstance(tree, ast.Module)
        assert src.strip()

    def test_no_site_tokens_in_conditional_tests(self):
        """No if/elif/while/ternary condition may reference a site name."""
        src, tree = _source_and_tree()

        condition_nodes = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.IfExp)):
                condition_nodes.append(node.test)

        for test_node in condition_nodes:
            segment = ast.get_source_segment(src, test_node) or ""
            low = segment.lower()
            for token in _SITE_TOKENS:
                assert token not in low, (
                    f"Site token {token!r} found in a conditional test: {segment!r}. "
                    "Provider hosts must be module-level constants, not branching logic."
                )

    def test_site_tokens_appear_only_in_module_level_constants(self):
        """Any host token must live in a module-level assignment (configuration data)."""
        src, tree = _source_and_tree()

        # Collect string constants assigned at module level.
        module_level_const_strings = []
        for node in tree.body:  # module level only
            if isinstance(node, ast.Assign):
                for value in ast.walk(node.value):
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        module_level_const_strings.append(value.value.lower())

        # Every occurrence of a host token in a *string constant* anywhere must be
        # matched by a module-level constant carrying that token (i.e. hosts are data).
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                low = node.value.lower()
                for token in _SITE_TOKENS:
                    if token in low:
                        assert any(token in c for c in module_level_const_strings), (
                            f"Host token {token!r} appears in a non-module-level "
                            f"string constant: {node.value!r}"
                        )
