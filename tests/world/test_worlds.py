"""M2 tests — ObservedWorld / PredictedWorld / DesiredWorld."""

from dataclasses import dataclass

from friday.world.belief import Belief
from friday.world.worlds import DesiredWorld, ObservedWorld, PredictedWorld


def test_desired_world_from_strings():
    desired = DesiredWorld.from_requirements(["file exists", "message delivered"])
    assert desired.conditions == ["file exists", "message delivered"]


def test_desired_world_from_requirement_objects():
    """M2 criterion: Desired World representable from a RequirementSet."""

    @dataclass
    class FakeRequirement:
        description: str

    @dataclass
    class FakeRequirementSet:
        requirements: list

    req_set = FakeRequirementSet(
        requirements=[FakeRequirement("gather info"), FakeRequirement("produce report")]
    )
    desired = DesiredWorld.from_requirements(req_set)
    assert desired.conditions == ["gather info", "produce report"]


def test_desired_world_from_real_requirement_set():
    from friday.planner.requirements import Requirement, RequirementSet

    req_set = RequirementSet(
        goal="g",
        requirements=[Requirement(description="create the file")],
    )
    desired = DesiredWorld.from_requirements(req_set)
    assert desired.conditions == ["create the file"]


def test_unmet_conditions():
    observed = ObservedWorld(
        beliefs={
            "b1": Belief(description="file exists", confidence=0.9, source="fs"),
            "b2": Belief(description="page loaded", confidence=0.2, source="dom"),
        }
    )
    desired = DesiredWorld(conditions=["file exists", "page loaded", "sent"])
    assert desired.unmet(observed, min_confidence=0.5) == ["page loaded", "sent"]


def test_predicted_world_holds_expectations():
    predicted = PredictedWorld(expected=["button clicked"], confidence=0.8)
    assert predicted.expected == ["button clicked"]


def test_observed_world_filters_expired_and_low_confidence():
    import time

    observed = ObservedWorld(
        beliefs={
            "b1": Belief(description="stale", confidence=1.0, source="s", expires_at=time.time() - 1),
            "b2": Belief(description="weak", confidence=0.1, source="s"),
            "b3": Belief(description="good", confidence=0.9, source="s"),
        }
    )
    active = observed.active_beliefs(min_confidence=0.5)
    assert [b.description for b in active] == ["good"]
