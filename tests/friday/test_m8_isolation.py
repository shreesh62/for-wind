"""M8 Import-Boundary and Site-Agnosticism Tests.

Static-analysis tests that structurally guarantee the M8 subsystem boundaries
(Ch 52 kernel-event communication + Axiom 15 site-agnosticism). They extend the
M6/M7 AST pattern (see ``test_m7_isolation.py``) with the M8 boundaries:

1. ``friday/cognition/reflection.py`` imports NONE of ``friday.memory.*``,
   ``friday.competence.*``, or ``friday.recovery.*``, and references neither the
   ``FridayMemory`` nor ``MemoryStore`` symbol (Req 5.2). Reflection touches
   memory ONLY by emitting the ``memory.candidate`` kernel event.
2. ``friday/competence/*.py`` does not import ``friday.memory.controller`` (Req 5.3).
3. ``friday/recovery/*.py`` does not import ``friday.memory.controller`` (Req 5.3).
4. Each new M8 module carries a "Ch NN - ..." module docstring (Req 7.3).
5. The M8 file set contains no hardcoded URL scheme literals and no banned
   site/application names in string literals (Req 5.4).

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 7.3
"""

import ast
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

# Root of the friday package (mirrors the M7 test's location logic).
_FRIDAY_ROOT = Path(__file__).resolve().parent.parent.parent / "friday"

# ---------------------------------------------------------------------------
# Import-boundary configuration
# ---------------------------------------------------------------------------

# Reflection must not import ANY submodule of these packages (Req 5.2).
_REFLECTION_FORBIDDEN_PACKAGES = (
    "friday.memory",
    "friday.competence",
    "friday.recovery",
)
# ...nor reference these symbols anywhere in its source (Req 5.2).
_REFLECTION_FORBIDDEN_SYMBOLS = ("FridayMemory", "MemoryStore")

# Competence and Recovery must not import the memory controller (Req 5.3).
_MEMORY_CONTROLLER_MODULE = "friday.memory.controller"

# ---------------------------------------------------------------------------
# Site-agnosticism configuration - scoped to the M8 file set
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

# Chapter-docstring expectations: module path (relative to friday/) → chapter no.
_CHAPTER_DOCSTRING_MODULES = {
    "cognition/reflection.py": 13,
    "memory/runtime.py": 14,
    "competence/model.py": 28,
    "recovery/engine.py": 34,
}

# The M8 file set scanned for URLs and banned app names (Req 5.4).
_M8_FILE_SET = (
    "cognition/reflection.py",
    "cognition/__init__.py",
    "memory/runtime.py",
    "competence/model.py",
    "competence/__init__.py",
    "recovery/engine.py",
    "recovery/__init__.py",
)

# Matches a module docstring that starts with "Ch <number>" (e.g. "Ch 13 - ...").
_CHAPTER_DOCSTRING_RE = re.compile(r"^Ch \d+")


# ---------------------------------------------------------------------------
# Shared AST helpers (mirror the M7 pattern)
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
        for symbol in _REFLECTION_FORBIDDEN_SYMBOLS:
            if symbol in code_part:
                yield symbol


def _m8_files():
    """Resolve the M8 file set to existing paths under friday/."""
    files: list[Path] = []
    for rel in _M8_FILE_SET:
        path = _FRIDAY_ROOT / rel
        if path.exists():
            files.append(path)
    return files


# ---------------------------------------------------------------------------
# 1. Reflection isolation
# ---------------------------------------------------------------------------


def test_reflection_does_not_import_memory_competence_recovery():
    """friday/cognition/reflection.py imports no memory/competence/recovery module.

    Reflection proposes; Memory decides. The only way Reflection touches memory
    is by emitting the ``memory.candidate`` kernel event, so it MUST NOT import
    any submodule of friday.memory / friday.competence / friday.recovery, nor
    reference the FridayMemory / MemoryStore symbols (Req 5.2).
    """
    reflection = _FRIDAY_ROOT / "cognition" / "reflection.py"
    assert reflection.exists(), "friday/cognition/reflection.py not found"

    violations = []
    for module, _name in _parse_imports(reflection):
        for forbidden in _REFLECTION_FORBIDDEN_PACKAGES:
            if _module_matches(module, forbidden):
                violations.append(f"imports forbidden module '{module}'")
    assert violations == [], (
        "Reflection isolation violated - forbidden imports found:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )

    # No CODE reference to the forbidden storage symbols. Docstrings/comments are
    # excluded because reflection.py legitimately documents this very constraint
    # ("MUST NOT reference FridayMemory/MemoryStore") in its module docstring.
    symbol_hits = sorted(_forbidden_symbol_hits(reflection))
    assert symbol_hits == [], (
        "Reflection references forbidden storage symbol(s) in code: "
        + ", ".join(symbol_hits)
    )


# ---------------------------------------------------------------------------
# 2. Competence must not import the memory controller
# ---------------------------------------------------------------------------


def test_competence_does_not_import_memory_controller():
    """No file in friday/competence/ imports friday.memory.controller (Req 5.3)."""
    competence_dir = _FRIDAY_ROOT / "competence"
    assert competence_dir.exists(), "friday/competence/ not found"

    violations = []
    for filepath in _python_files(competence_dir):
        for module, _name in _parse_imports(filepath):
            if _module_matches(module, _MEMORY_CONTROLLER_MODULE):
                violations.append(
                    f"{filepath.relative_to(_FRIDAY_ROOT)}: imports '{module}'"
                )
    assert violations == [], (
        "Competence isolation violated - memory.controller imports found:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# 3. Recovery must not import the memory controller
# ---------------------------------------------------------------------------


def test_recovery_does_not_import_memory_controller():
    """No file in friday/recovery/ imports friday.memory.controller (Req 5.3)."""
    recovery_dir = _FRIDAY_ROOT / "recovery"
    assert recovery_dir.exists(), "friday/recovery/ not found"

    violations = []
    for filepath in _python_files(recovery_dir):
        for module, _name in _parse_imports(filepath):
            if _module_matches(module, _MEMORY_CONTROLLER_MODULE):
                violations.append(
                    f"{filepath.relative_to(_FRIDAY_ROOT)}: imports '{module}'"
                )
    assert violations == [], (
        "Recovery isolation violated - memory.controller imports found:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# 4. Chapter docstrings on each M8 module
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel_path, chapter",
    sorted(_CHAPTER_DOCSTRING_MODULES.items()),
)
def test_m8_modules_have_chapter_docstrings(rel_path, chapter):
    """Each M8 module docstring exists and starts with 'Ch <number>' (Req 7.3).

    reflection→Ch 13, runtime→Ch 14, model→Ch 28, engine→Ch 34.
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
    assert docstring.startswith(f"Ch {chapter}"), (
        f"{rel_path} docstring should start with 'Ch {chapter}': "
        f"{docstring.splitlines()[0]!r}"
    )


# ---------------------------------------------------------------------------
# 5. No hardcoded URLs or app names in the M8 file set
# ---------------------------------------------------------------------------


def test_no_hardcoded_urls_or_app_names_in_m8():
    """The M8 file set contains no URL schemes and no banned app names (Req 5.4).

    URL schemes are scanned in non-comment, non-docstring source lines; banned
    application names are scanned in string literals (via AST, excluding
    docstrings).
    """
    files = _m8_files()
    assert files, "no M8 files found"

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
        "Site-agnosticism violated - URL scheme literals found in M8 files:\n"
        + "\n".join(f"  - {v}" for v in url_violations)
    )
    assert name_violations == [], (
        "Site-agnosticism violated - banned application names found in M8 files:\n"
        + "\n".join(f"  - {v}" for v in name_violations)
    )
