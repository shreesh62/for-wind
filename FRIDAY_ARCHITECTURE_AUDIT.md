# FRIDAY Architecture Audit & Compliance Report

**Author:** Lead Software Architect / Principal Engineer (acting)
**Reference:** FRIDAY Architecture Specification (FAS) v2.0 — treated as Constitution
**Subject:** `c:\Projects\JARVIS\for wind\` (the `friday/` package + legacy JARVIS)
**Method:** Forensic code inspection cross-referenced against all 67 chapters of the FAS
**Status:** AUDIT ONLY — no implementation. Awaiting explicit approval before any code.

---

## 0. The One Sentence You Need First

> The specification describes a **persistent, event-driven Cognitive Operating System** built around a Kernel, World Model, Goal Graph, and continuous cognition. The current implementation is a **stateless, request-driven, linear pipeline** (`Goal → Requirements → Plan → Execute → Verify → Repair`) that terminates after each request.

This is the single most important finding in this document. Every subsystem-level gap below is a symptom of this root mismatch. We are not "60% done." We have built a competent **prototype of one slice** (the deliberation→operation→verification loop for simple goals) on top of an architecture that the Constitution explicitly rejects (Chapters 6, 17, 20, 21).

**This is not a criticism of the work done.** The existing code is clean, typed, documented, and the Evidence Law (Ch 5/9/32) is genuinely well-implemented. But measured against the FAS, the foundation must be laid before the existing pieces can become more than a prototype.

---

## 1. Overall Compliance Scorecard

Compliance = (architectural intent satisfied) × (correctly implemented) × (not violated). It is NOT "does code exist."

| # | Subsystem (FAS Chapter) | Exists? | Correct? | Violates? | Compliance | Risk | Priority |
|---|--------------------------|---------|----------|-----------|-----------|------|----------|
| 1 | Cognitive Kernel (Ch 20) | ❌ NO | — | YES (absent) | **0%** | CRITICAL | P0 |
| 2 | Persistent Cognitive Runtime (Ch 17) | ❌ NO | — | YES | **0%** | CRITICAL | P0 |
| 3 | Cognitive Event System (Ch 21) | ❌ NO | — | YES | **0%** | CRITICAL | P0 |
| 4 | World Model (Ch 9) | ⚠️ PARTIAL | NO | YES | **20%** | CRITICAL | P0 |
| 5 | Goal Lifecycle (Ch 18) | ⚠️ PARTIAL | NO | YES | **15%** | HIGH | P1 |
| 6 | Goal Graph (Ch 19) | ❌ NO | — | YES | **0%** | HIGH | P1 |
| 7 | Three Cognitive Layers (Ch 6) | ⚠️ PARTIAL | NO | YES | **30%** | HIGH | P1 |
| 8 | Intent Analysis Engine (Ch 7) | ⚠️ PARTIAL | NO | NO | **35%** | MEDIUM | P2 |
| 9 | Problem Classification (Ch 8) | ❌ NO | — | NO | **5%** | MEDIUM | P2 |
| 10 | Deliberation (Ch 10) | ⚠️ PARTIAL | NO | YES | **25%** | HIGH | P1 |
| 11 | Operation (Ch 11) | ✅ PARTIAL | YES | YES | **65%** | MEDIUM | P2 |
| 12 | Perception (Ch 12) | ⚠️ PARTIAL | NO | YES | **30%** | HIGH | P1 |
| 13 | Reflection (Ch 13) | ✅ PARTIAL | YES | YES | **60%** | HIGH | P1 |
| 14 | Memory (Ch 14) | ✅ PARTIAL | YES | YES (wired) | **60%** | HIGH | P1 |
| 15 | Learning (Ch 15) | ✅ PARTIAL | YES | YES | **60%** | MEDIUM | P2 |
| 16 | Capabilities (Ch 16) | ✅ PARTIAL | YES | YES | **60%** | HIGH | P1 |
| 17 | Decision Architecture (Ch 22) | ⚠️ PARTIAL | NO | YES | **20%** | HIGH | P1 |
| 18 | Environment Architecture (Ch 23) | ✅ PARTIAL | YES | YES | **70%** | HIGH | P1 |
| 19 | Interaction Architecture (Ch 24) | ⚠️ PARTIAL | PARTIAL | NO | **45%** | MEDIUM | P2 |
| 20 | Unknown Environment Exploration (Ch 25/66) | ✅ PARTIAL | YES | YES | **60%** | HIGH | P1 |
| 21 | Procedure Synthesis (Ch 26) | ⚠️ PARTIAL | NO | YES | **30%** | MEDIUM | P2 |
| 22 | Capability Evolution (Ch 27) | ❌ NO | — | NO | **0%** | LOW | P3 |
| 23 | Competence Model (Ch 28) | ✅ PARTIAL | YES | YES | **60%** | MEDIUM | P2 |
| 24 | Browser Runtime (Ch 29) | ✅ PARTIAL | YES | YES | **65%** | MEDIUM | P2 |
| 25 | Desktop Runtime (Ch 30) | ✅ PARTIAL | YES | YES | **60%** | HIGH | P1 |
| 26 | Motor System (Ch 31) | ✅ PARTIAL | YES | YES | **60%** | MEDIUM | P2 |
| 27 | Verification Engine (Ch 32) | ✅ PARTIAL | YES | YES | **70%** | LOW | P2 |
| 28 | Evidence System (Ch 33) | ✅ PARTIAL | YES | YES | **65%** | LOW | P2 |
| 29 | Recovery Engine (Ch 34) | ✅ PARTIAL | YES | YES | **60%** | MEDIUM | P2 |
| 30 | Safety & Permission (Ch 35) | ⚠️ PARTIAL | NO | YES | **20%** | HIGH | P1 |
| 31 | Human Collaboration (Ch 36) | ⚠️ PARTIAL | NO | NO | **20%** | MEDIUM | P2 |
| 32 | Research Domain (Ch 37) | ✅ PARTIAL | PARTIAL | NO | **45%** | LOW | P2 |
| 33 | Knowledge Acquisition (Ch 38) | ❌ NO | — | NO | **5%** | LOW | P3 |
| 34 | Communication Domain (Ch 39) | ⚠️ PARTIAL | NO | YES | **25%** | MEDIUM | P2 |
| 35 | Document Intelligence (Ch 40) | ⚠️ PARTIAL | NO | NO | **20%** | LOW | P3 |
| 36 | Software Engineering Domain (Ch 41) | ❌ NO | — | NO | **0%** | LOW | P3 |
| 37 | Long-Horizon Planning (Ch 42) | ✅ PARTIAL | YES | YES | **60%** | MEDIUM | P2 |
| 38 | Background Cognition (Ch 43) | ✅ PARTIAL | YES | YES | **60%** | MEDIUM | P2 |
| 39 | Self-Improvement (Ch 44) | ❌ NO | — | NO | **0%** | LOW | P3 |
| 40 | Resource Model (Ch 45-48) | ❌ NO | — | YES | **0%** | MEDIUM | P2 |
| 41 | Temporal Reasoning (Ch 49) | ✅ PARTIAL | YES | YES | **60%** | MEDIUM | P2 |
| 42 | Memory Architecture / 4-tier (Ch 50) | ⚠️ PARTIAL | PARTIAL | YES (orphaned) | **35%** | MEDIUM | P2 |
| 43 | Cognitive Identity (Ch 51) | ❌ NO | — | YES | **0%** | MEDIUM | P2 |
| 44 | Runtime Communication (Ch 52) | ❌ NO | — | YES | **5%** | HIGH | P1 |
| 45 | Runtime Composition / Replaceability (Ch 53) | ⚠️ PARTIAL | NO | YES | **30%** | MEDIUM | P2 |
| 46 | Plugin Architecture (Ch 54) | ❌ NO | — | NO | **0%** | LOW | P3 |
| 47 | Benchmark Architecture (Ch 55) | ❌ NO | — | NO | **0%** | MEDIUM | P2 |
| 48 | Testing Philosophy (Ch 56) | ⚠️ PARTIAL | NO | YES | **25%** | HIGH | P1 |
| 49 | Deployment Architecture (Ch 57) | ⚠️ PARTIAL | NO | NO | **15%** | LOW | P3 |
| 50 | Operational Arch / Observability (Ch 58) | ⚠️ PARTIAL | NO | NO | **15%** | MEDIUM | P2 |

### Weighted Overall Architecture Compliance

```
Foundational subsystems (Kernel, PCR, Events, World Model, Goal Graph):   ~7%
Cognitive subsystems (Deliberation, Reflection, Learning, Competence):    ~12%
Execution subsystems (Operation, Browser, Desktop, Motor, Verification):  ~42%
Domain subsystems (Research, Comms, Documents, SWE):                      ~22%
Cross-cutting (Safety, Resources, Temporal, Identity, Testing):           ~10%

═══════════════════════════════════════════════════════════════════════
OVERALL FAS v2.0 COMPLIANCE:  ~18%
═══════════════════════════════════════════════════════════════════════
```

Note the symmetry with the functional audit (`CURRENT_PROJECT_STATE.md` = 18% functional). This is not a coincidence: **the functional ceiling is capped by the architectural foundation.** You cannot reliably do communication/desktop/multi-app work without the Kernel, World Model, Event System, and Resource Model that those tasks structurally require.

---

## 2. PHASE 1 — Detailed Subsystem Audit

Each entry: spec reference → what the code actually does → problems → architecture-compliance verdict → recommendation.

### 2.1 Cognitive Kernel — Chapter 20

- **Status:** ❌ DOES NOT EXIST
- **Specification:** A minimal, permanent runtime owning exactly six things: Runtime Clock, Event Bus, World Model, Goal Graph, Scheduler, Capability Registry. Everything else is a replaceable plug-in. Exactly one Kernel; one authoritative World Model; every event passes through it.
- **Implementation reality:** There is no kernel. Control flow originates in `friday/bridge.py` → `Operator.run()` (`operator.py`), which directly constructs `RequirementsDiscovery`, `OperatorPlanner`, `GoalExecutor`, `EnvironmentObserver`. Subsystems call each other directly (Operator → Executor → research/web_agent/browser). There is no central authority, no clock, no scheduler, no registry-as-authority.
- **Problems:**
  - No single owner of global cognitive state (Invariant 1/2 of Ch 20 violated).
  - Subsystems are directly coupled (violates Ch 52 entirely).
  - No checkpoint/restore → no continuity (violates Ch 17, 51).
  - `build_default_registry()` exists but is consulted only for planning metadata, never owned/enforced.
- **Compliance:** **0%**
- **Recommendation:** BUILD FIRST. Nothing else in the FAS can be correct without it. This is the keystone (Milestone 1).

### 2.2 Persistent Cognitive Runtime — Chapter 17

- **Status:** ❌ DOES NOT EXIST
- **Specification:** A continuously executing substrate. States include Observing/Thinking/Operating/Reflecting/Idle-Observation. "There is no Stopped, only Shutdown." Survives restarts. Idle is productive. Long-running tasks survive user disconnection.
- **Implementation reality:** Request-driven. `operator.run(goal)` executes synchronously and returns an `OperatorOutcome`, then the process is idle/dead. There is no loop, no tick, no background cognition, no persistence of in-flight work. `main.py` (legacy) has a forever loop but it is BLOCKED by default and is the old JARVIS voice loop, not PCR.
- **Problems:** Directly violates Axiom 4 (Observation Never Ends), Ch 6 (Continuous Cognition), Ch 43 (Background Cognition). A task cannot continue while the user is away — the explicit motivating example in §17.3.
- **Compliance:** **0%**
- **Recommendation:** BUILD in Milestone 1 alongside the Kernel (the Kernel's `tick()` lives here).

### 2.3 Cognitive Event System — Chapter 21

- **Status:** ❌ DOES NOT EXIST
- **Specification:** Immutable, timestamped, causally-ordered events are the language of cognition. Everything meaningful becomes an event. Replayable. Deterministic. Nothing bypasses the Kernel.
- **Implementation reality:** Communication is plain Python method calls and return values. There is no event bus, no event schema, no causality chain, no replay. `trace: List[str]` in the Operator is a human-readable log, not an event stream.
- **Problems:** Without events there is no replay (Ch 21/56), no observability (Ch 58), no device federation (Ch 47), no time-travel debugging. The entire "explainable, replayable cognition" promise is absent.
- **Compliance:** **0%**
- **Recommendation:** BUILD in Milestone 1. Event Bus + immutable event schema + persistence.

### 2.4 World Model — Chapter 9

- **Status:** ⚠️ PARTIAL — wrong abstraction
- **Specification:** A continuously evolving probabilistic structure of **beliefs**. Every belief has confidence, source, timestamp, expiration, dependencies, supporting/contradicting evidence. Stores Objects + Relationships + Events. Maintains Observed/Predicted/Desired worlds. Multi-sensor fusion. The single source of cognition.
- **Implementation reality:** `friday/perception/world_state.py` — `WorldState` is an **immutable snapshot** built fresh each call via `WorldStateBuilder`. It stores raw lists (`ui_elements`, `browser_elements`, `ocr_regions`), a few derived booleans (`DerivedFacts`), and timestamps. There are NO beliefs, NO confidence per fact, NO evidence graph, NO expiration, NO relationships, NO Predicted/Desired worlds, NO continuity (rebuilt every time).
- **Problems (this is critical):**
  - It is "WorldState" (a snapshot) not "World Model" (a living hypothesis). Violates Ch 9 §9.2, 9.6, 9.7.
  - No `Desired World` representation → Deliberation (Ch 10) cannot compute "distance to goal" as specified.
  - No probabilistic fusion (Ch 9 §9.14, Ch 12 §12.6).
  - No temporal decay (Ch 9 §9.11, Ch 49).
  - Indirect Cognition (Ch 9 §9.3) is violated: the executor reasons partly on raw browser dicts.
- **Compliance:** **20%** (it does fuse a couple of sources into derived facts and is read by some consumers).
- **Recommendation:** REWRITE as a belief store owned by the Kernel (Milestone 2). Keep `BoundingBox`/`UIElement`/`BrowserElement` value types; replace the container.

### 2.5 Goal Lifecycle — Chapter 18

- **Status:** ⚠️ PARTIAL
- **Specification:** Goal is a first-class persistent cognitive object with 11 states (Created→Understood→Specified→Deliberating→Executing→Waiting→Recovering→Verifying→Completed/Failed/Cancelled), identity, history, dependencies, suspension/resumption across restarts, evolution, splitting, merging.
- **Implementation reality:** A goal is a `str` parameter to `operator.run()`. `RequirementSet`/`Requirement` capture some "Specified" semantics. There is no Goal object, no state machine, no persistence, no suspension/resume, no hierarchy beyond a flat requirement list.
- **Problems:** Goals do not survive the function call. No `Waiting`/`Recovering` states → long tasks and human-in-the-loop (Ch 36) cannot be modeled. Violates Ch 18 invariants wholesale.
- **Compliance:** **15%**
- **Recommendation:** BUILD Goal object + state machine (Milestone 2/3), owned by Kernel, persisted, feeding the Goal Graph.

### 2.6 Goal Graph — Chapter 19

- **Status:** ❌ DOES NOT EXIST
- **Specification:** Directed graph of goal nodes with typed edges (dependency/information/resource/temporal/trigger/observation), shared knowledge reuse, dynamic split/merge, parallel regions, persistence, multi-device.
- **Implementation reality:** None. Plans are flat `List[OperatorStep]`. No graph, no reuse, no parallel regions.
- **Compliance:** **0%**
- **Recommendation:** BUILD after Goal object exists (Milestone 3). This is the backbone for long-horizon (Ch 42) and federation (Ch 47).

### 2.7 Three Cognitive Layers — Chapter 6

- **Status:** ⚠️ PARTIAL / conflated
- **Specification:** Strict separation: Understanding (what is happening) / Reasoning (what should happen) / Operation (how to change reality). Understanding never decides; Reasoning never executes; Operation never interprets.
- **Implementation reality:** `RequirementsDiscovery` ≈ Understanding (partial). `OperatorPlanner` ≈ Reasoning (partial, but it produces a fixed step list, not continuous reasoning). `GoalExecutor` ≈ Operation — but it VIOLATES the separation: the executor interprets goals (`_target_to_url`, keyword sniffing), generates content (calls the LLM), and decides (if/elif dispatch). Layers are blended.
- **Compliance:** **30%**
- **Recommendation:** Re-establish clean layer boundaries when the Kernel/Deliberation are built (Milestone 4).

### 2.8 Intent Analysis Engine — Chapter 7

- **Status:** ⚠️ PARTIAL
- **Specification:** Produces a structured Intent Object (primary/secondary goals, constraints, assumptions with a 4-level spectrum, unknowns, risks, clarification-needed, deliverables, success conditions, complexity, confidence). Reconstructs intent from full context, not language alone.
- **Implementation reality:** `RequirementsDiscovery.discover()` does an LLM call producing a flat list of requirement strings + structural augmentation. No assumption spectrum, no risk classification, no clarification policy, no complexity estimation, no context fusion (no memory/world consulted).
- **Compliance:** **35%**
- **Recommendation:** Extend into a real Intent Engine (Milestone 5). Does not violate architecture, just incomplete.

### 2.9 Problem Classification Engine — Chapter 8

- **Status:** ❌ ESSENTIALLY ABSENT
- **Specification:** Classify goals by cognitive structure (Knowledge Acquisition / Transformation / Communication / Creation / Diagnostic / Repair / Exploration / Navigation / Execution / Monitoring / Coordination), produce a Problem Graph with confidence, reclassify dynamically.
- **Implementation reality:** None. The planner's `_generic_capabilities` does crude keyword sniffing (`needs_info`, `needs_file`, `needs_send`) — this is a faint shadow, not classification, and it lives in the wrong place.
- **Compliance:** **5%**
- **Recommendation:** BUILD as a distinct stage (Milestone 5).

### 2.10 Deliberation — Chapter 10

- **Status:** ⚠️ PARTIAL — fundamentally different model
- **Specification:** Continuous utility-driven selection of the **next best single action** by comparing Current vs Desired world, generating candidate actions, scoring by utility (benefit − risk − cost − uncertainty), reversibility, opportunity cost. "Planning is one consequence of deliberation, not the reverse."
- **Implementation reality:** The opposite of the spec. `OperatorPlanner.plan()` generates an entire fixed step list up-front via one LLM decomposition call. There is no per-step candidate generation, no utility function, no reversibility scoring, no Desired-World distance. The web_agent's observe→decide→act loop is the ONLY place that resembles real deliberation, and only inside a browser.
- **Problems:** Violates Ch 10 §10.3-10.4 (incremental decisions), Axiom 2 (disposable strategies). The plan-then-execute model is exactly what §10.3 says fails.
- **Compliance:** **25%**
- **Recommendation:** BUILD a real Deliberation Engine (Milestone 4). Generalize the web_agent loop to all environments.

### 2.11 Operation — Chapter 11

- **Status:** ✅ PARTIAL — closest to spec
- **Specification:** Execute one capability/primitive at a time, each separated by observation; environment-independent; atomic; interruptible; long-running aware; event-driven; returns reality, not conclusions.
- **Implementation reality:** `GoalExecutor._execute_step` executes capability-by-capability; primitives layer (`friday/actions/primitives.py`) is genuinely environment-independent with adapter cascade (browser/desktop/desktop_actions/vision). This is the most spec-aligned area. BUT: not interruptible, not event-driven, not truly one-action-with-observation-between (it runs a planned list), and `_build_world_state` is shallow.
- **Compliance:** **55%**
- **Recommendation:** Keep the primitives/adapters; rewire under Deliberation + Events (Milestone 6).

### 2.12 Perception — Chapter 12

- **Status:** ⚠️ PARTIAL
- **Specification:** The ONLY subsystem allowed to touch reality. Uniform sensor interface (`observe/subscribe/query/track/...`), uniform Observation objects, multi-sensor fusion with confidence, event-based + active observation, attention, prediction-guided.
- **Implementation reality:** Sensors exist (`screen.py`, `ocr.py`, `vision.py`, `desktop.py`, `browser.py`) but do NOT share a uniform interface, do NOT emit uniform Observation objects, and there is no fusion engine producing confidence. `DesktopPerception` returns empty without a legacy `state_cache` that the Operator never wires (confirmed in state audit). No event subscription, no attention, no prediction-guided observation.
- **Problems:** Violates Ch 12 §12.4 (uniform interface), §12.6 (fusion), §12.9 (events). Other subsystems (executor) read raw sensor output directly, violating the "only Perception touches reality" rule.
- **Compliance:** **30%**
- **Recommendation:** Standardize sensor contract + Observation type + fusion (Milestone 6/7).

### 2.13 Reflection — Chapter 13

- **Status:** ❌ DOES NOT EXIST
- **Specification:** Continuous evaluation after every action: prediction error, the Five Questions, confidence calibration, opportunity discovery, reflection records, multi-scale (micro/task/goal/session/long-term). Proposes memory candidates; never writes memory directly.
- **Implementation reality:** None. There is no prediction (so no prediction error), no reflection records, no confidence calibration. `RepairDiagnoser` is reactive repair, not reflection.
- **Compliance:** **0%**
- **Recommendation:** BUILD (Milestone 8). Requires prediction (Deliberation) and Events first.

### 2.14 Memory — Chapter 14 / 50

- **Status:** ⚠️ PARTIAL but ORPHANED (violation)
- **Specification:** Four/five tiers (Working/Episodic/Procedural/Semantic/Preference); behavioural (memory exists only if it changes future behaviour); confidence; forgetting; contradiction resolution; never overrides reality; formed only via Reflection.
- **Implementation reality:** `friday/memory/` is genuinely implemented (Working/Episodic/Procedural/Semantic, JSON store, NVIDIA embeddings + lexical fallback, temporal edges). HOWEVER — and this is the violation — **it is completely orphaned.** `operator.py` imports no memory. The executor consults no procedural memory. Nothing forms memories via reflection (there is no reflection). It is dead, well-built infrastructure.
- **Problems:** Violates Ch 14 §14.8 (formation via reflection) by simply not being connected. Memory does not influence cognition (the entire point of Ch 14).
- **Compliance:** **30%** (built but disconnected ⇒ 0 behavioural value).
- **Recommendation:** Wire to Kernel + Reflection (Milestone 8). Keep the stores.

### 2.15 Learning — Chapter 15

- **Status:** ❌ EMPTY
- **Specification:** Transform validated experience into reusable competence; pattern discovery; generalization; 4 levels; negative learning; transfer; measurable.
- **Implementation reality:** `friday/learning/__init__.py` is an 8-line docstring. Nothing.
- **Compliance:** **2%**
- **Recommendation:** BUILD after Reflection + Competence (Milestone 9+).

### 2.16 Capabilities — Chapter 16

- **Status:** ⚠️ PARTIAL — registry is metadata-only
- **Specification:** Environment-independent, composable, self-describing units with contract (preconditions/outcome/verification/recovery/confidence/learning hooks), hierarchy (primitive→micro→core→composite), registry with confidence/success-rate, versioning, sandboxing.
- **Implementation reality:** `ToolRegistry` exists but **every tool has `handler=None`** — it is a planning catalogue, not an execution framework. Real execution is the executor's if/elif. The `primitives.py` layer is the genuine capability layer but it is not modeled as Ch-16 Capabilities (no contracts, no confidence, no versioning, no self-description).
- **Problems:** Violates Ch 16 §16.5 (self-describing), §16.7 (contracts), §16.11 (confidence), §16.15 (versioning).
- **Compliance:** **25%**
- **Recommendation:** Define the Capability contract; make registry authoritative with handlers (Milestone 7).

### 2.17 Decision Architecture — Chapter 22

- **Status:** ⚠️ PARTIAL
- **Specification:** Every action originates from an explainable decision: candidate generation, utility estimation, risk/reversibility, exploration vs exploitation, ethical hard boundaries, structured decision records.
- **Implementation reality:** Decisions are implicit in if/elif dispatch and the LLM's plan. No candidate sets, no utility, no decision records, no hard ethical boundaries enforced in code.
- **Compliance:** **20%**
- **Recommendation:** Co-build with Deliberation (Milestone 4).

### 2.18 Environment Architecture — Chapter 23

- **Status:** ⚠️ PARTIAL
- **Specification:** Everything is an Environment with uniform contract (`Observe/Interact/Verify/QueryObjects/QueryCapabilities/Pause/Resume/Shutdown`); nested environments; environment graph; auto-discovery; unknown→exploration.
- **Implementation reality:** There is an implicit notion (`browser_strategy.py` picks CDP vs desktop), and `BrowserController`/`DesktopChromeController` share a duck-typed surface (good instinct!). But there is no formal Environment abstraction/contract, no environment graph, no nesting, no discovery.
- **Compliance:** **35%**
- **Recommendation:** Formalize Environment contract (Milestone 6). The duck-typed browser/desktop parity is a strong foundation to build on.

### 2.19 Interaction Architecture — Chapter 24

- **Status:** ⚠️ PARTIAL — actually reasonable
- **Specification:** Dynamic selection across interaction levels (Observation/Native/Semantic/Human-Interface/Visual); principle of least resistance; hybrid; verification per interaction.
- **Implementation reality:** The adapter cascade (`AdapterResolver`: browser DOM → desktop UIA → desktop_actions → vision) genuinely implements "least resistance" priority selection. This is one of the better-aligned areas. Missing: per-interaction prediction/verification, dynamic mid-task switching is partial.
- **Compliance:** **45%**
- **Recommendation:** Keep and extend (Milestone 6).

### 2.20 Unknown Environment Exploration — Chapter 25 / 66

- **Status:** ❌ ABSENT
- **Specification:** Treat unknown software as learnable: object graph, affordance inference, safe experimentation ladder, external knowledge acquisition, human demonstration, capability generation. This is "what makes FRIDAY a true General Operator" (§66.1).
- **Implementation reality:** None. The web_agent can operate unknown *websites* via DOM observation, which is a partial shadow for the browser only. No desktop exploration, no object graph, no affordance inference, no demonstration learning.
- **Compliance:** **5%**
- **Recommendation:** BUILD — this is high-value and central to the GCO thesis (Milestone 7+).

### 2.21 Procedure Synthesis — Chapter 26

- **Status:** ⚠️ PARTIAL — but retrieval-flavored
- **Specification:** Construct novel capability GRAPHS incrementally and interleaved with execution; revise continuously; recursive; parallel; destroyed after goal, lessons kept.
- **Implementation reality:** `OperatorPlanner` does LLM decomposition into a flat list once, up-front. This is closer to "plan retrieval/generation" than incremental graph synthesis. No interleaving, no graph, no recursion, no continuous revision.
- **Compliance:** **30%**
- **Recommendation:** Rebuild as incremental graph synthesis under Deliberation (Milestone 5).

### 2.22 Capability Evolution — Chapter 27

- **Status:** ❌ ABSENT. **Compliance 0%.** P3. (Candidate→sandbox→benchmark→promote→rollback pipeline; needs Competence + Benchmark first.)

### 2.23 Competence Model — Chapter 28

- **Status:** ❌ ABSENT. **Compliance 0%.** P2. No evidence-backed per-capability/-environment performance metrics. Decision-making cannot reason about its own reliability. Needed before Learning/Evolution.

### 2.24 Browser Runtime — Chapter 29

- **Status:** ✅ PARTIAL — best-built runtime
- **Specification:** Browser as environment adapter, NO cognition; vendor-independent; profiles/tabs/frames first-class; multi-modal observe; verification; recovery; contracts.
- **Implementation reality:** `browser_controller.py` (710 lines) is genuinely capable: CDP via Playwright, persistent loop thread, `observe_interactive` with iframe/shadow-DOM traversal, tab management, scroll, upload/download, screenshot. Live-verified on dedicated profile. VIOLATIONS: (a) it is Playwright-specific, not a pluggable multi-backend runtime (Ch 29 §29.23); (b) it owns no formal Environment contract; (c) profiles are handled via `chrome_profiles.py` but not modeled as first-class World objects; (d) CDP fails on the signed-in profile (documented).
- **Compliance:** **50%**
- **Recommendation:** Refactor behind the Environment + Browser Runtime contract; keep the implementation as the first adapter (Milestone 6).

### 2.25 Desktop Runtime — Chapter 30

- **Status:** ⚠️ PARTIAL — the spec calls this the PRIMARY world; we barely have it
- **Specification:** Desktop is the primary environment. Window/Display/Workspace/Clipboard/Notification/Focus/Session/Power model. Multi-monitor, DPI-aware, OS-independent contract.
- **Implementation reality:** `DesktopChromeController` (OCR + pyautogui, just built) operates ONLY Chrome via screen reading. `system.py` can launch apps + focus windows. `DesktopPerception` needs the unwired legacy `state_cache`. No window manager, no display topology, no multi-monitor, no DPI awareness, no clipboard/notification model.
- **Problems:** The Constitution (Ch 30 §30.24) explicitly says desktop cognition should REPLACE application automation — we have the inverse (Chrome-specific OCR). Critical gap for the GCO thesis.
- **Compliance:** **20%**
- **Recommendation:** BUILD a real Desktop Runtime (Milestone 6/7). High priority.

### 2.26 Motor System — Chapter 31

- **Status:** ⚠️ PARTIAL
- **Specification:** Closed-loop, observe-predict-move-observe-correct; target acquisition; motion profiles; interruptible; verified; OS-independent contract.
- **Implementation reality:** `pyautogui` direct calls in adapters (open-loop). No closed-loop correction, no target re-acquisition, no motion profiles, not interruptible.
- **Compliance:** **25%**
- **Recommendation:** Wrap motor actions in a feedback-controlled Motor Runtime (Milestone 7).

### 2.27 Verification Engine — Chapter 32

- **Status:** ✅ PARTIAL — genuinely good
- **Specification:** Predict expected world before action; collect multi-modal evidence; confidence; contradiction detection; goal-level verification.
- **Implementation reality:** TWO verifiers exist. (a) `evidence_law.py::EvidenceVerifier` — excellent, artifact-based, prevents false completion, live-verified. (b) `verifier.py::ActionVerifier` — WorldState before/after diff with per-action-type strategies. PROBLEM: ActionVerifier is orphaned (only used by the orphaned `FridayEngine`/core.py). Also: no explicit "predict before action" step feeding verification (because Deliberation doesn't predict).
- **Compliance:** **55%**
- **Recommendation:** Unify the two verifiers into one Kernel-owned Verification Engine; add prediction inputs (Milestone 6/8).

### 2.28 Evidence System — Chapter 33

- **Status:** ✅ PARTIAL — good core
- **Implementation reality:** `evidence_law.py` (ExecutionEvidence, EvidenceKind, artifacts) + `screenshot_evidence.py` are real and well-used in the executor/research. Missing: evidence as a queryable repository/graph (Ch 33 §33.5/33.9), signatures, lifetime/retention policies, evidence index/search.
- **Compliance:** **50%**
- **Recommendation:** Promote to a first-class Evidence Repository (Milestone 8).

### 2.29 Recovery Engine — Chapter 34

- **Status:** ⚠️ PARTIAL
- **Implementation reality:** `repair.py::RepairDiagnoser` + operator repair loop diagnose unmet requirements and run targeted repairs. This is a decent seed for "recovery is re-deliberation." Missing: failure taxonomy (Ch 34 §34.3), multi-level recovery, recovery-as-deliberation generality, recovery learning.
- **Compliance:** **30%**
- **Recommendation:** Generalize into recovery = a deliberation mode (Milestone 8).

### 2.30 Safety & Permission — Chapter 35

- **Status:** ⚠️ PARTIAL — under-built for an autonomous operator
- **Specification:** Permission levels, trust zones, confirmation policies, least authority, secret vault, immutable self-protection.
- **Implementation reality:** `delivery.py` has a confirmation gate (`FRIDAY_AUTOCONFIRM`), `FRIDAY_DRY_RUN` blocks external actions in tests, `main.py` has a legacy-launch guard. But there is NO permission model, NO trust zones, NO secret vault (the `.env` holds keys in plaintext), NO least-authority enforcement, NO immutable safety boundary.
- **Problems:** Ch 35 §35.5 ("self-protection," cannot disable safety) is unenforced — there is nothing to disable because there is no safety engine. For a system meant to operate the user's real logged-in accounts, this is a HIGH risk.
- **Compliance:** **20%**
- **Recommendation:** BUILD Safety Engine + Secret Vault + Permission Manager (Milestone 4/5). Treat as P1.

### 2.31 Human Collaboration — Chapter 36

- **Status:** ⚠️ PARTIAL. Confirmation gate + clarification exist in fragments. No interruption manager, no demonstration recorder, no approval objects, no shared-control manager. **20%.** P2.

### 2.32 Research Domain — Chapter 37

- **Status:** ✅ PARTIAL — works, but "search+read," not "research"
- **Implementation reality:** `research.py` does DDG search → decode redirects → follow links → read pages → record source URLs + gathered text → citations. Live-verified. BUT it is closer to Ch 13's "reading" critique than the full Ch 37 research lifecycle: no hypotheses, no source-credibility ranking model, no contradiction engine, no knowledge graph, no multi-hop sub-questions.
- **Compliance:** **45%**
- **Recommendation:** Extend with credibility + contradiction + knowledge graph (Milestone 9, domain phase).

### 2.33 Knowledge Acquisition — Chapter 38

- **Status:** ❌ ABSENT (research gathers text but no validated Knowledge Store/Graph with freshness). **5%.** P3.

### 2.34 Communication Domain — Chapter 39

- **Status:** ⚠️ PARTIAL + VIOLATION
- **Implementation reality:** `delivery.py` + web_agent-based sending is generic (good). BUT `bridge.py::_target_to_url` HARDCODES instagram/gmail/whatsapp/etc. URLs — a direct violation of Axiom 15, Ch 39 ("no Gmail Agent"), and Anti-Patterns Ch 63. Delivery verification uses keyword matching ("sent") — weak.
- **Compliance:** **25%**
- **Recommendation:** DELETE the hardcoded URL map; replace with generic environment discovery (Milestone 5). Flagged in Technical Debt.

### 2.35 Document Intelligence — Chapter 40

- **Status:** ⚠️ PARTIAL. `file_tool.py` writes real txt/md/csv/xlsx/docx/html — but as files, not as a semantic document model. No semantic editing, no multi-format-from-one-source, no citation engine, no PDF/PPTX. **20%.** P3.

### 2.36 Software Engineering Domain — Chapter 41

- **Status:** ❌ ABSENT. **0%.** P3.

### 2.37 Long-Horizon Planning — Chapter 42

- **Status:** ❌ ABSENT (no persistence ⇒ nothing can span time). **0%.** P2 (unlocked by Kernel/PCR/Goal Graph).

### 2.38 Background Cognition — Chapter 43

- **Status:** ❌ ABSENT (no PCR). **0%.** P2.

### 2.39 Self-Improvement — Chapter 44

- **Status:** ❌ ABSENT. **0%.** P3.

### 2.40 Resource Model — Chapters 45-48

- **Status:** ❌ ABSENT
- **Specification:** Everything useful is a Resource (CPU/GPU/browser/human/LLM/cloud/...), with discovery, allocation, scheduling, federation, economics.
- **Implementation reality:** Resources are hardcoded constructor params. No registry, no allocation, no scheduling, no federation, no cost model. `ModelRouter` is a faint shadow (routes LLM calls by capability) but not a Resource Model.
- **Compliance:** **0%**
- **Recommendation:** BUILD Resource Registry + Scheduler (Milestone 4, part of Kernel scheduling). P2.

### 2.41 Temporal Reasoning — Chapter 49

- **Status:** ❌ ABSENT (timestamps exist; no temporal reasoning, decay, prediction, deadlines, recurrence). **0%.** P2.

### 2.42 Cognitive Identity — Chapter 51

- **Status:** ❌ ABSENT (no checkpoint, no cross-session continuity, no cross-device identity). **0%.** P2.

### 2.43 Runtime Communication — Chapter 52

- **Status:** ❌ ABSENT + actively VIOLATED
- **Specification:** All communication via Kernel + typed contracts + immutable messages; dependencies point inward; no cross-runtime calls.
- **Implementation reality:** Direct method calls everywhere (Operator→Executor→research/web_agent→browser). This is exactly the "everything depends on everything" anti-pattern §52.1 warns against.
- **Compliance:** **5%**
- **Recommendation:** Enforce via the Event Bus + contracts once the Kernel exists (Milestone 1-3).

### 2.44 Runtime Composition / Replaceability — Chapter 53

- **Status:** ⚠️ PARTIAL. Adapters are somewhat replaceable; but tight coupling and no plug-in boundaries. **30%.** P2.

### 2.45 Plugin Architecture — Chapter 54

- **Status:** ❌ ABSENT. **0%.** P3.

### 2.46 Benchmark Architecture — Chapter 55

- **Status:** ❌ ABSENT (no goal-completion benchmarks; only unit tests). **0%.** P2.

### 2.47 Testing Philosophy — Chapter 56

- **Status:** ⚠️ PARTIAL + VIOLATION
- **Specification:** Goal-based testing pyramid, synthetic worlds, deterministic replay, failure injection, adversarial, unknown-world tests.
- **Implementation reality:** 802 tests, ALL `FRIDAY_DRY_RUN=1`, ALL mocked. Zero real-I/O integration tests, zero goal-completion tests, zero replay, zero failure injection, zero adversarial. The test suite validates code consistency, not cognition (exactly the §56.1 distinction).
- **Compliance:** **25%**
- **Recommendation:** Add goal-level + replay + failure-injection tiers as the Kernel is built (every milestone).

### 2.48 Deployment (Ch 57) / Operational (Ch 58)

- **Status:** ⚠️ PARTIAL. FastAPI app DEFINED but never served (no `uvicorn.run`). No identity sync, no telemetry runtime in `friday/`, no health/diagnostics/checkpoint. **15%.** P3/P2.

---

## 3. PHASE 2 — Traceability Matrix (Specification ↔ Codebase)

Every chapter mapped to implementing files, missing pieces, and compliance. "—" = nothing exists.

| FAS Chapter | Implementing Files (current) | Missing Implementation | Compliance |
|-------------|------------------------------|------------------------|-----------|
| Ch 5 Ontology (Goal/Capability/Env/Evidence) | `planner/requirements.py`, `tools/registry.py`, `verification/evidence_law.py` | Goal object, Environment type, Belief type, Strategy type | 25% |
| Ch 6 Cognitive Architecture (3 layers) | `planner/requirements.py` (Understanding), `planner/operator_planner.py` (Reasoning), `executor.py` (Operation) | Clean separation; continuous loop | 30% |
| Ch 7 Intent Analysis | `intent/{intent,analyzer}.py` (M5: immutable Intent, Assumption spectrum, clarification policy, complexity estimate, kernel-event-driven IntentAnalyzer); `planner/requirements.py`, `planner/goal_parser.py` | LLM-backed analysis behind the same interface | 60% |
| Ch 8 Problem Classification | `intent/classifier.py` (M5: weighted multi-class ProblemClassifier with reclassify(); deterministic, app-agnostic signals) | Problem Graph; evidence-driven reclassification triggers | 45% |
| Ch 9 World Model | `world/{belief,objects,worlds,world_model}.py` (M2: beliefs with confidence/decay/expiry, object graph, Observed/Predicted/Desired worlds, kernel-event-fed WorldModel); legacy `perception/world_state.py` kept for the pipeline until M6 | Predictive modelling; pipeline migration (M6) | 55% |
| Ch 10 Deliberation | `deliberation/{candidate,utility,deliberator}.py` (M4: CandidateAction with PredictedOutcome, deterministic UtilityFunction, Deliberator); `planner/operator_planner.py` | LLM-backed candidate generation; next-action model | 50% |
| Ch 11 Operation | `executor.py`, `actions/primitives.py`, `actions/adapters/*`; M6 `environments/{contract,runtime}.py` (EnvironmentContract.interact→ActionResult, EnvironmentRuntime bridge) | Interruptible, event-driven, observe-between-actions | 65% |
| Ch 12 Perception | `perception/{screen,ocr,vision,desktop,browser}.py`; M2 adds `perception/{contracts,observation,fusion}.py` (SensorContract, uniform Observation, noisy-OR SensorFusion, ScreenSensor adapter) | Migrate remaining sensors to SensorContract; attention | 45% |
| Ch 13 Reflection | M8 `cognition/reflection.py` (ReflectionEngine: prediction-error via Jaccard, 5 Questions, 4 scales, ConfidenceCalibrator, emits `memory.candidate`/`reflection.completed`; never writes memory directly) | Multi-scale session/long-term reflection depth | 60% |
| Ch 14 Memory | M8 `memory/runtime.py` (MemoryRuntime: RuntimeContract wrapping FridayMemory, verified-only + reality-outranks-memory decide(), accept/reject/merge/forget, degraded-mode); `memory/{controller,working,episodic,procedural,semantic,stores,interfaces}.py` (wired, not rewritten) | Retrieval router, richer merge/forget policy | 60% |
| Ch 15 Learning | M9 `learning/{models,patterns,generalization,validation,engine}.py` (LearningEngine: discover→generalize→validate over verified experience only; PatternDiscovery repetition threshold; Generalizer transfer + monotonic confidence; LearningValidator hard verified-gate + measurable-improvement + unlearning; improvement tracking from `competence.updated`; emits `learning.pattern_discovered`/`validated`/`rejected`/`unlearned` + verified `memory.candidate`; never writes memory directly) | Deeper transfer, cross-goal principle reuse | 60% |
| Ch 16 Capabilities | M7 `kernel/contracts/capability.py` (full 9-member CapabilityContract + Condition/WorldStateDelta/CompetenceRecord), `capabilities/contracts.py` (BaseCapability, Laplace confidence), `capabilities/registry.py` (CapabilityRegistry, confidence-ranked, TD-5 legacy coexistence); `tools/registry.py` (adapted), `actions/primitives.py`, `actions/adapters/*` | Versioning, sandbox, full handler wiring | 60% |
| Ch 17 Persistent Runtime | `kernel/scheduler.py`, `kernel/checkpoint.py` (M1: continuous tick loop + checkpoint/restore) | Goal execution on the runtime; session continuity across reboots | 40% |
| Ch 18 Goal Lifecycle | `goals/goal.py` (M3: immutable Goal, legal-transition state machine incl. suspension, failure reasons, serialization); `planner/requirements.py` | Wiring the pipeline to Goal objects (M6) | 55% |
| Ch 19 Goal Graph | `goals/graph.py`, `goals/manager.py` (M3: decomposition + dependency graph, cycle detection, readiness, kernel-event-driven GoalManager with auto parent completion) | Priority/utility ordering (M4) | 50% |
| Ch 20 Cognitive Kernel | `kernel/kernel.py`, `kernel/clock.py`, `kernel/contracts/*`, `kernel/echo_runtime.py` (M1) | World Model/Goal Graph ownership (M2/M3); capability dispatch (M7) | 45% |
| Ch 21 Event System | `events/event.py`, `events/bus.py`, `events/store.py` (M1: immutable signed events, pattern bus, append-only store, replay, checkpoints) | Async handler queues; cross-process event transport | 55% |
| Ch 22 Decision Architecture | `deliberation/deliberator.py` (M4: candidate sets, utility ranking, immutable DecisionRecords on the event log, inaction threshold, irreversibility penalty); `executor.py` | Hard boundaries / permission gates (M5+) | 50% |
| Ch 23 Environment Architecture | M6 `environments/{contract,runtime,stub}.py`, `environments/browser/adapter.py`, `environments/desktop/__init__.py` (uniform EnvironmentContract, EnvironmentRuntime bridge, StubEnvironment gate, site-agnostic); `actions/browser_strategy.py`, `actions/browser_factory.py` | Environment graph, nesting, discovery | 70% |
| Ch 24 Interaction Architecture | `actions/adapters/resolver.py` + adapters | Per-interaction prediction/verification | 45% |
| Ch 25/66 Exploration | M7 `environments/unknown/{object_graph,affordances,experiment,demonstration,exploration}.py` (ObjectGraph, AffordanceInferrer, SafeExperimentPlanner risk-ladder, DemonstrationRecorder principles-not-coordinates, ExplorationEngine — abstract-contract only, M7 Gate passes on unknown software); `capabilities/web_agent.py` | Capability candidate promotion depth, richer object-graph edges | 60% |
| Ch 26 Procedure Synthesis | `planner/operator_planner.py`, `planner/llm_decomposer.py` | Incremental graph synthesis, interleaving, recursion | 30% |
| Ch 27 Capability Evolution | — | Entire pipeline | 0% |
| Ch 28 Competence Model | M8 `competence/model.py` (CompetenceModel: evidence-only per-(capability,environment) via CompetenceRecord, time-decay toward neutral prior, monotonic risk-confidence gate, kernel-driven `verification.completed`→`competence.updated`) | Competence-graph edges, cross-context transfer | 60% |
| Ch 29 Browser Runtime | M6 `environments/browser/adapter.py` (BrowserEnvironment wraps controller behind EnvironmentContract, dict-dispatch routing, no Playwright leakage); `actions/browser_controller.py`, `chrome_launcher.py`, `chrome_profiles.py`, `profile_clone.py` | Multi-backend (WebDriver adapter), first-class profiles/tabs | 65% |
| Ch 30 Desktop Runtime | M7 `environments/desktop/{runtime,window_manager,display_manager,clipboard,session}.py` (real DesktopEnvironment on EnvironmentContract, UIA+OCR fusion, WindowManager/DisplayManager DPI/ClipboardManager/SessionManager gated lock; supersedes broken DesktopPerception TD-7); `actions/desktop_chrome.py`, `actions/system.py` | UIA sensor depth, notifications, multi-monitor live | 60% |
| Ch 31 Motor System | M7 `capabilities/motor.py` (closed-loop MotorSystem: acquire_target UIA>OCR, move_to observe→predict→move→observe→correct, MotionProfile/TargetLock/MotorResult, DisplayManager transform, no blind clicks) | Live pyautogui verification, motion easing | 60% |
| Ch 32 Verification Engine | M6 `verification/engine.py` (UnifiedVerificationEngine merges EvidenceVerifier + ActionVerifier; verify_action/requirement/goal; Evidence Law preserved verbatim); `verification/evidence_law.py`, `verification/verifier.py` | Prediction input from Deliberation | 70% |
| Ch 33 Evidence System | M6 `verification/evidence_repo.py` (EvidenceRepository: HMAC-signed, append-only, indexed by goal/kind, tamper-evident, for_goal reconstruction); `verification/evidence_law.py`, `verification/evidence.py`, `screenshot_evidence.py` | Evidence graph, retention policies, full-text search | 65% |
| Ch 34 Recovery Engine | M8 `recovery/engine.py` (RecoveryEngine wraps RepairDiagnoser into the full loop: FailureClass taxonomy, RecoveryLevel ladder, RollbackKind contracts, goal-id-preserving `recover()`, irreversible-action confidence floor → HUMAN escalation, emits `recovery.proposed`); `planner/repair.py`, `planner/replanner.py` | Recovery-outcome learning, live re-entry into Deliberation | 60% |
| Ch 35 Safety & Permission | `actions/delivery.py`, `FRIDAY_DRY_RUN` guards | Permission model, trust zones, secret vault, immutable boundary | 20% |
| Ch 36 Human Collaboration | `actions/delivery.py` (gate), clarification fragments | Interruption/approval/demonstration/shared-control managers | 20% |
| Ch 37 Research Domain | `capabilities/research.py`, `planner/query_extractor.py` | Hypotheses, credibility ranking, contradiction engine, knowledge graph | 45% |
| Ch 38 Knowledge Acquisition | (research gathers text) | Knowledge store/graph, validation, freshness | 5% |
| Ch 39 Communication Domain | `actions/delivery.py`, `capabilities/web_agent.py` | Remove hardcoded URLs; conversation model; delivery verification | 25% |
| Ch 40 Document Intelligence | `actions/file_tool.py` | Semantic doc model, multi-format, citations, PDF/PPTX | 20% |
| Ch 41 Software Engineering | — | Entire domain | 0% |
| Ch 42 Long-Horizon Planning | M9 `horizon/planner.py` (LongHorizonPlanner: Vision>Mission>Project>Milestone>Goal; prerequisite-gated `next_actionable`; verification-gated `advance`; dynamic `revise_roadmap` with immutable vision; checkpoint/restore reusing Goal serialization; emits `horizon.milestone_reached`/`project_advanced`) | Mission-level roadmap synthesis | 60% |
| Ch 43 Background Cognition | M9 `background/runtime.py` (BackgroundRuntime: RuntimeContract; event-driven idle tracking; foreground preemption; bounded round-robin work units — consolidate/decay/freshness/advance; DRY_RUN-safe; degraded-mode containment; emits `background.work_done` + proposes `memory.candidate`) | Richer work-unit policies | 60% |
| Ch 44 Self-Improvement | — | Entire subsystem | 0% |
| Ch 45-48 Resource Model | `models/router.py` (LLM-only shadow) | Resource registry, allocation, scheduling, federation, economics | 0% |
| Ch 49 Temporal Reasoning | M9 `temporal/{clock,aging,deadlines}.py` (TemporalReasoner freshness/staleness/time-remaining over the kernel clock; KnowledgeAging half-life decay reusing the CompetenceModel precedent; DeadlineTracker ON_TRACK/APPROACHING/MISSED classification + emits `temporal.deadline_approaching`/`missed`; reads time only from Kernel_Events) | Predictive scheduling, richer TTL policy | 60% |
| Ch 50 Memory Architecture | `memory/*` | Wiring; preference tier; compression; forgetting policy | 35% |
| Ch 51 Cognitive Identity | — | Checkpoint, continuity, cross-device | 0% |
| Ch 52 Runtime Communication | — (direct calls) | Event bus, contracts, dependency inversion | 5% |
| Ch 53 Runtime Composition | `actions/adapters/*` | Plug-in boundaries, independent deploy | 30% |
| Ch 54 Plugin Architecture | — | Entire subsystem | 0% |
| Ch 55 Benchmark Architecture | — | Entire subsystem | 0% |
| Ch 56 Testing Philosophy | `tests/friday/*` (802, mocked) | Goal tests, replay, failure injection, adversarial, synthetic worlds | 25% |
| Ch 57 Deployment | `api/*` (defined, unserved) | Served runtime, identity sync, multi-device | 15% |
| Ch 58 Operational | `api/routes/status.py` | Telemetry runtime, health, diagnostics, checkpoint | 15% |

**Unmapped specification chapters (0% — nothing in code):** 17, 19, 20, 21, 27, 28, 41, 42, 43, 44, 45-48, 49, 51, 54, 55.

That is **15 of ~50 chapters with literally no implementation** — and they include the foundational ones (Kernel, PCR, Events, Goal Graph).

---

## 4. PHASE 1 — Missing Subsystem Report (consolidated)

### Tier A — Foundational (system cannot be FAS-compliant without these)
1. **Cognitive Kernel** (Ch 20) — the keystone.
2. **Persistent Cognitive Runtime** (Ch 17) — continuity.
3. **Cognitive Event System** (Ch 21) — the language of cognition.
4. **World Model as belief store** (Ch 9) — currently a snapshot.
5. **Runtime Communication via contracts/events** (Ch 52) — currently direct calls.

### Tier B — Core Cognition (required for the GCO loop)
6. Goal object + Lifecycle (Ch 18) and Goal Graph (Ch 19).
7. Deliberation Engine + Decision Architecture (Ch 10, 22).
8. Reflection (Ch 13).
9. Competence Model (Ch 28).
10. Resource Model + Scheduler (Ch 45-48).
11. Safety Engine + Secret Vault + Permission Manager (Ch 35).

### Tier C — Generality (the "General" in GCO)
12. Environment Architecture contract (Ch 23).
13. Desktop Runtime (Ch 30) — currently 20%.
14. Unknown Environment Exploration (Ch 25/66).
15. Capability contract + authoritative registry + Evolution (Ch 16, 27).
16. Motor System closed-loop (Ch 31).

### Tier D — Domains & Long-term
17. Learning (Ch 15), Knowledge (Ch 38), Temporal (Ch 49), Identity (Ch 51).
18. Domain depth: Research (Ch 37), Communication (Ch 39), Documents (Ch 40), SWE (Ch 41).
19. Long-horizon (Ch 42), Background (Ch 43), Self-improvement (Ch 44).
20. Plugins (Ch 54), Benchmarks (Ch 55), Federation (Ch 47).

---

## 5. Technical Debt Report

| # | Debt | Location | FAS Violation | Severity |
|---|------|----------|---------------|----------|
| TD-1 | Hardcoded site URL map (instagram/gmail/whatsapp/...) | `bridge.py::_target_to_url` | Axiom 15, Ch 39, Ch 63 Anti-Patterns | CRITICAL |
| TD-2 | Two parallel execution paths (bridge `_execute_operator_step` AND `GoalExecutor`) | `bridge.py` vs `executor.py` | Ch 52 (coupling), Ch 53 | HIGH |
| TD-3 | Two parallel verification systems, one orphaned | `verifier.py` (orphaned) vs `evidence_law.py` | Ch 32 (one engine) | HIGH |
| TD-4 | `FridayEngine` (core.py) orphaned from Operator | `core.py` | Ch 6/20 (single cognition) | HIGH |
| TD-5 | Registry tools all `handler=None`; real dispatch is if/elif | `tools/registry.py`, `executor.py` | Ch 16 (capabilities), Ch 22 | HIGH |
| TD-6 | Memory fully built but unwired | `memory/*`, `operator.py` | Ch 14 (behavioural memory) | HIGH |
| TD-7 | `DesktopPerception` needs legacy `state_cache` never provided | `perception/desktop.py` | Ch 12, Ch 30 | HIGH |
| TD-8 | Direct cross-subsystem method calls everywhere | all of `friday/` | Ch 52 | HIGH |
| TD-9 | Secrets in plaintext `.env`, no vault | `.env`, all providers | Ch 35 §35.6 | HIGH |
| TD-10 | 802 tests all mocked / DRY_RUN; no goal/replay/failure tests | `tests/friday/*` | Ch 56 | HIGH |
| TD-11 | API defined but never served (`uvicorn.run` absent) | `api/*` | Ch 57 | MEDIUM |
| TD-12 | Massive legacy tree (~16k lines) coexisting, partially referenced | `automation/`, `awareness/`, `core/`, `server/`, `services/` | Ch 53 (clean composition) | MEDIUM |
| TD-13 | Browser runtime is Playwright-locked, not multi-backend | `browser_controller.py` | Ch 29 §29.23 | MEDIUM |
| TD-14 | Open-loop pyautogui motor calls | `adapters/desktop*.py` | Ch 31 | MEDIUM |
| TD-15 | Plan-then-execute (not deliberate-incrementally) | `operator_planner.py` | Ch 10 | MEDIUM |
| TD-16 | `.git - Copy`, `.git - Copy (2)` duplicate VCS dirs in tree | repo root | hygiene | LOW |
| TD-17 | Duplicate `pytest - Copy.ini`, scattered root test scripts | repo root | hygiene | LOW |
| TD-18 | Delivery verification by keyword ("sent") | `executor.py::_execute_delivery` | Ch 32/39 | MEDIUM |

---

## 6. Risk Assessment

| Risk | Description | Likelihood | Impact | Severity | Mitigation |
|------|-------------|-----------|--------|----------|------------|
| R-1 | **Foundation-last trap** — continuing to add features on the pipeline makes the eventual Kernel migration exponentially harder | HIGH | CRITICAL | CRITICAL | Freeze feature work; build Kernel/PCR/Events first |
| R-2 | **Sunk-cost pressure** — 802 tests + working demos create the illusion of progress, discouraging the rewrite the FAS implies | HIGH | HIGH | HIGH | This audit; explicit reset decision |
| R-3 | **Signed-in profile blocker** — primary use cases need the user's session; CDP blocked; desktop OCR path unproven | CERTAIN | HIGH | HIGH | Desktop Runtime + Exploration (Tier C) |
| R-4 | **Safety gap on real accounts** — autonomous operator on logged-in Gmail/bank with no permission model/vault | MEDIUM | CRITICAL | HIGH | Safety Engine in Tier B (early) |
| R-5 | **LLM latency** — free-tier NIM cold starts 20-30s; multi-iteration loops minutes | HIGH | MEDIUM | MEDIUM | Resource Model + model tiering + async PCR |
| R-6 | **Scope vs. solo capacity** — FAS is a multi-year, multi-engineer system | CERTAIN | MEDIUM | MEDIUM | Strict milestone gating; ruthless prioritization |
| R-7 | **Determinism/replay absent** — cannot debug autonomous long tasks without event replay | HIGH | HIGH | HIGH | Event System (Tier A) |
| R-8 | **Legacy entanglement** — bridge still depends on legacy automation/awareness | MEDIUM | MEDIUM | MEDIUM | Quarantine legacy behind adapters, then delete |

---

## 7. Dependency Graph (current reality vs. FAS target)

### 7.1 Current (violates Ch 52 — sideways coupling)

```
main.py (blocked) ─┐
                   ▼
            FridayBridge ──────────────► FridayEngine (core.py) [ORPHANED]
                   │  hardcoded URLs            │
                   ▼                            ▼
              Operator ──► RequirementsDiscovery  (verifier.py ActionVerifier [ORPHANED])
                   │  ├──► OperatorPlanner ──► LLMDecomposer ──► ModelRouter ──► NVIDIA/GROQ
                   │  ├──► GoalExecutor ──┬──► research.py ──► BrowserController
                   │  │                   ├──► web_agent.py ─► BrowserController / DesktopChrome
                   │  │                   ├──► primitives ──► adapters ──► pyautogui / Playwright
                   │  │                   ├──► file_tool
                   │  │                   └──► evidence_law (EvidenceVerifier)
                   │  └──► EnvironmentObserver
                   ▼
            (returns OperatorOutcome, process idle)

   memory/*  ............................. [BUILT, UNWIRED]
   tools/registry .... [metadata only, handler=None]
   api/* ............. [defined, never served]
```

Everything calls everything. No central authority. Two orphaned subsystems.

### 7.2 FAS Target (Ch 20/52 — dependencies point inward to the Kernel)

```
              Frontends (Desktop / Mobile / Voice / API)
                              │  (Kernel API only)
                              ▼
                      ┌───────────────┐
                      │ COGNITIVE     │   owns: Clock, Event Bus, World Model,
                      │ KERNEL        │         Goal Graph, Scheduler, Registry
                      └───────┬───────┘
            ┌─────────────────┼───────────────────┐
            ▼ (events/contracts only — no sideways calls)
   ┌────────────┐    ┌──────────────┐    ┌──────────────┐
   │ Perception │    │ Deliberation │    │ Reflection   │
   │ Runtimes   │    │ + Decision   │    │ + Learning   │
   └─────┬──────┘    └──────┬───────┘    └──────┬───────┘
         ▼                  ▼                   ▼
   Environment        Capabilities /       Memory /
   Runtimes           Procedure Synth      Competence
  (Browser/Desktop/   (Operation)          Evidence Repo
   Terminal/Unknown)
         ▼
   Interaction + Motor + Verification
         ▼
   Resources (CPU/GPU/Browser/Human/Cloud/LLM)  ← Resource Model
```

Every arrow is mediated by the Kernel via immutable events and typed contracts.

---

## 8. Proposed Repository Structure (target)

This separates **stable cognition** (Kernel + contracts) from **replaceable implementations** (runtimes/adapters), per Ch 20/53.

```
friday/
├── kernel/                      # Ch 20 — the permanent core (stable API)
│   ├── kernel.py                #   submitGoal/submitObservation/publishEvent/...
│   ├── clock.py                 #   logical + wall time (Ch 20.8, Ch 49)
│   ├── scheduler.py             #   cognitive tick + goal scheduling (Ch 20.10)
│   ├── checkpoint.py            #   checkpoint/restore (Ch 17.14, Ch 51)
│   └── contracts/               #   typed interfaces ALL runtimes implement (Ch 52)
│       ├── runtime.py           #   initialize/tick/observe/receive/publish/...
│       ├── environment.py       #   Ch 23 environment contract
│       ├── capability.py        #   Ch 16 capability contract
│       ├── sensor.py            #   Ch 12 perception contract
│       └── resource.py          #   Ch 45 resource contract
│
├── events/                      # Ch 21 — Cognitive Event System
│   ├── bus.py                   #   publish/subscribe/route/filter
│   ├── event.py                 #   immutable event schema + causality
│   └── store.py                 #   persistence + replay
│
├── world/                       # Ch 9 — World Model (belief store)
│   ├── world_model.py           #   beliefs, objects, relationships, worlds
│   ├── belief.py                #   confidence/source/expiry/evidence links
│   ├── objects.py               #   Object + Relationship graph
│   └── worlds.py                #   Observed / Predicted / Desired
│
├── goals/                       # Ch 18/19 — Goal object + Graph
│   ├── goal.py                  #   first-class Goal + state machine
│   ├── graph.py                 #   Goal Graph (nodes, typed edges)
│   └── requirements.py          #   requirements (migrated)
│
├── cognition/                   # Ch 6/7/8/10/13/22 — the thinking layers
│   ├── intent.py                #   Intent Analysis (Ch 7)
│   ├── classification.py        #   Problem Classification (Ch 8)
│   ├── deliberation.py          #   utility-based next-action (Ch 10)
│   ├── decision.py              #   decision records + boundaries (Ch 22)
│   ├── procedure.py             #   incremental procedure synthesis (Ch 26)
│   └── reflection.py            #   reflection + prediction error (Ch 13)
│
├── perception/                  # Ch 12 — sensors implement sensor contract
│   ├── fusion.py                #   multi-sensor fusion → beliefs
│   ├── screen.py  ocr.py  vision.py        # (migrated, behind contract)
│   └── sensors/                 #   uia.py, dom.py, clipboard.py, process.py, ...
│
├── environments/                # Ch 23/29/30 — environment runtimes (plug-ins)
│   ├── browser/                 #   Ch 29 — multi-backend (playwright adapter first)
│   ├── desktop/                 #   Ch 30 — window/display/clipboard/session managers
│   ├── terminal/                #   future
│   └── unknown/                 #   Ch 25/66 — Exploration Engine
│
├── capabilities/                # Ch 16/27 — capability contract + registry + evolution
│   ├── registry.py              #   authoritative, handlers wired
│   ├── primitives/              #   (migrated primitives + adapters)
│   ├── interaction.py           #   Ch 24 — least-resistance selection
│   ├── motor.py                 #   Ch 31 — closed-loop motor runtime
│   └── evolution.py             #   Ch 27 — candidate→sandbox→promote
│
├── verification/                # Ch 32/33 — unified engine + evidence repo
│   ├── engine.py                #   single verification engine (merge the two)
│   └── evidence_repo.py         #   queryable evidence graph
│
├── memory/                      # Ch 14/50 — wired to Kernel + Reflection
│   └── (migrated tiers)
│
├── competence/                  # Ch 28 — empirical performance model
├── resources/                   # Ch 45-48 — registry, scheduler, economics, federation
├── safety/                      # Ch 35 — permission manager, trust zones, secret vault
├── learning/                    # Ch 15/44 — pattern→generalization→validation
├── domains/                     # Ch 37/39/40/41 — research/comms/documents/swe (capability compositions, NOT agents)
├── models/                      # LLM providers (a Resource type) — migrated
├── frontends/                   # Ch 57 — API/desktop/mobile thin clients (Kernel API only)
└── benchmarks/                  # Ch 55 — goal-completion benchmark suite

legacy/                          # quarantined old JARVIS until fully replaced, then deleted
tests/
├── unit/        ├── contracts/    ├── goals/   (goal-completion)
├── replay/      ├── failure_injection/   └── adversarial/
```

Guiding rule (Ch 53): `kernel/` and `*/contracts` change rarely; everything under `environments/`, `capabilities/`, `models/`, `domains/` is a replaceable plug-in.

---

## 9. PHASE 3 — New Implementation Roadmap

The old roadmap (ROADMAP.md, M0-M9, feature-driven) is **discarded** per your instruction. This roadmap is **architecture-driven**: foundation first, then cognition, then generality, then domains. Each milestone has a hard architectural acceptance gate. **No milestone is "done" without: design + contracts + unit tests + goal/replay tests + benchmark + docs.**

Effort is in "engineering weeks" for a single focused engineer (you + me). Treat as relative sizing, not promises.

### MILESTONE 1 — The Kernel Foundation  `(Ch 17, 20, 21, 52)`
**Objective:** A continuously running, event-driven Kernel that owns global state and can checkpoint/restore. No cognition yet — just the substrate.
- **Build:** `kernel/` (kernel, clock, scheduler skeleton, checkpoint), `events/` (bus, immutable event, store+replay), `kernel/contracts/runtime.py`.
- **Acceptance criteria:**
  - Kernel boots, runs a cognitive tick loop, stays alive (no "stopped" state).
  - Every state change flows through an immutable, timestamped, causally-linked event.
  - Kill the process mid-run → restart → state restored from checkpoint + event replay (deterministic).
  - A trivial "echo runtime" plugs in via the runtime contract and communicates ONLY through events.
- **Risks:** Over-engineering the event schema; async complexity on Windows. **Effort:** 3-4 wks.
- **Gate:** Replay produces byte-identical state. No subsystem calls another directly.

### MILESTONE 2 — World Model as Beliefs  `(Ch 9, 12 partial)`
**Objective:** Replace the WorldState snapshot with a living belief store owned by the Kernel.
- **Build:** `world/` (world_model, belief, objects, worlds), migrate value types from `perception/types.py`. One sensor (screen) emits Observations → fusion → beliefs.
- **Acceptance:** Beliefs carry confidence/source/timestamp/expiry; contradictory observations lower confidence; beliefs decay over time; Observed/Desired worlds representable; everything reads world via the Kernel.
- **Effort:** 3 wks. **Gate:** No raw sensor data read outside Perception (Indirect Cognition, Ch 9.3).

### MILESTONE 3 — Goals & Goal Graph  `(Ch 18, 19, 51)`
**Objective:** First-class persistent Goal objects in a Goal Graph; cognitive identity across restarts.
- **Build:** `goals/` (goal+state machine, graph), checkpoint integration, Identity service.
- **Acceptance:** Goals persist across restart and resume in-state; dependency/information edges work; split/merge supported; a suspended goal survives reboot and resumes (the Ch 17.3 "finished while you were away" test, minus real work).
- **Effort:** 3 wks. **Gate:** No goal exists without Kernel ownership; goal history is event-sourced.

### MILESTONE 4 — Deliberation, Decision, Resources, Safety  `(Ch 10, 22, 45-48, 35)`
**Objective:** Replace plan-then-execute with utility-driven next-action deliberation; add the safety boundary and resource scheduling the Kernel needs.
- **Build:** `cognition/deliberation.py`, `cognition/decision.py`, `resources/` (registry+scheduler), `safety/` (permission manager, trust zones, secret vault).
- **Acceptance:** Given a Desired World + capabilities, the engine generates candidate actions, scores by utility, picks the next single action, predicts its outcome; irreversible/dangerous actions require confirmation via the safety boundary; secrets never leave the vault.
- **Effort:** 4 wks. **Gate:** Every action has a decision record + predicted outcome; no irreversible action without policy check.

### MILESTONE 5 — Intent, Classification, Procedure Synthesis  `(Ch 7, 8, 26)` + **kill TD-1**
**Objective:** Real understanding stage; incremental procedure graphs; delete hardcoded site logic.
- **Build:** `cognition/intent.py`, `cognition/classification.py`, `cognition/procedure.py`. **Delete** `bridge.py::_target_to_url` hardcoded map; replace with generic environment discovery.
- **Acceptance:** Intent Object produced with assumption spectrum + clarification policy; goals classified into problem classes; procedures synthesized incrementally and revised mid-execution; zero hardcoded site names (the existing `test_no_site_names_in_source` extended repo-wide).
- **Effort:** 4 wks. **Gate:** No application-specific branches anywhere (Axiom 15 / Ch 63).

### MILESTONE 6 — Environment + Operation + Verification Unification  `(Ch 11, 23, 24, 29, 32, 33)`
**Objective:** Formal Environment contract; migrate browser behind it; one Verification Engine; Evidence Repository.
- **Build:** `kernel/contracts/environment.py`, `environments/browser/` (Playwright as first adapter), `capabilities/interaction.py` (keep adapter cascade), unify `verifier.py`+`evidence_law.py` → `verification/engine.py`, `verification/evidence_repo.py`. Migrate primitives/adapters.
- **Acceptance:** Browser is a plug-in implementing the Environment contract; operation is one-action-with-observation-between, event-driven, interruptible; single verification engine with prediction input; evidence is queryable.
- **Effort:** 4 wks. **Gate:** Swap a stub browser backend without touching the Kernel.

### MILESTONE 7 — Desktop Runtime, Motor, Capabilities, Exploration  `(Ch 16, 25/30/31, 66)`
**Objective:** Make "General" real — operate the desktop and unknown software.
- **Build:** `environments/desktop/` (window/display/clipboard/session managers, multi-monitor, DPI), `capabilities/motor.py` (closed-loop), `capabilities/registry.py` (handlers wired, contracts, confidence), `environments/unknown/` (Exploration Engine: object graph + affordance inference + safe-experiment ladder + demonstration recorder).
- **Acceptance:** FRIDAY operates a never-seen desktop app to a simple goal via exploration; motor actions self-correct; capabilities self-describe + report confidence.
- **Effort:** 6 wks. **Gate:** A goal completes on software with zero app-specific code.

### MILESTONE 8 — Reflection, Memory wiring, Competence, Recovery  `(Ch 13, 14, 28, 34)`
**Objective:** Close the learning loop; make the system self-aware of competence; wire the orphaned memory.
- **Build:** `cognition/reflection.py`, wire `memory/` to Kernel+Reflection, `competence/`, generalize recovery as a deliberation mode.
- **Acceptance:** Every action produces prediction error + reflection record; memories form only via reflection and measurably change behaviour; competence scores drive deliberation; recovery is re-deliberation.
- **Effort:** 4 wks. **Gate:** A repeated task shows measurable competence improvement.

### MILESTONE 9 — Learning, Temporal, Long-Horizon, Background  `(Ch 15, 42, 43, 49)`
**Objective:** Time-aware, continuously improving, can run projects across days.
- **Effort:** 5 wks. **Gate:** A multi-session goal advances while the user is away and improves on repetition.

### MILESTONE 10 — Domains as Compositions  `(Ch 37, 39, 40, 41)`
**Objective:** Research/Communication/Document/SWE depth as capability compositions (NOT agents).
- **Effort:** 6 wks. **Gate:** Each domain is pure composition over capabilities; deleting a domain leaves capabilities intact.

### MILESTONE 11 — Capability Evolution, Plugins, Benchmarks, Frontends, Federation  `(Ch 27, 47, 54, 55, 57)`
**Objective:** Self-extension, measurement, real UI, multi-device.
- **Effort:** 6+ wks. **Gate:** New capability promoted via sandbox→benchmark→rollback; API served + a thin client; a goal spans two devices via one Goal Graph.

```
Foundation ──────────► Cognition ─────────► Generality ──────► Domains ──────► Scale
 M1  M2  M3            M4  M5               M6  M7  M8         M9  M10        M11
Kernel World Goals    Delib Intent         Env Desktop Reflect  Learn Domains Evolution
Events Belief Graph   Safety Procedure     Verify Explore Mem   Time         Plugins/UI
```

---

## 10. PHASE — Recommended First Milestone (DETAILED)

**MILESTONE 1: The Kernel Foundation.** I recommend we start here and nowhere else. Justification: every FAS invariant ("everything passes through the Kernel," "nothing bypasses the World Model," "replayable cognition," "survives restart") is impossible without this substrate. Building any cognition first means rebuilding it later on top of the Kernel — pure waste.

**Scope (precise):**
1. `events/event.py` — immutable `Event` (id, logical+wall time, type, source, payload, correlation_id, parent_id, causality chain, signature).
2. `events/bus.py` — publish/subscribe/route/filter; in-process first.
3. `events/store.py` — append-only persistence + deterministic replay.
4. `kernel/clock.py` — logical clock + wall clock; total ordering.
5. `kernel/contracts/runtime.py` — the interface every future runtime implements (`initialize/tick/observe/receive/publish/checkpoint/restore/shutdown/health`).
6. `kernel/kernel.py` — owns state; exposes ONLY the Ch 20.19 API (`submitGoal/submitObservation/publishEvent/queryWorld/queryGoals/requestCapability/checkpoint/restore/shutdown/health`); runs the tick loop.
7. `kernel/checkpoint.py` — checkpoint + restore from event log.
8. One trivial demo runtime ("EchoRuntime") to prove plug-in isolation via events only.

**Acceptance criteria (all must pass):**
- A1: Kernel runs continuously through ticks; has no "stopped" state, only `shutdown()`.
- A2: 100% of state mutations are event-sourced and immutable.
- A3: Deterministic replay: replay the event log → byte-identical Kernel state. (Ch 21 Invariant 4.)
- A4: Crash/restart mid-run → `restore()` reconstructs state from last checkpoint + event replay. (Ch 17.14.)
- A5: EchoRuntime communicates with the Kernel ONLY through events — zero direct calls (Ch 52). Enforced by an import-boundary test.
- A6: Property-based tests for event ordering/causality; failure-injection test (drop/duplicate events) shows graceful degradation (Ch 17 Invariant 7).
- A7: Docs + a `benchmarks/` harness stub measuring tick latency.

**Explicitly OUT of scope for M1:** any LLM call, any browser/desktop action, any planning. M1 is pure infrastructure. This keeps it small, testable, and correct.

**What happens to existing code during M1:** Nothing is deleted. The current `operator.py` pipeline keeps working as-is (it's our reference behavior + regression oracle). We build the Kernel beside it. Migration of existing pieces (primitives, evidence law, research, browser controller) happens in M2/M6 by wrapping them as runtimes/capabilities — we reuse, not rewrite, the genuinely good parts.

---

## 11. Architect's Recommendation & Honest Challenge

You asked me to challenge decisions, not agree automatically. Here is my professional position.

### 11.1 The core decision you must make
The FAS describes a system that is **fundamentally different in kind** from what exists. This is not refactoring; it is laying a new foundation and migrating the good pieces onto it. There are three honest paths:

- **Path A — Full FAS build (foundation-first).** Build the Kernel/PCR/Events/World Model, then migrate. Highest fidelity to the Constitution. Slowest to visible features. Years of work for a solo dev. This is what the FAS literally demands.
- **Path B — Pragmatic convergence.** Keep the working pipeline as the "reference operator," build the Kernel in parallel, and incrementally route capabilities through it milestone by milestone, deleting the pipeline only when the Kernel surpasses it. Same destination as A, but you always have a working system. **This is what I recommend.**
- **Path C — Spec as aspiration.** Keep building features on the pipeline, treat the FAS as a north star, accept permanent ~20% compliance. Fastest features, but the Constitution is effectively abandoned. I do **not** recommend this — you explicitly elevated the FAS to "Constitution."

### 11.2 My recommendation: **Path B**, starting at Milestone 1.
Rationale: it honors the Constitution (we genuinely build the Kernel-centric architecture) while respecting reality (you're one person; a multi-year big-bang rewrite with nothing working in between is how projects die). The existing 802 tests and live-verified demos become the **regression oracle** that proves the Kernel-based system reaches parity before we delete the old path.

### 11.3 Challenges to assumptions in the spec itself (my job)
1. **The FAS is a multi-team, multi-year OS-grade spec.** As a solo project, attempting literal full compliance on every chapter (Federation, Robots, AR, Self-Improvement, Plugin Marketplace) risks never shipping. I recommend we treat Chapters 1-36 + 49-53 as the *binding core* and Chapters 41/44/47/54/64's Vision-2035 items as *aspirational, deferred*. I want your explicit agreement on that boundary.
2. **"No hardcoding ever" vs. bootstrapping.** Pure generality (Exploration-only, zero priors) is extremely slow and unreliable on today's models for desktop tasks. I propose a permitted, architecturally-clean exception: **learned/cached procedures and environment maps stored in Memory** (Ch 14) — which is *not* hardcoding (it's earned, confidence-scored, forgettable) and is explicitly endorsed by Ch 13.10/15. The hard rule we keep: **no application-specific code in source.** TD-1 still must die.
3. **World Model rewrite is non-negotiable but risky.** It's the highest-value, highest-churn change. I want it isolated in M2 with the snapshot kept as a fallback adapter until beliefs prove out.
4. **Don't let the legacy tree rot in place.** ~16k lines of legacy + duplicate `.git` copies create confusion and false dependencies. I recommend quarantining `legacy/` early (M1/M2) so the bridge's legacy fallbacks are explicit and deletable.

### 11.4 What I will NOT do
- I will not add features to the existing pipeline while the foundation is missing (R-1).
- I will not silently compromise an axiom; if a milestone can't be done compliantly, I'll stop and bring you an architectural option (per your Phase-4 Rule 6).
- I will not begin any implementation until you approve this audit and the roadmap.

---

## 12. Approval Gate

Before a single line of implementation, I need your decisions on:

- **D1.** Accept **Path B** (parallel Kernel build + incremental migration, pipeline as regression oracle)? Or A or C?
- **D2.** Agree to the **binding-core vs. deferred-aspirational** chapter boundary in §11.3.1?
- **D3.** Approve **Milestone 1 (Kernel Foundation)** scope and acceptance criteria in §10 as the first build?
- **D4.** Approve the **target repository structure** (§8) as the destination layout?
- **D5.** Authorize Tier-0 cleanup now (quarantine `legacy/`, remove duplicate `.git - Copy*` dirs, delete TD-1 hardcoded URLs) — these are low-risk and unblock everything?

On your approval of D1-D5, I will produce the Milestone 1 detailed design doc (contracts, event schema, module-by-module spec, test plan) — still no implementation — for one more review, then build.

**Nothing is implemented until you say go.**
