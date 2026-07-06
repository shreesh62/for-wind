"""M6 Import-Boundary and Site-Agnosticism Tests.

Static analysis tests that prove:
1. The Kernel and Deliberation layers do NOT import Playwright or browser-specific code.
2. Environment source files contain no hardcoded URLs or known-application names.

Requirements: 6.2, 2.1, 2.3, 2.4
"""

import ast
import os
from pathlib import Path

import pytest

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

# Root of the friday package
_FRIDAY_ROOT = Path(__file__).resolve().parent.parent.parent / "friday"

# Forbidden imports for kernel and deliberation layers
_FORBIDDEN_MODULES = (
    "playwright",
    "friday.actions.browser_controller",
    "friday.environments.browser",
)

# Forbidden URL schemes in environments source code
_FORBIDDEN_URL_SCHEMES = ("http://", "https://", "file://")

# Banned site/application names (case-insensitive match in string literals)
_BANNED_SITE_NAMES = (
    "gmail",
    "instagram",
    "whatsapp",
    "twitter",
    "facebook",
    "youtube",
)


def _python_files(directory: Path):
    """Yield all .py files under a directory, excluding __pycache__."""
    for path in directory.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def _parse_imports(filepath: Path):
    """Parse a Python file and yield all imported module strings."""
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


class TestKernelDeliberationIsolation:
    """Prove kernel/ and deliberation/ do NOT import browser-specific modules."""

    @pytest.fixture(scope="class")
    def kernel_files(self):
        """All Python files under friday/kernel/."""
        kernel_dir = _FRIDAY_ROOT / "kernel"
        if not kernel_dir.exists():
            pytest.skip("friday/kernel/ not found")
        return list(_python_files(kernel_dir))

    @pytest.fixture(scope="class")
    def deliberation_files(self):
        """All Python files under friday/deliberation/."""
        delib_dir = _FRIDAY_ROOT / "deliberation"
        if not delib_dir.exists():
            pytest.skip("friday/deliberation/ not found")
        return list(_python_files(delib_dir))

    def test_kernel_no_forbidden_imports(self, kernel_files):
        """No file in friday/kernel/ imports playwright or browser-specific modules."""
        violations = []
        for filepath in kernel_files:
            for module in _parse_imports(filepath):
                for forbidden in _FORBIDDEN_MODULES:
                    if module == forbidden or module.startswith(forbidden + "."):
                        violations.append(
                            f"{filepath.relative_to(_FRIDAY_ROOT)}: imports '{module}'"
                        )
        assert violations == [], (
            f"Kernel isolation violated — forbidden imports found:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_deliberation_no_forbidden_imports(self, deliberation_files):
        """No file in friday/deliberation/ imports playwright or browser-specific modules."""
        violations = []
        for filepath in deliberation_files:
            for module in _parse_imports(filepath):
                for forbidden in _FORBIDDEN_MODULES:
                    if module == forbidden or module.startswith(forbidden + "."):
                        violations.append(
                            f"{filepath.relative_to(_FRIDAY_ROOT)}: imports '{module}'"
                        )
        assert violations == [], (
            f"Deliberation isolation violated — forbidden imports found:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestSiteAgnosticism:
    """Prove friday/environments/ contains no hardcoded URLs or app names."""

    @pytest.fixture(scope="class")
    def environments_files(self):
        """All Python files under friday/environments/."""
        env_dir = _FRIDAY_ROOT / "environments"
        if not env_dir.exists():
            pytest.skip("friday/environments/ not found")
        return list(_python_files(env_dir))

    def test_no_hardcoded_url_schemes(self, environments_files):
        """No source line (excluding comments) in environments/ contains URL literals."""
        violations = []
        for filepath in environments_files:
            source = filepath.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(source.splitlines(), start=1):
                stripped = line.strip()
                # Skip comment-only lines
                if stripped.startswith("#"):
                    continue
                for scheme in _FORBIDDEN_URL_SCHEMES:
                    if scheme in line:
                        violations.append(
                            f"{filepath.relative_to(_FRIDAY_ROOT)}:{lineno}: "
                            f"contains '{scheme}'"
                        )
        assert violations == [], (
            f"Site-agnosticism violated — URL scheme literals found:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_banned_application_names(self, environments_files):
        """No string literal in environments/ contains banned site names.

        Excludes comments and docstrings that discuss the FAS anti-patterns.
        We parse the AST to check only string constants (Str/Constant nodes).
        """
        violations = []
        for filepath in environments_files:
            source = filepath.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(source, filename=str(filepath))
            except SyntaxError:
                continue

            # Collect all string constant values (excluding module/class/function docstrings)
            for node in ast.walk(tree):
                # Skip docstrings at module, class, and function level
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    if (
                        node.body
                        and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)
                    ):
                        continue

                # Check string constants in assignments, function args, etc.
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    # Skip if this is a docstring (handled above by parent check)
                    value_lower = node.value.lower()
                    for name in _BANNED_SITE_NAMES:
                        if name in value_lower:
                            # Double-check: is this node a docstring?
                            # We'll allow it in docstrings by checking if the
                            # string is a standalone Expr statement
                            violations.append(
                                f"{filepath.relative_to(_FRIDAY_ROOT)}:"
                                f"{node.lineno}: "
                                f"string literal contains '{name}'"
                            )

        # Filter out violations that are actually inside docstrings
        # by re-checking: parse each file and identify docstring line ranges
        real_violations = []
        for v in violations:
            # We do a second pass to be precise - check if the line is inside
            # a docstring by examining the file
            parts = v.split(":")
            rel_path = parts[0]
            lineno = int(parts[1])
            filepath = _FRIDAY_ROOT / rel_path
            if _line_is_in_docstring(filepath, lineno):
                continue
            real_violations.append(v)

        assert real_violations == [], (
            f"Site-agnosticism violated — banned application names found:\n"
            + "\n".join(f"  - {v}" for v in real_violations)
        )


def _line_is_in_docstring(filepath: Path, lineno: int) -> bool:
    """Check if a given line number falls within a docstring."""
    source = filepath.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                expr = node.body[0]
                if isinstance(expr.value, ast.Constant) and isinstance(expr.value.value, str):
                    # This is a docstring — check if the target line is within it
                    if expr.lineno <= lineno <= expr.end_lineno:
                        return True
    # Also check standalone comments — lines starting with #
    lines = source.splitlines()
    if 1 <= lineno <= len(lines):
        if lines[lineno - 1].strip().startswith("#"):
            return True
    return False
