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

**Code state:** partial — M9 learning + M11 evolution provide pieces; the unified pipeline is not
formalized.

**Normative pipeline (§A2.5.1):** a skill SHALL mature through:
`Observation → Experiment → Reflection → Verification → Compilation → Optimization → Generalization →
Capability Registry`. A skill that generalizes sufficiently becomes a candidate for formal promotion
through the Capability Lifecycle (§A2.4). Only verified experience feeds the pipeline (Ch 15.19).

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

**Code state:** absent as a distinct layer — retrieval is ad hoc.

**Normative additions (§A2.7.1):** a **Retrieval Router** SHALL select the correct information source
per request BEFORE any search runs, routing among: World Model, Memory (episodic/semantic/procedural),
Filesystem index, RAG, external APIs, Capability Registry, and Connectors. Vector search is ONE
strategy, never the default for everything.

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

**Code state:** partial — M8 reflection engine exists; the layer hierarchy is not fully formalized.

**Normative layers (§A2.10.1):** Reflection SHALL operate at five layers:
`Immediate` (per action) → `Session` (per goal/session) → `Long-Term` (across sessions) →
`Skill` (per capability, feeds §A2.5) → `Architectural` (evaluates whether the architecture itself
still serves the user, proposes structural change). Reflection PROPOSES; Memory DECIDES (Ch 14.8);
reflection never writes memory directly.

---

## A2.11 Memory — Seven Tiers  `[EXPAND Ch 14/50]`

**Code state:** partial — M8 built Working/Episodic/Semantic/Procedural; Capability/Failure/Preference
tiers are not all formalized on the live path.

**Normative tiers (§A2.11.1):** Memory SHALL comprise seven tiers:
`Working, Episodic, Semantic, Procedural, Capability, Failure, Preference`. Each tier has distinct
formation/retention/forgetting rules. Memory forms ONLY via Reflection (Ch 14.8), carries confidence,
supports forgetting and contradiction resolution, and NEVER overrides observed reality. **Failure
Memory** is first-class: mistakes are remembered as sharply as successes.

---

## A2.12 Cognitive State Manager  `[ADD → Ch 67]`

**Code state:** partial — M4 `friday/cognition/state.py` exists (CognitiveMode/ThinkingDepth); the full
mental-state model per Ch 67 is not complete on the live path.

**Normative additions (§A2.12.1):** a single **Cognitive State Manager** SHALL represent FRIDAY's own
mental state (distinct from the World Model's model of reality), maintaining:
{Current Focus, Active Goal, Attention allocation, Interruptibility, Cognitive Load, Reasoning Depth,
Exploration mode, Execution mode, Conversation mode, Background cognition state}. It COORDINATES
cognition; it stores no domain knowledge. Every other subsystem MAY query it (e.g. the Event System to
decide whether to surface an interruption now; Deliberation to size reasoning depth to the moment).

**Invariant:** FRIDAY knows what it is doing, not merely what it is doing it for.

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
