import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

"""M10 gate test — the defining constraint of the domain layer.

Domains under ``friday/domains/`` are pure composition leaves: they own no
durable state and no capability lives inside them. Deleting any single domain
module must leave every capability intact and every other domain still
importable and runnable.

Property 1: Domains own no durable state
    Constructing a domain and invoking a pure method twice with identical
    arguments yields equal results and does not mutate the instance.

Property 2: Deleting a domain leaves capabilities intact
    Removing a domain module from ``sys.modules`` leaves
    ``CapabilityRegistry.capability_count`` and every ``find_for(verb)`` result
    unchanged, and every other domain remains importable.

Validates: Requirements 4.1, 4.2, 4.3
"""

import ast
import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from friday.actions.result import ActionResult
from friday.capabilities.contracts import BaseCapability
from friday.capabilities.registry import CapabilityRegistry
from friday.domains.communication import CommunicationDomain
from friday.domains.documents import DocumentDomain
from friday.domains.models import (
    Conversation,
    DocumentFormat,
    SemanticDocument,
)
from friday.domains.research import ResearchDomain
from friday.domains.software import SoftwareDomain
from friday.kernel.contracts.capability import (
    CapabilityContract,
    Condition,
    WorldStateDelta,
)

# The four domain modules that make up the M10 domain layer.
_DOMAIN_MODULES = (
    "friday.domains.research",
    "friday.domains.communication",
    "friday.domains.documents",
    "friday.domains.software",
)

# Directory holding the domain layer source.
_DOMAINS_DIR = Path(__file__).resolve().parents[2] / "friday" / "domains"

# Base names that indicate a class is a capability contract. No class defined
# inside the domain layer may subclass any of these.
_CAPABILITY_BASE_NAMES = frozenset(
    {
        "CapabilityContract",
        "BaseCapability",
        "ToolDescriptorCapability",
        "PromotedCapability",
    }
)


class _StubCapability(BaseCapability):
    """A minimal executable stub capability exposing an id and abstract verbs."""

    def __init__(self, capability_id: str, verbs: List[str]) -> None:
        super().__init__()
        self._id = capability_id
        self._verbs = list(verbs)

    @property
    def id(self) -> str:
        return self._id

    @property
    def version(self) -> str:
        return "stub"

    @property
    def verbs(self) -> List[str]:
        return list(self._verbs)

    def preconditions(self) -> List[Condition]:
        return []

    def expected_outcome(self) -> WorldStateDelta:
        return WorldStateDelta()

    async def execute(self, params: Dict[str, Any], world: Any) -> ActionResult:
        return ActionResult.success(action=self._id, message="stub executed")

    def verify(self, result: ActionResult, world: Any) -> bool:
        return result.is_success

    def recover(self, failure: ActionResult) -> Optional[CapabilityContract]:
        return None


def _seed_registry() -> CapabilityRegistry:
    """Build a registry seeded with a couple of stub capabilities."""
    reg = CapabilityRegistry()
    reg.register(_StubCapability("stub.messenger.deliver", ["deliver"]))
    reg.register(_StubCapability("stub.filesystem.create_file", ["create_file"]))
    return reg


def _snapshot(reg: CapabilityRegistry) -> Dict[str, Any]:
    """Capture the registry state that domains must never affect."""
    return {
        "count": reg.capability_count,
        "deliver": tuple(c.id for c in reg.find_for("deliver")),
        "create_file": tuple(c.id for c in reg.find_for("create_file")),
    }


def test_deleting_a_domain_leaves_capabilities_intact() -> None:
    """Property 2: popping any domain from sys.modules changes nothing in the
    registry, and every other domain still imports.

    Validates: Requirements 4.2, 4.3
    """
    reg = _seed_registry()
    baseline = _snapshot(reg)

    # Sanity: the registry actually resolves the seeded verbs.
    assert baseline["count"] == 2
    assert baseline["deliver"] == ("stub.messenger.deliver",)
    assert baseline["create_file"] == ("stub.filesystem.create_file",)

    for name in _DOMAIN_MODULES:
        # Remove the domain module (and re-import fresh afterwards).
        sys.modules.pop(name, None)

        # The registry is a pure runtime index: removing a domain module cannot
        # change the capability count nor any find_for(...) result.
        after = _snapshot(reg)
        assert after == baseline, (
            f"registry changed after popping {name}: {after} != {baseline}"
        )

        # Every OTHER domain must remain importable while this one is gone.
        for other in _DOMAIN_MODULES:
            if other == name:
                continue
            module = importlib.import_module(other)
            assert module is not None

        # Re-import the popped module fresh so the layer is whole again.
        reimported = importlib.import_module(name)
        assert reimported is not None

    # Final: registry is still exactly as it began.
    assert _snapshot(reg) == baseline


def test_no_capability_defined_inside_domains() -> None:
    """No class defined under friday/domains/ subclasses a capability contract —
    proving no capability lives inside the domain layer.

    Validates: Requirements 4.3
    """
    domain_files = sorted(_DOMAINS_DIR.rglob("*.py"))
    assert domain_files, "expected domain .py files under friday/domains/"

    offenders: List[str] = []
    for path in domain_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                base_name = _base_name(base)
                if base_name in _CAPABILITY_BASE_NAMES:
                    offenders.append(f"{path.name}:{node.name} -> {base_name}")

    assert not offenders, (
        "capability contract subclasses found inside the domain layer: "
        + ", ".join(offenders)
    )


def _base_name(base: ast.expr) -> Optional[str]:
    """Extract the terminal name of a class base expression (Name or Attribute)."""
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def test_domains_own_no_durable_state() -> None:
    """Property 1: each domain constructed with a fresh registry is pure — a
    pure method called twice with identical args returns equal results and does
    not mutate the instance __dict__.

    Validates: Requirements 4.1
    """
    # ResearchDomain.rank_sources — pure over its input tuple.
    research = ResearchDomain(CapabilityRegistry())
    _assert_pure(
        research,
        lambda d: d.rank_sources(("a.gov/x",)),
    )

    # DocumentDomain.render — deterministic pure render.
    documents = DocumentDomain(CapabilityRegistry())
    doc = SemanticDocument("T")
    _assert_pure(
        documents,
        lambda d: d.render(doc, DocumentFormat.MARKDOWN),
    )

    # CommunicationDomain.append_turn — returns a new immutable Conversation.
    communication = CommunicationDomain(CapabilityRegistry())
    _assert_pure(
        communication,
        lambda d: d.append_turn(Conversation(), "u", "h"),
    )

    # SoftwareDomain.status — deferred stub, pure.
    software = SoftwareDomain(CapabilityRegistry())
    _assert_pure(
        software,
        lambda d: d.status(),
    )


def _assert_pure(domain: Any, call) -> None:
    """Call a pure domain method twice and assert equal results with no instance
    mutation. The ``registry`` attribute must remain the same object and no new
    attributes may appear across the calls."""
    registry_before = domain.registry
    keys_before = set(domain.__dict__.keys())

    first = call(domain)
    dict_after_first = dict(domain.__dict__)
    second = call(domain)
    dict_after_second = dict(domain.__dict__)

    # Same args -> equal results (determinism / no hidden state).
    assert first == second

    # The registry stays the same object; no new attributes appear; and no
    # existing attribute value changed by identity across the calls.
    assert domain.registry is registry_before
    assert set(domain.__dict__.keys()) == keys_before
    assert dict_after_first.keys() == dict_after_second.keys()
    for key in dict_after_first:
        assert dict_after_first[key] is dict_after_second[key]


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
