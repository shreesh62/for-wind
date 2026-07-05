"""M1 tests — EchoRuntime behavior and A5 import boundary."""

import ast
import pathlib

from friday.events.event import make_event
from friday.kernel.echo_runtime import EchoRuntime
from friday.kernel.kernel import CognitiveKernel

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_a5_import_boundary():
    """EchoRuntime must only import from friday.events / friday.kernel.contracts."""
    src = (ROOT / "friday" / "kernel" / "echo_runtime.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    allowed_prefixes = ("friday.events", "friday.kernel.contracts", "abc", "typing", "__future__")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert any(
                node.module.startswith(p) for p in allowed_prefixes
            ), f"Illegal import in echo_runtime.py: {node.module}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert any(
                    alias.name.startswith(p) for p in allowed_prefixes
                ), f"Illegal import in echo_runtime.py: {alias.name}"


def test_echo_responds_to_request(tmp_path):
    kernel = CognitiveKernel(store_path=str(tmp_path / "s.jsonl"))
    echo = EchoRuntime()
    kernel.register_runtime(echo)
    responses = []
    kernel._bus.subscribe("echo.response", responses.append)
    request = make_event("echo.request", "tests", 1, payload={"msg": "hi"})
    kernel.publish_event(request)
    assert len(responses) == 1
    assert responses[0].parent_id == request.id
    assert responses[0].payload["echo"] == {"msg": "hi"}
    assert responses[0].correlation_id == request.correlation_id


def test_checkpoint_restore(tmp_path):
    echo = EchoRuntime()
    echo.tick(1)
    echo.tick(2)
    state = echo.checkpoint()
    fresh = EchoRuntime()
    fresh.restore(state)
    assert fresh.health()["ticks"] == 2


def test_ticks_counted(tmp_path):
    echo = EchoRuntime()
    for i in range(5):
        echo.tick(i)
    assert echo.observe() == [{"runtime": "echo", "ticks": 5}]


def test_shutdown_health():
    echo = EchoRuntime()
    assert echo.health()["status"] == "ok"
    echo.shutdown()
    assert echo.health()["status"] == "stopped"
