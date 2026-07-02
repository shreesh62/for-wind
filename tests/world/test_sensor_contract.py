"""M2 tests — SensorContract and the ScreenSensor adapter."""

from friday.perception.contracts import ScreenSensor, SensorContract
from friday.perception.observation import Observation


class FakeShot:
    width = 1920
    height = 1080


class FakeCapture:
    def grab(self):
        return FakeShot()


class EmptyCapture:
    def grab(self):
        return None


def test_screen_sensor_is_a_sensor_contract():
    assert isinstance(ScreenSensor(capture=FakeCapture()), SensorContract)


def test_screen_sensor_emits_uniform_observations():
    """M2 criterion: ScreenCapture emits Observations via SensorContract."""
    sensor = ScreenSensor(capture=FakeCapture())
    observations = sensor.observe()
    assert len(observations) == 1
    obs = observations[0]
    assert isinstance(obs, Observation)
    assert obs.sensor == "screen"
    assert obs.environment == "desktop"
    assert obs.attributes["width"] == 1920
    assert obs.bbox == (0, 0, 1920, 1080)


def test_screen_sensor_handles_failed_grab():
    assert ScreenSensor(capture=EmptyCapture()).observe() == []


def test_query_filters_by_object_type():
    sensor = ScreenSensor(capture=FakeCapture())
    assert sensor.query(object_type="screenshot")
    assert sensor.query(object_type="button") == []
