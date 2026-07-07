"""M11 Import-Boundary and Site-Agnosticism Tests.

Static-analysis tests that structurally guarantee the M11 subsystem boundaries
(Ch 27 evolution, Ch 54 plugins, Ch 47 federation, Ch 55 benchmarks). They mirror
the M10 AST pattern (see ``test_m10_isolation.py``):

1. Each M11 module carries a "Ch NN - ..." module docstring (Req 5.1).
2. No file under ``friday/plugins/`` imports a protected subsystem
   (``friday.kernel``/``friday.world``/``friday.goals``/``friday.safety``/
   ``friday.verification``) — Ch 54.5 (Req 5.2).
3. No file under ``friday/evolution/`` imports ``friday.plugins`` (Req 5.2).
4. Every ``friday.*`` import under ``friday/federation/`` is under
   ``friday.resources`` or ``friday.events``; non-friday imports are stdlib (Req 5.2).
5. The M11 file set contains no hardcoded URL scheme literals and no banned
   site/application names in string literals (Axiom 15, Req 5.3/5.4).

Requirements: 5.1, 5.2, 5.3, 5.4
Property 11: M11 modules hardcode no application or site name
"""

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import ast
import re
import sys
from pathlib import Path

import pytest

# Root of the friday package (mirrors the M10 test's location logic).
_FRIDAY_ROOT = Path(__file__).resolve().parent.parent.parent / "friday"

# ---------------------------------------------------------------------------
# Import-boundary configuration
# ---------------------------------------------------------------------------

# Plugins must NOT reach any protected subsystem (Ch 54.5).
_PLUGIN_FORBIDDEN_PREFIXES = (
    "friday.kernel",
    "friday.world",
    "friday.goals",
    "friday.safety",
    "friday.verification",
)

# Federation may import ONLY these friday.* prefixes plus stdlib (Req 5.2).
# (Intra-package imports under friday.federation are naturally allowed.)
_FEDERATION_ALLOWED_FRIDAY_PREFIXES = (
    "friday.resources",
    "friday.events",
    "friday.federation",
)

# ---------------------------------------------------------------------------
# Site-agnosticism configuration - scoped to the M11 file set
# ---------------------------------------------------------------------------

_FORBIDDEN_URL_SCHEMES = ("http://", "https://", "file://")

_BANNED_SITE_NAMES = (
    "gmail",
    "instagram",
    "whatsapp",
    "twitter",
    "facebook",
    "youtube",
)

# The M11 file set scanned for chapter docstrings, URLs and app names.
_M11_FILE_SET = (
    "benchmarks/__init__.py",
    "benchmarks/suite.py",
    "evolution/__init__.py",
    "evolution/lifecycle.py",
    "evolution/rollback.py",
    "evolution/pipeline.py",
    "plugins/__init__.py",
    "plugins/manifest.py",
    "plugins/sandbox.py",
    "plugins/loader.py",
    "plugins/registry.py",
    "federation/__init__.py",
    "federation/directory.py",
    "federation/federation.py",
)

_CHAPTER_DOCSTRING_RE = re.compile(r"^Ch \d+")


# ---------------------------------------------------------------------------
# Shared AST helpers (mirror the M10 pattern)
# ---------------------------------------------------------------------------


def _python_files(directory: Path):
    for path in directory.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def _parse_imports(filepath: Path):
    source = filepath.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, None
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for alias in node.names:
                    yield node.module, alias.name


def _module_matches(module: str, target: str) -> bool:
    return module == target or module.startswith(target + ".")


def _top_level_name(module: str) -> str:
    return module.split(".", 1)[0]


def _is_stdlib_module(module: str) -> bool:
    return _top_level_name(module) in sys.stdlib_module_names


def _docstring_line_numbers(filepath: Path) -> set:
    source = filepath.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return set()
    lines: set = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            if node.body and isinstance(node.body[0], ast.Expr):
                expr = node.body[0]
                if isinstance(expr.value, ast.Constant) and isinstance(
                    expr.value.value, str
                ):
                    start = expr.value.lineno
                    end = getattr(expr.value, "end_lineno", start)
                    lines.update(range(start, end + 1))
    return lines


def _url_scheme_hits(filepath: Path):
    source = filepath.read_text(encoding="utf-8", errors="replace")
    docstring_lines = _docstring_line_numbers(filepath)
    for lineno, line in enumerate(source.splitlines(), start=1):
        if lineno in docstring_lines:
            continue
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        code_part = line.split("#", 1)[0]
        for scheme in _FORBIDDEN_URL_SCHEMES:
            if scheme in code_part:
                yield lineno, scheme


def _docstring_node_ids(tree: ast.AST) -> set:
    docstring_nodes: set = set()
    for node in ast.walk(tree):
        if isinstance(
            node,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                docstring_nodes.add(id(node.body[0].value))
    return docstring_nodes


def _m11_files():
    files = []
    for rel in _M11_FILE_SET:
        path = _FRIDAY_ROOT / rel
        if path.exists():
            files.append(path)
    return files


# ---------------------------------------------------------------------------
# 1. Chapter docstrings on each M11 module
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel_path", sorted(_M11_FILE_SET))
def test_m11_modules_have_chapter_docstrings(rel_path):
    path = _FRIDAY_ROOT / rel_path
    assert path.exists(), f"{rel_path} not found under friday/"
    source = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=str(path))
    docstring = ast.get_docstring(tree)
    assert docstring is not None, f"{rel_path} has no module docstring"
    assert _CHAPTER_DOCSTRING_RE.match(docstring), (
        f"{rel_path} docstring does not start with 'Ch <number>': "
        f"{docstring.splitlines()[0]!r}"
    )


# ---------------------------------------------------------------------------
# 2. Plugins never import a protected subsystem (Ch 54.5)
# ---------------------------------------------------------------------------


def test_plugins_do_not_import_protected_subsystems():
    plugins_dir = _FRIDAY_ROOT / "plugins"
    assert plugins_dir.exists(), "friday/plugins/ not found"

    violations = []
    for filepath in _python_files(plugins_dir):
        rel = filepath.relative_to(_FRIDAY_ROOT)
        for module, _name in _parse_imports(filepath):
            for forbidden in _PLUGIN_FORBIDDEN_PREFIXES:
                if _module_matches(module, forbidden):
                    violations.append(f"{rel}: imports protected module '{module}'")

    assert violations == [], (
        "Plugin isolation violated - protected imports found:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# 3. Evolution never imports plugins
# ---------------------------------------------------------------------------


def test_evolution_does_not_import_plugins():
    evolution_dir = _FRIDAY_ROOT / "evolution"
    assert evolution_dir.exists(), "friday/evolution/ not found"

    violations = []
    for filepath in _python_files(evolution_dir):
        rel = filepath.relative_to(_FRIDAY_ROOT)
        for module, _name in _parse_imports(filepath):
            if _module_matches(module, "friday.plugins"):
                violations.append(f"{rel}: imports '{module}'")

    assert violations == [], (
        "Evolution isolation violated - imports plugins:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# 4. Federation imports only resources + events + stdlib
# ---------------------------------------------------------------------------


def test_federation_imports_only_resources_events_stdlib():
    federation_dir = _FRIDAY_ROOT / "federation"
    assert federation_dir.exists(), "friday/federation/ not found"

    violations = []
    for filepath in _python_files(federation_dir):
        rel = filepath.relative_to(_FRIDAY_ROOT)
        for module, _name in _parse_imports(filepath):
            if _top_level_name(module) == "friday":
                allowed = any(
                    _module_matches(module, prefix)
                    for prefix in _FEDERATION_ALLOWED_FRIDAY_PREFIXES
                )
                if not allowed:
                    violations.append(
                        f"{rel}: imports disallowed friday module '{module}'"
                    )
            elif not _is_stdlib_module(module):
                violations.append(f"{rel}: imports non-stdlib module '{module}'")

    assert violations == [], (
        "Federation isolation violated - disallowed imports found:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# 5. No hardcoded URLs or app names in the M11 file set
# ---------------------------------------------------------------------------


def test_no_hardcoded_urls_or_app_names_in_m11():
    files = _m11_files()
    assert files, "no M11 files found"

    url_violations = []
    name_violations = []

    for filepath in files:
        rel = filepath.relative_to(_FRIDAY_ROOT)

        for lineno, scheme in _url_scheme_hits(filepath):
            url_violations.append(f"{rel}:{lineno}: contains '{scheme}'")

        source = filepath.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source, filename=str(filepath))
        except SyntaxError:
            continue

        docstring_nodes = _docstring_node_ids(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstring_nodes
            ):
                value_lower = node.value.lower()
                for banned in _BANNED_SITE_NAMES:
                    if banned in value_lower:
                        name_violations.append(
                            f"{rel}:{node.lineno}: string literal contains '{banned}'"
                        )

    assert url_violations == [], (
        "Site-agnosticism violated - URL scheme literals found in M11 files:\n"
        + "\n".join(f"  - {v}" for v in url_violations)
    )
    assert name_violations == [], (
        "Site-agnosticism violated - banned application names found in M11 files:\n"
        + "\n".join(f"  - {v}" for v in name_violations)
    )
