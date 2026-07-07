# Implementation Plan: M10 — Domain Depth as Pure Capability Compositions

## Overview

This plan converts the approved M10 design into incremental, code-focused steps. M10 adds one new
top-level package `friday/domains/` whose modules are **pure compositions** over the existing
`CapabilityRegistry` (`find_for` by abstract verb) and the `ExecutionEvidence` bundle. Nothing in
M1–M9 is modified — domains are leaves that depend downward only. The defining gate: deleting any
domain module leaves every capability and every other domain intact.

Ordering is dependency-driven and validates functionality early through code:

1. **Data models first** (`friday/domains/models.py`) — all frozen value objects
   (`RankedSource`/`Claim`/`Contradiction`/`HypothesisScore`/`ResearchFinding`, `Conversation`/`Turn`/
   `DeliveryOutcome`/`DeliveryStatus`, `SemanticDocument`/`Section`/`Block`/`Citation`/`DocumentFormat`/
   `ExportOutcome`, `DeferredOutcome`), directly unit/property testable.
2. **ResearchDomain** (`friday/domains/research.py`) — composes `research(...)`; adds credibility
   ranking, contradiction detection, hypothesis scoring.
3. **CommunicationDomain** (`friday/domains/communication.py`) — env-independent deliver + verify +
   immutable transcript.
4. **DocumentDomain** (`friday/domains/documents.py`) — semantic render + multi-format export +
   citations.
5. **SoftwareDomain** (`friday/domains/software.py`) — Ch 41 deferred v2 stub.
6. **Package surface** (`friday/domains/__init__.py`) exporting the public domains + models.
7. **Tests** — unit, all 11 Hypothesis properties, AST isolation, integration, and the M10 gate.
8. **Final regression checkpoint** (keep ≥ 1044 tests green).

Every pure core (`render` / `rank_sources` / `detect_contradictions` / `score_hypotheses` /
`with_turn`/`append_turn` / `cite`) is separated from capability wiring so it is directly unit- and
property-testable under `FRIDAY_DRY_RUN=1`. All new modules carry a `"""Ch NN — ..."""` docstring,
contain no hardcoded app/site names or URLs (Axiom 15), and import only `friday.capabilities.*`,
`friday.verification.evidence_law`, `friday.actions.result`, and stdlib.

**Language:** Python 3.12. **Test command:** `python -m pytest tests/friday/ -q`.

## Tasks

- [x] 1. Domain data models — `friday/domains/models.py`
  - [x] 1.1 Create the domain data models and package skeleton
    - Add `friday/domains/models.py` with a `"""Ch 37/39/40/41 — ..."""` module docstring
    - Define research frozen models: `RankedSource` (`url`, `authority_class`, `credibility` clamped
      `[0,1]` in `__post_init__`), `Claim` (`subject`, `polarity`, `source_url`), `Contradiction`
      (`subject`, `positive_source`, `negative_source`), `HypothesisScore` (`hypothesis`, `support`
      clamped `[0,1]`, `supporting`, `total`), `ResearchFinding` (`query`, `sources_read`,
      `ranked_sources`, `hypotheses`, `contradictions`, `blocked`, `error`) with a `success` property
    - Define communication frozen models: `DeliveryStatus(str, Enum)`
      (`CONFIRMED`/`FAILED`/`UNAVAILABLE`), `Turn` (`speaker`, `text`, `logical_index`), `Conversation`
      (`turns`) with `with_turn(speaker, text) -> Conversation`, `DeliveryOutcome` (`recipient`,
      `status`, `capability_id`, `detail`) with a `confirmed` property
    - Define document frozen models: `DocumentFormat(str, Enum)`
      (`MARKDOWN`/`HTML`/`PLAINTEXT`/`DOCX`/`PDF`), `Citation` (`marker`, `source_url`), `Block`
      (`text`, `style`), `Section` (`heading`, `blocks`), `SemanticDocument` (`title`, `sections`,
      `citations`), `ExportOutcome` (`filename`, `fmt`, `bytes_written`, `success`, `error`)
    - Define `DeferredOutcome` (`domain`, `reason`, `would_compose`, `deferred=True`)
    - Create `friday/domains/__init__.py` with a `"""Ch 37 — domains as pure capability compositions"""`
      docstring (exports extended in task 6)
    - _Requirements: 1.4, 2.4, 3.1, 4.5, 5.1_

  - [x]* 1.2 Write unit tests for the domain data models
    - Assert all models are frozen/immutable, `credibility`/`support` clamp to `[0,1]`, tuple fields
      are tuples, and `Conversation.with_turn` returns a new value with a strictly-increasing
      `logical_index`
    - Set `os.environ.setdefault("FRIDAY_DRY_RUN", "1")` before importing any `friday` module
    - _Requirements: 1.4, 2.4, 3.1, 5.4_

- [x] 2. ResearchDomain — `friday/domains/research.py`
  - [x] 2.1 Implement ResearchDomain composition over `research(...)`
    - Create `friday/domains/research.py` with a `"""Ch 37 — ..."""` module docstring
    - Implement `__init__(registry, browser_controller=None)`, `investigate(query, evidence, *,
      hypotheses=(), max_sources=3) -> ResearchFinding`, `rank_sources(source_urls) ->
      Tuple[RankedSource, ...]`, `detect_contradictions(claims) -> Tuple[Contradiction, ...]`,
      `score_hypotheses(hypotheses, claims) -> Tuple[HypothesisScore, ...]`
    - `investigate` composes the existing `friday.capabilities.research.research(...)` for gathering
      (or degrades to a blocked/unavailable finding when no browser/capability); ranking uses an
      authority-*class* heuristic (host suffix class, never a literal site name); claim extraction is
      lightweight (subject + polarity); everything deterministic over inputs
    - Import only `friday.capabilities.*`, `friday.verification.evidence_law`, stdlib
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 5.2_

  - [x]* 2.2 Write property tests for research determinism, credibility, contradictions, hypotheses
    - **Property 3: Research findings are deterministic in gathered evidence**
    - **Property 4: Credibility scores are bounded and authority-ordered**
    - **Property 5: Contradiction detection is symmetric and subject-scoped**
    - **Property 6: Hypothesis support is a bounded ratio**
    - **Validates: Requirements 1.2, 1.3, 1.4**

- [x] 3. CommunicationDomain — `friday/domains/communication.py`
  - [x] 3.1 Implement environment-independent CommunicationDomain
    - Create `friday/domains/communication.py` with a `"""Ch 39 — ..."""` module docstring
    - Implement `__init__(registry)`, `async deliver(recipient, message, evidence, world=None) ->
      DeliveryOutcome`, `verify_delivery(evidence) -> bool`, `append_turn(transcript, speaker, text)
      -> Conversation`
    - `deliver` discovers the capability via `find_for("deliver")`, executes it, and returns
      `CONFIRMED` only when a real `DELIVERY_CONFIRMATION` artifact is present; `UNAVAILABLE` when no
      capability matches; `FAILED` when it ran but delivery is unconfirmed; never references any
      literal app/site name (Axiom 15)
    - Import only `friday.capabilities.*`, `friday.verification.evidence_law`,
      `friday.actions.result`, stdlib
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.2_

  - [x]* 3.2 Write property tests for delivery confirmation and conversation immutability
    - **Property 7: Delivery requires real confirmation evidence**
    - **Property 8: Conversation memory is immutable and append-only**
    - **Validates: Requirements 2.2, 2.3, 2.4**

- [x] 4. DocumentDomain — `friday/domains/documents.py`
  - [x] 4.1 Implement DocumentDomain semantic render + export + citations
    - Create `friday/domains/documents.py` with a `"""Ch 40 — ..."""` module docstring
    - Implement `__init__(registry)`, `render(document, fmt) -> str` (deterministic MARKDOWN/HTML/
      PLAINTEXT), `async export(document, filename, fmt, evidence, world=None) -> ExportOutcome`
      (renders then persists via a `find_for("create_file")` capability; records `FILE_ARTIFACT` +
      `GENERATED_CONTENT`; `UNAVAILABLE`/failed when none), `cite(document, evidence) ->
      SemanticDocument` (citations reference only `SOURCE_URL` artifacts present in evidence)
    - Import only `friday.capabilities.*`, `friday.verification.evidence_law`,
      `friday.actions.result`, stdlib
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.2_

  - [x]* 4.2 Write property tests for render round-trip and citation provenance
    - **Property 9: Document render round-trips structure**
    - **Property 10: Citations reference only real gathered sources**
    - **Validates: Requirements 3.1, 3.2, 3.3**

- [x] 5. SoftwareDomain — `friday/domains/software.py` (Ch 41 deferred v2 stub)
  - [x] 5.1 Implement the deferred SoftwareDomain stub
    - Create `friday/domains/software.py` with a `"""Ch 41 — ... DEFERRED to v2"""` module docstring
    - Implement `SoftwareDomain(registry)` with `DEFERRED = True` and `status() -> DeferredOutcome`
      documenting the v2 deferral and the abstract verbs a future SWE domain would compose (edit /
      run / test); no SWE behaviour
    - _Requirements: 4.5, 5.1_

- [x] 6. Package surface — `friday/domains/__init__.py`
  - [x] 6.1 Export the public domain + model surface
    - Extend `friday/domains/__init__.py` to export `ResearchDomain`, `CommunicationDomain`,
      `DocumentDomain`, `SoftwareDomain` and the public data models
    - Keep the module docstring `"""Ch 37 — ..."""`; no capability or durable state defined here
    - _Requirements: 4.3, 5.1_

- [x] 7. Tests — isolation, integration, gate
  - [x]* 7.1 Write the AST isolation / site-agnosticism test
    - Add `tests/friday/test_m10_isolation.py` mirroring `test_m9_isolation.py`: each domain module
      carries a `"""Ch NN — ..."""` docstring; imports only the allowed prefixes (no kernel/memory/
      goals/other-domain); no banned app/site name or URL scheme literal in code
    - **Property 11: Domains hardcode no application or site name**
    - **Validates: Requirements 4.4, 5.1, 5.2, 5.3**

  - [x]* 7.2 Write the integration test (research → document → dry-run deliver)
    - Add `tests/friday/test_m10_integration.py`: seed an in-memory `CapabilityRegistry` with stub
      `create_file` and `deliver` capabilities, gather stub evidence, build a cited `SemanticDocument`,
      export it, and assert the Evidence Law artifacts (`SOURCE_URL`/`FILE_ARTIFACT`/
      `DELIVERY_CONFIRMATION`) line up end-to-end
    - _Requirements: 1.1, 2.2, 3.2, 3.3_

  - [x]* 7.3 Write the M10 gate test (delete-a-domain leaves capabilities intact)
    - Add `tests/friday/test_m10_gate.py`: for each domain module, pop it from `sys.modules` and assert
      `CapabilityRegistry.capability_count` and `find_for(verb)` are unchanged and the remaining
      domains still import; assert no `CapabilityContract` subclass is defined inside `friday/domains/`
    - **Property 1: Domains own no durable state**
    - **Property 2: Deleting a domain leaves capabilities intact**
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [x] 8. Final regression checkpoint
  - [x] 8.1 Run the full suite and confirm green
    - Run `python -m pytest tests/friday/ -q`; confirm ≥ 1044 pre-existing tests plus the new M10
      tests pass under `FRIDAY_DRY_RUN=1`
    - _Requirements: 5.4_

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "3.1", "4.1", "5.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "4.2", "6.1"] },
    { "id": 3, "tasks": ["7.1", "7.2", "7.3"] },
    { "id": 4, "tasks": ["8.1"] }
  ]
}
```

## Notes

- Tasks marked with `*` (e.g. 1.2, 2.2, 3.2, 4.2, 7.1–7.3) are test tasks and may be executed
  alongside or immediately after their implementation task within the same wave.
- All work is additive under `friday/domains/`; no M1–M9 file is modified. Domains import only
  `friday.capabilities.*`, `friday.verification.evidence_law`, `friday.actions.result`, and stdlib.
- Every module carries a `"""Ch NN — ..."""` docstring and contains no hardcoded app/site name or URL
  scheme literal (Axiom 15).
- All tests set `os.environ.setdefault("FRIDAY_DRY_RUN", "1")` before importing any `friday` module so
  the existing suite (≥ 1044 tests) stays green.
- The defining M10 gate (task 7.3): deleting any domain module leaves every capability and every other
  domain intact — domains are pure composition leaves that own no durable state.
