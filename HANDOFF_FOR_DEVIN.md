# FRIDAY Project — Complete Engineering Handoff for Devin

**Owner:** Shreesh (Windows, personal agent)
**Project root:** `c:\Projects\JARVIS\for wind\`
**Python:** 3.14 dev installed, target 3.12, Windows-only v1
**Run tests:** `python -m pytest tests/friday/ -q` (set `$env:PYTHONPATH="C:\Projects\JARVIS\for wind"`)
**Primary LLM:** NVIDIA NIM (`NVIDIA_API_KEY` in `.env`). Fallback: GROQ (`GROQ_API_KEY`).
**Test count at handoff:** 802 passing, 0 failing

---

## PART 1 — WHO YOU ARE AND YOUR ROLE

You are **Lead Software Architect and Principal Engineer** on the FRIDAY project.
Your role is NOT to generate code. Your role is to transform the Architecture Specification into a production-grade system while preserving EVERY architectural principle.

When implementation conflicts with the specification: **the specification wins.**

The constitution is: `FRIDAY Architecture Specification (FAS) v2.0` — it was attached in the previous conversation and is also referenced in full in `FRIDAY_ARCHITECTURE_AUDIT.md`.

---

## PART 2 — WHAT FRIDAY IS

FRIDAY is a **General Computer Operator (GCO)**. Not a chatbot, not an RPA tool, not browser automation, not a collection of specialized agents. It is defined as:

> A cognitive system that continuously perceives digital environments, understands arbitrary user goals, discovers strategies, executes them across heterogeneous software environments, verifies completion through evidence, and improves competence over time.

**Core thesis (FAS Ch 0.3):** Program the computer around GOALS, not applications. Applications are merely environments.

**The 20 Architectural Axioms (FAS Ch 3) — non-negotiable:**
1. Goals are immutable
2. Strategies are disposable
3. Observation precedes action
4. Observation never ends
5. Evidence outranks execution
6. Failure is information
7. Applications are environments
8. Capabilities are universal
9. Tasks are compositions
10. Unknown does not mean impossible
11. Every decision carries confidence
12. WorldState is reality
13. The user should never think procedurally
14. Learning changes competence, not identity
15. Generality outranks optimization
16. Time is a resource
17. Humans are part of the system
18. Every capability must be composable
19. Intelligence exists above software
20. The operator exists to reduce human cognitive load

---

## PART 3 — CURRENT STATE (what exists RIGHT NOW)

### 3.1 Repository Layout
```
c:\Projects\JARVIS\for wind\
├── friday/                    ← NEW architecture (~9,300 lines, 75+ modules)
│   ├── actions/               ← browser_controller, desktop_chrome, primitives, adapters, file_tool, system, delivery
│   ├── api/                   ← FastAPI app (DEFINED but never served — no uvicorn.run anywhere)
│   ├── capabilities/          ← web_agent.py, research.py
│   ├── config/                ← browser_config.py (per-device Chrome profile)
│   ├── learning/              ← __init__.py ONLY (8-line docstring, EMPTY)
│   ├── memory/                ← 4-tier system: working, episodic, procedural, semantic (BUILT BUT UNWIRED)
│   ├── models/                ← router.py, providers/nvidia_provider.py, providers/groq_provider.py
│   ├── perception/            ← screen.py, ocr.py, vision.py, desktop.py, browser.py, world_state.py, priority.py, types.py
│   ├── planner/               ← requirements.py, operator_planner.py, llm_decomposer.py, decomposer.py, repair.py, replanner.py, query_extractor.py, goal_parser.py
│   ├── router/                ← classifier.py, request_router.py
│   ├── tools/                 ← registry.py (ALL tools have handler=None — metadata only)
│   ├── verification/          ← evidence_law.py, verifier.py, evidence.py, screenshot_evidence.py
│   ├── bridge.py              ← routes between JARVIS/FRIDAY modes (HAS HARDCODED URLs — critical tech debt)
│   ├── core.py                ← FridayEngine (ORPHANED — not called by Operator)
│   ├── executor.py            ← GoalExecutor
│   └── operator.py            ← Operator (main pipeline entry point)
│
├── automation/                ← LEGACY (~10,387 lines) — keep quarantined
├── awareness/                 ← LEGACY (~1,659 lines) — keep quarantined
├── core/                      ← LEGACY (~3,466 lines) — keep quarantined
├── server/                    ← LEGACY remote server
├── services/                  ← LEGACY weather/maps
├── main.py                    ← LEGACY JARVIS loop — BLOCKED by default (FRIDAY_ALLOW_LEGACY_MAIN=1 to run)
├── tests/friday/              ← 802 tests, ALL mocked under FRIDAY_DRY_RUN=1
├── scripts/                   ← live_*.py validation scripts (manual only, not CI)
├── CURRENT_PROJECT_STATE.md   ← forensic audit of what works TODAY
├── FRIDAY_ARCHITECTURE_AUDIT.md ← full FAS compliance audit, traceability, roadmap
└── ROADMAP.md                 ← OLD roadmap — DISCARDED, replaced by FRIDAY_ARCHITECTURE_AUDIT.md
```

### 3.2 The Existing Pipeline (what CURRENTLY runs)

When a user submits a goal, the flow is:
```
main.py (BLOCKED) ─► FridayBridge.process(command)
                           │
                           ├─► JARVIS mode → ModelRouter.complete() → response text
                           │
                           └─► FRIDAY mode → Operator(model_router, browser_controller).run(goal)
                                   │
                                   ├─ RequirementsDiscovery.discover(goal)  ← LLM call (parallel)
                                   ├─ OperatorPlanner.plan(goal, env)       ← LLM call (parallel)
                                   │
                                   ├─ GoalExecutor.execute_plan(plan, goal)
                                   │     └─ per step: research / navigate / click / type / generate / create_file / deliver
                                   │
                                   ├─ EvidenceVerifier.verify_one(req, evidence)  ← artifact-based
                                   │
                                   ├─ RepairDiagnoser (if unmet reqs)
                                   │
                                   └─ return OperatorOutcome
```

This is **stateless** and **request-driven** — it terminates after every goal. It violates FAS Ch 17 (Persistent Runtime) and Ch 20 (Kernel) fundamentally.

### 3.3 What Actually Works (live-verified)

| Capability | Status | Evidence |
|---|---|---|
| LLM chat (NVIDIA NIM) | WORKS | Real HTTP calls, live verified |
| Requirements discovery via LLM | WORKS | qwen3-next-80b, ~1-2s |
| Goal decomposition via LLM | WORKS | LLMDecomposer → OperatorPlanner |
| DuckDuckGo search → follow links → read pages | WORKS | research.py, live verified |
| Synthesize content + citations | WORKS | executor._generate, live verified |
| Create .txt/.md/.csv/.xlsx/.docx/.html files | WORKS | file_tool.py, live verified |
| Full research+file pipeline in ~6.6s | WORKS | scripts/live_validate.py |
| CDP browser control (DEDICATED PROFILE) | WORKS | BrowserController, 19/20 live checks pass |
| observe_interactive (iframe/shadow DOM) | WORKS | 60 elements on Wikipedia |
| viewport_size with DPR | WORKS | 1048×714, DPR=1.25 on live Chrome |
| Tab management (list/switch) | WORKS | live verified |
| Scroll, click_index, fill_index | WORKS | live verified |
| Desktop control on signed-in Chrome (OCR) | WORKS | DesktopChromeController, live verified |
| Navigate via Ctrl+L in user's Chrome | WORKS | live verified |
| Web agent loop (observe→decide→act) | PARTIAL | 8 steps Wikipedia, LLM latency issue |
| Evidence Law (false completion impossible) | WORKS | EvidenceVerifier, prevents false positives |

| Capability | Status |
|---|---|
| CDP on user's signed-in Chrome (Shreesh/Profile 1) | BROKEN — Google Sync blocks it |
| Gmail/Instagram/WhatsApp via signed-in profile | BROKEN |
| Voice I/O / wake word in new architecture | NOT IMPLEMENTED |
| API server (uvicorn) | NOT STARTED |
| Frontend (desktop/mobile app) | NOT BUILT |
| Memory wired to execution | NOT WIRED |
| Learning | EMPTY MODULE |

### 3.4 Critical Known Issues (must NOT introduce more)

1. **`bridge.py::_target_to_url`** has a hardcoded dict of 11 sites (instagram, gmail, whatsapp, etc.). This VIOLATES FAS Axiom 15, Ch 39, Ch 63. Must be deleted.
2. **`friday/core.py` (FridayEngine)** is completely orphaned — never called by the Operator. Dead code.
3. **`tools/registry.py`** — all 22 registered tools have `handler=None`. The registry is metadata only; real dispatch is in executor.py's if/elif chain.
4. **`memory/`** — 4-tier memory system is fully built (Working/Episodic/Procedural/Semantic, JSON stores, NVIDIA embeddings) but `operator.py` imports none of it. Completely disconnected.
5. **`perception/desktop.py`** — requires `state_cache` from the LEGACY awareness system that is never passed in. Always returns empty elements.
6. **Two verification systems** that never interact: `evidence_law.py::EvidenceVerifier` (active, good) and `verifier.py::ActionVerifier` (orphaned with core.py).
7. **Direct method calls everywhere** violating FAS Ch 52 (no cross-runtime calls; everything through Kernel via events).

---

## PART 4 — ARCHITECTURE COMPLIANCE SCORES

From `FRIDAY_ARCHITECTURE_AUDIT.md`:

| Subsystem | FAS Chapter | Compliance | Priority |
|---|---|---|---|
| Cognitive Kernel | Ch 20 | **0%** | P0 |
| Persistent Cognitive Runtime | Ch 17 | **0%** | P0 |
| Cognitive Event System | Ch 21 | **0%** | P0 |
| World Model (beliefs) | Ch 9 | **20%** | P0 |
| Goal Lifecycle | Ch 18 | **15%** | P1 |
| Goal Graph | Ch 19 | **0%** | P1 |
| Three Cognitive Layers | Ch 6 | **30%** | P1 |
| Deliberation | Ch 10 | **25%** | P1 |
| Operation | Ch 11 | **55%** | P2 |
| Perception (unified) | Ch 12 | **30%** | P1 |
| Reflection | Ch 13 | **0%** | P1 |
| Memory (wired) | Ch 14 | **30%** | P1 |
| Learning | Ch 15 | **2%** | P2 |
| Capabilities (contract) | Ch 16 | **25%** | P1 |
| Decision Architecture | Ch 22 | **20%** | P1 |
| Environment Architecture | Ch 23 | **35%** | P1 |
| Interaction Architecture | Ch 24 | **45%** | P2 |
| Unknown Env Exploration | Ch 25/66 | **5%** | P1 |
| Procedure Synthesis | Ch 26 | **30%** | P2 |
| Competence Model | Ch 28 | **0%** | P2 |
| Browser Runtime | Ch 29 | **50%** | P2 |
| Desktop Runtime | Ch 30 | **20%** | P1 |
| Motor System | Ch 31 | **25%** | P2 |
| Verification Engine | Ch 32 | **55%** | P2 |
| Evidence System | Ch 33 | **50%** | P2 |
| Recovery Engine | Ch 34 | **30%** | P2 |
| Safety & Permission | Ch 35 | **20%** | P1 |
| Research Domain | Ch 37 | **45%** | P2 |
| Communication Domain | Ch 39 | **25%** | P2 |
| **OVERALL** | — | **~18%** | — |

---

## PART 5 — THE APPROVED DECISION (what Shreesh approved)

### Path B — Pragmatic Convergence (APPROVED)
- Build the Cognitive Kernel IN PARALLEL with the existing pipeline
- Keep the existing `operator.py` pipeline as a **regression oracle** (it keeps passing 802 tests)
- Incrementally route capabilities through the Kernel milestone by milestone
- Delete the old pipeline ONLY when the Kernel-based system surpasses it
- Do NOT do a big-bang rewrite

### Binding Core vs Deferred Aspirational (APPROVED)
- **BINDING (must implement):** FAS Ch 1-36, Ch 49-53 (Kernel, PCR, Events, World Model, Goals, Deliberation, Reflection, Memory, Learning, Capabilities, Environments, Verification, Evidence, Safety, Research, Communication, Documents, Resources, Temporal, Identity, Runtime Communication, Composition)
- **DEFERRED (aspirational, after v1):** Ch 41 (SWE domain depth), Ch 44 (Self-improvement automation), Ch 47 (Device federation), Ch 54 (Plugin marketplace), Ch 64 (Vision-2035: robots, AR, wearables)

### What must NEVER be in source code (FAS Axiom 15, Ch 63)
- No Gmail-specific logic
- No Instagram-specific logic
- No WhatsApp-specific logic
- No VS Code-specific logic
- No hardcoded site URLs
- No application-specific branches
- Only general mechanisms that work on ANY site/app

### Implementation Rules (all binding)
1. No hardcoding. Ever.
2. No application-specific logic.
3. Everything maps back to the specification.
4. Every new subsystem requires: Design + Tests + Benchmarks + Documentation + Acceptance Criteria.
5. Nothing bypasses the Kernel / World Model / Verification / Evidence / Safety.
6. If a feature cannot be implemented without violating the architecture — STOP, explain, propose architectural solution.

---

## PART 6 — WHAT TO BUILD NEXT (MILESTONE 1 — FULL SPEC)

### MILESTONE 1: The Cognitive Kernel Foundation (FAS Ch 17, 20, 21, 52)

This is the first and most critical build. **Nothing else should be touched until this is complete and its acceptance criteria pass.**

#### Why M1 first
Every FAS invariant ("everything passes through the Kernel," "replayable cognition," "survives restart," "nothing bypasses the World Model") is impossible without this substrate. Building any cognition feature first means rebuilding it again on top of the Kernel — pure waste.

#### Files to CREATE (new package: `friday/kernel/`)

```
friday/kernel/__init__.py
friday/kernel/kernel.py         ← The Kernel itself
friday/kernel/clock.py          ← Logical + wall clock
friday/kernel/scheduler.py      ← Cognitive tick loop + goal scheduling skeleton
friday/kernel/checkpoint.py     ← checkpoint() / restore() from event log

friday/kernel/contracts/__init__.py
friday/kernel/contracts/runtime.py     ← RuntimeContract interface
friday/kernel/contracts/environment.py ← EnvironmentContract interface (stub for M6)
friday/kernel/contracts/capability.py  ← CapabilityContract interface (stub for M7)
friday/kernel/contracts/sensor.py      ← SensorContract interface (stub for M6)
friday/kernel/contracts/resource.py    ← ResourceContract interface (stub for M4)

friday/events/__init__.py
friday/events/event.py          ← Immutable Event dataclass
friday/events/bus.py            ← In-process publish/subscribe/route/filter
friday/events/store.py          ← Append-only persistence + deterministic replay
```

#### What each file must do

**`friday/events/event.py`**
```python
# Immutable, frozen dataclass
@dataclass(frozen=True)
class Event:
    id: str                    # UUID4
    logical_time: int          # Lamport clock
    wall_time: float           # time.time()
    event_type: str            # e.g. "goal.created", "observation.received"
    source: str                # which runtime emitted this
    payload: dict              # immutable (use tuple/frozenset for nested)
    correlation_id: str        # groups related events
    parent_id: Optional[str]   # causality chain (None = root)
    signature: str             # sha256 of (id+type+payload+parent_id)
```
Events are immutable. Once published, they become history. New reality = new event.

**`friday/events/bus.py`**
- `publish(event: Event) -> None` — emit to all subscribers + append to store
- `subscribe(event_type_pattern: str, handler: Callable) -> str` — returns subscription_id
- `unsubscribe(subscription_id: str) -> None`
- `route(event: Event) -> List[Callable]` — finds matching handlers
- No cross-subsystem direct calls allowed — everything goes through the bus

**`friday/events/store.py`**
- Append-only log (simple: one JSON-lines file per session, path configurable)
- `append(event: Event) -> None`
- `replay(from_logical_time: int = 0) -> Iterator[Event]` — yields events in order
- `checkpoint(state: dict, at_logical_time: int) -> str` — saves state snapshot, returns path
- `load_checkpoint(path: str) -> dict` — loads saved state
- `replay_from_checkpoint(checkpoint_path: str) -> Iterator[Event]` — loads snapshot then replays subsequent events

**`friday/kernel/clock.py`**
```python
class CognitiveClock:
    _logical: int = 0
    
    def tick(self) -> int:          # increment logical clock, return new value
    def now(self) -> Tuple[int, float]:  # (logical_time, wall_time)
    def update(self, received_time: int):  # Lamport: max(local, received) + 1
```

**`friday/kernel/scheduler.py`**
- `CognitiveScheduler` — runs the tick loop
- Tick rate: adaptive (10ms min, 1000ms idle max)
- Per tick: process pending events → evaluate goals (stub for M3) → dispatch next capability (stub for M4) → run reflection queue (stub for M8)
- Runs in a dedicated daemon thread
- `start() / stop() / pause() / resume()`

**`friday/kernel/checkpoint.py`**
```python
class CheckpointManager:
    def checkpoint(self) -> str:       # save full Kernel state, return path
    def restore(self, path: str) -> None  # load state + replay events since checkpoint
    def list_checkpoints(self) -> List[str]
    def auto_checkpoint_interval_s: float = 300.0  # every 5 min by default
```

**`friday/kernel/kernel.py`** — the Kernel itself
```python
class CognitiveKernel:
    """
    The single global cognitive authority (FAS Ch 20).
    Owns: Clock, EventBus, EventStore, Scheduler, WorldModel(stub), GoalGraph(stub), Registry(stub)
    
    Public API (FAS §20.19 — ONLY these are exposed):
    """
    def submit_goal(self, goal_text: str, constraints: dict = None) -> str  # returns goal_id
    def submit_observation(self, observation: dict) -> None
    def publish_event(self, event: Event) -> None
    def query_world(self) -> dict                    # returns current world state
    def query_goals(self) -> List[dict]              # returns active goals
    def request_capability(self, capability: str, params: dict) -> str  # returns request_id
    def checkpoint(self) -> str                      # returns checkpoint path
    def restore(self, checkpoint_path: str) -> None
    def shutdown(self) -> None
    def health(self) -> dict                         # {"status": "ok"|"degraded", "tick": int, ...}
    
    # Exactly ONE Kernel instance (singleton via module-level _kernel variable)
    # Started via: kernel = CognitiveKernel(); kernel.start()
```

**`friday/kernel/contracts/runtime.py`**
```python
from abc import ABC, abstractmethod

class RuntimeContract(ABC):
    """Every future runtime (Browser, Desktop, Memory, etc.) must implement this."""
    
    @abstractmethod
    def initialize(self, kernel: 'CognitiveKernel') -> None: ...
    
    @abstractmethod  
    def tick(self, logical_time: int) -> None: ...
    
    @abstractmethod
    def observe(self) -> List[dict]: ...          # returns raw observations
    
    @abstractmethod
    def receive(self, event: Event) -> None: ...  # handle an incoming event
    
    @abstractmethod
    def publish(self, event: Event) -> None: ...  # emit an event (goes through Kernel)
    
    @abstractmethod
    def checkpoint(self) -> dict: ...             # return serializable state
    
    @abstractmethod
    def restore(self, state: dict) -> None: ...
    
    @abstractmethod
    def shutdown(self) -> None: ...
    
    @abstractmethod
    def health(self) -> dict: ...
```

#### Demo Runtime (proves isolation)
Create `friday/kernel/echo_runtime.py`:
- Implements `RuntimeContract`
- On `tick()`: emits `Event(event_type="echo.tick", payload={"count": n})`
- On `receive(event)`: if `event.event_type == "echo.request"`, replies with `Event(event_type="echo.response")`
- CRITICAL: **must communicate with the Kernel ONLY through the event bus** — zero direct method calls to other subsystems

#### M1 Acceptance Criteria (ALL must pass before M2 starts)

- **A1:** Kernel runs continuously through ticks with no "stopped" state, only `shutdown()`.
- **A2:** 100% of state mutations are event-sourced. Every event is immutable (frozen dataclass, try to mutate → TypeError).
- **A3:** Deterministic replay: take a running Kernel, kill it mid-run, restart, `restore(checkpoint_path)`, replay events since checkpoint → exact same state. Write a test that asserts `state_before == state_after_replay`.
- **A4:** Crash/restart scenario test passes.
- **A5:** EchoRuntime communicates with the Kernel ONLY through events — add an import-boundary test using `ast.parse` / `importlib` that asserts EchoRuntime has zero imports from any other `friday/` module except `friday/events/` and `friday/kernel/contracts/`.
- **A6:** Property-based tests (Hypothesis) for: event ordering (logical time monotonically increasing), causality (parent_id always refers to a previously emitted event), signature integrity (tampered event fails verification).
- **A7:** Failure injection: drop 10% of events → `health()` reports degraded but Kernel keeps running (no crash).
- **A8:** Benchmark: tick loop sustains 100 ticks/s with EchoRuntime connected (measure with `time.perf_counter`).

#### What NOT to do in M1
- Do NOT touch `operator.py`, `executor.py`, `bridge.py`, `planner/`, `capabilities/`, `memory/` — leave them working exactly as-is
- Do NOT integrate with LLMs
- Do NOT touch the browser or desktop
- Do NOT start building the World Model yet (that's M2)

---

## PART 7 — FULL 11-MILESTONE ROADMAP

### MILESTONE 1 — Kernel Foundation (FAS Ch 17, 20, 21, 52)
- **Effort:** 3-4 weeks
- **Build:** `friday/kernel/`, `friday/events/`
- **Gate:** A3 deterministic replay passes. No subsystem calls another directly.

### MILESTONE 2 — World Model as Beliefs (FAS Ch 9, 12 partial)
- **Effort:** 3 weeks
- **Build:** `friday/world/` (world_model.py, belief.py, objects.py, worlds.py)
- Replace `perception/world_state.py` snapshot with a living belief store owned by the Kernel
- One sensor (ScreenCapture) emits Observations → fusion → Beliefs with confidence
- **Gate:** Beliefs carry confidence/source/timestamp/expiry; temporal decay works; Observed/Desired worlds representable; no raw sensor data read outside Perception.

### MILESTONE 3 — Goals & Goal Graph (FAS Ch 18, 19, 51)
- **Effort:** 3 weeks
- **Build:** `friday/goals/` (goal.py with state machine, graph.py with typed edges)
- Goal object with 11 states: Created→Understood→Specified→Deliberating→Executing→Waiting→Recovering→Verifying→Completed/Failed/Cancelled
- Goals persist across restart, resume in-state
- **Gate:** A suspended goal survives a simulated reboot and resumes in the correct state (the "finished while you were away" test).

### MILESTONE 4 — Deliberation, Decisions, Resources, Safety (FAS Ch 10, 22, 45-48, 35)
- **Effort:** 4 weeks
- **Build:** `friday/cognition/deliberation.py`, `friday/cognition/decision.py`, `friday/resources/`, `friday/safety/` (permission manager, trust zones, secret vault replacing plaintext .env)
- Replace plan-then-execute with utility-driven next-action selection
- Every decision: generate candidates → score by utility (benefit − risk − cost − uncertainty) → pick one → predict outcome → record decision
- Irreversible/dangerous actions require confirmation via safety boundary
- **Gate:** Every action has a decision record + predicted outcome; no irreversible action without policy check.

### MILESTONE 5 — Intent, Classification, Procedure Synthesis + Kill TD-1 (FAS Ch 7, 8, 26)
- **Effort:** 4 weeks
- **Build:** `friday/cognition/intent.py`, `friday/cognition/classification.py`, `friday/cognition/procedure.py`
- **DELETE** `bridge.py::_target_to_url` hardcoded URL map — replace with generic environment discovery
- Incremental procedure graphs, not fixed step lists
- **Gate:** Zero hardcoded site names anywhere in `friday/` (extend the existing `test_no_site_names_in_source` test to be repo-wide).

### MILESTONE 6 — Environment Contract, Browser Runtime, Unified Verification (FAS Ch 11, 23, 24, 29, 32, 33)
- **Effort:** 4 weeks
- **Build:** `friday/kernel/contracts/environment.py`, `friday/environments/browser/` (Playwright as first adapter behind contract), unify `verifier.py` + `evidence_law.py` → `friday/verification/engine.py`, `friday/verification/evidence_repo.py`
- Keep the existing BrowserController as the Playwright adapter — don't rewrite it, wrap it
- **Gate:** Swap a stub browser backend without touching the Kernel. Single verification engine with prediction input.

### MILESTONE 7 — Desktop Runtime, Motor System, Capabilities, Exploration (FAS Ch 16, 25, 30, 31, 66)
- **Effort:** 6 weeks
- **Build:** `friday/environments/desktop/` (window/display/clipboard/session managers, multi-monitor, DPI-aware), `friday/capabilities/motor.py` (closed-loop), `friday/capabilities/registry.py` (handlers wired, contracts, confidence), `friday/environments/unknown/` (Exploration Engine: object graph + affordance inference + safe-experiment ladder + human demonstration recorder)
- **Gate:** A goal completes on software FRIDAY has never seen, using ZERO app-specific code.

### MILESTONE 8 — Reflection, Memory Wiring, Competence, Recovery (FAS Ch 13, 14, 28, 34)
- **Effort:** 4 weeks
- **Build:** `friday/cognition/reflection.py`, wire existing `friday/memory/` to Kernel+Reflection, `friday/competence/`
- The existing memory modules are good — just wire them
- **Gate:** A repeated task shows measurable competence improvement (lower latency or higher success rate, measured by the benchmark harness).

### MILESTONE 9 — Learning, Temporal, Long-Horizon, Background (FAS Ch 15, 42, 43, 49)
- **Effort:** 5 weeks
- **Gate:** A multi-session goal advances while the user is away and improves on repetition.

### MILESTONE 10 — Domain Depth as Compositions (FAS Ch 37, 39, 40, 41)
- **Effort:** 6 weeks
- Research + Communication + Document + SWE as pure capability compositions, NOT agents
- **Gate:** Deleting a domain module leaves capabilities intact (no capability code lives in domain modules).

### MILESTONE 11 — Evolution, Plugins, Benchmarks, Frontends, Federation (FAS Ch 27, 47, 54, 55, 57)
- **Effort:** 6+ weeks
- Capability Evolution (sandbox→benchmark→promote→rollback), Plugin system, FastAPI finally served, thin client, multi-device Goal Graph

---

## PART 8 — ENVIRONMENT SETUP

### Install
```powershell
cd "C:\Projects\JARVIS\for wind"
python -m venv .venv312
.venv312\Scripts\activate
pip install -r requirements-312.txt
pip install hypothesis  # already installed (6.155.7)
```

### Environment Variables (`.env` at project root)
```
NVIDIA_API_KEY=<required for LLM>
GROQ_API_KEY=<optional fallback>
FRIDAY_DRY_RUN=0          # set to 1 in tests (auto-set by conftest.py)
FRIDAY_REQUIRE_REAL_CHROME=0
AUTO_LAUNCH_CHROME=0
FRIDAY_ALLOW_LEGACY_MAIN= # leave empty = BLOCKED
CHROME_REMOTE_DEBUG_PORT=9222
```

### Chrome Profile Config (Shreesh's device)
```json
// ~/.friday/config.json
{"chrome_profile": "Shreesh"}
```
This resolves to: `C:\Users\Shreesh\AppData\Local\Google\Chrome\User Data` / `Profile 1`
**CDP is blocked on this profile by Google Sync.** The workaround is:
1. CDP on dedicated profile (works perfectly, no logins)
2. Desktop OCR control on the signed-in profile (works, built)

### Run tests
```powershell
$env:PYTHONPATH = "C:\Projects\JARVIS\for wind"
python -m pytest tests/friday/ -q
# Expected: 802 passed
```

### Run a live validation (Chrome must be closed first for CDP)
```powershell
$env:PYTHONPATH = "C:\Projects\JARVIS\for wind"
python scripts/live_validate_hardening.py   # CDP dedicated profile, 19/20 pass
python scripts/live_desktop_agent.py        # OCR on signed-in Chrome (Chrome must be open)
python scripts/live_web_agent.py            # web agent on Wikipedia
```

---

## PART 9 — KEY FILES DEVIN MUST READ BEFORE ANYTHING

Read these files IN THIS ORDER before touching anything:

1. **`FRIDAY_ARCHITECTURE_AUDIT.md`** — the complete FAS compliance audit, traceability matrix, technical debt, risk assessment, and full roadmap
2. **`CURRENT_PROJECT_STATE.md`** — forensic audit of exactly what works today, 50-task benchmark, test analysis
3. **`friday/operator.py`** — the main pipeline entry point (to understand what currently runs)
4. **`friday/executor.py`** — the execution engine (understand _execute_step if/elif dispatch)
5. **`friday/actions/browser_controller.py`** — the best-built runtime (~710 lines, live-verified)
6. **`friday/verification/evidence_law.py`** — the Evidence Law (the genuinely excellent piece — understand before touching verification)
7. **`friday/capabilities/web_agent.py`** — the generic observe→decide→act loop (closest thing to deliberation in the codebase)
8. **`friday/memory/controller.py`** — the built-but-orphaned memory system
9. **`friday/bridge.py`** — note the hardcoded URL map (TD-1, must be deleted in M5)
10. **`friday/core.py`** — orphaned FridayEngine (understand it's dead, don't use it)

---

## PART 10 — WHAT DEVIN MUST NOT DO

- Do NOT touch `operator.py`, `executor.py`, `bridge.py`, `planner/`, `capabilities/`, `memory/`, `actions/`, `verification/` during M1
- Do NOT add features to the existing pipeline
- Do NOT add site-specific logic (no Gmail/Instagram/WhatsApp handlers)
- Do NOT hardcode any site names, URLs, or application names
- Do NOT reduce the test count below 802 (the existing tests are the regression oracle)
- Do NOT delete legacy code yet (quarantine is enough for now; deletion comes after M6+ migration)
- Do NOT serve the API (`friday/api/`) — it stays defined but unserved until M11
- Do NOT assume the existing `WorldState` is the World Model — it's a snapshot (see M2)
- Do NOT call memory/reflection/learning subsystems from the Kernel until those milestones complete
- Do NOT write a single line of implementation before the M1 design is reviewed by Shreesh

---

## PART 11 — TECHNICAL DEBT TO ELIMINATE (ordered by priority)

| ID | Where | What | When to fix |
|---|---|---|---|
| TD-1 | `bridge.py::_target_to_url` | HARDCODED site URL dict — delete entirely | M5 |
| TD-2 | `bridge.py` vs `executor.py` | Two parallel execution paths | M6 (migrate to Kernel) |
| TD-3 | `verifier.py` (orphaned) | Merge into unified verification engine | M6 |
| TD-4 | `core.py` (FridayEngine) | Orphaned — delete after M6 |  M6 |
| TD-5 | `tools/registry.py` | All handlers None — wire real handlers | M7 |
| TD-6 | `memory/` | Built but unwired — wire to Kernel | M8 |
| TD-7 | `perception/desktop.py` | Needs legacy state_cache — fix in Desktop Runtime | M7 |
| TD-8 | Direct cross-subsystem calls | Everything — migrate to events | M1→M6 gradually |
| TD-9 | `.env` secrets plaintext | No vault — build Secret Vault | M4 |
| TD-10 | 802 tests all mocked | Add goal/replay/failure injection tests | Every milestone |
| TD-11 | API never served | `uvicorn.run` absent — wire in M11 | M11 |
| TD-12 | `.git - Copy`, `.git - Copy (2)` | Delete these directories | Now (low risk) |

---

## PART 12 — ARCHITECTURE PRINCIPLES TO ENFORCE IN CODE REVIEW

Every PR must be checked against:
- [ ] Does any new module import directly from another subsystem without going through events/contracts? (FAIL if yes)
- [ ] Does any code path hardcode a site name, URL, or application name? (FAIL if yes)  
- [ ] Does any capability assume a specific environment (e.g., "this is Chrome", "this is Gmail")? (FAIL if yes)
- [ ] Does the change have unit tests? Goal-completion tests? (FAIL if no)
- [ ] Can the implemented module be replaced independently without touching the Kernel? (MUST be YES)
- [ ] Does every significant action have a predicted outcome? (Required by M4+)
- [ ] Does the change trace back to a specific FAS chapter? (Document it in the PR)
- [ ] Would this still work if we replaced the LLM with a future model? (Must be YES)
- [ ] Would this still work in 5 years? (Must be YES)

---

## PART 13 — WHAT GOOD LOOKS LIKE AT END OF M1

After Milestone 1 is complete, Devin (or the next engineer) should be able to:

1. Start the Kernel: `from friday.kernel import CognitiveKernel; k = CognitiveKernel(); k.start()`
2. Publish a goal event and see it logged: `k.publish_event(Event(event_type="goal.created", ...))`
3. Kill the process, restart, call `k.restore(checkpoint_path)`, and see identical state
4. Run `python -m pytest tests/friday/ -q` and still get 802+ passing (the old pipeline untouched)
5. Run the replay test: `python -m pytest tests/kernel/ -q` — all acceptance criteria pass
6. See in a benchmark: tick loop sustains 100+ ticks/second

The old pipeline is STILL the demo-able system. The Kernel is running in parallel, not yet doing anything useful. That's correct for M1.

---

## PART 14 — FINAL CHECKLIST BEFORE STARTING

- [ ] Read the full `FRIDAY_ARCHITECTURE_AUDIT.md` (every section)
- [ ] Read the full `CURRENT_PROJECT_STATE.md` (every section)
- [ ] Read all 10 key files listed in Part 9
- [ ] Run `python -m pytest tests/friday/ -q` and confirm 802 passing
- [ ] Run `python scripts/live_validate_hardening.py` (Chrome closed first) and confirm 19/20 pass
- [ ] Confirm M1 scope and acceptance criteria (Part 6) with Shreesh before writing code
- [ ] Create `friday/kernel/` package with empty `__init__.py` to claim the namespace
- [ ] Set up `tests/kernel/` test directory with its own `conftest.py`
- [ ] Begin with `friday/events/event.py` (the most foundational piece — everything else depends on it)

**Starting point: `friday/events/event.py`. Write the immutable Event dataclass first.**
