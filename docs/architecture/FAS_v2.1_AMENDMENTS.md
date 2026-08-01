# FRIDAY Architecture Specification — v2.1 Amendments (Normative)

**Status:** Constitution amendment, pending review/approval. **No implementation in M13.**
**Relationship to FAS v2.0:** these sections ADD or EXPAND normative requirements on existing chapters.
Where a v2.0 chapter already defines a concept, the amendment marks it **[EXPAND]**; where it is new,
**[ADD]**. Every section cross-references the FAS chapter(s) it amends and the current code state
(built / partial / absent).

**Preserved invariants (unchanged and binding):** one Cognitive Kernel, one World Model, one Goal
Graph, one Competence Model; general mechanisms over task-specific logic; no application-specific
logic; no hardcoded workflows; no architectural shortcuts.

---

## A2.1 World Model — Belief Freshness, Provenance, Staleness  `[EXPAND Ch 9]`

**Code state:** partial — `friday/world/belief.py` has beliefs + confidence; freshness/provenance
mostly absent on the live path; M9 `temporal/aging.py` provides the decay precedent.

**Normative additions:**
- **Belief Freshness (§A2.1.1):** every belief SHALL carry a `freshness ∈ [0,1]`, a `ttl_seconds`, and
  an `observed_at`. Freshness decays as `0.5 ** (age / half_life)` (reuse the `KnowledgeAging`
  precedent). Planners SHALL prefer refreshing a belief over relying on a stale one when refresh cost
  is acceptable (Ch 9.22).
- **TTL & Refresh Policy (§A2.1.2):** each belief class SHALL declare a refresh policy
  (`on_read` / `on_stale` / `periodic` / `never`) and a `refresh_cost`. A belief past its TTL is
  `stale` and MUST NOT be treated as ground truth without a freshness check.
- **Belief Provenance (§A2.1.3):** every belief SHALL record an evidence graph — supporting
  observations, contradicting observations, the derivation chain, and verification status — so the
  World Model can explain *why* it believes something, not merely *what*.
- **Staleness Handling (§A2.1.4):** the World Model SHALL expose `stale_beliefs(now)` and SHALL flag
  stale, high-impact beliefs for refresh before they gate an irreversible action.

**Invariant:** reality always outranks a belief; a stale belief is downgraded, never silently trusted.

---

## A2.2 Environment Intelligence — Fingerprints & Capability Invalidation  `[ADD → Ch 23]`

**Code state:** absent on the live path; M9 mentions fingerprints conceptually.

**Normative additions:**
- **Environment Fingerprint (§A2.2.1):** each environment SHALL compute a fingerprint from
  {application version, window class, accessibility signature, DOM signature, visual hash, platform,
  capability version, layout version}.
- **UI Fingerprint (§A2.2.2):** interactive surfaces SHALL carry a UI fingerprint so a changed layout
  is detectable.
- **Capability Invalidation (§A2.2.3):** when an environment's fingerprint changes, learned
  assumptions and cached affordances for that environment SHALL be invalidated and re-explored (Ch 25),
  rather than silently reused.
- **Version-Aware Adaptation (§A2.2.4):** capabilities SHALL record the environment fingerprint they
  were validated against; a fingerprint mismatch lowers their confidence for that environment.

**Invariant:** a UI update makes FRIDAY re-explore, never silently wrong.

---

## A2.3 Deliberation — Expanded Utility & Recovery Contracts  `[EXPAND Ch 10 & Ch 34]`

**Code state:** partial — `friday/deliberation/` exists; utility is simpler than below; recovery
contracts absent.

**Normative additions:**
- **Expanded Utility Function (§A2.3.1):** action utility SHALL be computed from at least:
  `Expected Goal Progress + Information Gain + Future Optionality − Risk − Time − Resource Cost −
  Attention Cost − Irreversibility − Opportunity Cost`. No single term dominates; weights are policy.
- **Action Safety term (§A2.3.2):** utility SHALL include an explicit safety penalty for actions that
  touch protected/irreversible surfaces (integrates the Ch 35 permission boundary).
- **Recovery Contracts (§A2.3.3):** every action SHALL declare a recovery contract:
  `{undo, rollback, verification, compensation, recovery}`. Actions with no undo path (e.g. "send")
  MUST raise their required confidence and incur the full irreversibility penalty, and MAY require
  human confirmation (Ch 36).
- **Rollback Plans & Compensating Actions (§A2.3.4):** where a true undo is impossible, a compensating
  action SHALL be defined; the Recovery Engine (Ch 34) uses these to act automatically instead of
  asking every time.

**Invariant:** the less reversible an action, the higher the confidence (and possibly approval) required.

---

## A2.4 Capability System — Lifecycle & Statistical Competence  `[EXPAND Ch 16 & Ch 28]`

**Code state:** built — M11 `friday/evolution/lifecycle.py` implements the lifecycle;
`friday/competence/model.py` implements evidence-only competence. This section makes them normative FAS.

**Normative additions:**
- **Capability Lifecycle (§A2.4.1):** every capability SHALL occupy exactly one state of
  `Draft → Experimental → Verified → Stable → Deprecated → Archived`, with only legal transitions
  (+ sanctioned rollback). A capability below `Verified` MUST NOT perform an irreversible action.
- **Capability Profile (§A2.4.2):** every capability SHALL maintain
  {version, success_rate, reliability, average_runtime, dependencies, failure_modes, benchmark_history}.
- **Statistical Competence (§A2.4.3):** competence SHALL be computed empirically (Laplace-smoothed
  success statistics), decayed over time, and **never** self-reported by an LLM (Ch 28.20, the 4th law).
- **Promotion Gate (§A2.4.4):** promotion between lifecycle states SHALL require a passing benchmark
  and non-regressing competence (M11 `PromotionPipeline`).

---

## A2.5 Skill Evolution Pipeline  `[ADD → Ch 15/27]`

**Code state:** M17 — built. The `SkillStage` taxonomy
(`friday/learning/skill_stage.py`) makes the eight §A2.5.1 stages explicit and ordered;
the `SkillEvolutionPipeline` coordinator + reusable `attach_skill_pipeline` helper
(`friday/learning/skill_pipeline.py`) track each skill's stage over the events the
learning and reflection subsystems already emit. The M9 `learning.validated` /
`learning.rejected` payloads are additively enriched with `(capability, environment)`
identity in `friday/learning/engine.py`, the M9 `LearningEngine` is now attached in
`friday/kernel/reactive_loop.py::attach_reactive_loop` (the production `learning.validated`
producer), and the pipeline is bootstrapped in `friday/api/server.py`
(`kernel.skill_pipeline`, guarded by `FRIDAY_USE_KERNEL_EXECUTION`). Was **Partial** in the
v2.1 matrix.

**Normative pipeline (§A2.5.1):** a skill SHALL mature through:
`Observation → Experiment → Reflection → Verification → Compilation → Optimization → Generalization →
Capability Registry`. A skill that generalizes sufficiently becomes a candidate for formal promotion
through the Capability Lifecycle (§A2.4). Only verified experience feeds the pipeline (Ch 15.19).

- **§A2.5.2 Pure coordinator over existing mechanisms.** The pipeline SHALL be a CONSUMER
  of `learning.validated` (M9) and `reflection.skill` (M20) that tracks each skill's stage;
  it SHALL reuse the M9 learning and M11 evolution subsystems and introduce NO duplicate
  learning, promotion, or lifecycle system.
- **§A2.5.3 Dual-signal proposal.** WHEN a skill carries BOTH a validated generalization
  (`learning.validated`) AND a skill-layer candidate signal (`reflection.skill`) the
  pipeline SHALL emit exactly one deduplicated `skill.candidate` PROPOSAL offering the skill
  to the M11 evidence-gated `PromotionPipeline`; promotion remains that pipeline's decision.
- **§A2.5.4 Proposes, never promotes.** The pipeline SHALL NOT self-promote, SHALL NOT
  advance the capability lifecycle, SHALL NOT write memory, and SHALL NOT fabricate
  competence; its only side effect SHALL be emitting `skill.*` proposal events.
- **§A2.5.5 Verified-only maturation.** ONLY verified, evidence-backed signals SHALL advance
  a skill; a `learning.rejected` SHALL disqualify it (clears the generalized flag). Skills
  SHALL be keyed only by generic `(capability, environment)` — no application-specific logic
  (Axiom 15).
- **§A2.5.6 Bounded + safe + replay-compatible.** The per-skill store SHALL be bounded
  (oldest evicted), handlers SHALL never raise into the event bus, and every `skill.*`
  payload SHALL be JSON-serializable so the append-only `EventStore` stays replay-compatible.
  The pipeline is additive and inert without a kernel; the default (flag-off) path is
  byte-unchanged.

**Invariant:** the coordinator only tracks stage and proposes matured skills — verified
evidence alone advances a skill, and the M11 evidence-gated pipeline still decides promotion.

---

## A2.6 Resource Manager  `[EXPAND Ch 45-48]`

**Code state:** partial — M4 `friday/resources/` has registry + scheduler; a unified manager over the
full resource set is not formalized.

**Normative additions (§A2.6.1):** a single **Resource Manager** SHALL own allocation of
{CPU, GPU, memory, local-vs-cloud execution, model selection, parallel jobs, scheduling, priority,
latency, battery}. Every subsystem SHALL request resources from it rather than assuming availability
(the 7th law). It SHALL support dynamic reallocation (substitute/queue/degrade) when a resource fails,
and cost-aware selection (Ch 48 economics: energy/latency/financial/opportunity cost + user policies).

**Invariant:** resources are allocated, never assumed.

---

## A2.7 Retrieval Router  `[ADD → Ch 14.13]`

**Code state:** M19 — built. `friday/memory/retrieval_router.py`
(`RetrievalRouter`, `RetrievedItem`), constructed by the controller factory
`friday/memory/controller.py::build_retrieval_router`, with the FAILURE tier
participating via `friday/memory/failure_memory.py::FailureMemory.retrieve`, and
bootstrap wiring in `friday/api/server.py` (`kernel.retrieval_router`, guarded by
`FRIDAY_USE_KERNEL_EXECUTION`). Was **Absent** in the v2.1 matrix.

**Normative additions (§A2.7.1):** a **Retrieval Router** SHALL select the correct information source
per request BEFORE any search runs, routing among: World Model, Memory (episodic/semantic/procedural),
Filesystem index, RAG, external APIs, Capability Registry, and Connectors. Vector search is ONE
strategy, never the default for everything.

- **§A2.7.2 Uniform source contract.** Every registered source SHALL expose the single
  retrieval surface `retrieve(query, top_k) -> List[MemoryEntry]`; the router treats all
  sources identically through that contract, so tier selection is data (registration +
  filter), never per-source code branches (Axiom 15).
- **§A2.7.3 Cross-tier routing with optional filter.** A route SHALL query all registered
  sources by default, and MAY be constrained to an explicit tier filter; a filtered route
  SHALL NEVER return an item from a tier outside the filter.
- **§A2.7.4 Rank-based weighted merge.** Results SHALL be scored per source from result
  rank scaled by a per-source weight, then merged and sorted into a single non-increasing
  ranking capped at `top_k`; no source is the implicit default.
- **§A2.7.5 Provenance-carrying results.** Each merged result SHALL be a `RetrievedItem`
  carrying its originating tier/source and score, and SHALL be JSON-safe (`to_dict()`), so
  every result explains *where it came from*.
- **§A2.7.6 De-duplication.** Items referring to the same memory SHALL be de-duplicated by
  `entry_id` (else by `(tier, content)`), keeping the highest-ranked occurrence.
- **§A2.7.7 Failing-source isolation.** A source that raises SHALL be isolated at an
  observable degradation boundary — skipped without failing the route, while healthy
  sources still return — and `route` SHALL never raise. This boundary is the single
  justified broad catch and MUST NOT silently swallow (A2.14.2); degradation is observable,
  not hidden.

**Invariant:** the router picks the source before it searches, ranks all sources uniformly
with provenance, and degrades observably when a source fails — retrieval is a general
mechanism, never an ad hoc, vector-first default.

---

## A2.8 Exploration Engine  `[EXPAND Ch 25/66]`

**Code state:** built — M7 `friday/environments/unknown/` (object graph, affordances, safe
experiment, exploration). This section makes its guarantees normative.

**Normative additions (§A2.8.1):** unknown software SHALL be handled ONLY through
`Observation → Object-Graph construction → Affordance inference → Safe experimentation (risk ladder) →
Reflection → Capability generation` — **never** through application-specific logic (Axiom 15/Ch 63).
Exploration integrates with §A2.2 (fingerprint change → re-explore) and §A2.5 (successful exploration →
skill/candidate).

---

## A2.9 Statistical Evaluation / Competence Scoring  `[EXPAND Ch 28]`

**Code state:** built — M8/M11 competence model. Normative reinforcement:

**Normative additions (§A2.9.1):** every capability SHALL continuously measure
{success_rate, failure_rate, average_latency, recovery_success, confidence_calibration,
benchmark_history}. **Confidence SHALL be derived from empirical evidence, never asserted by an LLM.**
FRIDAY reports competence by aggregating Competence Records, not by guessing (Ch 28.24).

---

## A2.10 Reflection — Layered  `[EXPAND Ch 13]`

**Code state:** M20 — built. The five-layer `ReflectionLayer` taxonomy
(`friday/cognition/reflection.py`) formalizes the hierarchy additively over the existing
M8 engine; the three higher consumer layers `LongTermReflector` / `SkillReflector` /
`ArchitecturalReflector` live in `friday/cognition/reflection_layers.py`, are wired by the
reusable `attach_reflection_layers` helper, and are bootstrapped in
`friday/api/server.py` (`kernel.reflection_layers`, guarded by
`FRIDAY_USE_KERNEL_EXECUTION`). Was **Partial** in the v2.1 matrix.

**Normative layers (§A2.10.1):** Reflection SHALL operate at five layers:
`Immediate` (per action) → `Session` (per goal/session) → `Long-Term` (across sessions) →
`Skill` (per capability, feeds §A2.5) → `Architectural` (evaluates whether the architecture itself
still serves the user, proposes structural change). Reflection PROPOSES; Memory DECIDES (Ch 14.8);
reflection never writes memory directly.

- **§A2.10.2 Lowest two layers reuse the engine.** `IMMEDIATE` and `SESSION` SHALL map to
  the existing `ReflectionEngine`'s per-action and per-goal/session reflection unchanged
  (micro→IMMEDIATE, task/goal/session→SESSION); no second reflection system is introduced
  and the engine's `memory.candidate` / `reflection.completed` outputs are byte-unchanged.
- **§A2.10.3 Higher three layers are pure consumers.** `Long-Term`, `Skill`, and
  `Architectural` SHALL be CONSUMERS of the `reflection.completed` stream that build bounded
  aggregates and emit JSON-safe proposal events — `reflection.longterm` (cross-session
  prediction-error/calibration trend), `reflection.skill` (per-capability candidate
  feeding the §A2.5 skill pipeline), and a single deduplicated advisory
  `reflection.architectural` (cross-capability meta-signal) — never a memory write.
- **§A2.10.4 Bounded + safe.** Every layer's aggregates SHALL be bounded (oldest samples
  evicted) and its handlers SHALL never raise into the event bus (malformed events
  ignored). The layers are additive and inert without a kernel; the default (flag-off)
  path is byte-unchanged and hermetic runs perform no unbidden I/O.
- **§A2.10.5 Proposes-not-decides across all five layers.** NO layer SHALL import
  `friday.memory.*` / `friday.competence.*` / `friday.recovery.*` or write long-term
  memory; every layer's only side effects SHALL be emitting `memory.candidate` and/or
  structured `reflection.*` proposal events (Ch 14.8), and each `reflection.*` payload
  SHALL be JSON-serializable so the append-only `EventStore` stays replay-compatible.

**Invariant:** reflection operates at every scope from a single action to the whole
architecture, yet at every layer it only proposes — memory and the skill pipeline decide.

---

## A2.11 Memory — Seven Tiers  `[EXPAND Ch 14/50]`

**Code state:** M21 (slice 2) — built. All seven FAS §A2.11.1 tiers now exist on the live
path: Working/Episodic/Semantic/Procedural (M8), Failure (M21 slice 1,
`friday/memory/failure_memory.py`), and now Capability
(`friday/memory/capability_memory.py::CapabilityMemory`) + Preference
(`friday/memory/preference_memory.py::PreferenceMemory`). All uniform-`retrieve` sources are
registered in `friday/memory/controller.py::build_retrieval_router` (under
`MemoryTier.CAPABILITY` / `MemoryTier.PREFERENCE`) and wired opt-in via
`friday/kernel/reactive_loop.py::attach_reactive_loop` and the guarded
`friday/api/server.py` bootstrap (`FRIDAY_USE_KERNEL_EXECUTION`). Was **Partial** in the v2.1
matrix. This completes the seven-tier model and the Architecture v2.1 build-out.

**Normative tiers (§A2.11.1):** Memory SHALL comprise seven tiers:
`Working, Episodic, Semantic, Procedural, Capability, Failure, Preference`. Each tier has distinct
formation/retention/forgetting rules. Memory forms ONLY via Reflection (Ch 14.8), carries confidence,
supports forgetting and contradiction resolution, and NEVER overrides observed reality. **Failure
Memory** is first-class: mistakes are remembered as sharply as successes.

- **§A2.11.2 Capability tier is a memory VIEW, not an authority.** `MemoryTier.CAPABILITY`
  SHALL be a queryable memory formed from `competence.updated` events, upserting by
  `(capability, environment)`. It records only what the event reported; it SHALL NOT
  recompute competence, SHALL NOT override the `CompetenceModel` (Ch 28, the sole competence
  authority), and SHALL import no `friday.competence` — deferring to that authority entirely.
- **§A2.11.3 Preference tier is upsert-by-key.** `MemoryTier.PREFERENCE` SHALL be a
  persistent, queryable memory of user preferences as `(key, value)` records (with optional
  description), upserting by `key` so a newer value supersedes the older, distinct from
  volatile working-memory context.
- **§A2.11.4 Reuse, bounded, defensive, routed.** Both tiers SHALL reuse the existing
  `JSONFileStore` / `MemoryEntry` contracts (no duplicate persistence), keep bounded storage
  (oldest evicted), use defensive event handlers that never raise into the bus, and
  participate in the M19 Retrieval Router via the uniform `retrieve(query, top_k)` surface.

**Invariant:** the seven-tier model is complete — Capability remembers what the competence
authority reported without ever becoming that authority, Preference remembers durable
user choices, and every tier reuses one bounded, defensive persistence mechanism routed
uniformly.

---

## A2.12 Cognitive State Manager  `[ADD → Ch 67]`

**Code state:** M22 — built. The completed
`friday/cognition/state.py::CognitiveStateManager` now models the full Ch 67
mind-state: the additive `cognitive_load` + `background_active` elements complete
the mental-state model, engagement-mode coverage (idle / exploration / execution /
conversation) is driven entirely from generic bus events, and a pure query surface
(`should_interrupt` / `suggested_thinking_depth`) lets any subsystem consult the
state. It is attached and exposed as `kernel.cognitive_state` in
`friday/api/server.py` (guarded by `FRIDAY_USE_KERNEL_EXECUTION`). Was **Partial**
in the v2.1 matrix. This closes the Architecture v2.1 build-out.

**Normative additions (§A2.12.1):** a single **Cognitive State Manager** SHALL represent FRIDAY's own
mental state (distinct from the World Model's model of reality), maintaining:
{Current Focus, Active Goal, Attention allocation, Interruptibility, Cognitive Load, Reasoning Depth,
Exploration mode, Execution mode, Conversation mode, Background cognition state}. It COORDINATES
cognition; it stores no domain knowledge. Every other subsystem MAY query it (e.g. the Event System to
decide whether to surface an interruption now; Deliberation to size reasoning depth to the moment).

- **§A2.12.2 Complete mind-state.** The state SHALL additionally carry **Cognitive
  Load** (`cognitive_load ∈ [0, 1]`, always clamped — rises with committed
  attention / active work, decays toward idle) and a **Background cognition state**
  (`background_active`) indicating whether non-foreground cognition (e.g. reflection
  while idle) is running. The snapshot SHALL remain an immutable copy and be
  JSON-projectable (`to_dict`) for events/logging; the additions are additive over
  the existing fields.
- **§A2.12.3 Mode coverage from generic events.** Engagement mode SHALL be driven
  purely from generic event types already present on the bus: `action.executed` →
  `EXECUTION` (preserved); `observation.received` → `EXPLORATION`; `goal.created` →
  `CONVERSATION`; a terminal goal state (`completed`/`failed`/`abandoned`) with
  nothing else active → `IDLE` (focus cleared, load lowered); `reflection.completed`
  while IDLE → `background_active`. No literal `exploration.*` / `conversation.*`
  event type is invented — the closest real generic signal is used (Axiom 15).
- **§A2.12.4 Pure coordination queries.** `should_interrupt(urgency)` SHALL honor
  `interruptible` and, when not interruptible, surface an interruption only above a
  load-scaled urgency threshold (higher load ⇒ higher bar); `suggested_thinking_depth()`
  SHALL derive a reasoning depth from budget / load (SHALLOW under low budget / high
  load, DEEP under ample budget / low load, else NORMAL). Both SHALL be pure,
  deterministic reads that never mutate state, consumable by the Event System /
  Deliberation.
- **§A2.12.5 Isolation preserved.** The manager SHALL import ONLY `friday.events` +
  stdlib (never goals/world/deliberation/memory), SHALL be updated purely from the
  kernel event stream, and its handlers SHALL never raise into the tick loop. It
  SHALL introduce NO duplicate mind-state store — it remains the model of FRIDAY's
  own mind, distinct from the World Model's model of reality — and SHALL be inert
  without a kernel (default flag-off path byte-unchanged).

**Invariant:** FRIDAY knows what it is doing, not merely what it is doing it for —
one mind-state authority, updated purely from events, queryable by every subsystem.

---

## Cross-Cutting Compliance

All amendments preserve: kernel-mediated communication (Ch 52 — subsystems talk only via events); one
authoritative instance of Kernel/World Model/Goal Graph/Competence Model; evidence over assertion
(Axiom 5 / the 4th law); generality over specialization (Axiom 15). No amendment introduces
application-specific logic or a hardcoded workflow.


---

## A2.13 Web Environment Runtime — Browser as a Generic Desktop Environment  `[EXPAND Ch 23/29/30]`

**Code state:** M23 — primary path built. Universal perception fusion
(`friday/perception/active_window.py`), generic controller
(`friday/actions/desktop_browser.py::DesktopBrowserController`), desktop-first
strategy (`friday/actions/browser_strategy.py`), CDP gated by `FRIDAY_ENABLE_CDP`.

**Rename (normative):** the environment class formerly called the **Browser
Runtime** is renamed the **Web Environment Runtime** — a web browser is one member
of the general set of desktop environments, not a special case.

**Normative additions:**
- **§A2.13.1 Browser is a desktop application.** FRIDAY SHALL operate Chrome, Edge,
  Firefox, Brave, Arc, Electron apps, and future browsers through the SAME general
  desktop-cognition pipeline used for every desktop application: perceive (Ch 12) →
  reason over World Objects → act via the Motor System (Ch 31) → verify by World-Model
  change (Ch 32). No application-, browser-, site-, or window-title-specific logic
  (Axiom 15 / Ch 63).
- **§A2.13.2 Optional optimization interfaces.** Browser-specific automation (CDP,
  Playwright, Selenium, DevTools Protocol, extensions) is an OPTIONAL optimization
  resource, never an architectural dependency. The desktop pipeline SHALL remain
  fully functional and equally correct with these disabled. CDP acceleration is
  enabled only via `FRIDAY_ENABLE_CDP`; the same switch is the rollback control.
- **§A2.13.3 Browser independence.** For any browser goal, the correctness outcome
  (verified success + evidence kinds) SHALL be identical whether the CDP optimization
  is enabled or disabled; only measured performance may differ.
- **§A2.13.4 Universal perception.** Every task SHALL build a complete WorldState for
  the active window by fusing the ranked perception stack (Accessibility/UIA → native
  semantic → OCR → Computer Vision → raw pixels). The planner/deliberator/executor
  reason only over World Objects and never depend on which source produced an
  observation.
- **§A2.13.5 Least-invasive motor.** The Motor System SHALL prefer the least-invasive
  reliable interaction: Keyboard → Accessibility Actions → Mouse → Pixel fallback.
- **§A2.13.6 Verified success.** Success SHALL be established only by an observed change
  in the World Model, never inferred from having dispatched an input.

**Invariant:** browsers are merely one class of environments FRIDAY already operates;
optimizing for arbitrary desktop environments subsumes optimizing for any browser.

---

## A2.14 Structured Failure & Recovery Activation  `[EXPAND Ch 21/34/52]`

**Code state:** M24 — built. Structured failure model
(`friday/verification/failure.py`), verification-event producer
(`friday/verification/publisher.py`), observability subscriber
(`friday/observability/failure_log.py`), additive Operator wiring
(`friday/operator.py::Operator(kernel=...)`).

**Root-cause finding (why this amendment exists):** the recovery, competence, and
reflection subsystems all *subscribe* to the `verification.completed` kernel event, but
no subsystem *published* it — so the entire failure → recovery / competence / reflection
loop was **dormant** in production. A2.14 makes publication of verification verdicts a
normative kernel responsibility, activating the loop.

**Normative additions:**
- **§A2.14.1 Failures are first-class objects.** A failure SHALL be representable as a
  structured object carrying its **domain** (the stage it arose in — perception,
  resource, environment, capability, verification, planning, execution, external
  service), **severity**, **confidence**, **recoverability**, **recommended recovery
  path**, and **evidence provenance**. The failure *domain* (where) is orthogonal to and
  MUST NOT replace the recovery `FailureClass` (how recoverable) or `RecoveryLevel`
  ladder (Ch 34) — both dimensions are retained.
- **§A2.14.2 Structured error model.** New code SHALL NOT silently swallow exceptions
  (`except Exception: pass`). Free-form `ActionResult.error_category` strings SHALL be
  classifiable to a canonical `FailureDomain` by a total, pure, data-driven classifier
  (generic tokens only — no application identity, Axiom 15), without requiring producers
  to be rewritten.
- **§A2.14.3 Verdict publication (loop activation).** When a kernel is present, each
  requirement verdict SHALL be published as a `verification.completed` event in the
  payload shape the recovery/competence/reflection subscribers consume, so those
  subsystems react. The producer SHALL be additive and inert without a kernel (no default
  change; rollback = do not inject a kernel) and SHALL never raise into the verdict path.
- **§A2.14.4 Replay-safe events.** Event payloads SHALL remain JSON-serializable so the
  append-only `EventStore` stays replay-compatible; a live evidence bundle SHALL be
  represented by a JSON-safe summary in the payload, not the object itself.
- **§A2.14.5 Observability as an event consumer.** Logging SHALL be a consumer of the
  event system: a subscriber turns failure/recovery events into structured log records
  (level from severity; subsystem id, goal id, correlation id, logical time, and failure
  domain as structured fields) rather than ad hoc prints. Observers SHALL never raise
  into the event bus.

**Invariant:** every failure is observable, classified, and actionable; success and
recovery are driven by evidence and events, never by silent assumption.

---

## A2.11(f) Failure Memory  `[EXPAND Ch 14/50]`

**Code state:** M21 (slice 1) — built. `friday/memory/failure_memory.py::FailureMemory`
(the seventh memory tier), attached via `friday/kernel/reactive_loop.py` and the API
bootstrap. Was **Absent** in the v2.1 matrix.

**Normative additions:**
- **§A2.11f.1 Failure memory is a tier.** FRIDAY SHALL maintain a persistent, queryable
  memory of failures (`MemoryTier.FAILURE`), each carrying requirement, failure domain,
  category, capability, environment, goal, severity, recoverability, and the recovery that
  was proposed (class + whether actionable).
- **§A2.11f.2 It consumes the failure loop.** Failure memory SHALL be a CONSUMER of the
  M24 loop — subscribing to `verification.completed` (record) and `recovery.proposed`
  (annotate) — reusing the `StructuredFailure` model and the kernel event bus, never a
  duplicate failure taxonomy or persistence mechanism.
- **§A2.11f.3 Bounded + safe.** Persistence SHALL be bounded (oldest evicted) and handlers
  SHALL never raise into the event bus. Failure memory is additive: attached only when
  supplied to the reactive loop, so hermetic runs perform no disk writes.
- **§A2.11f.4 Informs planning.** Planning/deliberation SHALL be able to ask
  `has_failed_before(...)` and recall prior failures so known failures are not silently
  repeated.

**Invariant:** failures are remembered with their causes and attempted recoveries, so
experience accrues rather than evaporating.


---

## A2.15 Learned Choice & Preference Resolution  `[ADD → Ch 10/14/36]`

**Code state:** M25 — built. `friday/deliberation/decision_point.py`
(`DecisionPoint`) and `friday/deliberation/preference_resolver.py`
(`PreferenceResolver` + `compute_preference_confidence` +
`contains_secret_material` + `attach_preference_resolver`), wired as
`kernel.preference_resolver` in the guarded bootstrap. Was **planned**; this is
the first post-v2.1 milestone.

**Normative additions:**

- **§A2.15.1 DecisionPoint as a first-class concept.** FRIDAY SHALL represent a recurring
  choice as a `DecisionPoint` — a structured object carrying the decision identity, context
  (goal, environment, available options), risk, reversibility, confidence, and any candidate
  preferences from memory. A `DecisionPoint` is NOT tied to dialogs/popups — it may arise
  from any state where multiple plausible actions exist and the correct choice depends on
  user preference or information FRIDAY does not possess. No application-specific detection
  logic (Axiom 15).

- **§A2.15.2 Preference Resolution Pipeline.** On encountering a `DecisionPoint`, FRIDAY
  SHALL execute a resolution pipeline:
  `Detect → Understand semantics → Determine context → Query Preference Memory + Retrieval
  Router → Evaluate contextual similarity + confidence + freshness → If confident & safe:
  apply automatically | Else if safely inferable: infer & verify | Else: ask user → Execute
  → Verify → Determine reusability → Store/update preference if appropriate`.
  The pipeline integrates with the existing Retrieval Router and Preference Memory rather
  than creating another isolated store.

- **§A2.15.3 Contextual scoping + precedence.** Preferences SHALL be contextually scoped
  (goal, environment, task category, object semantics) — never blindly reused across
  dissimilar contexts. Precedence SHALL be:
  `Explicit current instruction > Current-session choice > Exact contextual preference >
  Strong generalized preference > Safe inference > Ask user`.
  An explicit instruction always overrides memory.

- **§A2.15.4 Preference lifecycle (learn, apply, correct, supersede).** Preferences SHALL
  be learnable from explicit user statements, repeated selections, and corrections.
  Corrections SHALL refine contextual boundaries (not destroy history). Preferences have
  classes: one-time, session, contextual, general-default, sensitive/credential-reference.
  Confidence SHALL be empirical (evidence-derived: explicit statement, reuse count,
  corrections, recency, contradictions — never LLM-asserted).

- **§A2.15.5 Reversibility gates asking.** Low-risk, reversible, cheap-to-test decisions
  MAY be tried autonomously at high confidence and verified; irreversible, consequential, or
  security-sensitive decisions SHALL require much higher confidence or explicit confirmation.
  This integrates with the Deliberation utility's irreversibility/safety penalties (§A2.3)
  and the Cognitive State Manager's `should_interrupt` (§A2.12).

- **§A2.15.6 Credential separation.** Preference memory MAY store identity references
  (e.g. `preferred_identity: personal_google`); secret material (passwords, tokens, keys)
  SHALL remain exclusively in the secure credential subsystem and SHALL NEVER be placed in
  ordinary memory, logs, or events. This is a hard security boundary.

- **§A2.15.7 Explainability + provenance.** FRIDAY SHALL be able to explain why it made an
  automatic choice, citing: preference source, when learned, context, confidence, reuse
  count, corrections, and last verification. Provenance is carried end-to-end.

- **§A2.15.8 Event-driven + replay-safe.** Decision/preference lifecycle events
  (`decision.required`, `decision.resolved`, `preference.learned`, `preference.applied`,
  `preference.corrected`, `preference.superseded`) SHALL be JSON-serializable and published
  on the kernel bus so the event store remains replay-compatible and observability consumers
  can react.

- **§A2.15.9 General mechanism (Axiom 15).** The entire capability SHALL be generic —
  keyed by decision semantics and context, never by application/site/dialog identity. It
  works for arbitrary recurring choices (profiles, download paths, default apps, accounts,
  devices, templates, permissions, etc.) without per-application logic.

**Invariant:** ask when necessary; learn when appropriate; reuse when confident and safe;
override instantly when the user says otherwise; never confuse a learned preference with
permission to take a consequential action; never store secrets in preference memory.
