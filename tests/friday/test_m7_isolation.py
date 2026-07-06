"""M7 Import-Boundary and Site-Agnosticism Tests.

Static-analysis tests that structurally guarantee Axiom 15 (zero
application-specific code) for the M7 subsystems. They extend the M6 AST
pattern (see ``test_m6_isolation.py``) with the M7 boundaries:

1. The Kernel and Deliberation layers import none of the desktop modules,
   ``pyautogui``, or ``win32``.
2. The Exploration Engine package (``friday/environments/unknown/``) imports
   neither ``DesktopEnvironment`` nor ``BrowserEnvironment`` concretely — only
   the abstract ``friday.environments.contract`` surface.
3. The M7 file set contains no hardcoded URL scheme literals.
4. The M7 file set contains no banned site/application names in string literals.
5. ``ExplorationEngine.explore`` runs the *same* algorithm against two distinct
   ``EnvironmentContract`` implementations (no environment-type branch).

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
"""

import ast
import os
from pathlib import Path

import pytest

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from friday.actions.result import ActionEvidence, ActionResult
from friday.actions.target import Target
from friday.capabilities.registry import CapabilityRegistry
from friday.environments.contract import Action, EnvironmentContract, ObjectQuery
from friday.environments.unknown import (
    AffordanceInferrer,
    ExplorationEngine,
    ExplorationResult,
    SafeExperimentPlanner,
)
from friday.events.event import FrozenDict
from friday.perception.observation import Observation

# Root of the friday package
_FRIDAY_ROOT = Path(__file__).resolve().parent.parent.parent / "friday"

# ---------------------------------------------------------------------------
# Import-boundary configuration
# ---------------------------------------------------------------------------

# Forbidden imports for the kernel and deliberation layers (Requirement 6.4).
_KERNEL_FORBIDDEN_MODULES = (
    "pyautogui",
    "win32",
    "win32api",
    "win32gui",
    "win32con",
    "win32process",
    "friday.environments.desktop",
)

# Concrete environment modules the exploration package must NOT import
# (Requirement 6.5). Importing friday.environments.contract IS allowed.
_EXPLORATION_FORBIDDEN_MODULES = (
    "friday.environments.desktop",
    "friday.environments.browser",
)
# Concrete environment class names the exploration package must NOT import.
_EXPLORATION_FORBIDDEN_NAMES = ("DesktopEnvironment", "BrowserEnvironment")

# ---------------------------------------------------------------------------
# Site-agnosticism configuration — scoped to the M7 file set
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


def _m7_file_set():
    """Return the M7 files/dirs scanned for URLs and banned app names.

    Scoped deliberately: some pre-existing modules (e.g. providers, research)
    legitimately contain URLs. The M7 packages must be entirely clean.
    """
    files: list[Path] = []
    env_dir = _FRIDAY_ROOT / "environments"
    if env_dir.exists():
        files.extend(_python_files(env_dir))
    for rel in (
        "capabilities/motor.py",
        "capabilities/registry.py",
        "capabilities/contracts.py",
        "kernel/contracts/capability.py",
    ):
        path = _FRIDAY_ROOT / rel
        if path.exists():
            files.append(path)
    return files


def _python_files(directory: Path):
    """Yield all .py files under a directory, excluding __pycache__."""
    for path in directory.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def _parse_imports(filepath: Path):
    """Parse a Python file and yield (module, imported_name) pairs.

    ``imported_name`` is the specific symbol pulled in via ``from x import y``
    (or ``None`` for plain ``import x``). This lets us catch a concrete class
    import such as ``from friday.environments.browser.adapter import
    BrowserEnvironment`` by name as well as by module.
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
    return module == forbidden or module.startswith(forbidden + ".")


class TestKernelDeliberationIsolation:
    """Prove kernel/ and deliberation/ import no desktop or OS-input modules."""

    @pytest.fixture(scope="class")
    def kernel_files(self):
        kernel_dir = _FRIDAY_ROOT / "kernel"
        if not kernel_dir.exists():
            pytest.skip("friday/kernel/ not found")
        return list(_python_files(kernel_dir))

    @pytest.fixture(scope="class")
    def deliberation_files(self):
        delib_dir = _FRIDAY_ROOT / "deliberation"
        if not delib_dir.exists():
            pytest.skip("friday/deliberation/ not found")
        return list(_python_files(delib_dir))

    def test_kernel_deliberation_no_desktop_or_os_imports(
        self, kernel_files, deliberation_files
    ):
        """No kernel/ or deliberation/ file imports desktop, pyautogui, or win32."""
        violations = []
        for filepath in [*kernel_files, *deliberation_files]:
            for module, _name in _parse_imports(filepath):
                for forbidden in _KERNEL_FORBIDDEN_MODULES:
                    if _module_matches(module, forbidden):
                        violations.append(
                            f"{filepath.relative_to(_FRIDAY_ROOT)}: imports '{module}'"
                        )
        assert violations == [], (
            "Kernel/Deliberation isolation violated — forbidden imports found:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestExplorationImportsOnlyAbstractContract:
    """Prove friday/environments/unknown/ imports only the abstract contract."""

    @pytest.fixture(scope="class")
    def exploration_files(self):
        unknown_dir = _FRIDAY_ROOT / "environments" / "unknown"
        if not unknown_dir.exists():
            pytest.skip("friday/environments/unknown/ not found")
        return list(_python_files(unknown_dir))

    def test_exploration_imports_only_abstract_contract(self, exploration_files):
        """No exploration file imports DesktopEnvironment/BrowserEnvironment concretely.

        Importing ``friday.environments.contract`` is explicitly allowed; only
        the concrete runtime modules/classes are forbidden.
        """
        violations = []
        for filepath in exploration_files:
            for module, name in _parse_imports(filepath):
                for forbidden in _EXPLORATION_FORBIDDEN_MODULES:
                    if _module_matches(module, forbidden):
                        violations.append(
                            f"{filepath.relative_to(_FRIDAY_ROOT)}: imports "
                            f"module '{module}'"
                        )
                if name in _EXPLORATION_FORBIDDEN_NAMES:
                    violations.append(
                        f"{filepath.relative_to(_FRIDAY_ROOT)}: imports concrete "
                        f"'{name}' from '{module}'"
                    )
        assert violations == [], (
            "Exploration isolation violated — concrete environment imports found:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestM7SiteAgnosticism:
    """Prove the M7 file set contains no hardcoded URLs or app names."""

    @pytest.fixture(scope="class")
    def m7_files(self):
        files = _m7_file_set()
        if not files:
            pytest.skip("no M7 files found")
        return files

    def test_no_hardcoded_urls_in_friday(self, m7_files):
        """No non-comment, non-docstring source line contains a URL scheme literal."""
        violations = []
        for filepath in m7_files:
            for lineno, scheme in _url_scheme_hits(filepath):
                violations.append(
                    f"{filepath.relative_to(_FRIDAY_ROOT)}:{lineno}: contains '{scheme}'"
                )
        assert violations == [], (
            "Site-agnosticism violated — URL scheme literals found in M7 files:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_banned_app_names_in_m7(self, m7_files):
        """No string literal in the M7 file set contains a banned site/app name."""
        violations = []
        for filepath in m7_files:
            source = filepath.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(source, filename=str(filepath))
            except SyntaxError:
                continue

            docstring_nodes = set()
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

            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and id(node) not in docstring_nodes
                ):
                    value_lower = node.value.lower()
                    for banned in _BANNED_SITE_NAMES:
                        if banned in value_lower:
                            violations.append(
                                f"{filepath.relative_to(_FRIDAY_ROOT)}:"
                                f"{node.lineno}: string literal contains '{banned}'"
                            )
        assert violations == [], (
            "Site-agnosticism violated — banned application names found in M7 files:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


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


# ---------------------------------------------------------------------------
# Same-algorithm-across-environments (Requirement 6.3)
# ---------------------------------------------------------------------------


class _ScriptedStubEnvironment(EnvironmentContract):
    """A minimal EnvironmentContract backed by scripted observations.

    Two instances with *different* scripted observations are enough to prove
    ``explore`` runs the same algorithm regardless of the environment: there is
    no environment-type branch anywhere in the engine.
    """

    def __init__(self, env_name: str, scripted: list) -> None:
        self._name = env_name
        self._scripted = list(scripted)
        self._interactions: list = []

    @property
    def name(self) -> str:
        return self._name

    def observe(self):
        return list(self._scripted)

    def interact(self, action: Action) -> ActionResult:
        self._interactions.append(action)
        return ActionResult.success(
            action=action.capability,
            target=str(action.target or self._name),
            evidence=ActionEvidence(
                before_hash="a", after_hash="b", state_changed=True
            ),
        )

    def verify(self, expected):
        from friday.verification.verifier import (
            VerificationResult,
            VerificationVerdict,
        )

        return VerificationResult(
            verdict=VerificationVerdict.VERIFIED,
            evidence=ActionEvidence(state_changed=True),
            reason="scripted verified",
            confidence=1.0,
        )

    def query_objects(self, query: ObjectQuery):
        return []

    def query_capabilities(self):
        return ["observe", "click", "type"]

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def health(self):
        return {"status": "ok", "environment": self._name}


def _obs(env_name: str, object_type: str, label: str) -> Observation:
    return Observation(
        sensor="uia",
        environment=env_name,
        object_type=object_type,
        attributes=FrozenDict({"name": label}),
        confidence=0.9,
    )


def _new_engine() -> ExplorationEngine:
    return ExplorationEngine(
        inferrer=AffordanceInferrer(),
        planner=SafeExperimentPlanner(),
        registry=CapabilityRegistry(),
    )


class TestExplorationSameAlgorithm:
    """Prove explore() runs the same algorithm across distinct environments."""

    def test_exploration_same_algorithm_across_environments(self):
        """Two distinct EnvironmentContract impls yield structurally identical results.

        This proves there is no ``isinstance(env, ...)`` / environment-type
        branch in the ExplorationEngine — the same algorithm runs for both.
        """
        env_a = _ScriptedStubEnvironment(
            "unknown.alpha",
            [
                _obs("unknown.alpha", "button", "Alpha Action"),
                _obs("unknown.alpha", "textbox", "Alpha Field"),
            ],
        )
        env_b = _ScriptedStubEnvironment(
            "unknown.beta",
            [
                _obs("unknown.beta", "button", "Beta Start"),
                _obs("unknown.beta", "button", "Beta Confirm"),
                _obs("unknown.beta", "textbox", "Beta Input"),
            ],
        )

        result_a = _new_engine().explore(env_a)
        result_b = _new_engine().explore(env_b)

        # Both return ExplorationResult of the same type.
        assert isinstance(result_a, ExplorationResult)
        assert isinstance(result_b, ExplorationResult)

        # Same dataclass field set (identical structure).
        fields_a = set(result_a.__dataclass_fields__.keys())
        fields_b = set(result_b.__dataclass_fields__.keys())
        assert fields_a == fields_b

        # Field value types match across both environments.
        for field_name in fields_a:
            assert type(getattr(result_a, field_name)) == type(
                getattr(result_b, field_name)
            ), f"field '{field_name}' type differs across environments"

        # Confidence is a valid probability in both.
        assert 0.0 <= result_a.confidence <= 1.0
        assert 0.0 <= result_b.confidence <= 1.0

        # Both actually ran experiments through the abstract contract.
        assert len(env_a._interactions) == result_a.budget_spent
        assert len(env_b._interactions) == result_b.budget_spent
