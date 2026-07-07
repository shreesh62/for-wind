"""M9 Import-Boundary and Site-Agnosticism Tests.

Static-analysis tests that structurally guarantee the M9 subsystem boundaries
(Ch 15 learning proposes / memory decides + Ch 43 background isolation +
Axiom 15 site-agnosticism). They extend the M8 AST pattern (see
``test_m8_isolation.py``) with the M9 boundaries:

1. ``friday/learning/*.py`` import NONE of ``friday.memory.controller``,
   ``friday.memory.runtime``, or any ``friday.competence`` module, and reference
   neither the ``FridayMemory`` nor ``MemoryStore`` symbol (Req 5.2). Learning
   proposes procedural writes ONLY by emitting the ``memory.candidate`` kernel
   event; it never touches memory directly.
2. ``friday/background/runtime.py`` imports ONLY ``friday.events*``,
   ``friday.kernel.contracts*``, and standard-library modules (Req 5.1/5.3).
   Communication flows only through kernel-published events (Ch 52).
3. Each new M9 module carries a "Ch NN - ..." module docstring (Req 7.3).
4. The M9 file set contains no hardcoded URL scheme literals and no banned
   site/application names in string literals (Axiom 15, Req 5.4).

Requirements: 5.1, 5.2, 5.3, 5.4, 7.3
"""

import ast
import os
import re
import sys
from pathlib import Path

import pytest

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

# Root of the friday package (mirrors the M8 test's location logic).
_FRIDAY_ROOT = Path(__file__).resolve().parent.parent.parent / "friday"

# ---------------------------------------------------------------------------
# Import-boundary configuration
# ---------------------------------------------------------------------------

# Learning must not import these modules/packages (Req 5.2). Like M8 Reflection,
# it proposes procedural writes ONLY by emitting ``memory.candidate`` events.
_LEARNING_FORBIDDEN_PACKAGES = (
    "friday.memory.controller",
    "friday.memory.runtime",
    "friday.competence",
)
# ...nor reference these storage symbols anywhere in its source (Req 5.2).
_LEARNING_FORBIDDEN_SYMBOLS = ("FridayMemory", "MemoryStore")

# Background/runtime.py may import ONLY these friday.* prefixes plus stdlib
# modules (Req 5.1/5.3). Any friday.* import outside these is a violation.
_BACKGROUND_ALLOWED_FRIDAY_PREFIXES = (
    "friday.events",
    "friday.kernel.contracts",
)

# ---------------------------------------------------------------------------
# Site-agnosticism configuration - scoped to the M9 file set
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

# The M9 file set scanned for chapter docstrings, URLs and banned app names.
_M9_FILE_SET = (
    # Learning (Ch 15)
    "learning/models.py",
    "learning/patterns.py",
    "learning/generalization.py",
    "learning/validation.py",
    "learning/engine.py",
    "learning/__init__.py",
    # Temporal (Ch 49 / Ch 9.22)
    "temporal/clock.py",
    "temporal/aging.py",
    "temporal/deadlines.py",
    "temporal/__init__.py",
    # Horizon (Ch 42)
    "horizon/planner.py",
    "horizon/__init__.py",
    # Background (Ch 43)
    "background/runtime.py",
    "background/__init__.py",
)

# Matches a module docstring that starts with "Ch <number>" (e.g. "Ch 15 - ...",
# "Ch 9.22/49 - ..."). Some modules use compound chapter refs, so we assert the
# "Ch <number>" prefix rather than an exact chapter (Req 7.3).
_CHAPTER_DOCSTRING_RE = re.compile(r"^Ch \d+")


# ---------------------------------------------------------------------------
# Shared AST helpers (mirror the M8 pattern)
# ---------------------------------------------------------------------------


def _python_files(directory: Path):
    """Yield all .py files under a directory, excluding __pycache__."""
    for path in directory.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def _parse_imports(filepath: Path):
    """Parse a Python file and yield (module, imported_name) pairs.

    ``imported_name`` is the specific symbol pulled in via ``from x import y``
    (or ``None`` for a plain ``import x``).
    """
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


def _module_matches(module: str, forbidden: str) -> bool:
    """True if ``module`` equals ``forbidden`` or is a submodule of it."""
    return module == forbidden or module.startswith(forbidden + ".")


def _top_level_name(module: str) -> str:
    """Return the top-level package name of a dotted module path."""
    return module.split(".", 1)[0]


def _is_stdlib_module(module: str) -> bool:
    """True if ``module``'s top-level package is a standard-library module."""
    return _top_level_name(module) in sys.stdlib_module_names


def _docstring_line_numbers(filepath: Path) -> set:
    """Return the set of line numbers that fall inside a docstring."""
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
    """Yield (lineno, scheme) for URL schemes in non-comment, non-docstring lines."""
    source = filepath.read_text(encoding="utf-8", errors="replace")
    docstring_lines = _docstring_line_numbers(filepath)
    for lineno, line in enumerate(source.splitlines(), start=1):
        if lineno in docstring_lines:
            continue
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Drop any trailing inline comment before scanning.
        code_part = line.split("#", 1)[0]
        for scheme in _FORBIDDEN_URL_SCHEMES:
            if scheme in code_part:
                yield lineno, scheme


def _docstring_node_ids(tree: ast.AST) -> set:
    """Return ids of the ast.Constant nodes that are module/class/func docstrings."""
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


def _forbidden_symbol_hits(filepath: Path):
    """Yield each forbidden storage symbol referenced in non-docstring code.

    Comment-only lines and lines inside docstrings are ignored so a module can
    document the very constraint it enforces (e.g. "MUST NOT reference
    FridayMemory/MemoryStore") without tripping the check.
    """
    source = filepath.read_text(encoding="utf-8", errors="replace")
    docstring_lines = _docstring_line_numbers(filepath)
    for lineno, line in enumerate(source.splitlines(), start=1):
        if lineno in docstring_lines:
            continue
        code_part = line.split("#", 1)[0]
        for symbol in _LEARNING_FORBIDDEN_SYMBOLS:
            if symbol in code_part:
                yield symbol


def _m9_files():
    """Resolve the M9 file set to existing paths under friday/."""
    files: list[Path] = []
    for rel in _M9_FILE_SET:
        path = _FRIDAY_ROOT / rel
        if path.exists():
            files.append(path)
    return files


# ---------------------------------------------------------------------------
# 1. Learning isolation - no memory controller/runtime or competence imports
# ---------------------------------------------------------------------------


def test_learning_does_not_import_memory_controller_runtime_or_competence():
    """No file in friday/learning/ imports memory.controller/runtime or competence.

    Learning proposes; Memory decides. The only way Learning touches memory is by
    emitting the ``memory.candidate`` kernel event, so no learning module may
    import ``friday.memory.controller``, ``friday.memory.runtime``, or any
    ``friday.competence`` module (Req 5.2).
    """
    learning_dir = _FRIDAY_ROOT / "learning"
    assert learning_dir.exists(), "friday/learning/ not found"

    violations = []
    for filepath in _python_files(learning_dir):
        rel = filepath.relative_to(_FRIDAY_ROOT)
        for module, _name in _parse_imports(filepath):
            for forbidden in _LEARNING_FORBIDDEN_PACKAGES:
                if _module_matches(module, forbidden):
                    violations.append(f"{rel}: imports forbidden module '{module}'")

    assert violations == [], (
        "Learning isolation violated - forbidden imports found:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_learning_does_not_reference_storage_symbols():
    """No file in friday/learning/ references FridayMemory/MemoryStore in code (Req 5.2).

    Docstrings/comments are excluded because learning modules legitimately
    document this very constraint ("MUST NOT reference FridayMemory/MemoryStore")
    in their module docstrings.
    """
    learning_dir = _FRIDAY_ROOT / "learning"
    assert learning_dir.exists(), "friday/learning/ not found"

    violations = []
    for filepath in _python_files(learning_dir):
        rel = filepath.relative_to(_FRIDAY_ROOT)
        for symbol in sorted(set(_forbidden_symbol_hits(filepath))):
            violations.append(f"{rel}: references forbidden storage symbol '{symbol}'")

    assert violations == [], (
        "Learning references forbidden storage symbol(s) in code:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# 2. Background runtime imports only events + kernel.contracts + stdlib
# ---------------------------------------------------------------------------


def test_background_runtime_imports_only_allowed_modules():
    """friday/background/runtime.py imports only events, kernel.contracts, stdlib.

    The BackgroundRuntime communicates ONLY through kernel-published events
    (Ch 52). Every import must be either standard-library, or a ``friday.*``
    module under ``friday.events`` / ``friday.kernel.contracts`` (Req 5.1/5.3).
    """
    runtime = _FRIDAY_ROOT / "background" / "runtime.py"
    assert runtime.exists(), "friday/background/runtime.py not found"

    violations = []
    for module, _name in _parse_imports(runtime):
        if _top_level_name(module) == "friday":
            allowed = any(
                _module_matches(module, prefix)
                for prefix in _BACKGROUND_ALLOWED_FRIDAY_PREFIXES
            )
            if not allowed:
                violations.append(f"imports disallowed friday module '{module}'")
        elif not _is_stdlib_module(module):
            violations.append(f"imports non-stdlib module '{module}'")

    assert violations == [], (
        "Background runtime isolation violated - disallowed imports found:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# 3. Chapter docstrings on each M9 module
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel_path", sorted(_M9_FILE_SET))
def test_m9_modules_have_chapter_docstrings(rel_path):
    """Each M9 module docstring exists and starts with 'Ch <number>' (Req 7.3).

    Some modules use compound chapter refs (e.g. aging.py → "Ch 9.22/49"), so we
    assert the ``^Ch \\d+`` prefix rather than an exact chapter number.
    """
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
# 4. No hardcoded URLs or app names in the M9 file set
# ---------------------------------------------------------------------------


def test_no_hardcoded_urls_or_app_names_in_m9():
    """The M9 file set contains no URL schemes and no banned app names (Req 5.4).

    URL schemes are scanned in non-comment, non-docstring source lines; banned
    application names are scanned in string literals (via AST, excluding
    docstrings).
    """
    files = _m9_files()
    assert files, "no M9 files found"

    url_violations = []
    name_violations = []

    for filepath in files:
        rel = filepath.relative_to(_FRIDAY_ROOT)

        # URL scheme literals in non-comment/non-docstring lines.
        for lineno, scheme in _url_scheme_hits(filepath):
            url_violations.append(f"{rel}:{lineno}: contains '{scheme}'")

        # Banned app names in string literals (AST, excluding docstrings).
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
        "Site-agnosticism violated - URL scheme literals found in M9 files:\n"
        + "\n".join(f"  - {v}" for v in url_violations)
    )
    assert name_violations == [], (
        "Site-agnosticism violated - banned application names found in M9 files:\n"
        + "\n".join(f"  - {v}" for v in name_violations)
    )
