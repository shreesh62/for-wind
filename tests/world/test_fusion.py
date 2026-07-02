"""M2 tests — SensorFusion merging observations into beliefs."""

from friday.events.event import FrozenDict
from friday.perception.fusion import SensorFusion
from friday.perception.observation import Observation


def _obs(sensor="ocr", name="Submit", object_type="button", confidence=0.7, **attrs):
    return Observation(
        sensor=sensor,
        environment="browser",
        object_type=object_type,
        attributes=FrozenDict({"name": name, **attrs}),
        confidence=confidence,
    )


def test_two_sensors_same_object_raises_confidence():
    """M2 criterion: fusion merges two sensor observations into one belief
    with higher confidence."""
    fusion = SensorFusion()
    fusion.ingest([_obs(sensor="ocr", confidence=0.7)])
    fusion.ingest([_obs(sensor="dom", confidence=0.7)])
    assert len(fusion.beliefs) == 1
    belief = fusion.beliefs[0]
    assert belief.confidence > 0.7
    assert "ocr" in belief.source and "dom" in belief.source
    assert len(belief.supporting_evidence) == 2


def test_contradicting_observation_lowers_confidence():
    fusion = SensorFusion()
    fusion.ingest([_obs(confidence=0.9)])
    before = fusion.beliefs[0].confidence
    fusion.ingest([_obs(sensor="dom", confidence=0.8, absent=True)])
    after = fusion.beliefs[0].confidence
    assert after < before


def test_different_objects_stay_separate():
    fusion = SensorFusion()
    fusion.ingest([_obs(name="Submit"), _obs(name="Cancel")])
    assert len(fusion.beliefs) == 2
