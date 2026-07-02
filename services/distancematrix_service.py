import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests

from config import get_settings

# Allow overriding via env for tests (mock server)
DISTANCEMATRIX_BASE = os.getenv("DISTANCEMATRIX_BASE", "https://api.distancematrix.ai/maps/api")
GEOCODE_BASE = os.getenv("GEOCODE_BASE", "https://api-v2.distancematrix.ai/maps/api")


@dataclass
class GeoCandidate:
    formatted_address: str
    lat: float
    lon: float
    confidence: float


@dataclass
class DistanceResult:
    distance_km: float
    duration_min: float
    mode: str
    source: str = "distancematrix.ai (accurate)"
    confidence: float = 0.85


def _json_get(d: Dict, path: List[str], default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def geocode_address_accurate(address: str, *, max_candidates: int = 3) -> List[GeoCandidate]:
    settings = get_settings()
    key = settings.geocoding_api_key or settings.distance_api_key  # May be empty in tests

    url = f"{GEOCODE_BASE}/geocode/json"
    try:
        params = {"address": address}
        if key:
            params["key"] = key
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
    except Exception:
        return []

    if data.get("status") != "OK":
        return []

    results = []
    for i, item in enumerate(data.get("results", [])[:max_candidates]):
        loc = _json_get(item, ["geometry", "location"], {}) or {}
        lat, lng = loc.get("lat"), loc.get("lng")
        if lat is None or lng is None:
            continue
        # Heuristic confidence: first result highest; degrade slightly
        conf = 0.92 - 0.05 * i
        results.append(
            GeoCandidate(
                formatted_address=item.get("formatted_address", address),
                lat=float(lat),
                lon=float(lng),
                confidence=max(0.0, min(1.0, conf)),
            )
        )
    return results


def compute_distance_accurate(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    *,
    mode: str = "driving",
) -> Optional[DistanceResult]:
    settings = get_settings()
    key = settings.distance_api_key  # May be empty in tests

    if mode not in {"driving", "walking", "bicycling", "transit"}:
        mode = "driving"

    url = f"{DISTANCEMATRIX_BASE}/distancematrix/json"
    params = {
        "origins": f"{origin[0]:.6f},{origin[1]:.6f}",
        "destinations": f"{destination[0]:.6f},{destination[1]:.6f}",
        "mode": mode,
        **({"key": key} if key else {}),
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        data = r.json()
    except Exception:
        return None

    rows = data.get("rows", [{}])
    elements = rows[0].get("elements", [{}]) if rows else [{}]
    element = elements[0]
    if element.get("status") != "OK":
        return None

    dist_m = _json_get(element, ["distance", "value"])  # meters
    dur_s = _json_get(element, ["duration", "value"])  # seconds
    if dist_m is None or dur_s is None:
        return None

    km = round(float(dist_m) / 1000.0, 1)
    minutes = round(float(dur_s) / 60.0)
    # Confidence heuristic: if values present we return a high confidence
    return DistanceResult(distance_km=km, duration_min=minutes, mode=mode, confidence=0.89)


def distance_pipeline(
    origin_text: str,
    destination_text: str,
    *,
    mode: str = "driving",
) -> Tuple[str, Optional[DistanceResult], Optional[List[GeoCandidate]], Optional[List[GeoCandidate]]]:
    """
    Returns a tuple of:
    - message (string presented to user)
    - DistanceResult if computed
    - candidates_origin (if ambiguous)
    - candidates_destination (if ambiguous)
    """
    # Geocode both
    orig_candidates = geocode_address_accurate(origin_text)
    dest_candidates = geocode_address_accurate(destination_text)

    if not orig_candidates or not dest_candidates:
        return (
            "I couldn't fetch precise distance; would you like me to try again or enter addresses as coordinates?",
            None,
            None if orig_candidates else [],
            None if dest_candidates else [],
        )

    # Ambiguity handling: if more than 1 candidate or low confidence
    need_confirm = False
    if len(orig_candidates) > 1:
        need_confirm = True
    if len(dest_candidates) > 1:
        need_confirm = True

    if need_confirm:
        return (
            "I found multiple possible matches. Please confirm:",
            None,
            orig_candidates,
            dest_candidates,
        )

    # Compute distance with top candidates
    res = compute_distance_accurate(
        (orig_candidates[0].lat, orig_candidates[0].lon),
        (dest_candidates[0].lat, dest_candidates[0].lon),
        mode=mode,
    )
    if not res:
        # Fallback: perform a direct request and parse
        settings = get_settings()
        key = settings.distance_api_key
        url = f"{DISTANCEMATRIX_BASE}/distancematrix/json"
        params = {
            "origins": f"{orig_candidates[0].lat:.6f},{orig_candidates[0].lon:.6f}",
            "destinations": f"{dest_candidates[0].lat:.6f},{dest_candidates[0].lon:.6f}",
            "mode": mode,
        }
        if key:
            params["key"] = key
        try:
            r = requests.get(url, params=params, timeout=12)
            data = r.json()
            rows = data.get("rows", [{}])
            elements = rows[0].get("elements", [{}]) if rows else [{}]
            element = elements[0]
            if element.get("status") == "OK":
                dist_m = _json_get(element, ["distance", "value"]) or 0
                dur_s = _json_get(element, ["duration", "value"]) or 0
                km = round(float(dist_m) / 1000.0, 1)
                minutes = round(float(dur_s) / 60.0)
                res = DistanceResult(distance_km=km, duration_min=minutes, mode=mode, confidence=0.89)
        except Exception:
            res = None
        if not res:
            return (
                "I couldn't fetch precise distance; would you like me to try again or enter addresses as coordinates?",
                None,
                None,
                None,
            )

    msg = (
        f"Distance: {res.distance_km:.1f} km by {res.mode} (approx.). "
        f"ETA: {int(res.duration_min)} minutes. Source: {res.source}. Confidence: {res.confidence:.2f}."
    )
    return (msg, res, None, None)
