"""M2 tests — WorldModel fed by kernel events; sensor boundary."""

import ast
import pathlib

from friday.events.event import FrozenDict
from friday.kernel.kernel import CognitiveKernel
from friday.perception.observation import Observation
from friday.world.world_model import WorldModel
from friday.world.worlds import DesiredWorld

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _obs(name="Submit", sensor="dom", confidence=0.8):
    return Observation(
        sensor=sensor,
        environment="browser",
        object_type="button",
        attributes=FrozenDict({"name": name}),
        confidence=confidence,
    )


def test_world_model_updated_via_kernel_events(tmp_path):
    """M2 criterion: WorldModel is owned by the kernel and updated via events."""
    kernel = CognitiveKernel(store_path=str(tmp_path / "s.jsonl"))
    model = WorldModel()
    model.attach(kernel)
    kernel.submit_observation(
        {
            "sensor": "dom",
            "environment": "browser",
            "object_type": "button",
            "attributes": {"name": "Submit"},
            "confidence": 0.9,
        }
    )
    world = model.observed_world(apply_decay=False)
    assert len(world.beliefs) == 1
    belief = next(iter(world.beliefs.values()))
    assert "Submit" in belief.description
    assert model.object_count == 1


def test_ingest_tracks_objects_and_relationships():
    model = WorldModel()
    model.ingest([_obs(name="Window"), _obs(name="Button")])
    rel = model.relate(
        "browser:button:Window", "browser:button:Button", relation="contains"
    )
    assert rel is not None
    assert rel.relation == "contains"
    assert model.relate("missing", "browser:button:Button", "contains") is None


def test_unmet_conditions_against_desired_world():
    model = WorldModel()
    model.ingest([_obs(name="Submit", confidence=0.9)])
    belief = model.observed_world(apply_decay=False).active_beliefs()[0]
    desired = DesiredWorld(conditions=[belief.description, "something else"])
    assert model.unmet_conditions(desired) == ["something else"]


def test_decay_applied_in_observed_world():
    model = WorldModel(decay_rate=0.5)
    model.ingest([_obs(confidence=1.0)])
    import time

    time.sleep(0.1)
    world = model.observed_world(apply_decay=True)
    belief = next(iter(world.beliefs.values()))
    assert belief.confidence < 1.0


def test_import_boundary_world_never_touches_sensors():
    """M2 criterion: no raw sensor access outside friday/perception.

    friday/world may import friday.events and friday.perception's uniform
    types (Observation, fusion) but never concrete sensors or actions.
    """
    banned = (
        "friday.perception.screen",
        "friday.perception.ocr",
        "friday.perception.vision",
        "friday.actions",
        "mss",
        "pytesseract",
        "pyautogui",
    )
    for path in (ROOT / "friday" / "world").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            for module in modules:
                assert not any(
                    module == b or module.startswith(b + ".") for b in banned
                ), f"Illegal sensor import in {path.name}: {module}"
