"""Environment fingerprinting (M15 — Environment Intelligence).

A pure, deterministic library that derives a stable *fingerprint* of the current
environment from generic ``WorldState`` signals. It exists so FRIDAY can tell when an
environment's identity, version, or interactive layout has changed and therefore needs
re-exploration rather than silently reusing stale affordances (FAS §A2.2).

Design tenets (see design.md, components C1–C4):

* **Pure / total / deterministic.** Every public function is a pure function of its
  inputs. Identical inputs always produce an identical digest; any incorporated signal
  changing produces a different digest. Nothing here performs I/O or touches a kernel.
* **Sparse-safe.** A missing sensor simply omits its signal (empty string). Partial,
  ``None``-ish, or malformed inputs never raise — every attribute access is guarded.
* **Axiom 15 (no special-casing).** Fingerprints are built ONLY from generic
  structural/version signals. We never branch on a specific application, site, or window
  *title*. Window titles are volatile/site-specific identity and are deliberately excluded
  from fingerprint identity.

The concrete generic signals used:

* ``platform``           — supplied override, else ``sys.platform``.
* ``window_kind``        — ``WindowInfo.class_name`` (window class) combined with
  ``WindowInfo.process_name`` (process kind). Both are generic, opaque structural
  descriptors; the window TITLE text is never used.
* ``a11y_signature``     — sha256 over the sorted multiset of ``UIElement.control_type``
  values (accessibility roles/kinds). Structure only — never element text/values/coords.
* ``visual_hash``        — the existing ``WorldState.screenshot_hash`` (may be "").
* ``capability_version`` / ``layout_version`` — supplied version strings (default "").
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

__all__ = [
    "EnvironmentFingerprint",
    "compute_fingerprint",
    "compute_ui_fingerprint",
    "version_confidence_factor",
]

# --------------------------------------------------------------------------------------
# Policy constants
# --------------------------------------------------------------------------------------

# Confidence floor for a fully-diverged environment (version_confidence_factor).
_CONFIDENCE_FLOOR: float = 0.5

# Neutral penalty applied when a capability has no recorded validated fingerprint.
# Documented policy: an un-validated capability is neither fully trusted (1.0) nor
# treated as fully stale (floor); it sits in between so it is used cautiously.
_NEUTRAL_PENALTY: float = 0.75

# Generic, application-agnostic set of interactive/actionable control-type kinds.
# Selection is by GENERIC role/kind only — never by application, site, or window title
# (Axiom 15). Values are compared case-insensitively.
_INTERACTIVE_KINDS: frozenset[str] = frozenset(
    {
        "button",
        "splitbutton",
        "togglebutton",
        "radiobutton",
        "checkbox",
        "edit",
        "textbox",
        "input",
        "textarea",
        "combobox",
        "listitem",
        "menuitem",
        "menu",
        "hyperlink",
        "link",
        "tab",
        "tabitem",
        "slider",
        "spinner",
        "scrollbar",
        "treeitem",
        "cell",
        "dataitem",
        "switch",
    }
)

# Stable ordering of the component keys that feed the digest.
_COMPONENT_KEYS: tuple[str, ...] = (
    "platform",
    "window_kind",
    "a11y_signature",
    "visual_hash",
    "capability_version",
    "layout_version",
)


def _coerce_str(value: Any) -> str:
    """Coerce any value to a string defensively; ``None``/failure -> ""."""
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:  # pragma: no cover - str() on exotic objects; stay total.
        # Deliberate: coercion must be total. A value whose __str__ raises yields the
        # empty (missing) signal rather than propagating into a pure function.
        return ""


def _sha256_hex(text: str) -> str:
    """sha256 hex digest of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


# --------------------------------------------------------------------------------------
# C1 — EnvironmentFingerprint
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EnvironmentFingerprint:
    """A stable, JSON-projectable digest of an environment's identity/layout.

    Fields
    ------
    digest:
        Hex sha256 over the canonical serialization of ``components``. This is the
        environment identity used for equality/change-detection.
    components:
        The generic signals that fed the digest (platform, window_kind, a11y_signature,
        visual_hash, capability_version, layout_version). Kept for events/logging and for
        computing how many signals diverge between two fingerprints.
    ui_fingerprint:
        Hex digest of the interactive-surface structure (see ``compute_ui_fingerprint``).

    Equality is effectively by ``digest``: identical inputs produce identical fields, and
    since ``digest`` is derived deterministically from ``components``, dataclass equality
    over all fields coincides with digest equality for fingerprints of the same shape.
    """

    digest: str
    components: Dict[str, str]
    ui_fingerprint: str

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain JSON-safe dict (Requirement 1.4)."""
        return {
            "digest": self.digest,
            "components": {
                _coerce_str(k): _coerce_str(v)
                for k, v in dict(self.components or {}).items()
            },
            "ui_fingerprint": self.ui_fingerprint,
        }


# --------------------------------------------------------------------------------------
# C3 — compute_ui_fingerprint
# --------------------------------------------------------------------------------------


def _element_kind(element: Any) -> str:
    """Extract a generic role/kind from a UI element, defensively.

    Uses ``control_type`` (the generic accessibility role/kind). Never uses element text,
    values, or coordinates. Returns "" if unavailable.
    """
    kind = getattr(element, "control_type", None)
    if kind is None and isinstance(element, dict):
        kind = element.get("control_type")
    return _coerce_str(kind).strip().lower()


def _element_enabled(element: Any) -> bool:
    """Whether an element is enabled, defaulting to True when unknown (total)."""
    enabled = getattr(element, "enabled", None)
    if enabled is None and isinstance(element, dict):
        enabled = element.get("enabled")
    if enabled is None:
        return True
    return bool(enabled)


def _iter_ui_elements(world_state: Any) -> List[Any]:
    """Return the ui_elements list from a WorldState defensively (never raises)."""
    elements = getattr(world_state, "ui_elements", None)
    if elements is None and isinstance(world_state, dict):
        elements = world_state.get("ui_elements")
    if not elements:
        return []
    try:
        return list(elements)
    except Exception:  # pragma: no cover - non-iterable ui_elements; stay total.
        # Deliberate: a malformed (non-iterable) ui_elements field yields no structure
        # rather than raising inside a pure function.
        return []


def compute_ui_fingerprint(world_state: Any) -> str:
    """Digest the interactive-surface structure of a ``WorldState`` (Requirement 2).

    Computes a sha256 over the sorted multiset of *interactive* World-Object roles/kinds
    together with a stable per-role count (the "shape"), independent of any volatile
    element text/values/coordinates. Interactive elements are selected generically via
    ``_INTERACTIVE_KINDS`` (editable/actionable roles) — never by application or site.

    Sparse/empty input yields a stable empty string. Never raises.
    """
    counts: Dict[str, int] = {}
    for element in _iter_ui_elements(world_state):
        kind = _element_kind(element)
        if not kind or kind not in _INTERACTIVE_KINDS:
            continue
        if not _element_enabled(element):
            continue
        counts[kind] = counts.get(kind, 0) + 1

    if not counts:
        # Stable empty fingerprint for a sparse/empty interactive surface.
        return ""

    # Canonical, order-stable serialization: sorted "role:count" pairs.
    canonical = "|".join(f"{role}:{counts[role]}" for role in sorted(counts))
    return _sha256_hex(canonical)


# --------------------------------------------------------------------------------------
# C2 — compute_fingerprint
# --------------------------------------------------------------------------------------


def _window_kind(world_state: Any) -> str:
    """Derive a GENERIC window descriptor from the active window (Axiom 15).

    Uses ``WindowInfo.class_name`` (the window class) combined with
    ``WindowInfo.process_name`` (the process kind). Both are generic, opaque structural
    signals. The window TITLE text is deliberately NOT used: titles are volatile and
    site-/document-specific identity, which Axiom 15 forbids as fingerprint identity.

    Returns "" when no window info is available.
    """
    window = getattr(world_state, "active_window", None)
    if window is None and isinstance(world_state, dict):
        window = world_state.get("active_window")
    if window is None:
        return ""

    class_name = getattr(window, "class_name", None)
    process_name = getattr(window, "process_name", None)
    if isinstance(window, dict):
        class_name = class_name if class_name is not None else window.get("class_name")
        process_name = (
            process_name if process_name is not None else window.get("process_name")
        )

    class_part = _coerce_str(class_name).strip()
    process_part = _coerce_str(process_name).strip()

    if not class_part and not process_part:
        return ""
    # Canonical join of the two generic descriptors (order-stable).
    return f"{class_part}|{process_part}"


def _a11y_signature(world_state: Any) -> str:
    """sha256 over the sorted multiset of accessibility roles/kinds (Requirement 1.1).

    Uses ``UIElement.control_type`` only (structure), never element text/values/coords.
    Empty/sparse -> "". Never raises.
    """
    kinds: List[str] = []
    for element in _iter_ui_elements(world_state):
        kind = _element_kind(element)
        if kind:
            kinds.append(kind)
    if not kinds:
        return ""
    # Sorting the full list preserves the multiset (per-kind counts).
    canonical = "|".join(sorted(kinds))
    return _sha256_hex(canonical)


def _visual_hash(world_state: Any) -> str:
    """The existing screenshot hash, coerced defensively; missing -> ""."""
    value = getattr(world_state, "screenshot_hash", None)
    if value is None and isinstance(world_state, dict):
        value = world_state.get("screenshot_hash")
    return _coerce_str(value)


def compute_fingerprint(
    world_state: Any,
    *,
    platform: Optional[str] = None,
    capability_version: str = "",
    layout_version: str = "",
) -> EnvironmentFingerprint:
    """Compute a deterministic ``EnvironmentFingerprint`` from a ``WorldState``.

    Pure / total / deterministic (Requirements 1.1–1.4). Builds the generic component
    signals defensively (a missing signal becomes ""), computes a canonical sha256
    ``digest`` over them, and attaches the interactive ``ui_fingerprint``.

    Parameters
    ----------
    world_state:
        The perception snapshot. May be sparse/partial/None — never raises.
    platform:
        Optional platform override; falls back to ``sys.platform``.
    capability_version, layout_version:
        Optional version strings incorporated into identity (default "").
    """
    components: Dict[str, str] = {
        "platform": _coerce_str(platform) if platform is not None else _coerce_str(sys.platform),
        "window_kind": _window_kind(world_state),
        "a11y_signature": _a11y_signature(world_state),
        "visual_hash": _visual_hash(world_state),
        "capability_version": _coerce_str(capability_version),
        "layout_version": _coerce_str(layout_version),
    }

    # Canonical, order-stable serialization: fixed key order, "key=value" joined.
    canonical = "|".join(f"{key}={components[key]}" for key in _COMPONENT_KEYS)
    digest = _sha256_hex(canonical)

    ui_fingerprint = compute_ui_fingerprint(world_state)

    return EnvironmentFingerprint(
        digest=digest,
        components=components,
        ui_fingerprint=ui_fingerprint,
    )


# --------------------------------------------------------------------------------------
# C4 — version_confidence_factor
# --------------------------------------------------------------------------------------


def _fingerprint_components(fingerprint: Any) -> Dict[str, str]:
    """Extract a components dict from a fingerprint defensively (never raises)."""
    components = getattr(fingerprint, "components", None)
    if components is None and isinstance(fingerprint, dict):
        components = fingerprint.get("components")
    if not components:
        return {}
    try:
        return {
            _coerce_str(k): _coerce_str(v) for k, v in dict(components).items()
        }
    except Exception:  # pragma: no cover - malformed components; stay total.
        # Deliberate: a malformed components mapping contributes no divergence signal
        # rather than raising inside a pure advisory function.
        return {}


def _fingerprint_digest(fingerprint: Any) -> str:
    """Extract a digest from a fingerprint defensively (never raises)."""
    digest = getattr(fingerprint, "digest", None)
    if digest is None and isinstance(fingerprint, dict):
        digest = fingerprint.get("digest")
    return _coerce_str(digest)


def version_confidence_factor(validated: Any, current: Any) -> float:
    """Advisory confidence multiplier in ``[floor, 1.0]`` (Requirement 5).

    Returns ``1.0`` when ``validated`` matches ``current`` by digest. On a mismatch the
    factor DECREASES as more component signals diverge:

        factor = 1.0 - _CONFIDENCE_FLOOR * (diverging_components / total_components)

    clamped to ``[_CONFIDENCE_FLOOR, 1.0)``. When ``validated`` is ``None`` (no recorded
    validated fingerprint), returns the documented neutral penalty ``_NEUTRAL_PENALTY``.

    Pure, total, deterministic, advisory-only. Never raises; never writes competence.
    """
    if validated is None:
        return _NEUTRAL_PENALTY

    validated_digest = _fingerprint_digest(validated)
    current_digest = _fingerprint_digest(current)

    # Exact identity match -> full confidence.
    if validated_digest and validated_digest == current_digest:
        return 1.0

    validated_components = _fingerprint_components(validated)
    current_components = _fingerprint_components(current)

    # Union of component keys defines the divergence denominator.
    keys = set(validated_components) | set(current_components)
    total = len(keys)
    if total == 0:
        # No component signals to compare, yet digests differ (or are empty): apply the
        # floor as the most conservative defined outcome.
        return _CONFIDENCE_FLOOR

    diverging = sum(
        1
        for key in keys
        if validated_components.get(key, "") != current_components.get(key, "")
    )
    if diverging == 0:
        # Digests differ but no component diverges (degenerate/empty inputs): still a
        # mismatch, so stay strictly below full confidence.
        return _CONFIDENCE_FLOOR

    factor = 1.0 - _CONFIDENCE_FLOOR * (diverging / total)
    # Clamp to [floor, 1.0]; a real mismatch always yields < 1.0 here.
    if factor < _CONFIDENCE_FLOOR:
        return _CONFIDENCE_FLOOR
    if factor > 1.0:  # pragma: no cover - unreachable given ratio in (0, 1].
        return 1.0
    return factor
