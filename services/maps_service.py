from services.distancematrix_service import (
    distance_pipeline,
    DistanceResult,
    geocode_address_accurate,
    compute_distance_accurate,
)


_PENDING_DISTANCE: dict | None = None


def _parse_choice(text: str) -> tuple[int | None, int | None, int | None, int | None]:
    low = (text or "").lower().strip()
    # Patterns:
    # - "choose option 2"
    # - "choose 2"
    # - "choose 2 1" (origin 2, destination 1)
    # - "origin 2 destination 1"
    m = __import__("re").search(r"\b(?:choose|option)\b[^\d]*(\d+)(?:[^\d]+(\d+))?", low)
    if m:
        a = int(m.group(1)) if m.group(1) else None
        b = int(m.group(2)) if m.group(2) else None
    else:
        a, b = None, None

    mo = __import__("re").search(r"\borigin\b[^\d]*(\d+)", low)
    md = __import__("re").search(r"\bdest(?:ination)?\b[^\d]*(\d+)", low)
    o = int(mo.group(1)) if mo else None
    d = int(md.group(1)) if md else None
    return a, b, o, d


def handle_distance_followup(command: str) -> str | None:
    global _PENDING_DISTANCE
    if not _PENDING_DISTANCE:
        return None

    a, b, o_idx, d_idx = _parse_choice(command)

    orig_cands = _PENDING_DISTANCE.get("orig_cands") or []
    dest_cands = _PENDING_DISTANCE.get("dest_cands") or []
    origin_text = _PENDING_DISTANCE.get("origin_text") or ""
    dest_text = _PENDING_DISTANCE.get("dest_text") or ""
    mode = _PENDING_DISTANCE.get("mode") or "driving"

    origin_amb = isinstance(orig_cands, list) and len(orig_cands) > 1
    dest_amb = isinstance(dest_cands, list) and len(dest_cands) > 1

    if origin_amb or dest_amb:
        # Resolve indices
        if o_idx is None and d_idx is None:
            if origin_amb and dest_amb:
                o_idx, d_idx = a, b
            elif origin_amb:
                o_idx = a
            elif dest_amb:
                d_idx = a

        if origin_amb and (o_idx is None or o_idx < 1 or o_idx > len(orig_cands)):
            return "Please choose an origin option number."
        if dest_amb and (d_idx is None or d_idx < 1 or d_idx > len(dest_cands)):
            return "Please choose a destination option number."
        if origin_amb and dest_amb and (o_idx is None or d_idx is None):
            return "Please choose two option numbers: origin then destination."

        o_pick = orig_cands[(o_idx - 1) if origin_amb else 0]
        d_pick = dest_cands[(d_idx - 1) if dest_amb else 0]
        res = compute_distance_accurate((o_pick.lat, o_pick.lon), (d_pick.lat, d_pick.lon), mode=mode)
        _PENDING_DISTANCE = None
        if not res:
            return "missing details: I couldn't fetch precise distance. Would you like me to try again or use coordinates?"
        km = f"{res.distance_km:.1f} km"
        minutes = f"{int(res.duration_min)} minutes"
        return (
            f"Distance between {origin_text} and {dest_text} is {km}. "
            f"Estimated travel time is {minutes}. Source: {res.source}."
        )

    _PENDING_DISTANCE = None
    return None


def _format_candidates(title: str, candidates: list) -> str:
    lines = [f"{title}:"]
    for i, c in enumerate(candidates, start=1):
        lines.append(f"{i}) {c.formatted_address}")
    return "\n".join(lines)


def get_distance_and_time(origin: str, destination: str, *, mode: str = "driving") -> str:
    """Fetch distance & duration using Distancematrix Accurate pipeline.

    Backward-compatible message for existing tests:
    - "Distance between ORIG and DEST is X km. Estimated travel time is Y minutes."
    Fallbacks maintain older error texts.
    """
    msg, result, orig_cands, dest_cands = distance_pipeline(origin, destination, mode=mode)

    if result:
        km = f"{result.distance_km:.1f} km"
        minutes = f"{int(result.duration_min)} minutes"
        return (
            f"Distance between {origin} and {destination} is {km}. "
            f"Estimated travel time is {minutes}. Source: {result.source}."
        )

    if (isinstance(orig_cands, list) and orig_cands) or (isinstance(dest_cands, list) and dest_cands):
        global _PENDING_DISTANCE
        origin_list = orig_cands if isinstance(orig_cands, list) else []
        dest_list = dest_cands if isinstance(dest_cands, list) else []
        _PENDING_DISTANCE = {
            "origin_text": origin,
            "dest_text": destination,
            "mode": mode,
            "orig_cands": origin_list,
            "dest_cands": dest_list,
        }

        parts = [
            "Distance missing details due to ambiguous or incomplete addresses.",
            "I found multiple possible matches.",
        ]
        if origin_list:
            parts.append(_format_candidates("Origin", origin_list))
        if dest_list:
            parts.append(_format_candidates("Destination", dest_list))
        if origin_list and dest_list:
            parts.append("Reply with: 'choose 2 1' (origin 2, destination 1).")
        else:
            parts.append("Reply with: 'choose option 2'.")
        return "\n".join(parts)

    # Generic fallback text (back-compat: include exact 'missing details')
    return "missing details: I couldn't fetch precise distance. Would you like me to try again or use coordinates?"
