import os
import re
import pytest

from services.maps_service import get_distance_and_time


@pytest.mark.skipif(not os.getenv("DISTANCEMATRIX_API_KEY"), reason="Distance API key missing")
def test_distance_known_pair():
    msg = get_distance_and_time("Vartak Nagar, Thane", "Cadbury Junction, Thane")
    assert isinstance(msg, str)
    assert any(kw in msg for kw in ["Distance between", "No routes", "rejected", "missing details"])  # tolerant


@pytest.mark.skipif(not os.getenv("DISTANCEMATRIX_API_KEY"), reason="Distance API key missing")
@pytest.mark.parametrize(
    "orig,dest",
    [
        ("Thane Station", "Mulund Station"),
        ("Lower Parel, Mumbai", "Bandra Kurla Complex, Mumbai"),
    ],
)
def test_distance_multiple_pairs(orig, dest):
    msg = get_distance_and_time(orig, dest)
    assert isinstance(msg, str)
    assert re.search(r"Distance between .* and .* is .*", msg) or "No routes" in msg or "missing details" in msg
