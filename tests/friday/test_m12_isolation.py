"""M12 Import-Boundary and Site-Agnosticism Tests.

Guards the kernel-execution runtime's isolation (Property 7): it must delegate
to the Operator via an injected factory, so it may NOT import friday.operator,
friday.memory, friday.bridge, or friday.executor.

Requirements: 4.1, 5.1, 5.2
Property 7: Runtime isolation (import boundary)
"""

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import ast
import re
import sys
from pathlib import Path

import pytest

_FRIDAY_ROOT = Path(__file__).resolve().parent.parent.parent / "friday"

_EXECUTION_ALLOWED_FRIDAY_PREFIXES = (
    "friday.events",
    "friday.kernel.contracts",
)

_EXECUTION_FORBIDDEN_PREFIXES = (
    "friday.operator",
    "friday.memory",
    "friday.bridge",
    "friday.executor",
)

_FORBIDDEN_URL_SCHEMES = ("http://", "https://", "file://")
_BANNED_SITE_NAMES = ("gmail", "instagram", "whatsapp", "twitter", "facebook", "youtube")

_M12_FILE_SET = (
    "kernel/execution.py",
    "kernel/memory_sink.py",
)

_CHAPTER_DOCSTRING_RE = re.compile(r"^Ch \d+")


def _parse_imports(filepath: Path):
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
            if node.module:
                yield node.module


def _module_matches(module: str, target: str) -> bool:
    return module == target or module.startswith(target + ".")


def _top_level(module: str) -> str:
    return module.split(".", 1)[0]


def _is_stdlib(module: str) -> bool:
    return _top_level(module) in sys.stdlib_module_names


def _docstring_line_numbers(filepath: Path) -> set:
    source = filepath.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return set()
    lines: set = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                expr = node.body[0]
                if isinstance(expr.value, ast.Constant) and isinstance(expr.value.value, str):
                    start = expr.value.lineno
                    end = getattr(expr.value, "end_lineno", start)
                    lines.update(range(start, end + 1))
    return lines


def _docstring_node_ids(tree: ast.AST) -> set:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                ids.add(id(node.body[0].value))
    return ids


@pytest.mark.parametrize("rel_path", sorted(_M12_FILE_SET))
def test_m12_modules_have_chapter_docstrings(rel_path):
    path = _FRIDAY_ROOT / rel_path
    assert path.exists(), f"{rel_path} not found"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    doc = ast.get_docstring(tree)
    assert doc is not None and _CHAPTER_DOCSTRING_RE.match(doc), (
        f"{rel_path} lacks a 'Ch <number>' docstring"
    )


def test_execution_runtime_import_boundary():
    """execution.py imports only events + kernel.contracts + stdlib; never
    operator/memory/bridge/executor."""
    path = _FRIDAY_ROOT / "kernel" / "execution.py"
    violations = []
    for module in _parse_imports(path):
        for forbidden in _EXECUTION_FORBIDDEN_PREFIXES:
            if _module_matches(module, forbidden):
                violations.append(f"forbidden import '{module}'")
        if _top_level(module) == "friday":
            allowed = any(
                _module_matches(module, p) for p in _EXECUTION_ALLOWED_FRIDAY_PREFIXES
            )
            if not allowed:
                violations.append(f"disallowed friday import '{module}'")
        elif not _is_stdlib(module):
            violations.append(f"non-stdlib import '{module}'")
    assert violations == [], "execution.py isolation violated:\n" + "\n".join(violations)


def test_memory_sink_imports_stdlib_only():
    path = _FRIDAY_ROOT / "kernel" / "memory_sink.py"
    violations = []
    for module in _parse_imports(path):
        if _top_level(module) == "friday":
            violations.append(f"memory_sink imports friday module '{module}'")
        elif not _is_stdlib(module):
            violations.append(f"memory_sink imports non-stdlib '{module}'")
    assert violations == [], "\n".join(violations)


def test_no_hardcoded_urls_or_app_names_in_m12():
    url_violations = []
    name_violations = []
    for rel in _M12_FILE_SET:
        path = _FRIDAY_ROOT / rel
        source = path.read_text(encoding="utf-8", errors="replace")
        docstring_lines = _docstring_line_numbers(path)
        for lineno, line in enumerate(source.splitlines(), start=1):
            if lineno in docstring_lines:
                continue
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            code = line.split("#", 1)[0]
            for scheme in _FORBIDDEN_URL_SCHEMES:
                if scheme in code:
                    url_violations.append(f"{rel}:{lineno}: '{scheme}'")
        tree = ast.parse(source, filename=str(path))
        doc_ids = _docstring_node_ids(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_ids:
                low = node.value.lower()
                for banned in _BANNED_SITE_NAMES:
                    if banned in low:
                        name_violations.append(f"{rel}:{node.lineno}: '{banned}'")
    assert url_violations == [], "\n".join(url_violations)
    assert name_violations == [], "\n".join(name_violations)
