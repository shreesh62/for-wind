"""M4-Gaps Import-Boundary and Site-Agnosticism Tests.

Static-analysis tests that structurally guarantee the M4-gap subsystem
boundaries (Ch 52 kernel-event communication + Axiom 15 site-agnosticism).
They mirror the M8 AST pattern (see ``test_m8_isolation.py``) and encode the
Requirement 6.2 import contract per subsystem:

1. ``friday/safety/*.py`` import ONLY the standard library, ``friday.events*``,
   ``friday.safety*`` (intra-package), and an OPTIONAL guarded ``keyring``. They
   MUST NOT import memory/competence/learning/resources/identity/cognition.
2. ``friday/resources/*.py`` import ONLY the standard library, ``friday.events*``,
   ``friday.kernel.contracts*``, and ``friday.resources*`` (intra-package).
3. ``friday/identity/*.py`` import ONLY the standard library, ``friday.events*``,
   and ``friday.identity*`` (intra-package).
4. ``friday/cognition/state.py`` imports ONLY the standard library and
   ``friday.events*`` (scoped to state.py — other cognition/ modules such as
   reflection.py legitimately import friday.deliberation).
5. Every module in the M4 file set carries a 'Ch NN' module docstring.
6. No hardcoded application/site names or URLs appear anywhere in the M4 file
   set (Axiom 15).

Requirements: 6.1, 6.2, 6.3, 7.3
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
# Import-boundary configuration (Req 6.2)
# ---------------------------------------------------------------------------

# Each entry: subsystem label -> (directory-or-file, allowed friday prefixes,
# extra top-level modules allowed beyond stdlib). ``friday.events`` is allowed
# everywhere; each subsystem may also import its own package.
_SAFETY_ALLOWED_FRIDAY = ("friday.events", "friday.safety")
_RESOURCES_ALLOWED_FRIDAY = (
    "friday.events",
    "friday.kernel.contracts",
    "friday.resources",
)
_IDENTITY_ALLOWED_FRIDAY = ("friday.events", "friday.identity")
_COGNITION_STATE_ALLOWED_FRIDAY = ("friday.events",)

# keyring is the ONLY optional non-stdlib top-level import permitted (safety).
_SAFETY_EXTRA_TOPLEVEL = ("keyring",)

# ---------------------------------------------------------------------------
# Site-agnosticism configuration (Req 6.3 / Axiom 15)
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

# The M4 file set — every module scanned for docstrings / URLs / banned names.
_M4_FILE_SET = (
    "safety/permission.py",
    "safety/policy.py",
    "safety/vault.py",
    "safety/__init__.py",
    "resources/types.py",
    "resources/registry.py",
    "resources/scheduler.py",
    "resources/__init__.py",
    "identity/identity.py",
    "identity/__init__.py",
    "cognition/state.py",
)

# Matches a module docstring that starts with "Ch <number>" (e.g. "Ch 35 — ...").
_CHAPTER_DOCSTRING_RE = re.compile(r"^Ch \d+")

# Standard-library detection via the interpreter's own manifest.
_STDLIB = set(sys.stdlib_module_names)


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
    """Parse a Python file and yield the imported module string for each import.

    For ``import x.y`` yields ``"x.y"``; for ``from x.y import z`` yields
    ``"x.y"``. Relative imports (``from . import x``) yield ``None`` and are
    ignored by callers (they are intra-package by construction).
    """
    source = filepath.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import — intra-package, always allowed.
                continue
            if node.module:
                yield node.module


def _is_allowed_import(
    module: str,
    allowed_friday: tuple,
    extra_toplevel: tuple = (),
) -> bool:
    """True when ``module`` satisfies the import contract for a subsystem."""
    top = module.split(".")[0]

    # Standard-library modules (including __future__) are always allowed.
    if top in _STDLIB:
        return True

    # A small allow-list of optional non-stdlib top-level modules (keyring).
    if top in extra_toplevel:
        return True

    # friday.* imports must match one of the permitted prefixes exactly or as
    # a sub-package (prefix or prefix + ".").
    for prefix in allowed_friday:
        if module == prefix or module.startswith(prefix + "."):
            return True

    return False


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


def _m4_files():
    """Resolve the M4 file set to existing paths under friday/."""
    files: list[Path] = []
    for rel in _M4_FILE_SET:
        path = _FRIDAY_ROOT / rel
        if path.exists():
            files.append(path)
    return files


def _boundary_violations(files, allowed_friday, extra_toplevel=()):
    """Return a list of human-readable import-boundary violations for ``files``."""
    violations = []
    for filepath in files:
        rel = filepath.relative_to(_FRIDAY_ROOT)
        for module in _parse_imports(filepath):
            if not _is_allowed_import(module, allowed_friday, extra_toplevel):
                violations.append(f"{rel}: imports forbidden module '{module}'")
    return violations


# ---------------------------------------------------------------------------
# 1. Safety import boundary
# ---------------------------------------------------------------------------


def test_safety_imports_only_events_stdlib_and_optional_keyring():
    """friday/safety/*.py import only stdlib + friday.events* + friday.safety* +
    an optional guarded ``keyring`` — never memory/competence/learning/resources/
    identity/cognition (Req 6.2)."""
    safety_dir = _FRIDAY_ROOT / "safety"
    assert safety_dir.exists(), "friday/safety/ not found"

    violations = _boundary_violations(
        list(_python_files(safety_dir)),
        _SAFETY_ALLOWED_FRIDAY,
        _SAFETY_EXTRA_TOPLEVEL,
    )
    assert violations == [], (
        "Safety import boundary violated:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# 2. Resources import boundary
# ---------------------------------------------------------------------------


def test_resources_import_only_events_contracts_and_stdlib():
    """friday/resources/*.py import only stdlib + friday.events* +
    friday.kernel.contracts* + friday.resources* (Req 6.2)."""
    resources_dir = _FRIDAY_ROOT / "resources"
    assert resources_dir.exists(), "friday/resources/ not found"

    violations = _boundary_violations(
        list(_python_files(resources_dir)),
        _RESOURCES_ALLOWED_FRIDAY,
    )
    assert violations == [], (
        "Resources import boundary violated:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# 3. Identity import boundary
# ---------------------------------------------------------------------------


def test_identity_imports_only_events_and_stdlib():
    """friday/identity/*.py import only stdlib + friday.events* + friday.identity*
    (Req 6.2)."""
    identity_dir = _FRIDAY_ROOT / "identity"
    assert identity_dir.exists(), "friday/identity/ not found"

    violations = _boundary_violations(
        list(_python_files(identity_dir)),
        _IDENTITY_ALLOWED_FRIDAY,
    )
    assert violations == [], (
        "Identity import boundary violated:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# 4. Cognitive-state import boundary (scoped to state.py)
# ---------------------------------------------------------------------------


def test_cognition_state_imports_only_events_and_stdlib():
    """friday/cognition/state.py imports only stdlib + friday.events* (Req 6.2).

    Scoped to state.py specifically — sibling cognition/ modules such as
    reflection.py legitimately import friday.deliberation.
    """
    state_py = _FRIDAY_ROOT / "cognition" / "state.py"
    assert state_py.exists(), "friday/cognition/state.py not found"

    violations = _boundary_violations(
        [state_py],
        _COGNITION_STATE_ALLOWED_FRIDAY,
    )
    assert violations == [], (
        "Cognitive-state import boundary violated:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# 5. Chapter docstrings on every M4 module
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel_path", _M4_FILE_SET)
def test_m4_modules_have_chapter_docstrings(rel_path):
    """Each M4 module docstring exists and starts with 'Ch <number>' (Req 7.3)."""
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
# 6. No hardcoded URLs or app names in the M4 file set
# ---------------------------------------------------------------------------


def test_no_hardcoded_urls_or_app_names_in_m4():
    """The M4 file set contains no URL schemes and no banned app names (Req 6.3).

    URL schemes are scanned in non-comment, non-docstring source lines; banned
    application names are scanned in string literals (via AST, excluding
    docstrings).
    """
    files = _m4_files()
    assert files, "no M4 files found"

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
        "Site-agnosticism violated - URL scheme literals found in M4 files:\n"
        + "\n".join(f"  - {v}" for v in url_violations)
    )
    assert name_violations == [], (
        "Site-agnosticism violated - banned application names found in M4 files:\n"
        + "\n".join(f"  - {v}" for v in name_violations)
    )
