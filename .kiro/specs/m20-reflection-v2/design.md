# Design: M20 — Reflection v2 (Layered Reflection)

## Overview

Reflection v2 formalizes the five-layer hierarchy of FAS §A2.10.1 additively over the
existing `friday/cognition/reflection.py::ReflectionEngine`. The existing engine already
covers the two lowest layers (Immediate = its micro/action reflection; Session = its
goal/session reflection) and correctly emits only `memory.candidate` + `reflection.completed`
(Reflection proposes; Memory decides). M20 adds three higher **consumer** layers —
Long-Term, Skill, Architectural — that subscribe to the `reflection.completed` stream, build
bounded aggregates, and emit structured `reflection.*` **proposal** events when thresholds
are crossed. No layer writes memory or mutates any subsystem; no second reflection system is
introduced.

## Architecture

```
              action/verification/goal events
                          │
                          ▼
        ReflectionEngine (existing)  ── emits ──▶ memory.candidate
          (IMMEDIATE + SESSION)      ── emits ──▶ reflection.completed ──┐
                                                                         │ (stream)
        ┌────────────────────────────────────────────────────────────┘
        ▼                         ▼                          ▼
  LongTermReflector        SkillReflector          ArchitecturalReflector
  (across sessions)        (per capability)         (meta / cross-layer)
        │                         │                          │
        └── reflection.longterm ──┴── reflection.skill ──────┴── reflection.architectural
                     (all JSON-safe proposal events; never a memory write)
```

The three higher layers are pure aggregators over the existing per-reflection stream. They
are wired by one reusable helper, `attach_reflection_layers(kernel, ...)`, mirroring the
M24 `attach_reactive_loop` pattern, and are attached only in the guarded kernel-execution
bootstrap.

### Modified / new components

| Component | File | Change |
|---|---|---|
| Layer taxonomy | `friday/cognition/reflection.py` | add `ReflectionLayer` enum (additive) |
| Higher layers | `friday/cognition/reflection_layers.py` (NEW) | `LongTermReflector`, `SkillReflector`, `ArchitecturalReflector` |
| Wiring helper | `friday/cognition/reflection_layers.py` (NEW) | `attach_reflection_layers(kernel, ...)` |
| Bootstrap | `friday/api/server.py` | attach the layers in the guarded kernel path |
| Benchmark | `friday/benchmarks/reflection.py` (NEW) | deterministic layered-proposal benchmark |

## Components and Interfaces

### C1 — `ReflectionLayer` (enum, additive to reflection.py)
Five ordered members: `IMMEDIATE`, `SESSION`, `LONG_TERM`, `SKILL`, `ARCHITECTURAL`. A
`str` enum (like `ReflectionScale`) so `.value` is JSON-safe; an ordinal helper (index in
declaration order) makes scope comparable (Requirement 1.3). The existing `ReflectionScale`
is retained; `ReflectionLayer` is the normative layer taxonomy layered on top (micro→IMMEDIATE,
task/goal/session→SESSION mapping documented, no output change — Requirement 1.2, 5.3).

### C2 — `LongTermReflector`
- `attach(kernel)` subscribes to `reflection.completed`.
- Maintains a bounded per-`(capability, environment)` deque of recent
  `(prediction_error, calibration)` samples (max N, oldest evicted — Requirement 2.3).
- On each event: append the sample; when a key has ≥ `min_samples` and mean prediction
  error ≥ `error_threshold`, emit `reflection.longterm` with the trend summary
  (JSON-safe: key, sample_count, mean_error, mean_calibration) — Requirement 2.1, 2.2, 6.1.
- Query: `trend(capability, environment)` → current aggregate. Handlers never raise (2.4).

### C3 — `SkillReflector`
- `attach(kernel)` subscribes to `reflection.completed`.
- Aggregates per-capability: sample_count, mean_prediction_error, verified_rate
  (Requirement 3.1). Bounded per-capability window (3.4).
- When a capability reaches ≥ `min_samples` with `verified_rate ≥ v_thresh` and
  `mean_error ≤ e_thresh`, emit `reflection.skill` flagging a skill-pipeline candidate
  (proposal only — Requirement 3.2).
- Query: `summaries()` → per-capability summary dict (Requirement 3.3). Handlers never raise.

### C4 — `ArchitecturalReflector`
- `attach(kernel)` subscribes to `reflection.completed` (and MAY observe `reflection.longterm`).
- Tracks cross-capability meta-signals (e.g. count of distinct capabilities whose long-term
  mean error is high, or global mean calibration error). When a configurable meta-threshold
  is crossed, emit one advisory `reflection.architectural` proposal (deduplicated so it is
  not spammed) — Requirement 4.1, 4.2. Purely advisory; bounded; handlers never raise (4.3).

### C5 — `attach_reflection_layers(kernel, *, longterm=None, skill=None, architectural=None, ...)`
One reusable helper (function-local imports; no cycles) that instantiates the three layers
(or reuses injected ones) and attaches them to the kernel; returns a small holder object.
No-op without a kernel; each layer isolates its own exceptions (Requirement 6.2, 6.3).

### C6 — Bootstrap wiring (`friday/api/server.py`)
Within the guarded `FRIDAY_USE_KERNEL_EXECUTION=1` block (where `attach_reactive_loop` and
the retrieval router are already wired), call `attach_reflection_layers(kernel)`. Additive;
default path byte-unchanged; wiring failure logged with structured context, never crashes
bootstrap (Requirement 7.1, 7.2).

## Data Models

- `ReflectionLayer` — the new enum (C1).
- Per-layer aggregates are in-memory bounded structures (deques/dicts keyed by capability or
  (capability, environment)); no new persistence. Proposal event payloads are plain
  JSON-safe dicts. The existing `ReflectionRecord` / `reflection.completed` payload is the
  input stream, unchanged.

## Correctness Properties

### Property 1: taxonomy totality + ordering
`ReflectionLayer` has exactly five members in immediate→architectural order; ordinals are
strictly increasing; every `.value` JSON-serializes.
**Validates: Requirements 1.1, 1.3**

### Property 2: long-term aggregation + threshold proposal
Feeding a stream where a (capability, environment) key's mean error crosses the threshold
over ≥ min_samples yields exactly the expected `reflection.longterm` proposal(s); below
threshold yields none; the aggregate never exceeds the bound.
**Validates: Requirements 2.1, 2.2, 2.3**

### Property 3: skill aggregation + candidate proposal
A capability accumulating verified low-error experience triggers a `reflection.skill`
candidate proposal; `summaries()` reports correct counts/rates; bounded.
**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

### Property 4: architectural meta-proposal (advisory, deduped)
Crossing the meta-threshold emits one advisory `reflection.architectural` proposal and does
not re-emit spuriously; no subsystem is mutated.
**Validates: Requirements 4.1, 4.2**

### Property 5: proposes-not-decides isolation
The new module does not import memory/competence/recovery and emits only
`memory.candidate` / `reflection.*` events; malformed/empty events never raise; without a
kernel every layer is a no-op.
**Validates: Requirements 5.1, 5.2, 6.1, 6.2, 6.3**

### Property 6: existing engine unchanged
With the higher layers attached, the existing `ReflectionEngine` still emits its
`memory.candidate` + `reflection.completed` outputs identically for a given input.
**Validates: Requirements 5.3**

## Error Handling

Structured-error-model compliant (A2.14.2): every layer handler catches narrowly and
degrades to a no-op, never raising into the bus (mirrors the existing engine and the M24
subscribers). No silent blanket swallow without a justifying comment. Bootstrap wiring is
guarded and logs on failure. `BaseException` propagates.

## Testing Strategy

Hypothesis property tests (≥100 examples, tagged `# Feature: m20-reflection-v2, Property N`)
for Properties 1–6 using a fake/real `CognitiveKernel` and synthetic `reflection.completed`
streams. A deterministic, hermetic **reflection benchmark**
(`friday/benchmarks/reflection.py`) drives synthetic reflection streams through the layers
and measures proposal correctness (expected proposals emitted / no false proposals); it is
NOT part of the 5-domain scorecard and is never written to the committed baseline (mirrors
the M23/M24/M19 policy). Full regression suite must stay green (zero failures).

## Traceability

- FAS Ch 13; v2.1 amendment **A2.10 — Layered reflection** (Partial → Built).
- Consumes the existing `reflection.completed` stream; feeds the §A2.5 skill pipeline via a
  `reflection.skill` candidate proposal. No duplicate reflection system; no direct memory
  writes; no application-specific logic (Axiom 15).
