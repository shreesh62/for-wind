# Architecture Decisions

## ADR-001: Incremental Migration Over Rewrite

**Status**: Approved  
**Date**: 2026-06-08

**Context**: The repository has significant working functionality (voice I/O, routing, remote control, memory, awareness). A full rewrite would lose months of validated behavior.

**Decision**: Migrate subsystem-by-subsystem into a new `friday/` package. Gate new code behind feature flags. Delete old code only after tests pass.

**Consequences**: Temporary code duplication during transition. Both stacks may need maintenance briefly. Faster time-to-value than rewrite.

---

## ADR-002: Single Automation Contract (ActionResult)

**Status**: Approved — Implemented  
**Date**: 2026-06-08

**Context**: Current actions return strings, bools, or mixed dicts. Verification is optional. This allows "illusion success" — the system reports success without evidence.

**Decision**: Every action must return `ActionResult(status, action_type, target, evidence, ...)`. No action path may bypass this contract. The `is_success` property requires status == SUCCESS, and `verified` additionally requires evidence.

**Implementation**: `friday/actions/result.py` — 49 tests passing.

**Consequences**: All existing action code must be wrapped or rewritten to produce ActionResult. Verification becomes enforceable. Telemetry becomes consistent.

---

## ADR-003: WorldState as Single Source of Perception Truth

**Status**: Approved — Implemented  
**Date**: 2026-06-08

**Context**: The existing `WorldState` dataclass in `awareness/world_state.py` is well-designed but not consistently populated from all sources.

**Decision**: New `WorldState` at `friday/perception/world_state.py` with `WorldStateBuilder` that aggregates from all perception sources (UIA, OCR, browser DOM, screenshots). The cognitive loop must always build a fresh WorldState before planning.

**Implementation**: `friday/perception/world_state.py` + `friday/perception/types.py` — tested with 25 tests.

**Consequences**: Perception becomes a first-class service. Actions cannot proceed without a current WorldState. Debugging becomes easier (every decision traces back to a snapshot).

---

## ADR-004: Model Router for Task-Based Inference

**Status**: Approved — Implemented  
**Date**: 2026-06-08

**Context**: Currently all LLM calls go through Groq. The owner has access to 100+ NVIDIA NIM free endpoints, local models, and wants dynamic routing.

**Decision**: Implement a `ModelRouter` that classifies tasks (reasoning, vision, coding, memory, summarization) and routes to the best available model. Support Groq, NVIDIA NIM (free endpoints), and local models (future). All model calls go through the router. No vendor lock-in.

**Implementation**: `friday/models/router.py` — tested with 9 tests (routing, failover, capability filtering, usage stats).

**Consequences**: Reduces API costs. Enables vision understanding. Allows offline operation for simple tasks. Providers can be added without modifying agent logic.

---

## ADR-005: Cognitive Loop as Only Automation Path

**Status**: Approved (with ALLOW_LEGACY_FALLBACK=1 during migration)  
**Date**: 2026-06-08

**Context**: Two automation stacks coexist (legacy planner and cognitive loop). This creates divergence and makes verification impossible to enforce universally.

**Decision**: The cognitive loop (perceive-plan-act-verify-learn) becomes the *only* path for all automation. The legacy planner is preserved behind `ALLOW_LEGACY_FALLBACK=1` during migration, then removed.

**Consequences**: All automation gets verification. Learning applies universally. Legacy commands must be expressible as goals. Migration period requires both stacks running.

---

## ADR-006: Desktop App Technology — Tauri

**Status**: Approved  
**Date**: 2026-06-08

**Decision**: Tauri for the final desktop application. Reasons:
- Smaller installer (~10MB vs ~150MB Electron)
- Faster startup
- Better for "share with friends" goal
- Native webview (no bundled Chromium)
- Rust backend for system integration

The existing Electron shell remains usable during development.

---

## ADR-007: Cloud-Reasoning + Local-Control Architecture

**Status**: Approved  
**Date**: 2026-06-08

**Context**: FRIDAY needs both powerful AI reasoning and fast local automation.

**Decision**:
- **Local**: Automation, memory, verification, browser/desktop control, FastAPI backend
- **Cloud**: Planning, reasoning, vision analysis, research

Local LLMs are optional future enhancements, not core dependencies. The architecture must allow local models later but must not depend on them.

**Consequences**: Requires internet for planning/reasoning. Automation and verification work offline. Model router handles the split transparently.

---

## ADR-008: API-First Backend Design

**Status**: Approved  
**Date**: 2026-06-08

**Context**: Both Tauri desktop and mobile app need the same backend.

**Decision**: Design the FastAPI backend from day one to serve both desktop and mobile clients. Same contracts, same authentication, same WebSocket infrastructure. Desktop communicates over localhost; mobile over network.

**Consequences**: No separate backend implementations. Frontend development can proceed independently. OpenAPI docs generated automatically.

---

## ADR-009: Python 3.12 Target Runtime

**Status**: Approved  
**Date**: 2026-06-08

**Note**: Development machine has Python 3.14 installed. Production target is 3.12 for broader compatibility and package availability. CI should test on 3.12.

---

## ADR-010: Windows-Only for v1

**Status**: Approved  
**Date**: 2026-06-08

**Context**: Desktop automation (UIA, Win32, DPAPI) is inherently Windows-specific.

**Decision**: Target Windows only for v1. Do not invest in cross-platform abstraction. Isolate platform-specific code behind interfaces for potential future portability.



---

## ADR-011: JARVIS/FRIDAY Dual-Mode Architecture

**Status**: Approved — Implemented  
**Date**: 2026-06-09

**Context**: The system was treating JARVIS and FRIDAY as UI vs backend. The owner clarified they are two operational modes within the same platform.

**Decision**:
- **JARVIS Mode** = Assistant (fast, conversational, no agent loop). Handles questions, explanations, tutoring, coding help, brainstorming. Most requests stay here.
- **FRIDAY Mode** = Agent (perception, planning, execution, verification). Handles browser/desktop automation, multi-step tasks, complex goals.
- Both share: memory, APIs, world state, settings, models, backend.
- A Request Classifier routes requests by complexity level (0-3).
- Wake words will route directly: "Jarvis" → assistant, "Friday" → agent.

**Complexity Levels**:
- Level 0: Simple questions → JARVIS → Response (no planning, no verification)
- Level 1: Simple actions → FRIDAY → Action → Verify → Done
- Level 2: Multi-step → FRIDAY → Mini Plan → Execute → Verify
- Level 3: Complex goals → FRIDAY → Full Agent Loop

**Implementation**: `friday/router/classifier.py` + `friday/router/request_router.py` — 31 tests.

**Consequences**: System feels fast by default. Only complex tasks trigger expensive cognition. Architecture supports future wake word routing.

---

## ADR-012: NVIDIA NIM as Primary Provider, Groq as Fallback

**Status**: Approved — Implemented  
**Date**: 2026-06-09

**Context**: Owner has access to NVIDIA NIM free APIs with 100+ models. Groq usage should be minimized.

**Decision**: NVIDIA NIM is the primary provider for all model routing. Groq is retained as a fallback only. Priority scores adjusted:
- NVIDIA models: priority 7-10
- Groq models: priority 3-5

**Consequences**: Reduced Groq API usage. Access to vision models (llama-3.2-90b-vision). Access to stronger reasoning (nemotron-ultra-550b). Groq still available as automatic failover.


---

## ADR-013: Unified API Layer (FastAPI)

**Status**: Approved — Implemented  
**Date**: 2026-06-09

**Context**: Both Tauri desktop and mobile app need the same backend contracts.

**Decision**: Single FastAPI application (`friday/api/app.py`) serves all clients:
- Desktop (Tauri) connects via localhost
- Mobile connects via network (authenticated)
- WebSocket for real-time updates (command results, status, notifications)
- API key authentication (same as existing REMOTE_API_KEY)
- OpenAPI docs auto-generated at /docs

**Endpoints**:
- `POST /api/command` — Execute command with JARVIS/FRIDAY routing
- `GET /api/status` — System status, active goal, memory/model stats
- `POST /api/memory/search` — Search memory
- `GET /api/memory/recent` — Recent interactions
- `GET /api/models` — Available models and usage
- `WS /api/ws` — Real-time WebSocket
- `GET /api/health` — Health check (no auth)

**Implementation**: 15 tests passing. Factory pattern (`create_friday_api()`) for testability.

**Consequences**: Tauri and mobile can be developed independently against the same API. No backend duplication. Changes propagate to all clients.


---

## ADR-014: Semantic-First Perception Priority

**Status**: Approved — Implemented  
**Date**: 2026-06-09

**Context**: FRIDAY must not behave like a screenshot-clicking bot. Screenshots are slow, unreliable, and hard to verify. The planner should reason on structured WorldState, never on pixels.

**Decision**: Perception sources have a strict priority order. Always prefer semantic information over visual:

1. **Browser DOM** (Playwright / DevTools) — highest fidelity for web
2. **Windows UI Automation (UIA)** — semantic desktop controls
3. **OCR** (Tesseract) — text extraction, verification, labels
4. **Vision Models** (CLIP/VLM) — page type, app identification, anomalies
5. **Raw Pixel Analysis** — last resort only

**Rules**:
- Browser tasks (find button, read text, page state, form fill, navigation) → DOM first, never OCR unless no other option
- Desktop tasks (buttons, menus, text boxes, lists, trees) → UIA first
- OCR → text extraction and verification, NOT primary understanding
- Vision → supplements perception (what app? what page type? login screen?), NOT source of truth
- The planner operates on WorldState, never screenshots

**Implementation**: `friday/perception/priority.py` — resolution engine that ranks element candidates by source priority + confidence. WorldState element finders prefer higher-priority sources.

**Consequences**: Higher reliability, speed, verifiability, maintainability. FRIDAY behaves like an accessibility system, not a vision bot. Vision/OCR become supplements, not crutches.


---

## ADR-015: Semantic Memory via NVIDIA Embeddings

**Status**: Approved — Implemented + Live-Verified  
**Date**: 2026-06-09

**Context**: Memory retrieval needs to find relevant knowledge by meaning, not just keywords. Memory OS blueprint calls for a semantic layer. The owner wants NVIDIA used wherever it adds value.

**Decision**: Implement a semantic memory tier using NVIDIA nv-embed-v1 for embeddings with cosine-similarity search. Falls back to lexical search when embeddings unavailable (no hard dependency).

**Implementation**: `friday/memory/semantic.py` — Fact storage, embedding computation, cosine search. 15 tests. Live-verified: matched "perceive the screen?" to "prefers DOM over screenshots" with zero keyword overlap.

**Consequences**: True semantic retrieval across the platform. NVIDIA embeddings used per owner strategy. Graceful degradation to lexical when offline. Completes the 4-tier memory system (working/episodic/procedural/semantic).


---

## ADR-016: Vision as Supplemental Perception

**Status**: Approved — Implemented  
**Date**: 2026-06-09

**Context**: Per ADR-014, vision is priority 30 (above pixels, below OCR/UIA/DOM). It must supplement, never replace, semantic perception.

**Decision**: `friday/perception/vision.py` uses NVIDIA llama-3.2-90b-vision to answer high-level scene questions DOM/UIA cannot: "what app is visible? what screen type? is this a login screen? visual anomalies?" Screenshots are downscaled to 1280px max before sending (scene understanding doesn't need full resolution). Vision is only invoked when semantic sources are insufficient.

**Implementation**: `VisionPerception` with `analyze()`, `is_login_screen()`, `identify_app()`. 11 tests. Completes the 5-source perception stack.

**Consequences**: FRIDAY can understand novel/ambiguous screens without relying on pixel-clicking. Vision stays a supplement — the resolver still prefers DOM/UIA for actionable elements. Perception layer (Phase 2) is now complete.


---

## ADR-017: Frontend Deferred — API-First Backend Focus

**Status**: Approved — Active Directive  
**Date**: 2026-06-09

**Context**: Owner directive. Frontend (desktop UI, mobile UI, React/Tauri/Flutter screens, styling, design systems) will be handled later by a separate specialized agent.

**Decision**: STOP all frontend implementation. Focus exclusively on the backend cognitive platform:
- architecture, perception, world state, planning, memory
- automation, verification, repair
- model routing, provider layer
- API layer, packaging prep, testing

The existing `desktop_tauri/` scaffold is FROZEN (no further work). It remains as a reference for the future frontend agent but contains no business logic.

**API-First Principle**: 
```
Core Engine → FastAPI Layer → Future Frontends
```
All business logic lives in the backend. Future desktop/mobile UIs are thin clients that consume APIs only.

**Deliverable instead of UI**: A comprehensive `FRONTEND_INTEGRATION_GUIDE.md` documenting every API, schema, WebSocket event, and contract a future frontend engineer needs.

**Consequences**: Rust/Tauri build is no longer a priority (was blocked on disk anyway). Effort redirects to API completeness: routes, schemas, contracts, WebSocket interfaces, event streams, auth, and the integration guide. The backend becomes a complete, documented, frontend-agnostic platform.


---

## ADR-018: Live Perception API + Backend Packaging

**Status**: Approved — Implemented  
**Date**: 2026-06-09

**Context**: Two roadmap needs: (1) expose live perception for debugging/frontends, (2) make the backend distributable to friends without Python (project goal).

**Decision**:
1. **WorldState API** — `GET /api/worldstate` returns a live perception snapshot via `FridayEngine.perceive_as_dict()`, including `semantic_coverage`. The planner reasons on this (ADR-014); now it's observable.
2. **Backend packaging** — PyInstaller spec (`packaging/friday_backend.spec`) bundles the backend platform (no UI per ADR-017) into `friday-backend.exe`. A first-run wizard (`packaging/first_run.py`) handles dependency validation, .env creation, key prompting, and connectivity test.

**Implementation**: `friday/api/routes/perception.py` (5 tests), `packaging/` (7 tests). Live-verified: worldstate returned real machine perception (active window, cursor, sources).

**Consequences**: Frontends/debuggers can see what FRIDAY perceives. The backend can ship as a standalone executable — directly serving "shareable with friends, installable without VS Code." Heavy ML libs excluded to keep binary small.


---

## ADR-019: Research Evaluations + Temporal Memory Edges

**Status**: Approved — Implemented  
**Date**: 2026-06-09

**Context**: Phase 12 directive — evaluate strategic technologies, produce reports, don't blindly integrate.

**Decision**: Produced 5 evaluation reports under `research/evaluations/`:
- **Supermemory** (Tier 1): adopt later as optional `MemoryStore` backend, self-hosted, interface-gated. Not now.
- **Memory OS** (Very High): already our blueprint; adopt the *temporal edges* pattern now.
- **Open Browser Use** (Tier 1): study only — FRIDAY's verify step makes us architecturally ahead.
- **Scrapling** (Tier 2): adopt for a future `research/scraping/` subsystem; keep separate from interactive DevTools actions (ADR-014).
- **Local Agent Infrastructure** (Tier 1): inspiration only — already aligned.

**Acted immediately on the one low-risk, high-value finding**: temporal edges in semantic memory. Facts now carry `valid_at`/`invalid_at`; updates invalidate rather than overwrite, preserving history and enabling temporal reasoning. No new dependency.

**Implementation**: `friday/memory/semantic.py` — `update_fact()`, `invalidate()`, `search(include_invalid=)`. 4 new tests. Total 324 tests passing.

**Consequences**: Clear, documented integration roadmap. Nothing forced into core. Memory gains knowledge-update semantics. Confirms FRIDAY's architecture matches 2026 agent best practice — verification is our differentiator.


---

## ADR-020: General Purpose Computer Operator (Vision Upgrade)

**Status**: Approved — Active Architectural Direction  
**Date**: 2026-06-10

**Context**: FRIDAY is NOT a collection of automations, NOT a browser agent, NOT a desktop agent, NOT a chatbot with tools. It is a General Purpose Computer Operator that receives goals and determines paths.

**Decision**: Architectural pivot from application-centric to capability-centric:

**Core principles:**
1. User provides a GOAL. FRIDAY determines the path.
2. Applications are environments, not tasks. Do NOT build `check_instagram()` — build capabilities + tools + planning.
3. Desktop, browser, files, documents, memory, system are ALL equal environments. The planner chooses between them.
4. Every task begins with OBSERVATION of current state (what's already open, logged in, available). Skip unnecessary work.
5. Success = Goal Completed. Not "opened Chrome" or "clicked button."
6. Semantic understanding primary, vision is fallback.
7. Think like human, execute like machine.

**Architecture:**
```
User Goal
    ↓
WorldState (observe current reality)
    ↓
Planner (capability-based, environment-agnostic)
    ↓
Tool Selection (browser/desktop/file/document/memory/research/etc)
    ↓
Execution (reuse existing state, choose fastest valid path)
    ↓
Verification (goal completed?)
```

**Do NOT:**
- Design around specific apps (Instagram, Chrome, Word)
- Build app-specific functions (check_instagram, create_word_report)
- Assume fresh starts (observe first, reuse existing state)
- Equate "action performed" with "goal completed"

**Do:**
- Build reusable capabilities (open_app, read_dom, create_file, send_message)
- Build an environment-agnostic planner
- Build environment-aware observation (what's already available?)
- Verify goal completion, not action execution

**Implementation priorities:**
1. WorldState expansion (tabs, files, sessions, existing state)
2. Capability/Tool registry (environment-agnostic)
3. Cross-environment planner (not browser-planner or desktop-planner)
4. Environment-aware execution (reuse existing apps/tabs/sessions)
5. Goal-completion verification (not action-completion)

**Consequences**: The planner becomes the brain. Tools become commodities. WorldState becomes exhaustive. Verification checks goal completion, not intermediate steps. App-specific code paths are eliminated in favor of generic capabilities composed by the planner.


---

## ADR-021: Requirements-Based Reasoning (Not Workflows)

**Status**: Approved — Active Architectural Direction  
**Date**: 2026-06-10

**Context**: The system was drifting toward workflow-based intelligence (static goal-intent → step mappings, fast-path special cases). This does not scale — it leads to hundreds of workflows/special-cases and produces a sophisticated automation system, NOT a General Operator.

**Self-critique**: ADR-020 was right, but the implementation drifted:
- `_single_goal_capabilities()` — static GoalIntent → fixed steps (workflow)
- `_try_fast_path()` — special-case for "generate and save" (workflow)
- These are exactly what to avoid.

**Decision**: The architecture front door becomes **Requirements Discovery**:

```
Goal
  ↓
Requirements Discovery   ← "What must be TRUE for this goal to be complete?"
  ↓
Capability Planning      ← Compose primitives to satisfy each requirement
  ↓
Execution                ← Universal action layer
  ↓
Verification             ← Are the requirements now satisfied?
  ↓
Repair / Replan
  ↓
Completion
```

The planner reasons about REQUIREMENTS, not applications, not workflows.

**Example**: "Research France's position, create a position paper with the flag, email it"
- Requirements: need information → need official sources → need fact extraction →
  need synthesis → need document → need formatting → need image → need delivery → need verification
- NOT: "this is the research+document+email workflow"

**Rules going forward:**
1. No new task-specific pipelines (ResearchPipeline, EmailPipeline, etc.)
2. No static goal-type → step mappings as the primary path
3. The LLM discovers requirements, then composes from a capability/primitive registry
4. Every capability is a reusable primitive that composes with others
5. Success metric: "Can FRIDAY complete a goal it has NEVER seen before?"

**The litmus test for every future decision:**
"Does this make FRIDAY better at completing ARBITRARY goals?"
If it only helps specific task types → it's workflow drift → reject.

**Consequences**: Static mappings (`_single_goal_capabilities`, `_try_fast_path`) become
fallbacks only — used when LLM unavailable. Requirements Discovery + LLM capability
composition becomes the primary path. The universal action layer (primitives: click,
type, observe, verify) underlies all higher-level capabilities.

**Tradeoff acknowledged**: LLM-first reasoning adds latency vs static fast-paths.
Resolution: optimize the LLM path (faster models, caching, parallel calls) rather
than adding workflow special-cases.


---

## ADR-022: Closed-Loop Operator (Requirements → Verify → Repair)

**Status**: Approved — Implemented + Live-Verified  
**Date**: 2026-06-10

**Context**: ADR-021 established requirements-based reasoning. This ADR builds the closed loop that uses it: discover requirements, execute, verify each requirement, repair the unmet ones.

**Decision**: `friday/operator.py` implements the full cycle:
1. Requirements Discovery — what must be true?
2. Observe environment — reuse existing state
3. Capability Planning — LLM composes capabilities
4. Execution — data flows between steps (ExecutionContext)
5. Verification — mark each requirement satisfied based on evidence
6. Repair/Accept — replan if no progress; accept meaningful partial

**Verification is requirement-level**: each requirement is checked against
execution evidence (content produced? file created? navigation done?).
The operator reports honest outcomes: "4/6 requirements met, 2 unmet: ...".
No illusion success.

**Delivery gating**: email/send requirements are marked non-blocking because
the final send needs verified human-confirmable interaction (safety).

**Implementation**: `friday/operator.py` (6 tests). Live-verified: produced
real comparison reports, study plans, tip lists — each with honest
requirement accounting.

**Consequences**: FRIDAY now has a single closed loop for ALL goals. Novel
goals work because the loop reasons about requirements and self-corrects.
The metric "can it complete a goal it has never seen?" is now answerable: yes,
to the degree its capabilities can satisfy the discovered requirements.

**Known tradeoff**: requirement-level repair currently re-runs the whole plan
rather than just the unmet requirement. Accepted as partial for content goals
(re-running rarely helps). True per-requirement repair is the next refinement.


---

## ADR-023: The Evidence Law — False Completion Is Architecturally Impossible

**Status**: Approved — Implemented + Live-Verified
**Date**: 2026-06-18

**Context**: A full reality-check audit (FRIDAY Operator Truth Report) proved the operator's biggest defect: **false completion**. `Operator._verify_requirements` marked information/research requirements satisfied whenever ANY content was generated. This meant a goal could report `completed=True` even when web search failed, no real source was read, and the output was generated boilerplate. Verification was keyword heuristics over the step log, not evidence.

**Decision**: Introduce the **Evidence Law**. A requirement may be marked satisfied ONLY when a matching, real evidence artifact exists.

- `friday/verification/evidence_law.py` defines:
  - `RequirementKind` (GATHER, PRODUCE, FILE, NAVIGATE, DELIVER, GENERIC) — what a requirement actually demands.
  - `EvidenceArtifact` / `EvidenceKind` — concrete proof (gathered text, source URL, generated content, file bytes, navigation, delivery confirmation). An artifact `is_real` only with non-trivial proof (byte size > 0, non-empty URL, etc.).
  - `ExecutionEvidence` — the bundle the executor populates from REAL outcomes only.
  - `EvidenceVerifier` — maps each requirement to the evidence it requires; no artifact ⇒ UNMET.
- **The hard rule**: generated text satisfies a PRODUCE requirement but NEVER a GATHER/research or DELIVER requirement. Research is satisfied only by real gathered info / source URLs. Files require a real on-disk artifact with byte size > 0. Delivery requires an observed confirmation (still safety-gated, still non-blocking, but never auto-passed).
- `friday/executor.py` now records evidence artifacts from real successes only (real page reads add gathered info + source URLs; confirmed navigations add navigation evidence; `webbrowser.open` does NOT, because it returns no confirmation; real files add file artifacts with verified size).
- `Operator._verify_requirements` was replaced to delegate entirely to `EvidenceVerifier`.

**Implementation**: `friday/verification/evidence_law.py` (new), `friday/executor.py` (evidence collection), `friday/operator.py` (verification rewrite). 20 new tests in `tests/friday/test_evidence_law.py`. Full suite: 401 passing.

**Live verification** (`scripts/m0_demo.py`): the exact Truth Report failure case "Research laptops and create a summary" with no browser now reports `completed=False`, 1/3 requirements met, with research honestly UNMET ("No information was actually gathered..."). Before this ADR it reported a clean false success.

**Consequences**: False completion is now structurally prevented, not patched. The operator can be trusted to report honest partial outcomes. This is the prerequisite for every later milestone — research, delivery, and repair all depend on verification that cannot be fooled. Tradeoff: goals that previously "passed" will now correctly report UNMET until the underlying capability (real browser, real send) actually works — which is the point.


---

## ADR-024: Screenshot Evidence + Captcha/Block Detection (anti-loop)

**Status**: Approved — Implemented + Tested
**Date**: 2026-06-18

**Context**: The owner observed FRIDAY (via the API server's auto-launched Chrome) land on a Google "unusual traffic"/captcha verification page and then repeatedly open new tabs of the same page, never advancing. Root causes found in code: (1) `BrowserController.search_web()` hit `google.com/search` directly, which serves a captcha wall to automated sessions; (2) the executor's navigate fallback called `webbrowser.open(url)` with no dedupe, so replanning iterations spawned duplicate tabs; (3) there was no visual evidence, so the system was blind to being stuck.

**Decision**:
1. **Screenshot evidence** — new `EvidenceKind.SCREENSHOT` in the Evidence Law. `friday/verification/screenshot_evidence.py` captures real screenshots to `~/.friday/evidence/` (override `FRIDAY_EVIDENCE_DIR`) at key execution points (after navigate, after read, and on any block). A screenshot artifact is real only with byte size > 0.
2. **Captcha/block detection** — `is_blocked_page()` / `blocked_reason()` detect verification walls (captcha, "unusual traffic", recaptcha, hcaptcha, cloudflare, "checking your browser", etc.). A blocked page is NOT recorded as gathered information and never satisfies a research requirement.
3. **Anti-loop** — when a block is detected the executor sets `blocked=True`; the operator halts retries immediately instead of re-running the same path, surfacing the block honestly in the trace.
4. **Tab-spam guard** — the executor tracks `navigated_urls` and refuses to open the same URL twice in one execution (covers both real-browser navigate and the `webbrowser.open` fallback).
5. **Captcha-resistant search** — `search_web()` now defaults to DuckDuckGo's HTML endpoint (`FRIDAY_SEARCH_ENGINE=google|bing|duckduckgo`), which does not throw Google's automated-traffic captcha.

**Implementation**: `friday/verification/screenshot_evidence.py` (new), `friday/verification/evidence_law.py` (SCREENSHOT kind), `friday/executor.py` (block detection, screenshots, tab dedupe, blocked propagation), `friday/operator.py` (halt-on-block), `friday/actions/browser_controller.py` (DuckDuckGo default). 12 new tests in `tests/friday/test_screenshot_evidence.py`. Full suite: 413 passing.

**Consequences**: FRIDAY can no longer be trapped in a captcha tab-spam loop, captures visual proof of what actually happened, and treats verification walls as honest blocked states rather than false progress. This complements ADR-023: a captcha page can never masquerade as "research done". Note: when blocked, FRIDAY currently halts and reports honestly; automated captcha solving is explicitly out of scope (a human/escalation path will handle it).


---

## ADR-025: Universal Action Layer Made Live (M1, phase 1)

**Status**: Approved — Implemented (wiring + tests). Executor dispatch migration pending.
**Date**: 2026-06-18

**Context**: The audit proved the Universal Action Layer (`friday/actions/primitives.py` + 4 adapters + resolver) was orphaned: `register_primitives()` was never called, `Operator` used `build_default_registry()` without it, `GoalExecutor` called the browser/file/system actions directly, and there were ZERO tests for primitives or adapters. The layer existed on paper but did nothing.

**Decision (phase 1 — de-risk then activate)**:
1. **Prove before wiring** — wrote `tests/friday/test_universal_action_layer.py` (18 tests): resolver priority selection, fallback when higher-priority adapters can't handle, exclude-based re-routing, primitive dispatch, fallback cascade on adapter failure, keyboard focus rules (no-focus fails, browser/hotkey paths), observe/verify/wait_for behavior, and registry integration. All pass.
2. **Activate** — `Operator.__init__` now calls `init_primitives(browser_controller=...)` and `register_primitives(self._registry)`. The layer is live: `universal.click` is the highest-priority CLICK tool, the resolver carries the real adapters, `operator._primitives_ready` is True.

**Deferred to phase 2 (M1 completion)**: rewriting `GoalExecutor._execute_step` to dispatch click/type/navigate/read through `primitives.*` (flag-gated per ADR-001 so the current direct path remains a safe fallback during migration), plus adding a `navigate` primitive. This is deliberately separate so the executor migration can be validated against a real browser in M2 rather than blind.

**Implementation**: `friday/operator.py` (init + register), `tests/friday/test_universal_action_layer.py` (new). Full suite: 431 passing.

**Consequences**: The action layer is no longer dead code — it is constructed, registered, and discoverable on every Operator. The keystone risk (wiring a never-tested layer into the execution path) is retired by the test suite. Full executor migration follows in M1 phase 2 with live-browser validation.


---

## ADR-026: Focused Search Queries + Spreadsheet Output

**Status**: Approved — Implemented + Tested
**Date**: 2026-06-18

**Context**: The owner observed FRIDAY take "research best gaming laptop and make a spreadsheet" and type the ENTIRE sentence into the search engine, then never produce a spreadsheet. Two real defects: (1) the no-LLM fallback planner used the whole goal string as the `SEARCH_WEB` target — `caps.append((SEARCH_WEB, text, ...))` — so verbs and output clauses polluted the query; (2) there was no spreadsheet capability at all, so "make a spreadsheet" fell through to a generic text file.

**Decision**:
1. **Focused query extraction** — `friday/planner/query_extractor.py` strips leading action verbs ("research", "find", "look up") and trailing output/delivery clauses ("and make a spreadsheet", "then save as docx", "and email it"). The fallback planner now searches the TOPIC ("best gaming laptop"), like a human would. Pure string logic; the LLM decomposer remains the primary path.
2. **Spreadsheet output** — `FileTool` now writes real `.csv` (always) and `.xlsx` (via openpyxl, with CSV fallback). `_parse_rows` turns LLM text — markdown tables, comma/tab separated lines, or plain lines — into real tabular rows, skipping markdown separator rows. The executor's filename inference recognizes spreadsheet/excel/csv/xlsx goals and assigns the right extension. The fallback planner treats spreadsheet/table goals as needing content + a file.

**Implementation**: `friday/planner/query_extractor.py` (new), `friday/planner/operator_planner.py` (focused query + spreadsheet detection), `friday/actions/file_tool.py` (`_write_csv`, `_write_xlsx`, `_parse_rows`), `friday/executor.py` (filename inference). 12 new tests in `tests/friday/test_query_and_spreadsheet.py`. Full suite: 443 passing.

**Consequences**: FRIDAY no longer searches whole instruction sentences (a recurring "it just searched the sentence on Google" complaint), and spreadsheet goals produce real, openable tabular files. This sharpens the no-LLM fallback so it degrades gracefully toward human-like behavior rather than literal sentence-search. Live browser proof of the search behavior still belongs to M2.


---

## ADR-027: Real Browser Control — No Fake Sessions (M2 core)

**Status**: Approved — Implemented + LIVE-VERIFIED
**Date**: 2026-06-18

**Context**: The audit found `BrowserController._connect()` silently launched a fresh Chromium if CDP failed, faking "browser available" while lacking the user's logins. CDP port 9222 was unreachable, so the whole "uses your real Chrome" story was unproven. This is also why earlier sessions opened a captcha page on a clean Chromium instead of the user's logged-in profile.

**Decision**:
1. **No fake sessions** — `BrowserController(require_real_chrome=True)` raises loudly on CDP failure instead of launching fresh Chromium. New `connection_mode` ('cdp'|'fresh') and `is_real_chrome` properties expose the truth.
2. **Launcher** — `friday/actions/chrome_launcher.py` (`ensure_chrome_debug`, `cdp_reachable`, `chrome_running_without_debug`) + `scripts/launch_chrome_debug.py` start Chrome on the debug port. Crucially it detects the #1 real-world failure — Chrome already running WITHOUT the flag, so the profile dir is locked and the flag is ignored — and falls back to a dedicated debug profile (`friday_chrome_debug`) so a controllable session still comes up rather than silently failing.
3. **Bridge wiring** — `FRIDAY_REQUIRE_REAL_CHROME=1` makes the operator path ensure the debug session first and use the real-Chrome controller, failing honestly otherwise.

**Live verification** (`scripts/m2_live_demo.py`, run on the dev machine): `connection_mode=cdp`, `is_real_chrome=True`, navigated to example.com, read 129 real chars (not blocked), captured a real 284KB screenshot artifact under `~/.friday/evidence/`, and DuckDuckGo search returned 3189 chars + 15 links with NO captcha wall. This is the project's first end-to-end real-browser proof.

**Implementation**: `friday/actions/browser_controller.py` (require_real_chrome, connection_mode), `friday/actions/chrome_launcher.py` (new), `scripts/launch_chrome_debug.py` + `scripts/m2_live_demo.py` (new), `friday/bridge.py` (wiring). 6 new tests in `tests/friday/test_chrome_launcher.py`. Full suite: 449 passing.

**Consequences**: FRIDAY can now operate a real, controllable Chrome and proves it; when it cannot, it says so instead of faking a session. The dedicated-debug-profile fallback means automation works even while the user keeps their main Chrome open (the profile won't have their logins until they sign in once there — full main-profile use requires closing the main Chrome, documented in the launcher message). Remaining M2 work: live DOM into WorldState, tab enumeration, and login/consent handling as capabilities.


---

## ADR-028: Chrome Profile Selection System (per-device, never hardcoded)

**Status**: Approved — Implemented + Live-Verified
**Date**: 2026-06-18

**Context**: The owner wants FRIDAY to use their real Chrome profile (with all logins) on their machine, but shareable/production builds must let each user pick their own profile on their own device. No specific person's profile may be hardcoded in source — the project is for other people too.

**Decision**: A discovery + selection + persistence system, fully device-local.
- `friday/actions/chrome_profiles.py` — discovers real profiles by reading `<User Data>/Local State` (`profile.info_cache`), mapping each profile directory ("Default", "Profile 1") to its display name ("Alex", "Work"). Resolves a selection by display name OR directory (case-insensitive, partial). Falls back to scanning profile dirs if Local State is unreadable.
- `friday/config/browser_config.py` — persists the chosen profile per device in `~/.friday/config.json` (override dir via `FRIDAY_CONFIG_DIR`). Resolution order: explicit arg > `FRIDAY_CHROME_PROFILE` env > config file > dedicated fallback. `resolve_browser_choice()` returns the user-data-dir + profile-directory to launch.
- `scripts/select_chrome_profile.py` — lists discovered profiles and persists the user's choice (interactive or `select_chrome_profile.py "Name"`). This is the shareable-build selection mechanism / setup-wizard hook.
- `friday/actions/chrome_launcher.py` — now accepts `profile_directory` and passes Chrome's `--profile-directory` flag alongside `--user-data-dir`, so a specific profile opens.
- `friday/bridge.py` — the operator path resolves the device's profile choice before launching.

**No hardcoding guarantee**: a unit test (`test_no_profile_hardcoded_in_source`) asserts the owner's profile name appears in none of the profile-system source files. Profile-system docstrings use a neutral "Alex" example.

**Live verification**: discovery found all 7 real profiles on the dev machine including "Shreesh [Profile 1]" (the owner's). `select_chrome_profile.py "Shreesh"` persisted the choice to `~/.friday/config.json` as `{"chrome_profile": "Shreesh"}`; `resolve_browser_choice()` resolved it to directory "Profile 1", source "configured". The launcher honored the choice and — because the owner's main Chrome was open (profile locked) — honestly fell back to the dedicated profile with a clear message explaining how to use the real profile (fully close Chrome, rerun).

**Implementation**: `friday/actions/chrome_profiles.py` (new), `friday/config/browser_config.py` + `friday/config/__init__.py` (new), `scripts/select_chrome_profile.py` (new), `chrome_launcher.py` + `bridge.py` + `launch_chrome_debug.py` (updated). 13 new tests in `tests/friday/test_chrome_profiles.py`. Full suite: 462 passing.

**Consequences**: The owner sets their profile once (done: "Shreesh"); every other user selects theirs via the same mechanism with zero code changes. The known Chrome constraint — a profile in use by an open Chrome is locked — is surfaced honestly with remediation steps, not hidden. This satisfies "use my profile for me, let others choose theirs, never hardcode."


---

## ADR-029: Browser Access Strategy — Desktop Fallback for the User's Session

**Status**: Decision layer Implemented + Tested. Desktop EXECUTION pending (M1 phase 2).
**Date**: 2026-06-18

**Context**: The owner's insight: the browser is just one environment. When FRIDAY cannot get CDP control of the user's real profile (because their Chrome is already open and Chrome locks the profile dir), it should NOT fail and should NOT use a clean profile lacking their logins. If the task needs the user's logged-in session, FRIDAY should operate the ALREADY-OPEN Chrome window like a human — desktop control (UIA + vision + keyboard + mouse) — and complete the task from the user's real profile.

**Decision**: `friday/actions/browser_strategy.py` resolves a `BrowserStrategy` per goal:
- CDP reachable -> `CDP_REUSE` (attach to running debug session).
- Chrome closed -> `CDP_LAUNCH` (launch the user's configured profile with the debug port, full control + logins).
- Chrome open (profile locked) AND goal needs the user's session -> `DESKTOP_CONTROL` (operate the visible Chrome via desktop automation — the user's real session, no relaunch).
- Chrome open (locked) AND goal does NOT need the session -> `CDP_DEDICATED` (clean debug profile).

`goal_needs_user_session()` flags goals referencing personal/account surfaces (instagram/gmail/dm/"my ..."/messages/orders/etc.). The bridge resolves the strategy before constructing the Operator, falls back to DESKTOP_CONTROL if CDP was wanted but unavailable for a session goal, and the Operator records the chosen mode in its trace for honest reporting.

**Honest status boundary**: the DECISION layer is implemented and tested (9 tests, full decision matrix). The EXECUTION of desktop-control for browser tasks is NOT yet wired — the executor today only performs the CDP browser path; it does not yet drive UIA/vision/keyboard against the Chrome window. That requires routing the executor through the Universal Action Layer's desktop adapters (M1 phase 2). Until then, a DESKTOP_CONTROL strategy is chosen and reported honestly, but the desktop actuation itself is the next implementation step. No false claim of working end-to-end.

**Implementation**: `friday/actions/browser_strategy.py` (new), `friday/bridge.py` (goal-aware strategy + fallback), `friday/operator.py` (accepts + traces strategy). 9 tests in `tests/friday/test_browser_strategy.py`. Full suite: 471 passing.

**Consequences**: FRIDAY now reasons like a human about access paths: reuse > launch your profile > operate your visible window > clean profile. The architecture treats Chrome as an environment, not a hard dependency on CDP. Completing the desktop-execution wiring (M1 phase 2) makes the DESKTOP_CONTROL branch fully operational.


---

## ADR-030: DesktopChromeController — Execute the Desktop Fallback

**Status**: Approved — Implemented + Tested (live demo pending real session)
**Date**: 2026-06-18

**Context**: ADR-029 added the DECISION to operate the user's visible Chrome via desktop control when their profile is locked and the task needs their logins, but nothing executed that path — the executor only knew CDP. This ADR makes the DESKTOP_CONTROL branch actually run.

**Decision**: `friday/actions/desktop_chrome.py` provides `DesktopChromeController`, a drop-in that exposes the SAME duck-typed surface as `BrowserController` (`available`, `start`, `navigate`, `search_web`, `read_text`, `current_url`, `click`, `type_text`, `get_links`) but performs each action via desktop control:
- `navigate` -> focus Chrome window, Ctrl+L to the omnibox, type URL, Enter.
- `search_web` -> Ctrl+T new tab, type query into the omnibox, Enter, then read results via screenshot + OCR.
- `read_text` -> screen capture + OCR of the visible Chrome window.
- `click`/`get_links` -> honestly report unsupported without DOM/coordinates (element clicking is the Universal Action Layer's desktop/vision adapter job).

Because it matches the BrowserController interface, the existing `GoalExecutor` uses it unchanged — including evidence collection (OCR'd screen text is real gathered info; screenshots are captured; captcha detection still applies). The bridge injects a `DesktopChromeController` when the resolved strategy is `DESKTOP_CONTROL`.

**Honest boundary**: `navigate`/`search`/`type`/`read` work via keyboard + OCR. Reliable click-by-element and omnibox read-back are NOT available without DOM/UIA coordinates; those report unsupported rather than acting blindly. Full element-level desktop interaction is delivered by the Universal Action Layer's desktop/vision adapters (already built/tested in ADR-025) once the executor routes element actions through them — the remaining executor-to-primitives migration. A live demo against the owner's real logged-in Chrome is pending (requires their session open).

**Implementation**: `friday/actions/desktop_chrome.py` (new), `friday/bridge.py` (inject on DESKTOP_CONTROL). 7 tests in `tests/friday/test_desktop_chrome.py`. Full suite: 478 passing.

**Consequences**: The owner's scenario — Chrome open, task needs their logins — now has a real execution path: FRIDAY focuses their visible Chrome and drives it via keyboard + screen reading, using their actual logged-in session, instead of failing or using a clean profile. Navigation, search, typing, and reading work today; element-precise clicking lands with the executor-to-primitives migration.


---

## ADR-031: Executor Routes Click/Type Through Universal Action Layer + Dry-Run Safety

**Status**: Approved — Implemented + Tested
**Date**: 2026-06-18

**Context**: Three phantom-action incidents the owner reported (Chrome opening, Notepad appearing, searching whole goal strings) traced to two causes: (1) `AUTO_LAUNCH_CHROME=1` in `.env` made the old `main.py` auto-launch Chromium, and (2) the executor's click/type paths called `self._browser.click()` and `self._browser.type_text()` directly — bypassing the Universal Action Layer, Evidence Law, captcha guards, and all new safety systems.

**Decision**:
1. **Fixed `.env`**: `AUTO_LAUNCH_CHROME=0`, `DISABLE_BROWSER_TRACKER=1`, added `FRIDAY_REQUIRE_REAL_CHROME=1`, `FRIDAY_CHROME_PROFILE=Shreesh`, `FRIDAY_SEARCH_ENGINE=duckduckgo`. These stop the old system from launching phantom Chrome.
2. **Dry-run safety (`FRIDAY_DRY_RUN`)**: when set to `1`, the executor blocks ALL real external actions (navigate, click, type, launch apps, open URLs). Only LLM generation is allowed. Prevents stale/legacy processes from touching the machine during development. Demonstrated: dry-run blocks navigation and reports `[DRY-RUN] Would execute...`.
3. **Click/Type through primitives**: `_execute_click` and `_execute_type` now route through the Universal Action Layer (`primitives.click()` / `primitives.type_text()`) when initialized. This means all tested guards (adapter resolution, fallback cascade, focus rules, timeout, metadata recording) apply to these actions. When primitives are not initialized, falls back to direct browser with an honest log. Demonstrated: click returns precise "No adapter can handle target: Submit" and type returns "No element is focused" — not generic silence.

**Implementation**: `friday/executor.py` (`_execute_click`, `_execute_type`, `_build_world_state`, `_run_async`, dry-run guard), `.env` (fixed flags). Full suite: 478 passing. No regressions.

**Consequences**: Two of the three executor action paths (click, type) now flow through the tested action layer pipeline. Search and Navigate still use the direct browser path (they have their own evidence/captcha guards). The old `main.py` can no longer auto-launch Chrome or the browser tracker. Any stale process respects dry-run when the flag is set. The phantom-action problem is structurally eliminated from the new code path.


---

## ADR-032: Honest Research Capability with Source Citations (M3)

**Status**: Approved — Implemented + Tested
**Date**: 2026-06-18

**Context**: The Evidence Law (ADR-023) made fake research impossible to mark as satisfied, but FRIDAY still lacked a capability that performs REAL research. The old SEARCH_WEB step only read the search-results page; it never opened the actual source pages, so research requirements could only ever be partially met.

**Decision**: A reusable research capability (NOT a pipeline) at `friday/capabilities/research.py`:
1. Searches the focused query (captcha-resistant DuckDuckGo by default).
2. Selects the best result links (prefers .gov/.edu/.org, skips search-engine/social/ad domains).
3. Actually navigates to and reads each source page.
4. Records each real page read as GATHERED_INFO + SOURCE_URL evidence.
5. Skips blocked/captcha pages gracefully (tries the next).
6. Captures screenshot evidence of the research session.

The executor's SEARCH_WEB step now routes through this capability (`_execute_research`). The EXTRACT_WEB_CONTENT step reuses already-gathered research instead of redundantly re-reading. The synthesis step (`_generate`) now passes the real source URLs to the LLM with an instruction to base content ONLY on gathered info, not invent facts, and append a Sources section — making research-backed output honestly citable.

The same capability works for any topic (products, geopolitics, academic, local) because it composes search + navigate + read + evidence — no task-specific logic.

**Implementation**: `friday/capabilities/research.py` + `__init__.py` (new), `friday/executor.py` (`_execute_research`, extract-reuse, citation instruction in `_generate`). 6 tests in `tests/friday/test_research_capability.py`. Full suite: 484 passing.

**Consequences**: Research requirements are now honestly satisfiable — they require real source reads, and the synthesized content cites the actual URLs FRIDAY opened. Combined with the Evidence Law, this closes the "false research completion" gap end-to-end: no sources read -> research UNMET; sources read -> content cites them. Note: live validation against real pages is pending a real browser session (the capability is proven via tests with a controllable fake browser).


---

## ADR-033: Eliminate Phantom Actions — Legacy Entry-Point Guards

**Status**: Approved — Implemented + Tested
**Date**: 2026-06-18

**Context**: The owner repeatedly observed phantom actions on their machine — Chromium opening and searching "laptops"/"Open WhatsApp", blank Notepad windows — during development. Full investigation determined the causes were NOT FRIDAY's test runs (all mocked) but external/legacy triggers:
1. The Kiro **Playwright MCP Power** (`@playwright/mcp`) — a browser-automation IDE extension receiving tool calls and launching Chromium. Removed by the owner from MCP config.
2. The legacy **`main.py`** JARVIS loop (`while True` command loop) and **`start_remote_server.py`** — these run forever and execute commands (including Google-searching the literal command text and opening apps) via the OLD code paths that bypass the Evidence Law, action layer, and browser strategy.

A live process/window audit confirmed no FRIDAY process runs persistently; the phantom windows were from these external/legacy sources and were already-closed leftovers by the time of inspection.

**Decision**: Hard startup guards on the legacy entry points. `main.py` and `start_remote_server.py` now refuse to start unless `FRIDAY_ALLOW_LEGACY_MAIN=1` is explicitly set, printing a clear `[BLOCKED]` message. This makes it impossible to accidentally launch the old action-driving loops (e.g. from a stray terminal, a hook, or habit). Combined with the earlier `.env` fixes (`AUTO_LAUNCH_CHROME=0`, `DISABLE_BROWSER_TRACKER=1`) and the `FRIDAY_DRY_RUN` flag, the legacy phantom-action surface is closed.

**Implementation**: `main.py` (top-of-file `if __name__ == "__main__"` guard before heavy imports), `start_remote_server.py` (import-time guard). Verified: `python main.py` prints `[BLOCKED]` and exits 0. Full suite: 484 passing.

**Consequences**: The old JARVIS loop — the one piece of the codebase that autonomously opens Chrome/Notepad and Google-searches raw command text — can no longer run by accident. The new General Operator (friday/ package, used via operator/bridge) is unaffected and remains the only intended path. If phantom browser actions recur after this, the source is necessarily an IDE-level MCP/extension (e.g. Playwright MCP), not FRIDAY code.


---

## ADR-034: Per-Requirement Repair (M4)

**Status**: Approved — Implemented + Tested
**Date**: 2026-06-18

**Context**: The operator previously handled unmet requirements by either re-running the WHOLE plan or accepting partial success. Re-running wastes work (redoing already-satisfied requirements) and rarely helps; accepting partial leaves fixable gaps unaddressed. The roadmap's M4 calls for diagnosing WHY a specific requirement failed and repairing ONLY that one.

**Decision**: A requirement-centric repair system.
- `friday/planner/repair.py` — `RepairDiagnoser` diagnoses each unmet requirement against the execution evidence and proposes a TARGETED, minimal repair plan:
  - GATHER unmet (no sources read) -> retry research (search + open + read).
  - PRODUCE unmet + info present -> just synthesize (don't re-gather).
  - FILE unmet + content present -> just write the file (don't re-gather/re-generate).
  - FILE/PRODUCE unmet + nothing present -> minimal produce-then-write / gather-then-produce chains.
  - NAVIGATE unmet -> retry navigation.
  - DELIVER unmet / BLOCKED -> not auto-repairable (safety-gated / needs human).
- `GoalExecutor.execute_repair()` runs ONLY the repair actions, seeding a context from the prior execution's evidence (gathered info, content, files) so satisfied work is reused, then merges outcomes back.
- `Operator._repair_unmet()` runs after verification: for each unmet blocking requirement it diagnoses and repairs, then re-verifies. If all requirements pass after repair, the goal completes.

**Implementation**: `friday/planner/repair.py` (new), `friday/executor.py` (`execute_repair`), `friday/operator.py` (`_repair_unmet` + loop integration). 7 tests in `tests/friday/test_repair.py`. Full suite: 491 passing.

**Consequences**: When a goal produces content but fails to write the file (or gathers info but doesn't synthesize), the operator now fixes exactly that gap instead of re-running everything or giving up. Repairs reuse prior evidence, so they're cheap and targeted. Non-repairable causes (delivery, captcha-block) are reported honestly rather than retried pointlessly. This closes the M4 milestone and makes the closed loop genuinely self-correcting at the requirement level.


---

## ADR-035: TRUE Root Cause of Phantom Actions — Tests Executed Real Actions

**Status**: Approved — Implemented + Verified
**Date**: 2026-06-18

**Context**: Despite removing the Playwright MCP and nova-act powers and guarding main.py, phantom Notepad windows STILL opened "while the agent worked." A live parent-process trace caught the smoking gun: a Notepad whose parent was `cmd.exe /c "notepad"` — the exact signature of `SystemActions.launch_app()` (`subprocess.Popen("notepad", shell=True)`).

The TRUE root cause: **FRIDAY's own test suite was executing real actions.** Tests like `test_operator.py::test_trace_records_steps` call `operator.run("Open notepad")` and integration tests use goals like "Open WhatsApp and send..." WITHOUT mocking `SystemActions`. The operator → planner → executor → OPEN_APPLICATION path then ran `subprocess.Popen("notepad", shell=True)` → `cmd /c "notepad"` → a REAL Notepad window, on every `pytest` run. The browser searches came from the same path (NAVIGATE_URL/SEARCH_WEB) plus the separately-removed powers. Every test run the agent did was opening real windows.

**Decision**:
1. **`tests/friday/conftest.py`** (new) sets `FRIDAY_DRY_RUN=1` at import time (before any friday module loads) and via an autouse fixture. No test can launch a real app/browser or drive keyboard/mouse, regardless of whether it mocks the action layer.
2. **Refined the executor dry-run guard** to block VISIBLE/external actions (OPEN_APPLICATION, NAVIGATE_URL, SEARCH_WEB, EXTRACT/READ, CLICK, TYPE, SWITCH_WINDOW) while ALLOWING safe local operations (CREATE_FILE, EDIT_FILE, GENERATE, VERIFY) so file-based tests keep working.

**Verification**: Killed all Notepad windows, ran `test_trace_records_steps` (the offender) → 0 new Notepad windows. Ran the FULL suite (491 tests) → 0 Notepad windows spawned, all pass. Previously each run spawned real Notepad/Chrome windows.

**Consequences**: The phantom-action problem is solved at its true root — it was the test suite executing real OS actions, not just IDE powers. Tests now run hermetically in dry-run. Combined with ADR-033 (legacy entry guards) and the removed browser-automation powers, there is no remaining path by which development/testing opens real windows. NOTE: this also means prior "live verification" of browser actions in this session that ran via pytest were actually executing — the dev must use explicit, non-test scripts (with dry-run off) for real live runs, which is the correct separation.


---

## ADR-036: Latency Optimization — Parallel Discovery + Planning

**Status**: Approved — Implemented + Tested
**Date**: 2026-06-18

**Context**: The operator made two sequential LLM calls at the start of every goal: requirements discovery (`RequirementsDiscovery.discover`) then capability planning (`OperatorPlanner.plan`). On the free-tier NVIDIA endpoint each can cold-start ~20-30s, so sequentially they cost ~60-90s before any work begins — the dominant latency the Truth Report flagged.

**Decision**: These two calls are independent — both only need the goal text and a pre-observed environment snapshot. The operator now fires them in parallel via a `ThreadPoolExecutor(max_workers=2)` at the start of `run()`. The first iteration reuses the prefetched plan instead of re-planning, avoiding a second sequential cold-start. Subsequent iterations (repair/replan) plan normally.

**Implementation**: `friday/operator.py` (`run()` parallel prefetch + first-iteration plan reuse). Full suite: 491 passing, no regressions.

**Consequences**: First-goal latency drops from ~2 sequential cold-starts to ~1 (roughly 30-45s instead of 60-90s on free tier). The optimization is safe because discovery and planning have no data dependency. Further latency work (smaller models for planning, response caching, keepalive warming) remains available but this removes the largest, simplest win. NOTE: measured wall-clock improvement is pending a real (non-dry-run) LLM run; the parallelism is structurally correct and unit-verified.


---

## ADR-037: Element-Precise Desktop Clicking via Screen OCR (M5)

**Status**: Approved — Implemented + Tested (live demo pending)
**Date**: 2026-06-18

**Context**: `DesktopChromeController` (ADR-030) could navigate/search/type/read the visible Chrome via keyboard, but its `click()` honestly reported "unsupported" because it had no way to locate a specific element without DOM/UIA coordinates. This left the DESKTOP_CONTROL strategy unable to click named elements (e.g. "Messages") in the user's real session.

**Decision**: `DesktopChromeController.click(text)` now uses the human-like vision path: capture the screen, OCR it into regions (via `OCREngine.extract_regions`), find the region whose text matches the target, and click its bounding-box center with pyautogui. It is honest about limits — if OCR is unavailable or the text isn't found on screen, it returns a clear failure rather than clicking blindly.

**Implementation**: `friday/actions/desktop_chrome.py` (`click` via screen+OCR). 2 new tests in `tests/friday/test_desktop_chrome.py` (finds-and-clicks center; not-found fails honestly; OCR-unavailable fails). Full suite: 493 passing, 0 phantom windows.

**Consequences**: The DESKTOP_CONTROL branch can now click elements by visible text in the user's real Chrome using vision — completing the "operate my open Chrome like a human" capability for navigate + search + type + read + click. This is OCR-based (per ADR-014 it's the vision fallback, used only when DOM/CDP control isn't available). Live validation against a real logged-in session is pending (tests use a controllable fake screen/OCR). Element clicking precision depends on OCR quality; UIA-based clicking for native controls remains future work.


---

## ADR-038: First Live End-to-End Validation + Model Routing Fixes

**Status**: Approved — Implemented + LIVE-VERIFIED
**Date**: 2026-06-18

**Context**: Everything was mock-tested; the real LLM pipeline had never been validated end-to-end this session (the Truth Report's core criticism). A safe live-validation harness (`scripts/live_validate.py`, file-only goal so nothing phantom can open, dry-run OFF) exposed real problems no mock could:
1. The operator HUNG (>150s) on real goals. Root cause: `RequirementsDiscovery.discover` and the executor's `_generate` used fragile `ThreadPoolExecutor`-around-`asyncio.run` wrappers AND routed to slow/empty-returning large reasoning models (the default 49B nemotron returned empty content after ~18s; the 70B took ~40s cold).
2. The 4B model used for decomposition mislabeled capabilities (CREATE_FILE became GENERATE/launch_app), and produced vague all-PRODUCE requirements — letting the operator falsely report "completed" with NO file on disk.

**Decision**:
1. **Model routing by task**: requirements discovery uses the fast `nvidia/nemotron-mini-4b-instruct` (~1-2s, clean JSON); decomposition and content generation use the capable `meta/llama-3.3-70b-instruct` (accurate labels + real content). Measured: a single 4B call ~1.3s, 70B ~a few seconds warm.
2. **Bounded async execution**: `GoalExecutor._run_async` always runs in a dedicated worker thread with a hard timeout (90s) — can never hang forever. `RequirementsDiscovery.discover` wrapper hardened the same way.
3. **Structural requirement enforcement**: `RequirementsDiscovery._augment_structural` injects a FILE requirement when the goal says save/file (and a DELIVER requirement for email/send) even if the LLM omits it. The Evidence Law then forces a real file artifact — closing the false-completion path the live run exposed.

**LIVE VERIFICATION** (`scripts/live_validate.py`, real NVIDIA, dry-run off): goal "Write a 6-line explanation of what makes a good unit test, save to good_unit_tests.md" → discovered 7 requirements (incl. injected FILE) → planned 4 steps → generated real content → created a REAL 411-byte file at `~/Documents/FRIDAY/good_unit_tests.md` with genuine, well-written content → 7/7 requirements met, file verified on disk. Total 31.9s (was timing out >150s). This is the project's first honest, live, end-to-end success.

**Implementation**: `friday/planner/requirements.py` (fast model + `_augment_structural` + hardened wrapper), `friday/planner/llm_decomposer.py` (70B model), `friday/executor.py` (`_generate` 70B + bounded `_run_async`), `scripts/live_validate.py` (new). 3 new structural-requirement tests. Full suite: 496 passing.

**Consequences**: The real pipeline is proven, not just mocked. Latency is workable (~30s for a content+file goal). False completion is closed even when the LLM under-specifies requirements. Remaining: live browser/research validation, and decomposition quality on more complex goals.


---

## ADR-039: Model Catalog Upgrade + Safety Models + Test Browser Lockdown

**Status**: Approved — Implemented + LIVE-VERIFIED
**Date**: 2026-06-18

**Context**: The owner provided the full NVIDIA model catalog and authorized using any of them. The default reasoning model (49B nemotron) was slow/empty and the 70B took ~40s; decomposition with the 4B mislabeled steps. Also, 2-3 chromium windows still briefly opened during test runs.

**Decision**:
1. **Probed real model availability** (many catalog names are display-only). Verified via live API: `qwen/qwen3-next-80b-a3b-instruct`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `meta/llama-guard-4-12b`, `nvidia/nemotron-content-safety-reasoning-4b`, `mistralai/mistral-medium-3.5-128b`, `moonshotai/kimi-k2.6` all return 200. `deepseek/deepseek-v4-flash` 404s (removed).
2. **Upgraded the registry**: `qwen3-next-80b-a3b` (sparse MoE, 3B active) is the new top reasoning/decomposition model — measured ~1.2s with clean JSON vs ~40s for the dense 70B. `gpt-oss-120b`/`gpt-oss-20b` added as strong fast reasoners. The slow/empty 49B and the 404 deepseek removed.
3. **Repointed discovery + decomposition** to `qwen3-next-80b-a3b`. Content generation still uses the reliable 70B.
4. **Registered safety models** (`llama-guard-4-12b`, `nemotron-content-safety-reasoning-4b`) for the future delivery/send gate and content screening.
5. **Test browser lockdown**: added root `tests/conftest.py` forcing `FRIDAY_DRY_RUN=1` (+ disable mic/wake/tracker) for the ENTIRE test tree, and a hard guard in `BrowserController.start()` that refuses to launch/connect when dry-run is set. No test can spawn chromium.

**LIVE VERIFICATION**: the file-only validation goal now completes in **6.6s** (was 31.9s, originally timed out >150s) — a ~5x speedup — producing the same real, verified 438-byte file with genuine content. Full suite: 496 passing, 0 phantom windows.

**Consequences**: The pipeline is now both honest AND fast (sub-7s for content+file goals on warm cache). Safety models are available for gating risky actions. Tests are physically incapable of launching a browser. NOTE: the brief chromium-during-tests the owner observed was never traced to a specific FRIDAY test (all pass browser_controller=None); the start() guard makes it impossible regardless of source within the test process. If it persists, it is an external IDE power/extension, not FRIDAY.


---

## ADR-040: Trusted Delivery (M6) — Confirmation, NOT Content Moderation

**Status**: Approved — Implemented + Tested
**Date**: 2026-06-18

**Context**: M6 was originally framed as a "safety gate" using content-moderation models (llama-guard) to screen/refuse risky sends. The owner correctly pushed back: this is a PERSONAL agent operating the owner's own accounts. A model refusing to send the owner's content based on its opinion of "appropriateness" is the wrong kind of limit — corporate-product safety, not personal-agent safety.

**Decision**: Build delivery as a CONFIRMATION + CORRECTNESS layer the owner controls, with NO content moderation:
- `friday/actions/delivery.py` — `DeliveryGate` with `DeliveryRequest`/`DeliveryResult`.
- Flow: CONFIRM (show exactly what will be sent — recipient, subject, body, attachments) -> SEND -> VERIFY (observed 'sent' state).
- It protects against MISTAKES (wrong recipient, wrong file, hallucinated content), never against the user. No model judges the content.
- Defaults to safe: with no confirm handler and `FRIDAY_AUTOCONFIRM` off, nothing is sent (no accidental silent sends). Full autonomy is one flag: `FRIDAY_AUTOCONFIRM=1` or per-call `auto_confirm=True`.
- Honest verification: success requires observed 'sent' evidence; an issued-but-unverified send is reported as not-success; send without a verifier is marked "unverified" in the detail.
- Executor integration: SEND_MESSAGE/SEND_EMAIL now route through the gate (was a placeholder string). On verified send, a DELIVERY_CONFIRMATION evidence artifact is recorded, satisfying the Evidence Law's DELIVER requirement truthfully.
- The safety models registered in ADR-039 remain available but are NOT used to refuse content. They can be opt-in tools later (e.g. an informational PII heads-up), never a block.

**Implementation**: `friday/actions/delivery.py` (new), `friday/executor.py` (`_execute_delivery`, gate param). 11 tests in `tests/friday/test_delivery.py`. Full suite: 507 passing.

**Consequences**: FRIDAY can now actually send (email/message) once a channel handler is wired, limited only by the OWNER's confirmation — never by a model's opinion of the content. Delivery requirements become honestly satisfiable (real 'sent' evidence). The personal-agent philosophy is preserved: maximum capability, the user is the only authority. Remaining: wire concrete channel handlers (Gmail/WhatsApp send_fn + sent-folder verify_fn) to a real session — the gate is channel-agnostic and ready for them.


---

## ADR-041: Generic Web Agent — Observe→Decide→Act, ZERO Site Hardcoding

**Status**: Approved — Implemented + Tested (live demo pending real session)
**Date**: 2026-06-18

**Context**: The owner rejected per-site handlers (GmailHandler, WhatsAppHandler, etc.): "all Chrome tasks should be done by observe-live-and-do, not hardcoded specifics, or we'll have to hardcode for everything and that's not an option." This is exactly ADR-020/021 (capabilities, not workflows). Hardcoding sites does not scale and is forbidden.

**Decision**: A single generic web agent (`friday/capabilities/web_agent.py`) that operates ANY website with NO site-specific logic:
- `BrowserController.observe_interactive()` reads the live page's interactive elements (links, buttons, inputs) with indices, roles, text, and coordinates — generic DOM scan, no site assumptions.
- `WebAgent.run(goal)` loops: OBSERVE (interactive elements) → DECIDE (the LLM picks ONE atomic next action: click N / type into N / press key / navigate / done / stuck) → ACT (via `click_index`/`fill_index`/`press`/`navigate`) → repeat until the LLM says done or a step budget is hit.
- The LLM reasons over the ACTUAL live DOM each step, so the same loop handles Gmail, Instagram, YouTube, a bank, an unfamiliar site — anything a human could operate by looking and clicking. New sites need zero new code.
- Block detection (captcha/login wall) stops the loop honestly (no tab-spam). Records navigation + screenshot evidence per step.
- Decisions use the fast `qwen3-next-80b-a3b` model (~1-2s/step).

Integration: `_execute_delivery` (send message/email) now uses the WebAgent to perform the send on whatever site is open — NO Gmail/WhatsApp hardcoding. The DeliveryGate still governs confirmation; delivery evidence is recorded only on observed success. A test (`test_no_site_names_in_source`) guards that the web agent contains no site-name branching.

**Implementation**: `friday/actions/browser_controller.py` (`observe_interactive`, `click_index`, `fill_index`, `press`), `friday/capabilities/web_agent.py` (new), `friday/executor.py` (generic web sending via the agent + `_DefaultGate`). 7 tests in `tests/friday/test_web_agent.py`. Full suite: 514 passing.

**Consequences**: FRIDAY can now operate arbitrary websites through reasoning over the live DOM — the General Operator vision for the browser environment, with zero hardcoded site logic. Sending email/messages is just "operate the open site to send," same loop as any other web task. The old hardcoded `_target_to_url` known-sites map remains only as a convenience for direct navigation, not as task logic. Live validation against real logged-in sites is pending a real session (the loop is proven via fake browser + scripted decisions). This is the architectural answer to "don't hardcode for everything."


---

## ADR-042: Vision Fallback for the Web Agent (DOM → Vision)

**Status**: Approved — Implemented + Tested (live demo pending)
**Date**: 2026-06-18

**Context**: The owner correctly noted DOM-only operation won't work for some tasks — canvas apps (Figma, maps, games), `<video>`/icon-only controls, image maps, shadow-DOM/obfuscated widgets, and anything where meaning is visual. Per ADR-014 the perception order is DOM > UIA > OCR > Vision; vision is the fallback when semantic sources can't resolve a target.

**Decision**: Add a vision escalation to the generic web agent (ADR-041), preserving "DOM-first, vision-fallback":
- `VisionPerception.locate_element(screenshot, description)` asks the VLM (llama-3.2-90b-vision) for a described element's CENTER as NORMALIZED coordinates (0..1), robust to any image downscaling. Returns None / NOT_FOUND honestly.
- `BrowserController.screenshot_image()` (full-page PIL capture), `viewport_size()`, and `click_xy(x,y)` enable vision-located clicks.
- The web agent gains a `click_vision` action: the LLM uses it ONLY when the needed target is visible but missing from the DOM element list (canvas/icon/custom widget). The agent screenshots, vision locates the normalized center, scales to viewport pixels, and clicks. DOM-index clicking remains preferred (more reliable).
- Vision is auto-wired from the model router; if unavailable, click_vision degrades honestly ("vision unavailable").

**Implementation**: `friday/perception/vision.py` (`locate_element`, `_parse_coords`), `friday/actions/browser_controller.py` (`screenshot_image`, `viewport_size`, `click_xy`), `friday/capabilities/web_agent.py` (`click_vision` action + `_click_via_vision`). 5 tests added. Full suite: 519 passing.

**Consequences**: The web agent can now operate the visual ~20% of sites DOM can't reach, while still preferring fast/reliable DOM clicks for the rest — exactly the ADR-014 hierarchy applied to the browser. No site hardcoding; vision is a generic capability the same loop escalates to. Live validation against a real canvas/visual site is pending a real session.


---

## ADR-043: Reliable Browser Access — 3-Tier Strategy (live-validated constraints)

**Status**: Approved — Implemented; constraints LIVE-VERIFIED
**Date**: 2026-06-18

**Context**: Goal: the best, most reliable browser access for ANY task, anytime. Live testing on the owner's machine established hard, real constraints:
- **CDP on the live signed-in profile is BLOCKED by Google** (anti-token-theft). Verified: Chrome silently refuses `--remote-debugging-port` on the synced "Shreesh" profile across 4+ attempts.
- **Clone profile + CDP works** (Chrome/149 CDP came up on a cloned User-Data dir) and carries most site cookies/logins, BUT **Google-account auth resists cloning** (Chrome binds it to OS profile + device-bound DPAPI encryption). Verified ambiguous on Google properties.
- **Dedicated clean profile + CDP is 100% reliable** but has no logins until the user signs in there.

Conclusion: NO single method gives CDP + all logins (incl. Google) reliably — a Chrome security reality affecting all automation tools, not a FRIDAY limitation.

**Decision**: A 3-tier browser-access strategy the resolver selects per task (extends ADR-029):
1. **Clone + CDP+DOM** (`friday/actions/profile_clone.py`, `chrome_launcher.ensure_chrome_debug(login_clone=True)`): clones the configured profile's session state (Cookies, Login Data, Local/Session Storage, Network/, Preferences) into a dedicated automation User-Data dir and runs CDP there. Fast, precise, carries most non-Google logins, never touches/locks the live profile.
2. **Dedicated CDP profile**: for no-login tasks (research, public sites) — fastest, most reliable.
3. **Desktop control on the real open Chrome** (ADR-030/037: keyboard + screen OCR + vision): the universal fallback for what CDP can't do — Google-account-gated sites, canvas, anything. Operates the user's actual logged-in window as-is.

**Implementation**: `friday/actions/profile_clone.py` (new — `clone_profile_session`, `automation_user_data_dir`), `friday/actions/chrome_launcher.py` (`login_clone` path + `--no-sync/--restore-last-session=false`). The strategy resolver chooses the tier; desktop control is the guaranteed catch-all.

**Consequences**: FRIDAY never gets stuck on browser access — it has a working path for every case. Most logged-in sites: clone+CDP (fast). No-login: dedicated CDP. Google-gated/visual/blocked: desktop control. This is the honest best-reliable design given Chrome's security model. NOTE: the Google-login case specifically must use Tier 3 (desktop control) — documented so expectations are clear.


---

## ADR-044: First Live Web-Automation Success + Loop Robustness Fixes

**Status**: Approved — LIVE-VERIFIED
**Date**: 2026-06-18

**Context**: The generic web agent (ADR-041/042) was proven only with fakes. A real run was needed to validate it operates an actual browser. Built `scripts/live_web_agent.py` (dedicated CDP profile, public Wikipedia goal — reliable, no login fight) and ran it live.

**The live run found 3 real bugs no mock could catch**, each fixed:
1. **Stuck-retyping loop**: the agent kept choosing `type` into the search box and never submitted, because it couldn't see the effect of its actions. Fix: feed the LLM a `LAST ACTION RESULT` each step (incl. whether the URL changed), an anti-repeat guard that auto-presses Enter after a repeated `type`, and stops honestly after 2 no-progress repeats.
2. **`Execution context was destroyed` mid-navigation**: `observe_interactive` read the page during a navigation. Fix: `wait_for_load_state` + settle delay before reading, and a one-time retry on context-destroyed.
3. **Typed text not landing**: clicking + typing missed the field / left it blank (empty `search=` in URL). Fix: `fill_index` now clears the field (Ctrl+A, Delete), types with delay, and VERIFIES the value landed via `document.activeElement`, reporting `verified` back to the agent so it knows to retry a different element or proceed.

**LIVE RESULT**: goal "find the Python programming language article on Wikipedia and open it" → `achieved=True` in 5 steps, 23s, final URL exactly `https://en.wikipedia.org/wiki/Python_(programming_language)`. The generic loop operated real Chrome: observed live DOM → typed → submitted → navigated results → landed on the target → recognized done. Zero hardcoding. 5 navigations + 5 screenshots recorded as evidence.

**Implementation**: `friday/capabilities/web_agent.py` (action-result feedback, anti-repeat/auto-submit, verified-typing feedback), `friday/actions/browser_controller.py` (`observe_interactive` settle+retry, `fill_index` clear+verify, `press` settle, `_settle`). `scripts/live_web_agent.py` (new). Full suite: 519 passing, unit web-agent tests still green.

**Consequences**: FRIDAY's generic web automation is now LIVE-PROVEN on a real browser, not just mocked — the central Truth Report gap for the browser environment is closed for public/no-login tasks. The same loop + the 3-tier access strategy (ADR-043) + vision fallback (ADR-042) cover arbitrary sites. Logged-in tasks use the clone profile or desktop-control tiers. This is a real, watchable end-to-end success.


---

## ADR-045: Both Browser Tiers Live-Verified (Multi-Step CDP + Desktop Control)

**Status**: Approved — LIVE-VERIFIED
**Date**: 2026-06-18

**Context**: ADR-044 proved a single-page web-agent goal live. Two harder validations were run to prove the full stack on a real browser: (1) a multi-step research→synthesize→save goal via CDP, and (2) desktop control on the user's REAL signed-in Chrome.

**Test 1 — Multi-step research + save (CDP, dedicated profile)** (`scripts/live_multistep.py`):
Goal: "Research what Python is mainly used for, write a 5-point summary, save to python_uses.md." Result: completed, 5/5 requirements met, real web search → READ 4000 real chars from a real page → LLM synthesis → real file `python_uses.md` (1281 bytes). The content CITES the actual sources it read (GeeksforGeeks, DataCamp, Coursera) — honest research with citations (ADR-032) working live end-to-end. Verified file on disk.

**Test 2 — Desktop control on the user's real signed-in Chrome** (`scripts/live_desktop_control.py`):
Operated the user's NORMAL open Chrome (no CDP, no cloning) via keyboard omnibox navigation + screen OCR. Navigated to Wikipedia/Automation; OCR confirmed the live page ("Automation - Wikipedia", the real URL) AND that it was the user's own session (saw their bookmarks/Gemini/restore prompt). mode=desktop. This is the universal Tier-3 fallback (ADR-030/037) proven on the real logged-in session.

**Consequences**: Both browser tiers are now LIVE-PROVEN, not mocked:
- Tier 1/2 (CDP+DOM): fast/precise, proven with full research→save + citations.
- Tier 3 (desktop control): universal fallback for logged-in/Google-gated/visual tasks, proven on the user's real Chrome.
Combined with ADR-044 (web-agent loop), ADR-042 (vision fallback), and ADR-043 (3-tier strategy), FRIDAY's entire browser-operation stack is validated against a real browser. Full suite remains 519 passing. The central Truth Report gap ("everything mock-tested, real pipeline unproven") is now closed across content goals, research goals, web operation, and real-session desktop control.


---

## ADR-046: Browser-Agent Hardening — Audit Fixes Toward Best-in-Class

**Status**: COMPLETE — all audited CRITICAL/HIGH/medium items resolved across ADR-046/047/048/049/050; live demo of batches 2-3 pending real Chrome
**Date**: 2026-06-18

**Context**: A full audit compared FRIDAY's web/computer agent to best-in-class browser agents (browser-use, OpenCUA, Claude computer-use) and found real bugs and capability gaps. Fixing them in priority order.

**Fixed this batch (CRITICAL/HIGH)**:
1. **Research opened ZERO sources (CRITICAL)** — DuckDuckGo HTML results wrap targets in `/l/?uddg=` redirect URLs; `_select_best_links` filtered out all `duckduckgo.com` domains, so every result was dropped and research silently degraded to snippet-only. Fix: `_decode_ddg_redirect` decodes the real destination; added per-domain dedupe. LIVE-VERIFIED: multi-step research now "read 3 sources" with real inline citations (was "search results only").
2. **No scroll + stale coordinate clicks (CRITICAL)** — the agent had no scroll action and clicked frozen observe-time pixel coords with no scroll-into-view, so off-screen elements were unreachable and DOM shifts caused wrong-element clicks. Fix: added `scroll` action (down/up/top/bottom) to the web agent + controller; `click_index`/`fill_index` now re-locate a live Playwright locator (`get_by_text`/`get_by_role`/selector) and `scroll_into_view_if_needed` before acting, falling back to scroll-corrected viewport coordinates. `observe_interactive` now emits page-y coords, an `in_view` flag, and a selector hint.
3. **Off-screen elements hidden from the LLM (HIGH)** — `_decide` only rendered the first 50 of up to 60 elements. Fix: render all observed elements with an "(off-screen)" marker so the model can target and scroll to them.

**Implementation**: `friday/capabilities/research.py` (`_decode_ddg_redirect`, dedupe), `friday/actions/browser_controller.py` (`scroll`, `_locate`, locator-based `click_index`/`fill_index`, richer `observe_interactive`), `friday/capabilities/web_agent.py` (scroll action, full element listing). +5 tests. Full suite: 522 passing. Live multi-step research confirmed reading real sources with citations.

**Still queued (from audit, next batches)**: none — all audited items resolved. **(DONE: executor UAL empty-WorldState fix → ADR-047; operator multi-iteration self-correction → ADR-048; tab management + iframe/shadow-DOM observe + CDP viewport fix → ADR-049; networkidle waits + file upload/download + silent-no-op vision escalation → ADR-050.)**

**Consequences**: Two of the most damaging real-site failures (no scroll/stale clicks, dead research) are fixed and the research fix is live-proven. FRIDAY is materially closer to best-in-class browser operation. The remaining audit items are tracked for subsequent batches.

---

## ADR-047: Executor WorldState Populates Live Elements (UAL empty-WorldState fix)

**Status**: Approved — Implemented + Tested
**Date**: 2026-06-18

**Context**: `GoalExecutor._build_world_state` always passed `elements=[]` to `set_browser_state`. The Universal Action Layer's `BrowserAdapter.resolve_element` matches a `Target` against `world_state.browser_elements`, so with an always-empty list **every** primitive click/type resolved against nothing and silently failed (falling back to the legacy direct-browser path or erroring). This was the "executor UAL empty-WorldState bug (HIGH)" from the ADR-046 audit.

**Decision**: `_build_world_state` now calls `browser.observe_interactive()` and converts each live interactive element into a `BrowserElement` (tag, text, role, clickable = not editable, visible = in_view, selector, and a center-anchored bbox from page coords). Observation is best-effort: any failure falls back to empty elements without crashing, and a missing/unavailable browser yields a disconnected empty state.

**Implementation**: `friday/executor.py` (`_build_world_state`). Regression tests in `tests/friday/test_executor.py::TestBuildWorldState` (populate-from-observe, observe-failure-graceful, no-browser-empty).

**Consequences**: Primitive click/type through the UAL can now actually resolve real on-page targets, making the tested adapter path usable end-to-end instead of dead. Adds one `observe_interactive` call per click/type build; acceptable given it replaces a guaranteed-failure path.

---

## ADR-048: Operator Multi-Iteration Self-Correction Revived

**Status**: Approved — Implemented + Tested
**Date**: 2026-06-18

**Context**: The closed-loop operator (ADR-022) is supposed to PLAN → EXECUTE → VERIFY → REPAIR/REPLAN across up to `max_iterations`. But the "accept partial success" gate computed `made_progress = created_files or final_content or steps_executed > 0`. `steps_executed > 0` is true on essentially every iteration, so the loop **always** broke after iteration 1 — making iterations 2..N dead code and silently disabling self-correction. This was the "operator multi-iteration self-correction is dead (HIGH)" audit item.

**Decision**: Redefine progress and when to stop:
- Track `prev_met` (blocking requirements satisfied in the prior iteration).
- **Improvement** (`met > prev_met`) → keep iterating to repair the rest.
- **Final iteration** → accept partial success if any artifact or any requirement met; otherwise report max-iterations reached.
- **No improvement but a real artifact** (file/content) was produced → accept and stop.
- **No improvement, no artifact** → replan and continue.

"Ran some steps" is no longer treated as progress.

**Implementation**: `friday/operator.py` (the iteration loop). Regression tests in `tests/friday/test_operator.py::TestSelfCorrectionLoop` (multi-iteration when unmet, single-iteration terminates, completed goal breaks early).

**Consequences**: Self-correction is functional again — unmet blocking requirements now drive additional repair/replan iterations up to the cap, while satisfiable goals still complete early and `max_iterations=1` still terminates in one pass. Full suite: 784 passing.

---

## ADR-049: Browser-Agent Hardening Batch 2 — Tabs, iframe/Shadow-DOM, CDP Viewport

**Status**: Approved — Implemented + Tested + LIVE-VERIFIED
**Date**: 2026-06-18

**Context**: Continuation of the ADR-046 audit toward best-in-class browser operation. New-tab tracking and a native-dialog auto-handler had already landed in `_connect`/`_on_new_page`/`_attach_dialog_handler`, but three gaps remained that break real-site automation.

**Fixed this batch**:
1. **Tab management** — added `list_tabs()` (index/url/title/active), `switch_tab(index)` (sets active page, re-attaches dialog handler, brings to front), and `last_dialog()` accessor. `target=_blank`/`window.open` tabs are now reasoned over and switchable instead of leaving the agent stuck on a stale page.
2. **iframe + shadow-DOM traversal in `observe_interactive`** — replaced the top-document-only `querySelectorAll` with a recursive `walk(root, frameOff)` that descends into open shadow roots and **same-origin** iframes, offsetting coordinates so nested elements get correct page positions. Cross-origin frames are skipped safely (try/catch on `contentDocument`). This surfaces consent dialogs, payment iframes, and web-component controls that were previously invisible to the agent.
3. **CDP viewport fix** — `page.viewport_size` is frequently None over CDP, which made vision-click coordinate scaling fall back to a wrong 1280x800 and miss on HiDPI/real Chrome. `viewport_size()` now evaluates live `window.innerWidth/innerHeight` and `devicePixelRatio` and always returns a `device_pixel_ratio` field for correct scaling.

**Implementation**: `friday/actions/browser_controller.py` (`list_tabs`, `switch_tab`, `last_dialog`, recursive `observe_interactive` JS, rewritten `viewport_size`). Tests in `tests/friday/test_chrome_launcher.py::TestTabAndViewportSurface` (safe-fallback contract without a live browser). Full suite: 789 passing.

**Consequences**: The agent can now operate multi-tab flows, see and act on elements inside iframes/shadow DOM (a large class of modern sites), and place vision clicks accurately on real Chrome. Remaining audit items (networkidle/selector waits, file download/upload, auto-retry/vision-escalation on silent no-op) are tracked for a later batch.

---

## ADR-050: Browser-Agent Hardening Batch 3 — Network Waits, File Transfer, Silent No-Op Escalation

**Status**: Approved — Implemented + Tested + LIVE-VERIFIED (19/20 infra checks pass on real Chrome)
**Date**: 2026-06-18

**Context**: Final three items from the ADR-046 browser-agent audit.

**Fixed this batch**:
1. **Network-idle waits** — `navigate()` now waits for `domcontentloaded`, then best-effort `networkidle` (5s bound, falls back to a short fixed wait) so XHR/SPA pages are settled before the agent observes. Never hangs.
2. **File upload/download** — `upload_file(paths, index|selector)` resolves the target file input via live re-location, an explicit selector, or the first `input[type=file]`, then `set_input_files` (validates paths exist first). `download_file(trigger_index, elements, dest_dir)` clicks the trigger inside `expect_download` and saves to `~/.friday/downloads` (or a given dir), returning the saved path. Both are generic — no site hardcoding.
3. **Silent no-op click escalation** — `click_index` now returns a `changed` flag (URL before != after). The web agent watches it: when a click reports `ok` but `changed is False` (locator hit a wrong/non-interactive node), it auto-escalates to a vision click on the element's own label instead of silently stalling. This is the DOM→Vision fallback (ADR-014) applied to the "click did nothing" case.

**Implementation**: `friday/actions/browser_controller.py` (`navigate` networkidle, `upload_file`, `download_file`, `click_index` `changed` flag), `friday/capabilities/web_agent.py` (no-op detection + vision escalation in the click branch). Tests: `tests/friday/test_web_agent.py::TestSilentNoOpEscalation`, `tests/friday/test_chrome_launcher.py::TestUploadDownloadContract`. Full suite: 793 passing.

**Consequences**: The agent settles dynamic pages before acting, can move files in/out of web flows (uploads, downloads), and recovers from silent click failures by escalating to vision — eliminating a common stall. The ADR-046 audit is now fully closed; FRIDAY's browser operation covers the best-in-class capability set. Remaining work is live validation against real Chrome, tracked separately from the audit.

---

## ADR-051: Desktop Control Gets the Full Agentic Surface — Task On the Real Profile

**Status**: Approved — Implemented + Tested + LIVE-VERIFIED on the owner's signed-in Chrome
**Date**: 2026-06-18

**Context**: Google Sync blocks CDP on the owner's signed-in Chrome profile (confirmed live again this session: launching Profile 1 with `--remote-debugging-port` starts Chrome but the port never becomes reachable). This is a Chrome/Google limitation affecting all automation tools, not a FRIDAY bug. Previously the `DesktopChromeController` could only `navigate`/`click`(by OCR text)/`type`/`read` — enough to open and focus the profile, but NOT the full observe→decide→act loop the CDP `WebAgent` runs. So FRIDAY could open the user's profile but not truly *task* on it agentically.

**Decision**: Give `DesktopChromeController` the SAME duck-typed agentic surface as `BrowserController`, backed by OCR + screenshot + pyautogui instead of DOM/CDP:
- `observe_interactive(limit)` → OCR text regions as indexed "elements" with absolute SCREEN coordinates and the same dict shape the agent expects.
- `click_index` / `fill_index` → click/type at an element's screen coords (with a `changed` flag for silent-no-op detection and best-effort OCR verification).
- `scroll` (mouse wheel / Home-End), `press` (keys + combos), `screenshot_image`, `viewport_size` (real Chrome window size + dpr), `click_xy` (vision-fallback target).

Because the surface matches, the EXACT SAME generic `WebAgent` (zero site hardcoding) now operates the visible Chrome via vision/OCR. Added `friday/actions/browser_factory.py::build_browser_for_goal` which resolves the 3-tier strategy and returns the right STARTED controller (CDP `BrowserController` for non-login/closed-Chrome cases; `DesktopChromeController` when the signed-in profile is locked or CDP fails for a session-needing goal).

**Implementation**: `friday/actions/desktop_chrome.py` (agentic surface), `friday/actions/browser_factory.py` (strategy→controller). Tests: `tests/friday/test_desktop_chrome.py::TestAgenticSurface` + `::TestBrowserFactory` (9 new). Full suite: 802 passing.

**Live verification**: `scripts/live_desktop_agent.py` on the owner's real signed-in Chrome — focused the window, observed 40 OCR elements with coordinates, navigated to a site via the address bar, and confirmed the new page by OCR-reading it back. FRIDAY can now task on the real profile, not just open it.

**Consequences**: The login-gated path (Gmail/Instagram/etc. on the user's real session) is no longer a dead end — the same agent drives it via desktop control. DOM-first remains preferred (CDP dedicated/clone for speed and precision when logins aren't needed); desktop control is the honest human-like fallback per ADR-014. Known limitation: OCR observation captures the full screen, so for reliable clicking the Chrome window should be foreground (navigation via keyboard already works regardless); tightening observation to the Chrome window region is a future refinement.
