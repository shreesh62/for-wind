import types
import json
from services.distancematrix_service import (
    geocode_address_accurate,
    compute_distance_accurate,
    distance_pipeline,
    DistanceResult,
)

class DummyResp:
    def __init__(self, payload):
        self._payload = payload
    def json(self):
        return self._payload


def _make_geocode_payload(addr, lat, lng):
    return {
        "status": "OK",
        "results": [
            {
                "formatted_address": addr,
                "geometry": {"location": {"lat": lat, "lng": lng}},
            }
        ],
    }


def _make_distance_payload(meters: int, seconds: int):
    return {
        "rows": [
            {
                "elements": [
                    {
                        "status": "OK",
                        "distance": {"value": meters, "text": f"{meters/1000:.1f} km"},
                        "duration": {"value": seconds, "text": f"{int(seconds/60)} mins"},
                    }
                ]
            }
        ]
    }


def test_distance_pipeline_success(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=10):
        calls.append((url, params))
        if "geocode" in url:
            if "Vartak" in params.get("address", ""):
                return DummyResp(_make_geocode_payload("Vartak Nagar, Thane", 19.209, 72.972))
            return DummyResp(_make_geocode_payload("Cadbury Junction, Thane", 19.190, 72.949))
        else:
            # distance
            return DummyResp(_make_distance_payload(1500, 360))

    monkeypatch.setattr("services.distancematrix_service.requests.get", fake_get)

    msg, res, oc, dc = distance_pipeline("Vartak Nagar, Thane", "Cadbury Junction, Thane")
    assert isinstance(res, DistanceResult)
    assert "Distance: 1.5 km" in msg
    assert "ETA: 6 minutes" in msg
    assert res.distance_km == 1.5
    assert int(res.duration_min) == 6


def test_distance_pipeline_ambiguous(monkeypatch):
    def fake_get(url, params=None, timeout=10):
        if "geocode" in url:
            # return two candidates -> ambiguity
            return DummyResp({
                "status": "OK",
                "results": [
                    {"formatted_address": "Foo A", "geometry": {"location": {"lat": 10.0, "lng": 20.0}}},
                    {"formatted_address": "Foo B", "geometry": {"location": {"lat": 10.1, "lng": 20.1}}},
                ]
            })
        else:
            return DummyResp(_make_distance_payload(1500, 360))

    monkeypatch.setattr("services.distancematrix_service.requests.get", fake_get)
    msg, res, oc, dc = distance_pipeline("A", "B")
    assert res is None
    assert isinstance(oc, list) and isinstance(dc, list)
    assert "Please confirm" in msg
