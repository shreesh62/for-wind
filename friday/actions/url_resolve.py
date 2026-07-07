"""Ch 39/Axiom 15 — generic target→URL resolution (NO hardcoded site map).

FRIDAY must never carry a table of application/site names → URLs (that is the
"Gmail Agent" anti-pattern, FAS Ch 39/Ch 63, and a direct Axiom 15 violation).
A target is resolved to a URL ONLY when it is *already* a URL or a bare host
name (something containing a dotted domain). A bare app/site word like
"instagram" or "gmail" resolves to ``None`` on purpose: the runtime then
discovers the right environment generically (search / exploration) rather than
looking it up in a hardcoded map.

This module is a pure function with no application identity anywhere.
"""

from __future__ import annotations

import re
from typing import Optional

# A conservative "looks like a bare host" test: one or more dot-separated labels
# ending in a 2+ letter TLD, with no whitespace. This matches "example.com" and
# "sub.example.co.uk" but NOT a plain word like "instagram" or a sentence.
_BARE_HOST_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


def resolve_target_url(target: str) -> Optional[str]:
    """Return an ``https``/``http`` URL for ``target`` iff it is already a URL
    or a bare host name; otherwise ``None`` (Axiom 15 — no site lookup table).

    - ``"https://x.example/y"`` / ``"http://..."`` → returned unchanged.
    - ``"www.example.com"`` → ``"https://www.example.com"``.
    - ``"example.com"`` / ``"docs.example.org"`` → ``"https://..."``.
    - ``"instagram"`` / ``"open my mail"`` / ``"notepad"`` → ``None``.
    """
    if not target:
        return None
    t = target.strip()
    lowered = t.lower()

    if lowered.startswith(("http://", "https://")):
        return t
    if lowered.startswith("www."):
        return f"https://{t}"
    # A single bare token that looks like a domain (has a dot, no spaces).
    if " " not in t and _BARE_HOST_RE.match(lowered):
        return f"https://{t}"
    return None
