from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from flask import Flask, jsonify, request

app = Flask(__name__)


_PLACES: Dict[str, Tuple[float, float, str]] = {
    "thane": (19.2183, 72.9781, "Thane, Maharashtra, India"),
    "vartak nagar": (19.2090, 72.9720, "Vartak Nagar, Thane, Maharashtra, India"),
    "cadbury junction": (19.1900, 72.9490, "Cadbury Junction, Thane, Maharashtra, India"),
    "thane station": (19.1860, 72.9750, "Thane Railway Station, Maharashtra, India"),
    "mulund station": (19.1726, 72.9560, "Mulund Railway Station, Maharashtra, India"),
}


def _normalize(s: str) -> str:
    return " ".join((s or "").strip().lower().replace("-", " ").split())


def _geocode_candidates(address: str, max_candidates: int = 3) -> List[Dict[str, Any]]:
    addr_norm = _normalize(address)

    # Explicit ambiguity trigger for tests/manual validation
    if "ambiguous" in addr_norm or addr_norm in {"a", "b"}:
        return [
            {
                "formatted_address": "Foo A",
                "geometry": {"location": {"lat": 10.0, "lng": 20.0}},
            },
            {
                "formatted_address": "Foo B",
                "geometry": {"location": {"lat": 10.1, "lng": 20.1}},
            },
        ][:max_candidates]

    # Known place lookup by substring match
    matches: List[Tuple[str, Tuple[float, float, str]]] = []
    for key, val in _PLACES.items():
        if key in addr_norm:
            matches.append((key, val))

    if matches:
        # Deterministic order (longer keys first)
        matches.sort(key=lambda t: len(t[0]), reverse=True)
        out = []
        for _key, (lat, lon, label) in matches[:max_candidates]:
            out.append(
                {
                    "formatted_address": label,
                    "geometry": {"location": {"lat": lat, "lng": lon}},
                }
            )
        return out

    # Fallback: return a single synthetic location based on hash (stable-ish)
    seed = sum(ord(c) for c in addr_norm) or 1
    lat = 19.0 + (seed % 100) / 1000.0
    lon = 72.9 + (seed % 100) / 1000.0
    return [
        {
            "formatted_address": address or "Unknown",
            "geometry": {"location": {"lat": lat, "lng": lon}},
        }
    ]


@app.get("/maps/api/geocode/json")
def geocode() -> Any:
    address = request.args.get("address", "")
    if not address:
        return jsonify({"status": "ZERO_RESULTS", "results": []})
    results = _geocode_candidates(address)
    return jsonify({"status": "OK", "results": results})


def _haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    # crude Earth distance for mock determinism
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


@app.get("/maps/api/distancematrix/json")
def distancematrix() -> Any:
    origins = request.args.get("origins", "")
    destinations = request.args.get("destinations", "")

    def _parse_latlon(s: str) -> Tuple[float, float] | None:
        try:
            parts = [p.strip() for p in s.split(",")]
            if len(parts) != 2:
                return None
            return float(parts[0]), float(parts[1])
        except Exception:
            return None

    o = _parse_latlon(origins)
    d = _parse_latlon(destinations)
    if not o or not d:
        return jsonify({"rows": [{"elements": [{"status": "NOT_FOUND"}]}]})

    km = _haversine_km(o, d)
    # deterministic duration: 6 min for ~1.5km scale (matches your acceptance example)
    minutes = max(1, int(round(km * 4)))
    meters = int(round(km * 1000))
    seconds = minutes * 60

    return jsonify(
        {
            "rows": [
                {
                    "elements": [
                        {
                            "status": "OK",
                            "distance": {"value": meters, "text": f"{km:.1f} km"},
                            "duration": {"value": seconds, "text": f"{minutes} mins"},
                        }
                    ]
                }
            ]
        }
    )


@app.get("/v1/current.json")
def weather_current() -> Any:
    q = request.args.get("q", "")
    location = q or "Unknown"
    return jsonify(
        {
            "location": {"name": location.title(), "country": "Mock"},
            "current": {
                "temp_c": 25.0,
                "feelslike_c": 25.0,
                "humidity": 60,
                "wind_kph": 10.0,
                "condition": {"text": "Partly cloudy"},
            },
        }
    )


def main() -> None:
    app.run(host="127.0.0.1", port=5001, debug=False)


if __name__ == "__main__":
    main()
