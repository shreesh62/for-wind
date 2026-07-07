"""M10 Import-Boundary and Site-Agnosticism Tests.

Static-analysis tests that structurally guarantee the M10 domain layer stays a
set of pure composition leaves (Ch 37/39/40/41). They mirror the M9 AST pattern
(see ``test_m9_isolation.py``) with the M10 boundaries:

1. Each M10 domain module carries a "Ch NN - ..." module docstring (Req 5.1).
2. Every ``friday.*`` import under ``friday/domains/`` matches one of the allowed
   prefixes (``friday.capabilities``, ``friday.verification.evidence_law``,
   ``friday.actions.result``, ``friday.domains``); nothing imports
   ``friday.kernel``, ``friday.memory``, or ``friday.goals``. Non-friday imports
   must be standard-library (Req 5.2).
3. No domain module (research/communication/documents/software) imports another
   sibling domain module — they may import ``friday.domains.models`` only, so
   deleting any domain leaves the others intact (Req 4.3).
4. The M10 file set contains no hardcoded URL scheme literals and no banned
   site/application names in string literals (Axiom 15, Req 5.3).

Requirements: 4.4, 5.1, 5.2, 5.3
Property 11: Domains hardcode no application or site name
"""

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import ast
import re
import sys
from pathlib import Path

import pytest

# Root of the friday package (mirrors the M9 test's location logic).
_FRIDAY_ROOT = Path(__file__).resolve().parent.parent.parent / "friday"

# ---------------------------------------------------------------------------
# Import-boundary configuration
# ---------------------------------------------------------------------------

# Domain modules may import ONLY these friday.* prefixes plus stdlib modules
# (Req 5.2). Any friday.* import outside these is a violation - especially
# friday.kernel.*, friday.memory.*, friday.goals.*.
_DOMAIN_ALLOWED_FRIDAY_PREFIXES = (
    "friday.capabilities",
    "friday.verification.evidence_law",
    "friday.actions.result",
    "friday.domains",
)

# The sibling domain modules. A domain must not import another sibling domain;
# it may compose only ``friday.domains.models`` (Req 4.3).
_SIBLING_DOMAIN_MODULES = (
    "friday.domains.research",
    "friday.domains.communication",
    "friday.domains.documents",
    "friday.domains.software",
)

# ---------------------------------------------------------------------------
# Site-agnosticism configuration - scoped to the M10 file set
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

# The M10 domain file set scanned for chapter docstrings, URLs and app names.
_M10_FILE_SET = (
    "domains/models.py",
    "domains/research.py",
    "domains/communication.py",
    "domains/documents.py",
    "domains/software.py",
    "domains/__init__.py",
)

# Matches a module docstring that starts with "Ch <number>" (e.g. "Ch 37 - ...",
# "Ch 37/39/40/41 - ..."). Some modules use compound chapter refs, so we assert
# the "Ch <number>" prefix rather than an exact chapter (Req 5.1).
_CHAPTER_DOCSTRING_RE = re.compile(r"^Ch \d+")


# ---------------------------------------------------------------------------
# Shared AST helpers (mirror the M9 pattern)
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


def _module_matches(module: str, target: str) -> bool:
    """True if ``module`` equals ``target`` or is a submodule of it."""
    return module == target or module.startswith(target + ".")


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


def _m10_files():
    """Resolve the M10 file set to existing paths under friday/."""
    files: list[Path] = []
    for rel in _M10_FILE_SET:
        path = _FRIDAY_ROOT / rel
        if path.exists():
            files.append(path)
    return files


# ---------------------------------------------------------------------------
# 1. Chapter docstrings on each M10 module
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel_path", sorted(_M10_FILE_SET))
def test_m10_modules_have_chapter_docstrings(rel_path):
    """Each M10 module docstring exists and starts with 'Ch <number>' (Req 5.1).

    Some modules use compound chapter refs (e.g. models.py -> "Ch 37/39/40/41"),
    so we assert the ``^Ch \\d+`` prefix rather than an exact chapter number.
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
# 2. Domains import only allowed friday.* prefixes + stdlib
# ---------------------------------------------------------------------------


def test_domains_import_only_allowed_modules():
    """Every .py under friday/domains/ imports only allowed friday.* + stdlib.

    Domains are pure composition leaves: every ``friday.*`` import must match one
    of ``friday.capabilities``, ``friday.verification.evidence_law``,
    ``friday.actions.result`` or ``friday.domains``; anything else (especially
    ``friday.kernel``, ``friday.memory``, ``friday.goals``) is a violation. Every
    non-friday import must be standard-library (Req 5.2).
    """
    domains_dir = _FRIDAY_ROOT / "domains"
    assert domains_dir.exists(), "friday/domains/ not found"

    violations = []
    for filepath in _python_files(domains_dir):
        rel = filepath.relative_to(_FRIDAY_ROOT)
        for module, _name in _parse_imports(filepath):
            if _top_level_name(module) == "friday":
                allowed = any(
                    _module_matches(module, prefix)
                    for prefix in _DOMAIN_ALLOWED_FRIDAY_PREFIXES
                )
                if not allowed:
                    violations.append(
                        f"{rel}: imports disallowed friday module '{module}'"
                    )
            elif not _is_stdlib_module(module):
                violations.append(f"{rel}: imports non-stdlib module '{module}'")

    assert violations == [], (
        "Domain import isolation violated - disallowed imports found:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# 3. No domain imports another sibling domain
# ---------------------------------------------------------------------------


def test_no_domain_imports_another_domain():
    """No domain module imports a different sibling domain module (Req 4.3).

    research/communication/documents/software may compose only
    ``friday.domains.models``; importing another sibling domain would make the
    layer non-deletable, so it is forbidden.
    """
    violations = []
    for sibling in _SIBLING_DOMAIN_MODULES:
        rel_path = sibling.replace(".", "/") + ".py"
        filepath = _FRIDAY_ROOT / Path(rel_path).relative_to("friday")
        if not filepath.exists():
            continue
        rel = filepath.relative_to(_FRIDAY_ROOT)
        for module, _name in _parse_imports(filepath):
            for other in _SIBLING_DOMAIN_MODULES:
                if other == sibling:
                    continue
                if _module_matches(module, other):
                    violations.append(
                        f"{rel}: imports sibling domain '{module}'"
                    )

    assert violations == [], (
        "Domain cross-dependency violated - a domain imports another domain:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# 4. No hardcoded URLs or app names in the M10 file set
# ---------------------------------------------------------------------------


def test_no_hardcoded_urls_or_app_names_in_m10():
    """The M10 file set contains no URL schemes and no banned app names (Req 5.3).

    URL schemes are scanned in non-comment, non-docstring source lines; banned
    application names are scanned in string literals (via AST, excluding
    docstrings). Property 11: Domains hardcode no application or site name.
    """
    files = _m10_files()
    assert files, "no M10 files found"

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
        "Site-agnosticism violated - URL scheme literals found in M10 files:\n"
        + "\n".join(f"  - {v}" for v in url_violations)
    )
    assert name_violations == [], (
        "Site-agnosticism violated - banned application names found in M10 files:\n"
        + "\n".join(f"  - {v}" for v in name_violations)
    )
