"""M6 Property-Based Tests (Hypothesis) — universal correctness properties.

Encodes the numbered correctness properties from the M6 design document using
the Hypothesis property-based testing library. Each test validates a
universally-quantified statement that must hold across ALL generated inputs.

Properties covered:
  - Property 1  (10.1): Contract totality
  - Property 2  (10.2): Observation uniformity
  - Property 4  (10.3): Evidence Law is never weakened
  - Property 5  (10.4): No false completion for GATHER/DELIVER
  - Property 6  (10.5): Goal completeness
  - Property 7  (10.6): Evidence integrity
  - Property 9  (10.7): Checkpoint purity
  - Property 10 (10.8): Query soundness

All tests run under FRIDAY_DRY_RUN=1 — no real browser or I/O.
"""

import json
import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from hypothesis import given, settings, strategies as st

from friday.actions.result import ActionResult
from friday.environments.contract import Action, ObjectQuery
from friday.environments.stub import StubEnvironment
from friday.events.event import FrozenDict
from friday.goals.goal import Goal
from friday.perception.observation import Observation
from friday.verification.engine import UnifiedVerificationEngine
from friday.verification.evidence_law import (
    EvidenceArtifact,
    EvidenceKind,
    EvidenceVerifier,
    ExecutionEvidence,
)
from friday.verification.evidence_repo import EvidenceRepository
from friday.verification.verifier import VerificationVerdict
from friday.world.objects import WorldObject


# ======================================================================
# Shared strategies
# ======================================================================

# Non-empty lowercase identifier-ish text (guarantees != "").
_non_empty_text = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=12
)

# A small pool of object types used to build scripted observations.
_OBJECT_TYPES = ["button", "link", "textbox", "window", "text", "url", "checkbox"]

# The default capability vocabulary of a StubEnvironment.
_STUB_CAPABILITIES = [
    "observe", "read", "navigate", "click", "type", "scroll",
    "press", "upload", "download",
]

# Realistic requirement phrases spanning every RequirementKind.
_REQUIREMENT_PHRASES = [
    "research the topic",          # GATHER
    "gather information",          # GATHER
    "find sources",                # GATHER
    "write report",                # PRODUCE
    "generate a summary",          # PRODUCE
    "save file",                   # FILE
    "navigate to page",            # NAVIGATE
    "send email",                  # DELIVER
    "deliver the message",         # DELIVER
    "do something useful",         # GENERIC
]

# Phrases that classify as GATHER or DELIVER (for Property 5).
_GATHER_OR_DELIVER_PHRASES = [
    "research the topic",          # GATHER
    "gather information",          # GATHER
    "find sources",                # GATHER
    "send the email",              # DELIVER
    "deliver the message",         # DELIVER
]


@st.composite
def _observations(draw, object_type=None):
    """Build a single Observation with non-empty environment/object_type."""
    otype = object_type if object_type is not None else draw(st.sampled_from(_OBJECT_TYPES))
    return Observation(
        sensor=draw(_non_empty_text),
        environment=draw(_non_empty_text),
        object_type=otype,
        attributes=FrozenDict({"text": draw(st.text(max_size=20))}),
    )


@st.composite
def _execution_evidence(draw):
    """Build a random ExecutionEvidence bundle across all artifact kinds."""
    ev = ExecutionEvidence()
    for _ in range(draw(st.integers(min_value=0, max_value=3))):
        ev.add_gathered_info(draw(st.text(min_size=1, max_size=60)), source="src")
    for _ in range(draw(st.integers(min_value=0, max_value=3))):
        ev.add_generated_content(draw(st.text(min_size=1, max_size=60)))
    for _ in range(draw(st.integers(min_value=0, max_value=2))):
        ev.add_file(draw(_non_empty_text) + ".txt", draw(st.integers(min_value=1, max_value=999)))
    for _ in range(draw(st.integers(min_value=0, max_value=2))):
        ev.add_navigation(draw(_non_empty_text))
    for _ in range(draw(st.integers(min_value=0, max_value=2))):
        ev.add_delivery_confirmation(draw(_non_empty_text))
    for _ in range(draw(st.integers(min_value=0, max_value=2))):
        ev.add_source_url("//" + draw(_non_empty_text))
    return ev


# ======================================================================
# Property 1 (Task 10.1) — Contract totality
# Validates: Requirements 1.2, 6.5
# ======================================================================


@settings(max_examples=50)
@given(
    capability=st.sampled_from(_STUB_CAPABILITIES),
    param_key=st.text(max_size=10),
    param_val=st.text(max_size=20),
)
def test_property_1_contract_totality(capability, param_key, param_val):
    """For every Action with a capability in query_capabilities(),
    StubEnvironment.interact() returns an ActionResult and never raises.

    Validates: Requirements 1.2, 6.5
    """
    env = StubEnvironment()
    assert capability in env.query_capabilities()

    action = Action(capability=capability, params={param_key: param_val})
    result = env.interact(action)  # must never raise

    assert isinstance(result, ActionResult)


# ======================================================================
# Property 2 (Task 10.2) — Observation uniformity
# Validates: Requirements 1.3
# ======================================================================


@settings(max_examples=50)
@given(scripted=st.lists(_observations(), max_size=8))
def test_property_2_observation_uniformity(scripted):
    """For every environment, every element of observe() is an Observation
    with a non-empty environment and object_type.

    Validates: Requirements 1.3
    """
    env = StubEnvironment(scripted=scripted)
    for obs in env.observe():
        assert isinstance(obs, Observation)
        assert obs.environment != ""
        assert obs.object_type != ""


# ======================================================================
# Property 4 (Task 10.3) — Evidence Law is never weakened
# Validates: Requirements 3.2, 4.3
# ======================================================================


@settings(max_examples=50)
@given(
    requirement=st.one_of(st.text(max_size=40), st.sampled_from(_REQUIREMENT_PHRASES)),
    evidence=_execution_evidence(),
)
def test_property_4_evidence_law_preservation(requirement, evidence):
    """For every requirement description and evidence bundle, the unified
    engine's VERIFIED verdict equals EvidenceVerifier.verify_one().satisfied.

    Validates: Requirements 3.2, 4.3
    """
    engine = UnifiedVerificationEngine()
    verifier = EvidenceVerifier()

    engine_verified = engine.verify_requirement(requirement, evidence).verdict == (
        VerificationVerdict.VERIFIED
    )
    verifier_satisfied = verifier.verify_one(requirement, evidence).satisfied

    assert engine_verified == verifier_satisfied


# ======================================================================
# Property 5 (Task 10.4) — No false completion for GATHER/DELIVER
# Validates: Requirements 4.1, 4.2
# ======================================================================


@settings(max_examples=50)
@given(
    requirement=st.sampled_from(_GATHER_OR_DELIVER_PHRASES),
    contents=st.lists(st.text(min_size=1, max_size=60), min_size=1, max_size=5),
)
def test_property_5_no_false_completion(requirement, contents):
    """For every evidence bundle containing ONLY GENERATED_CONTENT artifacts,
    any GATHER or DELIVER requirement is UNMET.

    Validates: Requirements 4.1, 4.2
    """
    evidence = ExecutionEvidence()
    for text in contents:
        evidence.add_generated_content(text)

    engine = UnifiedVerificationEngine()
    result = engine.verify_requirement(requirement, evidence)

    assert result.verdict == VerificationVerdict.UNVERIFIED


# ======================================================================
# Property 6 (Task 10.5) — Goal completeness
# Validates: Requirements 3.3, 3.4
# ======================================================================


@settings(max_examples=50)
@given(
    requirements=st.lists(st.sampled_from(_REQUIREMENT_PHRASES), max_size=5),
    evidence=_execution_evidence(),
)
def test_property_6_goal_completeness(requirements, evidence):
    """verify_goal is satisfied iff the requirements list is non-empty AND
    every requirement verdict is satisfied. A goal with zero requirements is
    never satisfied.

    Validates: Requirements 3.3, 3.4
    """
    engine = UnifiedVerificationEngine()
    verifier = EvidenceVerifier()

    goal = Goal(text="a goal", constraints={"requirements": requirements})
    result = engine.verify_goal(goal, evidence)

    expected = bool(requirements) and all(
        verifier.verify_one(req, evidence).satisfied for req in requirements
    )
    assert result.satisfied == expected

    # Zero-requirements case is always False.
    if not requirements:
        assert result.satisfied is False


# ======================================================================
# Property 7 (Task 10.6) — Evidence integrity
# Validates: Requirements 5.1, 5.2
# ======================================================================


@settings(max_examples=50)
@given(
    kind=st.sampled_from(list(EvidenceKind)),
    detail=st.text(max_size=40),
    value=st.integers(min_value=0, max_value=9999),
    source=st.text(max_size=20),
    goal_id=_non_empty_text,
)
def test_property_7_evidence_integrity(kind, detail, value, source, goal_id):
    """For every repository record, the stored signature validates; mutating
    any field invalidates it.

    Validates: Requirements 5.1, 5.2
    """
    repo = EvidenceRepository()
    artifact = EvidenceArtifact(kind=kind, detail=detail, value=value, source=source)
    repo.add_artifact(goal_id, artifact, requirement="some requirement")

    # Signature validates on read.
    assert repo.verify_integrity() is True

    # Mutating a field (to a guaranteed-different value) invalidates the signature.
    record = repo._records[0]
    object.__setattr__(record, "goal_id", record.goal_id + "_mutated")
    assert repo.verify_integrity() is False


# ======================================================================
# Property 9 (Task 10.7) — Checkpoint purity
# Validates: Requirements 6.3
# ======================================================================


@settings(max_examples=50)
@given(
    paused=st.booleans(),
    capabilities=st.lists(st.sampled_from(_STUB_CAPABILITIES), max_size=9),
)
def test_property_9_checkpoint_purity(paused, capabilities):
    """For every EnvironmentRuntime, checkpoint() is JSON-serializable.

    Validates: Requirements 6.3
    """
    env = StubEnvironment(capabilities=capabilities)
    if paused:
        env.pause()

    # Must not raise — checkpoint contains only JSON-serializable primitives.
    blob = json.dumps(env.checkpoint())
    restored = json.loads(blob)
    assert restored["paused"] == paused


# ======================================================================
# Property 10 (Task 10.8) — Query soundness
# Validates: Requirements 1.4
# ======================================================================


@settings(max_examples=50)
@given(
    scripted=st.lists(_observations(), max_size=10),
    object_type=st.sampled_from(_OBJECT_TYPES),
)
def test_property_10_query_soundness(scripted, object_type):
    """For every ObjectQuery with object_type=t, every WorldObject returned by
    query_objects has object_type == t.

    Validates: Requirements 1.4
    """
    env = StubEnvironment(scripted=scripted)
    results = env.query_objects(ObjectQuery(object_type=object_type))

    for obj in results:
        assert isinstance(obj, WorldObject)
        assert obj.object_type == object_type
