# Design: M15 — Environment Intelligence (Fingerprints & Capability Invalidation)

## Overview

Environment Intelligence adds a **general** fingerprinting + change-detection mechanism over
the existing universal perception. A pure library computes an `EnvironmentFingerprint` and a
`ui_fingerprint` deterministically from a `WorldState` (which already carries a screenshot
`screenshot_hash`, UI-Automation `ui_elements`, and an `active_window` from M23). A kernel-
attached `FingerprintMonitor` tracks the last-seen fingerprint per environment key, detects
changes, and emits `environment.fingerprint_changed` + `environment.capabilities_invalidated`
proposal events so the Exploration Engine (A2.8) and competence consumers re-explore/re-
validate rather than silently reuse stale affordances. A pure `version_confidence_factor`
helper lets Deliberation lower a capability's confidence when the environment it was
validated against no longer matches.

No application-, site-, or window-title-specific identity is used as a special case
(Axiom 15): fingerprints are built only from generic structural/version signals. Everything
is additive, inert without a kernel, and event-driven (replay-safe).

## Architecture

```
   WorldState (from active_window perception, M23)
        │  platform / window kind / a11y element roles / screenshot hash / versions
        ▼
   compute_fingerprint(world_state, ...) ─▶ EnvironmentFingerprint {digest, components, ui_fingerprint}
        │                                              │ (pure, deterministic)
        ▼                                              ▼
   FingerprintMonitor.observe(env_key, world_state)   version_confidence_factor(validated, current) ─▶ [0,1]
        │  compare vs last-seen (bounded registry)
        ├── first-seen  → record baseline, no event
        ├── unchanged   → no event
        └── changed     → emit environment.fingerprint_changed
                          then emit environment.capabilities_invalidated (proposal)
                                    │  (JSON-safe; kernel-mediated, Ch 52)
                                    ▼
                 consumed by Exploration Engine (A2.8) / competence (re-explore / re-validate)
```

### Modified / new components

| Component | File | Change |
|---|---|---|
| Fingerprint library | `friday/perception/fingerprint.py` (NEW) | `EnvironmentFingerprint`, `compute_fingerprint`, `compute_ui_fingerprint`, `version_confidence_factor` |
| Change monitor | `friday/perception/fingerprint_monitor.py` (NEW) | `FingerprintMonitor` + `attach_fingerprint_monitor(kernel, ...)` |
| Bootstrap | `friday/api/server.py` | attach the monitor in the guarded kernel path |
| Benchmark | `friday/benchmarks/environment.py` (NEW) | deterministic fingerprint/change benchmark |

## Components and Interfaces

### C1 — `EnvironmentFingerprint` (frozen dataclass, JSON-projectable)
Fields: `digest` (hex str), `components` (dict of the signals that fed the digest:
`platform`, `window_kind`, `a11y_signature`, `visual_hash`, `capability_version`,
`layout_version`), and `ui_fingerprint` (hex str). `to_dict()` returns a plain JSON-safe
dict (Requirement 1.4). Two fingerprints compare equal iff their digests match.

### C2 — `compute_fingerprint(world_state, *, platform=None, capability_version="", layout_version="") -> EnvironmentFingerprint`
Pure/deterministic. Builds `components`:
- `platform`: supplied or `sys.platform`.
- `window_kind`: from `world_state.active_window` — a GENERIC descriptor (window class /
  process kind / control class), NEVER the title text (Axiom 15). Missing → "".
- `a11y_signature`: a stable digest of the SORTED multiset of `ui_elements` roles/kinds
  (structure, not volatile text/values). Missing/empty → "".
- `visual_hash`: `world_state.screenshot_hash` (may be "").
- `capability_version` / `layout_version`: supplied (default "").
The `digest` = sha256 over a canonical ordering of the components. `ui_fingerprint` is C3.
Total: a sparse `WorldState` simply omits signals; never raises (Requirement 1.2–1.4).

### C3 — `compute_ui_fingerprint(world_state) -> str`
A sha256 over the SORTED multiset of interactive World-Object roles/kinds (and stable
shape like count-per-role), independent of volatile text values (Requirement 2.1–2.2).
Interactive elements are selected generically (e.g. editable/actionable roles), never by
site/app. Sparse → stable "" or empty-digest; never raises (Requirement 2.3).

### C4 — `version_confidence_factor(validated, current) -> float`
Pure, total, deterministic. Returns `1.0` when `validated.digest == current.digest`; on a
mismatch returns a reduced factor scaled by how many component signals diverge (more
divergence → lower factor, bounded to a floor). A missing `validated` fingerprint yields a
defined neutral-penalty factor per policy. Never raises. Advisory multiplier only
(Requirement 5.1–5.3).

### C5 — `FingerprintMonitor`
- `attach(kernel)` — stores the kernel (no-op if None); the monitor is driven by explicit
  `observe(...)` calls (perception is not itself a kernel event today), and MAY also
  subscribe to a perception event if one exists.
- `observe(env_key, world_state, **versions) -> str` — compute the current fingerprint,
  compare to the bounded per-`env_key` last-seen entry, return `"first_seen"` /
  `"unchanged"` / `"changed"`. On `"changed"` (kernel present) emit
  `environment.fingerprint_changed` {env_key, previous_digest, current_digest,
  changed_components} then `environment.capabilities_invalidated` {env_key, reason,
  changed_components}. First-seen records a baseline and emits nothing (Requirement 3.1–3.3,
  4.1–4.3).
- Bounded registry: at most `max_environments` keys, oldest evicted (Requirement 3.4).
- Handlers/`observe` never raise (Requirement 6.3).

### C6 — `attach_fingerprint_monitor(kernel, *, monitor=None, max_environments=...) -> FingerprintMonitor`
Reusable wiring helper (mirrors `attach_reactive_loop`/`attach_reflection_layers`): builds or
reuses a monitor, attaches it, returns it. No-op holder without a kernel (Requirement 6.2).

### C7 — Bootstrap wiring (`friday/api/server.py`)
Within the guarded `FRIDAY_USE_KERNEL_EXECUTION=1` block, `attach_fingerprint_monitor(kernel)`
and expose it (e.g. `kernel.fingerprint_monitor`) so the executor can call `observe(...)` per
perception cycle. Additive; default path byte-unchanged; wiring failure logged, never crashes
(Requirement 7.1–7.2).

## Data Models

- `EnvironmentFingerprint` (C1) — the only new persistent-shape type; in-memory only.
- The monitor's registry is an in-memory bounded ordered dict keyed by env_key → last
  `EnvironmentFingerprint`. No new disk persistence. Event payloads are plain JSON-safe dicts.
- Inputs reuse the existing `WorldState` / `WindowInfo` / `UIElement` (no new perception).

## Correctness Properties

### Property 1: fingerprint determinism + sensitivity
Same `WorldState` (+ versions) → identical `digest`; changing any incorporated signal
(platform / window kind / a11y roles / visual hash / version) → different `digest`; a sparse
WorldState never raises.
**Validates: Requirements 1.1, 1.2, 1.4**

### Property 2: UI-fingerprint layout sensitivity + value-independence
Changing the interactive-role structure changes `ui_fingerprint`; re-observing the same
structure reproduces it; changing only volatile element TEXT (same roles/shape) does not
change it.
**Validates: Requirements 2.1, 2.2, 2.3**

### Property 3: change detection + bounded registry
For an env_key: first `observe` → "first_seen" (no event); same fingerprint → "unchanged"
(no event); differing fingerprint → "changed" (+ both events). The registry never exceeds
`max_environments`.
**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

### Property 4: invalidation emission
A detected change emits exactly one `environment.fingerprint_changed` and one
`environment.capabilities_invalidated`, both JSON-serializable, carrying the env_key +
changed components; no competence is mutated by the monitor.
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 5: version-aware confidence
`version_confidence_factor` returns 1.0 on digest match, a value in [floor, 1.0) on
mismatch (lower for larger divergence), and a defined factor when `validated` is missing;
total and never raises.
**Validates: Requirements 5.1, 5.2, 5.3**

### Property 6: isolation + safety
Fingerprint computation contains no app/site/window-title identity branching (Axiom 15);
`observe` and handlers never raise on malformed/sparse input; the monitor is a no-op without
a kernel; only `environment.*` events are emitted.
**Validates: Requirements 1.3, 6.1, 6.2, 6.3**

## Error Handling

Structured-error-model compliant (A2.14.2): the pure functions are total (guarded coercion,
never raise); the monitor catches narrowly and degrades to a no-op, never raising into the
bus. Bootstrap wiring is guarded and logs on failure. No silent blanket swallow without a
justifying comment. `BaseException` propagates.

## Testing Strategy

Hypothesis property tests (≥100 examples, tagged `# Feature: m15-environment-intelligence,
Property N`) for Properties 1–6 using synthetic `WorldState`s built via `WorldStateBuilder`
(plus lightweight fake window/element objects) and a fake/real `CognitiveKernel` capturing
emitted `environment.*` events. A deterministic, hermetic **environment benchmark**
(`friday/benchmarks/environment.py`) measures fingerprint stability (same input → same
digest), sensitivity (mutated input → changed), and change-detection precision over synthetic
WorldState sequences; NOT part of the 5-domain scorecard and never written to the committed
baseline (mirrors the M19/M20/M23/M24 policy). Full regression suite stays green (zero
failures).

## Traceability

- FAS Ch 23 / 9.23 / 25; v2.1 amendment **A2.2 — Environment Intelligence** (Absent → Built).
- Builds on M23 universal perception (`WorldState` visual hash + UIA elements + window info);
  feeds the A2.8 Exploration Engine (re-explore on change) and A2.9 competence (version-aware
  confidence). No duplicate perception system; no application-specific logic (Axiom 15).
