# FRIDAY — Complete Engineering Handoff v2 (Expanded)

> This document supersedes HANDOFF_FOR_DEVIN.md with full implementation detail.
> Audience: An independent senior engineer (Devin) who has zero prior context.
> Nothing is omitted. Nothing requires guessing.

---

## SECTION 0 — READ THIS FIRST

You are taking over as **Lead Architect + Principal Engineer** on FRIDAY.

Three documents define your world. Read them in order before writing a single line:

1. `FRIDAY Architecture Specification (FAS) v2.0` — the Constitutional document. Every architectural decision traces back here. If your implementation conflicts with this spec, **your implementation is wrong**.
2. `FRIDAY_ARCHITECTURE_AUDIT.md` — a full FAS compliance audit, traceability matrix, technical debt registry, and the 11-milestone roadmap. Already written. Do not redo it.
3. `CURRENT_PROJECT_STATE.md` — a forensic audit of the codebase as of this handoff. 50-task benchmark. Honest ratings. Read every section.

The single most important sentence in the entire codebase:

> The FAS describes a **persistent, event-driven Cognitive OS** built around a Kernel, World Model, Goal Graph, and continuous cognition. The current codebase is a **stateless, request-driven, linear pipeline** that terminates after each request.

Everything else follows from that gap.

---

## SECTION 1 — PROJECT IDENTITY

| Field | Value |
|---|---|
| Project name | FRIDAY (General Computer Operator) |
| Owner | Shreesh |
| OS target | Windows 10/11 (v1 is Windows-only) |
| Python target | 3.12 (3.14 dev installed; develop against 3.12) |
| Project root | `C:\Projects\JARVIS\for wind\` |
| PYTHONPATH | Must be set: `$env:PYTHONPATH="C:\Projects\JARVIS\for wind"` |
| Primary LLM | NVIDIA NIM API (`NVIDIA_API_KEY` in `.env`) |
| Fallback LLM | GROQ API (`GROQ_API_KEY` in `.env`) |
| Test command | `python -m pytest tests/friday/ -q` |
| Test count at handoff | 802 passing, 0 failing |
| Live validation scripts | `scripts/live_*.py` (manual only, not CI) |


---

## SECTION 2 — WHAT FRIDAY IS (AND IS NOT)

FRIDAY is a **General Computer Operator (GCO)**. Not a chatbot, assistant, browser automation tool, RPA system, or AutoGPT clone. The formal definition (FAS §5.21):

> A GCO accepts arbitrary human goals, converts them to explicit requirements, selects strategies, generates executable plans, continuously observes digital environments, executes reusable capabilities, verifies every claimed outcome with objective evidence, repairs failures through replanning, and learns safely from experience.

### What this means architecturally

Users express **goals** ("send the report to my professor"). FRIDAY determines the procedure. Applications are **environments** through which goals are achieved. There is no GmailAgent, no InstagramAgent, no hardcoded site logic. There is one cognition operating across many environments.

### The 20 Axioms (FAS Ch 3) — non-negotiable, binding on every line of code

| # | Axiom |
|---|---|
| 1 | Goals are immutable |
| 2 | Strategies are disposable |
| 3 | Observation precedes action |
| 4 | Observation never ends |
| 5 | Evidence outranks execution |
| 6 | Failure is information |
| 7 | Applications are environments |
| 8 | Capabilities are universal |
| 9 | Tasks are compositions |
| 10 | Unknown does not mean impossible |
| 11 | Every decision carries confidence |
| 12 | WorldState is reality |
| 13 | The user should never think procedurally |
| 14 | Learning changes competence, not identity |
| 15 | Generality outranks optimization |
| 16 | Time is a resource |
| 17 | Humans are part of the system |
| 18 | Every capability must be composable |
| 19 | Intelligence exists above software |
| 20 | The operator exists to reduce human cognitive load |

### Anti-patterns that are BANNED (FAS Ch 63)

Never build or commit:
- A GmailAgent / GmailHandler
- An InstagramAgent / InstagramHandler  
- A WhatsAppAgent / WhatsAppHandler
- Any hardcoded site URL in source
- Any hardcoded application name in logic branches
- A ResearchPipeline
- A SpecificAppWorkflow of any kind

Test `tests/friday/test_web_agent.py::test_no_site_names_in_source` enforces some of this. Extend it repo-wide in M5.


---

## SECTION 3 — REPOSITORY MAP (every folder, every file, every status)

```
C:\Projects\JARVIS\for wind\
│
├── friday/                          ← The new architecture (~9,300 lines)
│   │
│   ├── __init__.py                  ← empty
│   ├── bridge.py                    ← 450 lines. Routes commands between JARVIS
│   │                                   and FRIDAY modes. CONTAINS HARDCODED URL
│   │                                   MAP (TD-1, must die in M5). Also has
│   │                                   FridayBridge._execute_operator_step which
│   │                                   duplicates GoalExecutor — dead code path.
│   ├── core.py                      ← 280 lines. FridayEngine with execute_verified()
│   │                                   and perceive(). COMPLETELY ORPHANED — not
│   │                                   called by Operator. ActionVerifier inside also
│   │                                   orphaned. Will be deleted at M6.
│   ├── executor.py                  ← 715 lines. GoalExecutor. Executes capability
│   │                                   steps. Uses if/elif dispatch (not registry).
│   │                                   Has _build_world_state (shallow), _execute_click,
│   │                                   _execute_type, _execute_research, _execute_delivery,
│   │                                   _generate, execute_repair. The real execution engine.
│   └── operator.py                  ← 282 lines. Operator.run(goal). The main pipeline.
│                                       Runs Requirements+Plan in parallel, then
│                                       Execute→Verify→Repair loop (max 3 iterations).
│                                       Stateless. Terminates after each goal.
│
├── friday/actions/                  ← Low-level actuation layer
│   ├── __init__.py
│   ├── adapters/                    ← Universal Action Layer adapters
│   │   ├── __init__.py
│   │   ├── base.py                  ← AdapterProtocol (abstract interface)
│   │   ├── browser.py               ← BrowserAdapter: wraps BrowserController,
│   │   │                               priority=100
│   │   ├── desktop.py               ← DesktopAdapter: UIA via pyautogui,
│   │   │                               priority=80. Needs WorldState.ui_elements
│   │   │                               populated (currently shallow)
│   │   ├── desktop_actions.py       ← DesktopActionsAdapter: coord/hotkey
│   │   │                               fallback, priority=60
│   │   ├── resolver.py              ← AdapterResolver: priority-ordered cascade,
│   │   │                               exclude list for re-routing on failure
│   │   └── vision.py                ← VisionAdapter: OCR+pyautogui, priority=30,
│   │                                   last resort
│   ├── browser_controller.py        ← 710 lines. BrowserController over CDP/Playwright.
│   │                                   BEST-BUILT COMPONENT. Persistent loop thread.
│   │                                   observe_interactive (iframe+shadow DOM), tab
│   │                                   management, upload/download, viewport DPR fix.
│   │                                   LIVE-VERIFIED.
│   ├── browser_factory.py           ← build_browser_for_goal(). Strategy→controller.
│   ├── browser_session.py           ← Older BrowserSession (being superseded, keep but
│   │                                   don't extend)
│   ├── browser_strategy.py          ← resolve_browser_strategy(goal_text). 3-tier:
│   │                                   CDP_REUSE / CDP_LAUNCH / CDP_DEDICATED /
│   │                                   DESKTOP_CONTROL
│   ├── browser.py                   ← Older browser wrapper (legacy overlap)
│   ├── chrome_launcher.py           ← ensure_chrome_debug(), cdp_reachable(),
│   │                                   chrome_running_without_debug()
│   ├── chrome_profiles.py           ← Per-device profile discovery. resolve_profile().
│   │                                   NEVER hardcodes profile names.
│   ├── delivery.py                  ← DeliveryRequest, DeliveryGate (confirmation gate).
│   │                                   M6 debit: no hardcoded Gmail/WhatsApp logic here
│   │                                   (good). Uses WebAgent generically.
│   ├── desktop_chrome.py            ← 334 lines. DesktopChromeController. OCR+pyautogui
│   │                                   on the user's open Chrome. Full agentic surface:
│   │                                   observe_interactive, click_index, fill_index,
│   │                                   scroll, press, screenshot_image, viewport_size,
│   │                                   click_xy. LIVE-VERIFIED.
│   ├── file_tool.py                 ← FileTool. Real file creation. Supports
│   │                                   .txt/.md/.csv/.xlsx/.docx/.html. LIVE-VERIFIED.
│   ├── primitives.py                ← 626 lines. Universal Action Layer public API.
│   │                                   click/double_click/right_click/type_text/
│   │                                   press_key/press_hotkey/scroll/drag/
│   │                                   switch_window/observe/verify/wait_for/navigate.
│   │                                   init_primitives(browser_controller=...) wires adapters.
│   ├── profile_clone.py             ← Clone Chrome profile for CDP without locking user's
│   ├── result.py                    ← ActionResult contract. Every action returns this.
│   │                                   ActionStatus enum. ActionEvidence. ActionTimer.
│   ├── system.py                    ← SystemActions: launch_app, focus_window, list_windows.
│   │                                   Uses subprocess + pyautogui. LIVE-VERIFIED.
│   └── target.py                    ← Target dataclass: text/role/selector/automation_id/
│                                       window_title/coordinates/index. Frozen. Validated.
│
├── friday/api/                      ← FastAPI backend. DEFINED but NEVER SERVED.
│   │                                   No uvicorn.run() anywhere. Will be served in M11.
│   ├── __init__.py
│   ├── app.py                       ← create_friday_api(bridge, memory, ...) factory
│   ├── dependencies.py              ← AppContext, make_auth_dependency
│   ├── server.py                    ← server config
│   └── routes/                      ← commands, status, memory, models, tasks,
│       └── ...                         perception, websocket — all defined, none live
│
├── friday/capabilities/             ← Higher-order capabilities (composed from primitives)
│   ├── __init__.py
│   ├── research.py                  ← research(query, browser, evidence). DuckDuckGo→
│   │                                   follow links→read pages→record source URLs.
│   │                                   LIVE-VERIFIED. Does NOT classify as a pipeline;
│   │                                   called from executor when SEARCH_WEB capability needed.
│   └── web_agent.py                 ← 272 lines. WebAgent. Generic observe→decide→act loop.
│                                       ZERO site hardcoding. The closest thing to real
│                                       Deliberation in the codebase (browser-only).
│                                       LIVE-VERIFIED on dedicated profile.
│
├── friday/config/
│   ├── __init__.py
│   └── browser_config.py            ← Per-device Chrome profile config. ~/.friday/config.json.
│                                       resolve_browser_choice(). NEVER hardcodes profiles.
│
├── friday/learning/
│   └── __init__.py                  ← 8-LINE DOCSTRING. EMPTY. Nothing here.
│
├── friday/memory/                   ← 4-TIER SYSTEM. FULLY BUILT. COMPLETELY ORPHANED.
│   ├── __init__.py
│   ├── controller.py                ← FridayMemory coordinator. record_turn(), get_context(),
│   │                                   suggest_action_strategy(), remember_fact(). NOT USED.
│   ├── episodic.py                  ← EpisodicMemory. Interaction history. JSON file.
│   ├── interfaces.py                ← MemoryEntry, MemoryStore, MemoryTier abstractions
│   ├── procedural.py                ← ProceduralMemory. Learned patterns. JSON file.
│   ├── semantic.py                  ← SemanticMemory. Facts + NVIDIA nv-embed-v1 embeddings.
│   │                                   Temporal edges (valid_at/invalid_at). Cosine similarity
│   │                                   search + lexical fallback. NOT USED.
│   ├── stores.py                    ← JSONFileStore backend (all tiers)
│   └── working.py                   ← WorkingMemory. Volatile. Current session context. NOT USED.
│
├── friday/models/
│   ├── __init__.py
│   ├── router.py                    ← ModelRouter. Routes by ModelCapability to provider.
│   │                                   complete(prompt, capability, model, ...) → ModelResponse.
│   │                                   LIVE-VERIFIED.
│   └── providers/
│       ├── __init__.py
│       ├── nvidia_provider.py       ← NvidiaProvider. httpx async POST to
│       │                               integrate.api.nvidia.com/v1/chat/completions.
│       │                               embed() for nv-embed-v1. Rate limiting + retry.
│       │                               LIVE-VERIFIED. Uses: qwen3-next-80b-a3b-instruct (fast),
│       │                               meta/llama-3.3-70b-instruct (content), llama-guard-4-12b
│       │                               (safety), llama-3.2-90b-vision (vision).
│       └── groq_provider.py         ← GroqProvider. Fallback. Similar structure.
│
├── friday/perception/               ← Sensors. NOT unified. No shared interface.
│   ├── __init__.py
│   ├── browser.py                   ← BrowserPerception. Wraps BrowserController for
│   │                                   perception-layer consumption.
│   ├── desktop.py                   ← DesktopPerception. BROKEN: requires legacy
│   │                                   state_cache that is NEVER passed. Always returns [].
│   ├── environment.py               ← EnvironmentObserver + EnvironmentState. Used by
│   │                                   Operator to snapshot env. Very shallow.
│   ├── ocr.py                       ← OCREngine wrapping pytesseract. extract_text(),
│   │                                   extract_regions() → List[OCRRegion].
│   ├── priority.py                  ← ResolvedElement. PerceptionResolver. Semantic-first
│   │                                   priority system (Browser 100 > UIA 80 > ... > Vision 10).
│   ├── screen.py                    ← ScreenCapture using MSS. grab() → Screenshot.
│   ├── types.py                     ← BoundingBox, UIElement, BrowserElement, OCRRegion,
│   │                                   WindowInfo, PerceptionSource enum. These VALUE TYPES
│   │                                   are good — keep them in M2.
│   ├── vision.py                    ← VisionPerception. Uses NVIDIA llama-3.2-90b-vision.
│   │                                   locate_element(shot, description) → (x,y) normalized.
│   │                                   Used by web_agent for click_vision fallback.
│   └── world_state.py               ← WorldState (SNAPSHOT, not World Model). WorldStateBuilder.
│                                       DerivedFacts. Built fresh each call. Has confidence=0
│                                       on derived booleans. NOT a belief store.
│
├── friday/planner/                  ← Planning layer
│   ├── __init__.py
│   ├── decomposer.py                ← TaskDecomposer (legacy bridge). TaskPlan, TaskStep.
│   ├── goal_parser.py               ← GoalParser. Parses raw text → Goal(intent, target, ...).
│   ├── llm_decomposer.py            ← LLMDecomposer. Calls ModelRouter with task decomposition
│   │                                   prompt → List[DecomposedStep].
│   ├── operator_planner.py          ← OperatorPlanner. plan() → OperatorPlan (flat step list).
│   │                                   Calls LLMDecomposer; falls back to _generic_capabilities.
│   ├── query_extractor.py           ← extract_search_query(). Strips action verbs to get topic.
│   ├── repair.py                    ← RepairDiagnoser. diagnose(req, evidence) → RepairDiagnosis.
│   │                                   Classifies failure cause. Returns repair actions.
│   ├── replanner.py                 ← Replanner (thin wrapper, rarely used directly).
│   └── requirements.py              ← RequirementsDiscovery. discover(goal) → RequirementSet.
│                                       LLM prompt → JSON list of requirement strings.
│                                       _augment_structural adds FILE/DELIVER reqs.
│
├── friday/router/
│   ├── __init__.py
│   ├── classifier.py                ← ComplexityLevel (SIMPLE/MULTI_STEP/COMPLEX).
│   │                                   RequestMode (JARVIS/FRIDAY). classify(text) → label.
│   └── request_router.py            ← RequestRouter. route(command, wake_word) → RouteResult.
│
├── friday/tools/
│   ├── __init__.py
│   └── registry.py                  ← ToolCapability enum (34 values). Tool dataclass.
│                                       ToolRegistry. build_default_registry().
│                                       ALL 22 registered tools have handler=None.
│                                       Registry is used for PLANNING METADATA ONLY.
│                                       Real dispatch lives in executor.py if/elif.
│
├── friday/verification/
│   ├── __init__.py
│   ├── evidence.py                  ← collect_evidence(before, after) → ActionEvidence.
│   │                                   Diffs WorldState snapshots.
│   ├── evidence_law.py              ← THE CROWN JEWEL. EvidenceVerifier. ExecutionEvidence.
│   │                                   EvidenceKind enum. classify_requirement(). RequirementKind.
│   │                                   EvidenceArtifact. add_file/add_navigation/add_source_url/
│   │                                   add_gathered_info/add_generated_content/
│   │                                   add_delivery_confirmation/add_screenshot.
│   │                                   Prevents false completion by requiring real artifacts.
│   │                                   LIVE-VERIFIED. DO NOT CHANGE without deep understanding.
│   ├── screenshot_evidence.py       ← capture_screenshot(label) → ScreenshotEvidence.
│   │                                   is_blocked_page(text, url). blocked_reason().
│   └── verifier.py                  ← ActionVerifier. verify(action_type, target, before, after).
│                                       VerificationVerdict enum. ORPHANED with core.py.
│                                       Will be unified with evidence_law in M6.
│
├── automation/                      ← LEGACY ~10,387 lines. Browser automation services,
│                                       app control, old planner. Quarantine. Do not extend.
├── awareness/                       ← LEGACY ~1,659 lines. Windows UIA monitor (state_cache),
│                                       system monitor. Quarantine.
├── core/                            ← LEGACY ~3,466 lines. Assistant orchestrator,
│                                       capability dispatcher, telemetry. Quarantine.
├── server/                          ← LEGACY remote WebSocket server
├── services/                        ← LEGACY weather/maps services
│
├── main.py                          ← LEGACY JARVIS voice loop. BLOCKED by default.
│                                       Requires FRIDAY_ALLOW_LEGACY_MAIN=1 to run.
│                                       Voice (edge-tts), wake word (Porcupine), TTS,
│                                       microphone — ALL live here, NOT in friday/.
│
├── tests/
│   └── friday/                      ← 802 tests. ALL run under FRIDAY_DRY_RUN=1.
│       ├── conftest.py              ← Sets FRIDAY_DRY_RUN=1. CRITICAL. Never remove.
│       └── ...                      ← All mocked. Zero real I/O tests.
│
├── scripts/
│   ├── live_validate_hardening.py   ← Tests Ch29/30/49 features. 19/20 pass on dedicated CDP.
│   ├── live_desktop_agent.py        ← Tests DesktopChromeController on signed-in Chrome.
│   ├── live_web_agent.py            ← Tests WebAgent on Wikipedia.
│   └── live_your_profile.py        ← Tests launching Shreesh's profile via CDP (FAILS — Google Sync).
│
├── CURRENT_PROJECT_STATE.md        ← Forensic state audit. Read entirely.
├── FRIDAY_ARCHITECTURE_AUDIT.md    ← FAS compliance audit. Read entirely.
├── HANDOFF_FOR_DEVIN.md            ← Earlier version of this document (superseded).
└── .env                             ← API keys. Plaintext (no vault yet — TD-9).
```


---

## SECTION 4 — THE CURRENT PIPELINE (exact execution flow)

When `bridge.process("some goal")` is called:

```
FridayBridge.process(command, wake_word)
  │
  ├─ RequestRouter.route(command) → RouteResult
  │     └─ Classifier.classify(command) → (RequestMode, ComplexityLevel)
  │
  ├─ [JARVIS mode] → _handle_jarvis() → ModelRouter.complete() → text response
  │
  └─ [FRIDAY mode] → _handle_friday() → _execute_multi_step()
        │
        ├─ resolve_browser_strategy(goal_text) → BrowserStrategy
        │     (CDP_REUSE / CDP_LAUNCH / CDP_DEDICATED / DESKTOP_CONTROL)
        │
        ├─ [if CDP] → _get_browser_controller() → BrowserController
        ├─ [if DESKTOP] → DesktopChromeController()
        │
        └─ Operator(model_router, browser_controller, max_iterations=2).run(goal)
              │
              ├─ [PARALLEL] RequirementsDiscovery.discover(goal) → RequirementSet
              │             OperatorPlanner.plan(goal, env_state) → OperatorPlan
              │
              ├─ [LOOP up to max_iterations]:
              │     ├─ GoalExecutor.execute_plan(plan, goal) → ExecutionResult
              │     │     └─ per OperatorStep:
              │     │           ├─ SEARCH_WEB → _execute_research(query, ctx)
              │     │           │     └─ research(query, browser, evidence)
              │     │           │           ├─ browser.search_web(query) [DDG]
              │     │           │           ├─ for each link: browser.navigate(url)
              │     │           │           ├─ browser.read_text() → text
              │     │           │           └─ evidence.add_gathered_info(text, url)
              │     │           │
              │     │           ├─ NAVIGATE_URL → browser.navigate(url)
              │     │           ├─ READ_DOM → browser.read_text()
              │     │           ├─ CLICK_ELEMENT → _execute_click() → primitives.click()
              │     │           ├─ TYPE_TEXT → _execute_type() → primitives.type_text()
              │     │           ├─ GENERATE_TEXT → _generate() → ModelRouter.complete()
              │     │           ├─ CREATE_FILE → FileTool.create_file()
              │     │           └─ SEND_MESSAGE → _execute_delivery() → WebAgent.run()
              │     │
              │     ├─ EvidenceVerifier.verify_one(req, evidence) per requirement
              │     │     └─ classify_requirement(desc) → RequirementKind
              │     │           ├─ GATHER → needs EvidenceKind.GATHERED_INFO artifact
              │     │           ├─ PRODUCE → needs EvidenceKind.GENERATED_CONTENT
              │     │           ├─ FILE → needs EvidenceKind.FILE_ARTIFACT (size > 0)
              │     │           ├─ NAVIGATE → needs EvidenceKind.NAVIGATION
              │     │           └─ DELIVER → needs EvidenceKind.DELIVERY_CONFIRMATION
              │     │
              │     ├─ [if unmet] RepairDiagnoser.diagnose() → GoalExecutor.execute_repair()
              │     │
              │     └─ [if improved or artifacts] → accept / break
              │
              └─ return OperatorOutcome(completed, requirements_met, trace, files, content)
```

**What breaks about this flow architecturally:**
- Terminates after each goal (violates Ch 17 Persistent Runtime)
- No Kernel (violates Ch 20)
- No Events (violates Ch 21)
- No World Model with beliefs (violates Ch 9)
- Plan generated all-at-once upfront (violates Ch 10 Deliberation)
- Subsystems call each other directly (violates Ch 52)
- Memory never consulted (violates Ch 14)
- Reflection never happens (violates Ch 13)

The 802 tests treat this pipeline as a regression oracle during the new Kernel build.


---

## SECTION 5 — WHAT IS LIVE-VERIFIED (honest state)

### Confirmed working on real Chrome (live scripts)

| Capability | File | Evidence |
|---|---|---|
| LLM completion via NVIDIA NIM | `nvidia_provider.py` | httpx POST, real response, ~1-2s |
| Requirements discovery | `requirements.py` | qwen3-next-80b, real JSON |
| Goal decomposition | `llm_decomposer.py` | LLM → step list |
| DuckDuckGo search → follow links → read pages | `research.py` | DDG /l/?uddg= decoded |
| Content synthesis with citations | `executor._generate` | llama-3.3-70b |
| Create .txt/.md | `file_tool.py` | Disk write, byte-size verified |
| Create .csv/.xlsx/.docx | `file_tool.py` | Unit tested (not live) |
| Full research+file in 6.6s | `scripts/live_validate.py` | End-to-end pipeline |
| CDP browser: observe 60 elements | `browser_controller.py` | iframe+shadow DOM traversal |
| CDP browser: viewport DPR | `browser_controller.py` | 1048×714, DPR=1.25 |
| CDP browser: tab management | `browser_controller.py` | list_tabs/switch_tab |
| CDP browser: upload/download | `browser_controller.py` | set_input_files/expect_download |
| CDP browser: networkidle navigate | `browser_controller.py` | 0.6s on example.com |
| CDP browser: silent no-op escalation | `web_agent.py` | changed=False → vision fallback |
| Desktop OCR on signed-in Chrome | `desktop_chrome.py` | OCR reads 40 elements |
| Desktop Ctrl+L navigation | `desktop_chrome.py` | Navigated, confirmed by OCR |
| WebAgent 8 steps Wikipedia | `web_agent.py` | LLM latency limited, infra works |
| Evidence Law prevents false completion | `evidence_law.py` | GATHER needs real URL |

### Known broken / untested

| Capability | Why broken |
|---|---|
| CDP on Shreesh/Profile 1 | Google Sync blocks port. Confirmed. Permanent unless FRIDAY_REQUIRE_REAL_CHROME=0 |
| Gmail/Instagram/WhatsApp (signed-in) | No working CDP path + desktop OCR untested on these sites |
| Voice I/O (new architecture) | Not ported from legacy main.py |
| API server | No uvicorn.run() anywhere |
| Memory wired to execution | Orphaned. operator.py imports nothing from memory/ |
| Learning | Empty module |
| Multi-app tasks | Never tested |
| DesktopPerception UIA elements | Returns [] (needs legacy state_cache never passed) |

---

## SECTION 6 — CRITICAL TECHNICAL DEBT (ordered, must eliminate)

### TD-1 — HARDCODED SITE URLS (CRITICAL, violates Axiom 15)
**File:** `bridge.py`, function `_target_to_url`
**Code:**
```python
known_urls = {
    "instagram": "https://www.instagram.com/direct/inbox/",
    "gmail": "https://mail.google.com",
    "whatsapp": "https://web.whatsapp.com",
    # ... 8 more
}
```
**Problem:** Violates FAS Axiom 15, Ch 39, Ch 63 Anti-Patterns. Any new site requires code changes.
**Fix in:** M5. Delete the dict entirely. Replace with environment discovery.

### TD-2 — TWO PARALLEL EXECUTION PATHS
**Files:** `bridge.py::_execute_operator_step` AND `executor.py::GoalExecutor`
**Problem:** Dead code path in bridge. Confusing maintenance. Ch 52 violation.
**Fix in:** M6 (migrate both to Kernel-owned execution).

### TD-3 — TWO VERIFICATION SYSTEMS (one orphaned)
**Files:** `verifier.py::ActionVerifier` (orphaned with core.py) AND `evidence_law.py::EvidenceVerifier` (active)
**Problem:** Architectural inconsistency. Only one should exist.
**Fix in:** M6 (unify into `verification/engine.py`).

### TD-4 — ORPHANED FridayEngine (core.py)
**File:** `friday/core.py`
**Problem:** FridayEngine.execute_verified() and perceive() never called by Operator.
**Fix in:** M6 (delete after migration).

### TD-5 — REGISTRY TOOLS ALL handler=None
**File:** `tools/registry.py`, function `build_default_registry()`
**Problem:** 22 tools, all metadata-only. Real dispatch is if/elif in executor.
**Fix in:** M7 (wire real handlers).

### TD-6 — MEMORY SYSTEM ORPHANED
**Files:** `memory/` (all 7 modules)
**Problem:** Fully built but `operator.py` never imports memory.
**Fix in:** M8 (wire to Kernel + Reflection).

### TD-7 — DesktopPerception BROKEN
**File:** `perception/desktop.py`
**Problem:** `__init__(state_cache=None)` → always returns []. Never passed legacy state_cache.
**Fix in:** M7 (proper Desktop Runtime replaces this).

### TD-8 — DIRECT CROSS-SUBSYSTEM CALLS EVERYWHERE
**All of `friday/`:** Operator→Executor→research/web_agent→browser. Violates Ch 52.
**Fix in:** Gradually M1→M6 via Event Bus + contracts.

### TD-9 — SECRETS IN PLAINTEXT .env
**File:** `.env`
**Problem:** NVIDIA_API_KEY and GROQ_API_KEY in plaintext. Ch 35 §35.6 requires a Secret Vault.
**Fix in:** M4 (Security/Permission layer).

### TD-10 — ALL 802 TESTS MOCKED
**File:** `tests/friday/` — conftest.py sets `FRIDAY_DRY_RUN=1`
**Problem:** Tests prove code consistency, not real-world functionality. Ch 56 violation.
**Fix in:** Every milestone — add goal-completion, replay, and failure-injection tests alongside each build.

### TD-11 — .git COPY DIRECTORIES
**Location:** `.git - Copy/`, `.git - Copy (2)/`
**Problem:** Repo hygiene. Confuse git tools.
**Fix:** Delete now (safe, low-risk).


---

## SECTION 7 — FAS COMPLIANCE BY SUBSYSTEM (condensed reference)

| Subsystem | Chapter | Status | Compliance | Priority | Action |
|---|---|---|---|---|---|
| Cognitive Kernel | 20 | ❌ ABSENT | 0% | P0 | Build M1 |
| Persistent Runtime | 17 | ❌ ABSENT | 0% | P0 | Build M1 |
| Event System | 21 | ❌ ABSENT | 0% | P0 | Build M1 |
| World Model (beliefs) | 9 | ⚠️ SNAPSHOT | 20% | P0 | Rewrite M2 |
| Goal Lifecycle | 18 | ⚠️ str only | 15% | P1 | Build M3 |
| Goal Graph | 19 | ❌ ABSENT | 0% | P1 | Build M3 |
| 3 Cognitive Layers | 6 | ⚠️ CONFLATED | 30% | P1 | Separate M4 |
| Intent Analysis | 7 | ⚠️ PARTIAL | 35% | P2 | Extend M5 |
| Problem Classification | 8 | ❌ ABSENT | 5% | P2 | Build M5 |
| Deliberation | 10 | ⚠️ PLAN-ONLY | 25% | P1 | Rewrite M4 |
| Operation | 11 | ✅ PARTIAL | 55% | P2 | Extend M6 |
| Perception (unified) | 12 | ⚠️ PARTIAL | 30% | P1 | Unify M6 |
| Reflection | 13 | ❌ ABSENT | 0% | P1 | Build M8 |
| Memory (wired) | 14 | ⚠️ ORPHANED | 30% | P1 | Wire M8 |
| Learning | 15 | ❌ EMPTY | 2% | P2 | Build M9 |
| Capabilities (contract) | 16 | ⚠️ handler=None | 25% | P1 | Build M7 |
| Decision Architecture | 22 | ⚠️ IMPLICIT | 20% | P1 | Build M4 |
| Environment Architecture | 23 | ⚠️ DUCK-TYPED | 35% | P1 | Formalize M6 |
| Interaction Architecture | 24 | ⚠️ PARTIAL | 45% | P2 | Extend M6 |
| Unknown Env Exploration | 25/66 | ❌ ABSENT | 5% | P1 | Build M7 |
| Procedure Synthesis | 26 | ⚠️ FLAT LIST | 30% | P2 | Rewrite M5 |
| Competence Model | 28 | ❌ ABSENT | 0% | P2 | Build M8 |
| Browser Runtime | 29 | ✅ PARTIAL | 50% | P2 | Wrap M6 |
| Desktop Runtime | 30 | ⚠️ OCR-ONLY | 20% | P1 | Build M7 |
| Motor System | 31 | ⚠️ OPEN-LOOP | 25% | P2 | Build M7 |
| Verification Engine | 32 | ✅ TWO-VERIFIERS | 55% | P2 | Unify M6 |
| Evidence System | 33 | ✅ PARTIAL | 50% | P2 | Promote M8 |
| Recovery Engine | 34 | ⚠️ REPAIR-ONLY | 30% | P2 | Generalize M8 |
| Safety & Permission | 35 | ⚠️ GUARDS-ONLY | 20% | P1 | Build M4 |
| Research Domain | 37 | ✅ PARTIAL | 45% | P2 | Extend M10 |
| Communication Domain | 39 | ⚠️ HARDCODED | 25% | P2 | Fix M5 |
| **OVERALL** | — | — | **~18%** | — | — |

---

## SECTION 8 — ENVIRONMENT SETUP (step by step)

```powershell
# 1. Navigate to project
cd "C:\Projects\JARVIS\for wind"

# 2. Set PYTHONPATH (required for all commands)
$env:PYTHONPATH = "C:\Projects\JARVIS\for wind"

# 3. Create and activate venv (use 3.12 target)
python -m venv .venv312
.venv312\Scripts\activate

# 4. Install dependencies
pip install -r requirements-312.txt
# hypothesis is already installed (6.155.7)

# 5. Verify .env has required keys
# Required: NVIDIA_API_KEY
# Optional: GROQ_API_KEY

# 6. Run tests to confirm baseline
python -m pytest tests/friday/ -q
# Expected: 802 passed, 22 warnings

# 7. Verify imports work
python -c "import friday.operator, friday.executor, friday.actions.browser_controller; print('OK')"
```

### .env file contents (template)
```
NVIDIA_API_KEY=<your key here>
GROQ_API_KEY=<your key here, optional>
FRIDAY_DRY_RUN=0
FRIDAY_REQUIRE_REAL_CHROME=0
AUTO_LAUNCH_CHROME=0
CHROME_REMOTE_DEBUG_PORT=9222
FRIDAY_ALLOW_LEGACY_MAIN=
FRIDAY_CHROME_PROFILE=
FRIDAY_CONFIG_DIR=
FRIDAY_SEARCH_ENGINE=duckduckgo
```

### Chrome profile for Shreesh's device
```json
// C:\Users\Shreesh\.friday\config.json
{"chrome_profile": "Shreesh"}
```
Resolves to: `C:\Users\Shreesh\AppData\Local\Google\Chrome\User Data` + `Profile 1`

**IMPORTANT:** CDP is blocked on this profile by Google Sync. You cannot use `BrowserController` with `require_real_chrome=True` on this profile. Two workarounds:
1. Use `force_dedicated=True` in `ensure_chrome_debug()` → clean profile, no logins
2. Use `DesktopChromeController()` → OCR/keyboard on whatever Chrome is open

### Live validation commands
```powershell
# CDP dedicated profile (Chrome must be CLOSED first)
python scripts/live_validate_hardening.py   # 19/20 pass expected

# OCR desktop control (Chrome must be OPEN with signed-in profile)
python scripts/live_desktop_agent.py

# Web agent Wikipedia (Chrome must be CLOSED first for CDP)
python scripts/live_web_agent.py
```


---

## SECTION 9 — THE APPROVED BUILD STRATEGY

### Decision: Path B — Pragmatic Convergence

**Decision owner:** Shreesh (project owner)
**Rationale:** The FAS is a multi-year OS-grade spec. A big-bang rewrite with nothing working in between kills projects. Path B honors the Constitution while keeping a working system at all times.

**The contract:**
1. Build the Cognitive Kernel IN PARALLEL with the existing pipeline. Do not touch the pipeline.
2. The existing 802 tests + live scripts are the **regression oracle**. They must keep passing.
3. Migrate capabilities to the Kernel milestone by milestone.
4. Delete the old pipeline code ONLY after the Kernel-based system fully passes the regression oracle.

### Binding Core vs Deferred Aspirational

**Must implement (binding):** FAS Ch 1–36, Ch 49–53
These cover: Kernel, PCR, Events, World Model, Goals, Deliberation, Reflection, Memory, Learning, Capabilities, Environments, Verification, Evidence, Safety, Research, Communication, Documents, Resources, Temporal, Identity, Runtime Communication, Composition.

**Deferred to v2+ (aspirational):**
- Ch 41 (full SWE Domain depth)
- Ch 44 (Self-improvement automation)
- Ch 47 (Device federation)
- Ch 54 (Plugin marketplace)
- Ch 64 (Vision-2035: robots, AR, wearables)

### What MUST NEVER appear in source code
- Hardcoded site URL (`"instagram": "https://..."`)
- Site-specific method (`def send_instagram_dm(...)`)
- Application-specific logic branch (`if "gmail" in target: ...`)
- Any code that only works for one named application
- Any code that cannot be replaced by the Exploration Engine for an unknown app

---

## SECTION 10 — FULL 11-MILESTONE ROADMAP

### Milestone 1 — Cognitive Kernel Foundation (FAS Ch 17, 20, 21, 52)

**Objective:** A continuously running, event-driven Kernel that owns global state and can checkpoint/restore. Pure infrastructure — no LLMs, no browser, no cognition.

**Why first:** Without this, no FAS invariant can hold. Every subsystem built without it must be rebuilt on top of it. Zero architectural debt from the start.

**What to build:**
```
friday/events/
  event.py          ← Immutable Event (id, logical_time, wall_time, event_type,
                       source, payload, correlation_id, parent_id, signature)
  bus.py            ← EventBus (publish/subscribe/route/filter)
  store.py          ← Append-only EventStore + replay + checkpoint

friday/kernel/
  clock.py          ← CognitiveClock (Lamport logical clock + wall time)
  scheduler.py      ← CognitiveScheduler (adaptive tick loop in daemon thread)
  checkpoint.py     ← CheckpointManager (save/restore/auto-checkpoint)
  kernel.py         ← CognitiveKernel (the singleton authority)
  echo_runtime.py   ← Demo RuntimeContract implementation (proves isolation)
  contracts/
    runtime.py      ← RuntimeContract ABC
    environment.py  ← EnvironmentContract stub
    capability.py   ← CapabilityContract stub
    sensor.py       ← SensorContract stub
    resource.py     ← ResourceContract stub
```

**Full data schemas:**

Event schema:
```python
@dataclass(frozen=True)
class Event:
    id: str                  # uuid4 string
    logical_time: int        # monotonically increasing Lamport clock
    wall_time: float         # time.time() at emission
    event_type: str          # dot-namespaced, e.g. "goal.created", "observation.received"
    source: str              # runtime name that emitted this
    payload: FrozenDict      # immutable payload — use frozenset/tuple for nesting
    correlation_id: str      # ties related events (e.g. a whole goal run)
    parent_id: Optional[str] # event that caused this one (None = root cause)
    signature: str           # sha256(id + event_type + repr(payload) + str(parent_id))

# FrozenDict helper:
class FrozenDict(dict):
    """Immutable dict for use in frozen dataclasses."""
    def __setitem__(self, *_): raise TypeError("FrozenDict is immutable")
    def __hash__(self): return hash(tuple(sorted(self.items())))
```

EventBus interface:
```python
class EventBus:
    def publish(self, event: Event) -> None
    # Pattern matching: "goal.*" matches "goal.created", "goal.completed"
    # Use fnmatch for pattern. Returns subscription_id (UUID string).
    def subscribe(self, pattern: str, handler: Callable[[Event], None]) -> str
    def unsubscribe(self, subscription_id: str) -> None
    def route(self, event: Event) -> List[Callable]
    # Thread-safe. All handlers called synchronously in publish() thread.
    # Future: async handlers via queue.
```

EventStore interface:
```python
class EventStore:
    def __init__(self, path: str):  # e.g. "~/.friday/events/session.jsonl"
    def append(self, event: Event) -> None
    def replay(self, from_logical_time: int = 0) -> Iterator[Event]
    def checkpoint(self, state: dict, at_logical_time: int) -> str  # returns path
    def load_checkpoint(self, path: str) -> Tuple[dict, int]  # state, logical_time
    def replay_from_checkpoint(self, checkpoint_path: str) -> Tuple[dict, Iterator[Event]]
    # Storage: JSON-lines file. One Event per line. Deterministic serialization.
```

CognitiveClock interface:
```python
class CognitiveClock:
    def tick(self) -> int          # increment and return logical time
    def now(self) -> Tuple[int, float]  # (logical_time, wall_time)
    def update(self, received: int)  # Lamport merge: self._t = max(self._t, received) + 1
    def serialize(self) -> dict    # {"logical": int, "wall": float}
    def restore(self, state: dict) -> None
```

CognitiveKernel public API (FAS §20.19 — ONLY these exposed externally):
```python
class CognitiveKernel:
    def start(self) -> None
    def shutdown(self) -> None
    def submit_goal(self, goal_text: str, constraints: dict = None) -> str  # goal_id
    def submit_observation(self, observation: dict) -> None
    def publish_event(self, event: Event) -> None
    def query_world(self) -> dict
    def query_goals(self) -> List[dict]
    def request_capability(self, capability: str, params: dict) -> str  # request_id
    def checkpoint(self) -> str    # checkpoint path
    def restore(self, path: str) -> None
    def health(self) -> dict       # {"status": "ok"|"degraded", "tick": int, ...}
```

RuntimeContract (every future runtime implements this):
```python
class RuntimeContract(ABC):
    @abstractmethod
    def initialize(self, kernel: CognitiveKernel) -> None: ...
    @abstractmethod
    def tick(self, logical_time: int) -> None: ...
    @abstractmethod
    def observe(self) -> List[dict]: ...
    @abstractmethod
    def receive(self, event: Event) -> None: ...
    @abstractmethod
    def publish(self, event: Event) -> None: ...
    @abstractmethod
    def checkpoint(self) -> dict: ...
    @abstractmethod
    def restore(self, state: dict) -> None: ...
    @abstractmethod
    def shutdown(self) -> None: ...
    @abstractmethod
    def health(self) -> dict: ...
```

EchoRuntime (demo — proves plug-in isolation):
```python
# Must import ONLY from friday.events and friday.kernel.contracts
# Zero imports from operator.py, executor.py, browser_controller.py, etc.
class EchoRuntime(RuntimeContract):
    def tick(self, logical_time: int) -> None:
        self.publish(Event(event_type="echo.tick", payload={"count": logical_time}, ...))
    def receive(self, event: Event) -> None:
        if event.event_type == "echo.request":
            self.publish(Event(event_type="echo.response", parent_id=event.id, ...))
```

**M1 Acceptance Criteria (ALL must pass before M2):**

- A1: `kernel.start()` → runs continuously. Only `kernel.shutdown()` stops it. Test: assert `health()["status"]` remains "ok" for 5 seconds with no goals.
- A2: Every emitted Event is immutable. `event.id = "x"` raises `FrozenInstanceError`. Test with pytest.raises.
- A3: Deterministic replay test:
  ```python
  # 1. Start kernel, submit 10 events, checkpoint at t=5
  # 2. Kill kernel (simulate crash)
  # 3. Restore from checkpoint, replay events 6-10
  # 4. Assert kernel.health()["tick"] == original_tick
  # 5. Assert query_goals() == original_goals
  ```
- A4: A4 = A3 with actual process restart (subprocess.Popen + kill + restart). Optional if A3 passes.
- A5: Import boundary test for EchoRuntime:
  ```python
  import ast, pathlib
  src = pathlib.Path("friday/kernel/echo_runtime.py").read_text()
  tree = ast.parse(src)
  imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
  allowed = {"friday.events", "friday.kernel.contracts"}
  for imp in imports:
      module = getattr(imp, "module", None) or (imp.names[0].name if hasattr(imp,"names") else "")
      assert any(module.startswith(a) for a in allowed), f"Illegal import: {module}"
  ```
- A6: Hypothesis property tests:
  - logical_time is monotonically increasing across published events
  - parent_id (when set) always refers to an event with lower logical_time
  - signature fails verification if any field is tampered
- A7: Drop 10% of events via `EventStore` subclass that skips every 10th append. `kernel.health()["status"]` == "degraded" but no exception raised.
- A8: Benchmark: 100 ticks/second sustained for 5 seconds with EchoRuntime. Assert with `time.perf_counter`.

**What NOT to do in M1:**
- Do NOT modify operator.py, executor.py, bridge.py, planner/, capabilities/, memory/
- Do NOT integrate with LLMs, browser, desktop
- Do NOT build the World Model yet (M2)
- Do NOT submit goals that do anything (goals are stubs in M1)


### Milestone 2 — World Model as Beliefs (FAS Ch 9, 12 partial)

**Objective:** Replace the WorldState snapshot with a living probabilistic belief store owned by the Kernel.

**What to build:**
```
friday/world/
  world_model.py    ← WorldModel (owned by Kernel, updated via Events)
  belief.py         ← Belief dataclass (confidence, source, timestamp, expiry, evidence_ids)
  objects.py        ← WorldObject + Relationship graph
  worlds.py         ← ObservedWorld, PredictedWorld, DesiredWorld
friday/perception/
  contracts.py      ← SensorContract ABC (observe/subscribe/query/track)
  observation.py    ← Observation dataclass (uniform from all sensors)
  fusion.py         ← SensorFusion (combines observations → beliefs with confidence)
```

**Belief schema:**
```python
@dataclass
class Belief:
    id: str
    description: str       # human-readable
    confidence: float      # 0.0 to 1.0
    source: str            # which sensor/runtime
    observed_at: float     # wall time
    expires_at: Optional[float]  # None = never expires
    supporting_evidence: List[str]    # evidence artifact IDs
    contradicting_evidence: List[str] # evidence artifact IDs
    dependencies: List[str]           # other belief IDs this depends on
    last_updated: float

    def decay(self, rate: float = 0.01) -> 'Belief':
        """Return new Belief with reduced confidence (temporal decay)."""
        dt = time.time() - self.observed_at
        new_conf = max(0.0, self.confidence - rate * dt)
        return replace(self, confidence=new_conf, last_updated=time.time())
```

**Uniform Observation schema (all sensors must produce this):**
```python
@dataclass(frozen=True)
class Observation:
    id: str
    sensor: str            # "screen", "ocr", "dom", "uia", "clipboard", etc.
    environment: str       # "browser", "desktop", "system"
    object_type: str       # "window", "button", "text", "url", etc.
    attributes: FrozenDict # sensor-specific data
    confidence: float
    timestamp: float
    bbox: Optional[Tuple[int,int,int,int]]  # (x,y,w,h) if visual
```

**Three Worlds:**
```python
class ObservedWorld:  # what sensors say right now
class PredictedWorld: # what the operator expects after next action
class DesiredWorld:   # what must be true for the goal to be complete
```

**M2 Acceptance Criteria:**
- Beliefs carry confidence + decay over time (test: belief confidence < 1.0 after 10s)
- Contradictory observations produce lower confidence belief (not higher)
- Desired World representable from a RequirementSet
- ScreenCapture emits Observations via SensorContract interface
- Fusion merges two sensor observations on same object into one Belief with higher confidence
- No raw sensor data read outside `friday/perception/` (import boundary test)
- Keep existing `WorldState` working as-is for the pipeline (do NOT remove it — migration happens in M6)

### Milestone 3 — Goals & Goal Graph (FAS Ch 18, 19, 51)

**What to build:**
```
friday/goals/
  goal.py       ← Goal dataclass + state machine (11 states)
  graph.py      ← GoalGraph (nodes, typed edges)
  lifecycle.py  ← GoalLifecycleManager (transition rules)
friday/identity/
  identity.py   ← CognitiveIdentity (checkpoint + restore across sessions)
```

**Goal state machine:**
```
Created → Understood → Specified → Deliberating → Executing → Waiting
                                                           ↓         ↓
                                               Recovering ←──────────┘
                                                    ↓
                                               Verifying
                                              ↙    ↓    ↘
                                        Completed Failed Cancelled
```

**Goal schema:**
```python
@dataclass
class Goal:
    id: str
    text: str
    creator: str             # "user", "system", "subgoal"
    created_at: float
    priority: int            # 1-10
    desired_world: DesiredWorld
    requirements: List[Requirement]
    constraints: List[str]
    evidence: List[str]      # evidence artifact IDs
    history: List[GoalEvent] # every state transition
    current_state: GoalState
    parent_id: Optional[str] # if this is a subgoal
    children: List[str]      # subgoal IDs
```

**Goal Graph edge types:**
```python
class EdgeType(str, Enum):
    DEPENDENCY = "dependency"   # B cannot start until A completes
    INFORMATION = "information" # A's output feeds into B
    RESOURCE = "resource"       # A and B share a resource
    TEMPORAL = "temporal"       # A must complete before B starts in time
    TRIGGER = "trigger"         # A completion triggers B creation
    OBSERVATION = "observation" # a world observation triggers B
```

**M3 Acceptance Criteria:**
- Goal survives a simulated process restart (pickle to disk, unpickle, correct state)
- A suspended goal resumes in its pre-suspension state
- Dependency edge: B refuses to start until A is Completed
- split_goal(goal_id) → 3 subgoals with correct parent reference
- merge_goals([id1, id2]) → one combined goal preserving both evidence sets

### Milestone 4 — Deliberation, Decisions, Resources, Safety (FAS Ch 10, 22, 45-48, 35)

**What to build:**
```
friday/cognition/
  deliberation.py   ← DeliberationEngine (utility-driven next-action)
  decision.py       ← DecisionRecord (structured, explainable)
friday/resources/
  registry.py       ← ResourceRegistry (discover + register resources)
  scheduler.py      ← ResourceScheduler (allocate + release)
  types.py          ← Resource dataclass (type, health, availability, cost)
friday/safety/
  permission.py     ← PermissionManager (trust zones, permission levels)
  vault.py          ← SecretVault (replaces plaintext .env — uses keyring or encrypted file)
  policy.py         ← SafetyPolicy (hard boundaries, confirmation rules)
```

**Deliberation — the most important architectural change:**

The existing `OperatorPlanner.plan()` generates an entire plan upfront. This must be replaced. Deliberation selects ONE action at a time:

```python
class DeliberationEngine:
    def next_action(
        self,
        current_world: ObservedWorld,
        desired_world: DesiredWorld,
        goal: Goal,
        available_capabilities: List[CapabilityMetadata],
    ) -> DecisionRecord:
        """
        1. Generate candidate actions from available capabilities
        2. For each candidate, predict(action) → PredictedWorld
        3. Score each by utility:
           utility = goal_progress(predicted, desired)
                   + information_gain(predicted, current)
                   - risk(action)
                   - cost(action, resources)
                   - uncertainty(prediction_confidence)
        4. Apply reversibility: if utility tie, prefer reversible
        5. Apply safety policy: reject irreversible actions below confidence threshold
        6. Return DecisionRecord for highest utility
        """
```

**Decision schema:**
```python
@dataclass
class DecisionRecord:
    id: str
    goal_id: str
    timestamp: float
    logical_time: int
    candidates: List[CandidateAction]  # all options considered
    chosen: CandidateAction
    predicted_outcome: PredictedWorld
    utility: float
    confidence: float
    reasoning: str            # brief text — NOT LLM chain-of-thought
    safety_checked: bool
    reversible: bool
```

**Safety — required before any dangerous action:**

Permission levels (Ch 35):
```
OBSERVATION (0) — read, inspect, hover          → No confirmation needed
INTERACTION (1) — click, type, navigate         → No confirmation needed  
MODIFICATION (2) — create files, send messages  → Notify
DELETION (3) — delete files, close apps         → Confirm
FINANCIAL (4) — purchases, transfers            → Always confirm
IDENTITY (5) — passwords, auth tokens           → Always confirm + vault
ADMINISTRATIVE (6) — system settings            → Always confirm
```

Secret Vault must:
- Never store plaintext credentials in `.env` after M4
- Use `keyring` library (Windows Credential Manager) as backend
- API: `vault.get("NVIDIA_API_KEY")` — never returns raw to logs

**M4 Acceptance Criteria:**
- A utility-scored DecisionRecord is produced for any (world, goal, capabilities) triple
- Two equally-useful candidates: prefer the reversible one
- A DELETION action without explicit user approval → SafetyViolation exception
- ResourceScheduler.allocate() prevents double-allocation of exclusive resources (browser session, mouse)
- NVIDIA_API_KEY retrievable via vault.get(), never via os.getenv() in new code

### Milestone 5 — Intent, Classification, Procedure Synthesis + TD-1 (FAS Ch 7, 8, 26)

**Objective:** Real understanding stage; incremental procedure graphs; DELETE hardcoded site logic.

**What to build:**
```
friday/cognition/
  intent.py         ← IntentAnalysisEngine → IntentObject
  classification.py ← ProblemClassificationEngine → ProblemClass
  procedure.py      ← ProcedureSynthesizer → ProcedureGraph (incremental)
```

**IntentObject schema:**
```python
@dataclass
class IntentObject:
    primary_goal: str
    secondary_goals: List[str]
    constraints: List[Constraint]
    assumptions: List[Assumption]  # each has AssumptionLevel (Safe/Probable/Uncertain/Dangerous)
    unknowns: List[str]
    risks: List[Risk]
    clarification_needed: bool
    clarification_questions: List[str]
    deliverables: List[str]
    success_conditions: List[str]
    estimated_complexity: int   # 1-5
    confidence: float
```

**Problem classes** (FAS Ch 8):
```python
class ProblemClass(str, Enum):
    KNOWLEDGE_ACQUISITION = "knowledge_acquisition"
    INFORMATION_TRANSFORMATION = "information_transformation"
    COMMUNICATION = "communication"
    CREATION = "creation"
    DIAGNOSTIC = "diagnostic"
    REPAIR = "repair"
    EXPLORATION = "exploration"
    NAVIGATION = "navigation"
    EXECUTION = "execution"
    MONITORING = "monitoring"
    COORDINATION = "coordination"
```

**TD-1 fix (REQUIRED in M5):**
```python
# DELETE this from bridge.py:
known_urls = {
    "instagram": "https://www.instagram.com/direct/inbox/",
    # ...
}

# Replace with: the browser strategy + environment discovery selects where to go.
# If the user says "open Instagram DMs", the intent engine recognizes
# it as COMMUNICATION, the procedure synthesizer composes:
# [navigate_to_communication_environment, find_dm_interface, compose_message, send]
# The specific URL is discovered at runtime via the web agent, not hardcoded.
```

**M5 Gate:** Run repo-wide site-name check:
```python
import ast, pathlib
friday_src = list(pathlib.Path("friday").rglob("*.py"))
banned = ["gmail", "instagram", "whatsapp", "twitter", "facebook", "youtube"]
for f in friday_src:
    src = f.read_text().lower()
    for site in banned:
        # Allow in comments and string literals that are log messages
        # Fail on: dict keys, if conditions, function names, class names
        tree = ast.parse(src)
        # check all Name nodes, attribute access, dict keys...
assert no_violations, "Site-specific code found"
```

### Milestone 6 — Environment Contracts, Unified Verification, Operation (FAS Ch 11, 23, 24, 29, 32, 33)

**What to build:**
```
friday/environments/
  contract.py       ← EnvironmentContract ABC
  browser/
    adapter.py      ← BrowserEnvironment(EnvironmentContract) wraps BrowserController
  desktop/          ← stub (fleshed out in M7)
friday/verification/
  engine.py         ← UnifiedVerificationEngine (merges evidence_law + verifier)
  evidence_repo.py  ← EvidenceRepository (queryable, indexed, signed)
```

**Environment contract (FAS Ch 23):**
```python
class EnvironmentContract(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...          # e.g. "browser.chrome.dedicated"
    
    @abstractmethod
    def observe(self) -> List[Observation]: ...
    
    @abstractmethod
    def interact(self, action: Action) -> ActionResult: ...
    
    @abstractmethod
    def verify(self, expected: PredictedWorld) -> VerificationResult: ...
    
    @abstractmethod
    def query_objects(self, query: ObjectQuery) -> List[WorldObject]: ...
    
    @abstractmethod
    def query_capabilities(self) -> List[str]: ...
    
    @abstractmethod
    def pause(self) -> None: ...
    
    @abstractmethod
    def resume(self) -> None: ...
    
    @abstractmethod
    def shutdown(self) -> None: ...
    
    @abstractmethod
    def health(self) -> dict: ...
```

**Migration rule for BrowserController:**
- Do NOT rewrite `browser_controller.py`
- Create `friday/environments/browser/adapter.py` that wraps it
- BrowserEnvironment.observe() calls `browser_controller.observe_interactive()`
- BrowserEnvironment.interact(action) routes to the appropriate controller method
- This is the "Playwright adapter" — in M11 or M7+ you can add a WebDriver adapter behind the same contract

**Unified Verification:**
```python
class UnifiedVerificationEngine:
    """Merges EvidenceVerifier (artifact-based) and ActionVerifier (diff-based)."""
    
    def verify_action(
        self,
        action_type: str,
        predicted: PredictedWorld,
        observed: ObservedWorld,
        evidence: ExecutionEvidence,
    ) -> VerificationResult: ...
    
    def verify_requirement(
        self,
        requirement: Requirement,
        evidence: ExecutionEvidence,
    ) -> VerificationResult: ...
    
    def verify_goal(
        self,
        goal: Goal,
        evidence: ExecutionEvidence,
    ) -> GoalVerificationResult: ...
```

**M6 Gate:** Swap BrowserEnvironment for a StubEnvironment that returns fake observations. The Kernel + Deliberation should produce the same DecisionRecord structure with either backend — proving the Kernel never depends on Playwright.

### Milestone 7 — Desktop Runtime, Motor, Capabilities, Exploration (FAS Ch 16, 25, 30, 31, 66)

**The most impactful milestone for the GCO thesis. Makes FRIDAY actually general.**

**What to build:**
```
friday/environments/desktop/
  runtime.py        ← DesktopRuntime(EnvironmentContract)
  window_manager.py ← WindowManager (enumerate, focus, resize, minimize)
  display_manager.py← DisplayManager (multi-monitor, DPI, scaling)
  clipboard.py      ← ClipboardManager (read/write/history)
  session.py        ← SessionManager (power state, lock, restore)
  notifications.py  ← NotificationManager (subscribe to OS notifications)

friday/capabilities/
  motor.py          ← MotorSystem (closed-loop: observe→move→observe→correct)
  registry.py       ← CapabilityRegistry (handlers wired, confidence tracked)
  contracts.py      ← CapabilityContract ABC

friday/environments/unknown/
  exploration.py    ← ExplorationEngine
  object_graph.py   ← ObjectGraph (build from any interface)
  affordances.py    ← AffordanceInferrer (what can I do with this object?)
  experiment.py     ← SafeExperimentPlanner (risk-ladder: observe→hover→click→modify)
  demonstration.py  ← DemonstrationRecorder (watch user, extract principles)
```

**Motor System — closed-loop (not open-loop pyautogui):**
```python
class MotorSystem:
    """Closed-loop motor control. Observe→predict→move→observe→correct."""
    
    def acquire_target(self, description: str, world: ObservedWorld) -> Optional[TargetLock]: ...
    
    def move_to(self, target: TargetLock, profile: MotionProfile = MotionProfile.PRECISE) -> MotorResult:
        """
        1. Observe current cursor position
        2. Predict cursor trajectory
        3. Move step-by-step (not directly to destination)
        4. After each step: observe → compare to prediction
        5. If target moved: re-acquire and correct
        6. On arrival: verify target still there
        """
    
    def click(self, target: TargetLock) -> MotorResult: ...
    def type_text(self, text: str, target: TargetLock) -> MotorResult: ...
    def scroll_to_visible(self, target: TargetLock) -> MotorResult: ...
```

**Exploration Engine — the heart of "general":**
```python
class ExplorationEngine:
    """Makes unknown software learnable. This is what makes FRIDAY a GCO."""
    
    def explore(self, environment: EnvironmentContract) -> ExplorationResult:
        """
        1. observe() → raw observations
        2. build_object_graph() → objects with inferred types
        3. infer_affordances(objects) → what can be done with each
        4. plan_experiments() → ordered by risk (observe<hover<click<modify)
        5. execute_safe_experiment() → update object graph
        6. Repeat until sufficient confidence or budget exceeded
        """
    
    def learn_from_demonstration(self, recording: DemonstrationRecording) -> List[Procedure]:
        """
        User demonstrated a task. Extract reusable principles (not coordinates).
        Principles: "clicked the most prominent button in top-right area"
        Not: "clicked at (1243, 56)"
        """
    
    def generate_capability_candidate(self, exploration: ExplorationResult) -> Optional[CapabilityCandidate]:
        """If exploration succeeded repeatedly, propose a new capability."""
```

**CapabilityContract — all capabilities must implement this:**
```python
class CapabilityContract(ABC):
    @property
    @abstractmethod
    def id(self) -> str: ...
    
    @property
    @abstractmethod
    def version(self) -> str: ...
    
    @property
    @abstractmethod
    def confidence(self) -> float: ...  # evidence-backed, updated after each run
    
    @abstractmethod
    def preconditions(self) -> List[Condition]: ...
    
    @abstractmethod
    def expected_outcome(self) -> WorldStateDelta: ...
    
    @abstractmethod
    async def execute(self, params: dict, world: ObservedWorld) -> ActionResult: ...
    
    @abstractmethod
    def verify(self, result: ActionResult, world: ObservedWorld) -> bool: ...
    
    @abstractmethod
    def recover(self, failure: ActionResult) -> Optional['CapabilityContract']: ...
    
    @abstractmethod
    def update_competence(self, result: ActionResult) -> None: ...
```

**M7 Gate:** Run a goal on software FRIDAY has never seen. Use ExplorationEngine to understand the interface, then complete the goal. ZERO app-specific code anywhere.

### Milestones 8-11 (abbreviated — full detail in FRIDAY_ARCHITECTURE_AUDIT.md)

**M8 — Reflection, Memory Wiring, Competence, Recovery (FAS Ch 13, 14, 28, 34)**
- Build `friday/cognition/reflection.py` (prediction error, 5 Questions, multi-scale)
- Wire existing `friday/memory/` to Kernel + Reflection
- Build `friday/competence/` (evidence-backed per-capability performance)
- Gate: repeated task shows measurable improvement

**M9 — Learning, Temporal, Long-Horizon, Background (FAS Ch 15, 42, 43, 49)**
- Build `friday/learning/` (pattern discovery, generalization, validation pipeline)
- Build `friday/temporal/` (deadline tracking, knowledge aging, prediction)
- Gate: multi-session goal advances while user is away

**M10 — Domain Depth as Compositions (FAS Ch 37, 39, 40, 41)**
- Deepen Research, Communication, Document domains
- All implemented as pure capability compositions (no domain-specific state)
- Gate: deleting a domain module leaves all capabilities intact

**M11 — Evolution, Plugins, Benchmarks, Frontends, Federation (FAS Ch 27, 47, 54, 55, 57)**
- Capability Evolution: candidate→sandbox→benchmark→promote→rollback
- Plugin architecture
- Benchmark suite (goal-completion, not unit test counts)
- FastAPI finally served with uvicorn
- Multi-device Goal Graph


---

## SECTION 11 — TARGET REPOSITORY STRUCTURE

This is where the codebase should land after all milestones. The guiding principle (FAS Ch 53): `kernel/` and `*/contracts/` change rarely; `environments/`, `capabilities/`, `models/`, `domains/` are replaceable plug-ins.

```
friday/
├── kernel/                    # Ch 20 — Stable API, changes rarely
│   ├── kernel.py
│   ├── clock.py
│   ├── scheduler.py
│   ├── checkpoint.py
│   ├── echo_runtime.py
│   └── contracts/
│       ├── runtime.py
│       ├── environment.py
│       ├── capability.py
│       ├── sensor.py
│       └── resource.py
│
├── events/                    # Ch 21 — Event infrastructure
│   ├── event.py
│   ├── bus.py
│   └── store.py
│
├── world/                     # Ch 9 — Belief store (replaces world_state.py)
│   ├── world_model.py
│   ├── belief.py
│   ├── objects.py
│   └── worlds.py
│
├── goals/                     # Ch 18/19 — Goal + Graph
│   ├── goal.py
│   ├── graph.py
│   └── lifecycle.py
│
├── cognition/                 # Ch 6/7/8/10/13/22/26 — Thinking
│   ├── intent.py
│   ├── classification.py
│   ├── deliberation.py
│   ├── decision.py
│   ├── procedure.py
│   └── reflection.py
│
├── perception/                # Ch 12 — Sensors
│   ├── contracts.py
│   ├── observation.py
│   ├── fusion.py
│   ├── screen.py              # migrated (now implements SensorContract)
│   ├── ocr.py                 # migrated
│   ├── vision.py              # migrated
│   └── sensors/
│       ├── uia.py             # Windows UIA
│       ├── dom.py             # Browser DOM
│       ├── clipboard.py
│       └── process.py
│
├── environments/              # Ch 23 — Replaceable environment plug-ins
│   ├── contract.py
│   ├── browser/
│   │   ├── adapter.py         # wraps BrowserController (Playwright)
│   │   └── profiles.py        # migrated chrome_profiles.py
│   ├── desktop/
│   │   ├── runtime.py
│   │   ├── window_manager.py
│   │   ├── display_manager.py
│   │   ├── clipboard.py
│   │   └── session.py
│   └── unknown/
│       ├── exploration.py
│       ├── object_graph.py
│       ├── affordances.py
│       ├── experiment.py
│       └── demonstration.py
│
├── capabilities/              # Ch 16 — Capability contracts + registry
│   ├── contracts.py
│   ├── registry.py
│   ├── motor.py
│   ├── interaction.py         # adapter cascade (migrated from actions/adapters)
│   └── primitives/            # migrated from actions/primitives.py + adapters/
│
├── verification/              # Ch 32/33 — Unified
│   ├── engine.py
│   └── evidence_repo.py
│
├── memory/                    # Ch 14/50 — MIGRATED (keep stores, wire to Kernel)
│   ├── controller.py
│   ├── working.py
│   ├── episodic.py
│   ├── procedural.py
│   ├── semantic.py
│   ├── interfaces.py
│   └── stores.py
│
├── competence/                # Ch 28
├── resources/                 # Ch 45-48
│   ├── registry.py
│   ├── scheduler.py
│   └── types.py
│
├── safety/                    # Ch 35
│   ├── permission.py
│   ├── vault.py
│   └── policy.py
│
├── identity/                  # Ch 51
├── learning/                  # Ch 15/44
├── temporal/                  # Ch 49
│
├── domains/                   # Ch 37/39/40/41 — Compositions, NOT agents
│   ├── research.py
│   ├── communication.py
│   ├── documents.py
│   └── software_engineering.py
│
├── models/                    # LLM providers (a Resource type)
│   ├── router.py              # migrated
│   └── providers/
│       ├── nvidia_provider.py # migrated
│       └── groq_provider.py   # migrated
│
├── frontends/                 # Ch 57 — Thin clients
│   └── api/                   # migrated from api/
│
└── benchmarks/                # Ch 55 — Goal-completion suite

legacy/                        # Quarantined JARVIS code
tests/
├── unit/
├── contracts/                 # import boundary tests
├── goals/                     # goal-completion tests
├── replay/                    # deterministic replay tests
├── failure_injection/
└── adversarial/
```

---

## SECTION 12 — KEY DESIGN DECISIONS AND RATIONALE

### Why start with the Event System, not the Kernel?

The Event dataclass is the simplest, most atomic piece with zero dependencies. Start there. Every other M1 file depends on it. If Event is wrong, everything is wrong. Get it right first.

### Why not wrap the existing pipeline in a "Kernel facade"?

Because it would be fake compliance. The FAS requires that cognition is continuous (Ch 6, 17). Wrapping a stateless pipeline in a Kernel class doesn't make it continuous — it makes it a lie. Build the real thing.

### Why keep the existing pipeline untouched during M1-M5?

Risk management. The pipeline handles real goals right now. It is the demonstration vehicle for Shreesh and the regression oracle for Devin. Breaking it has no benefit during foundation work. Migration happens in M6 when the Kernel can actually run capabilities.

### Why merge the two verifiers (M6, not earlier)?

`evidence_law.py::EvidenceVerifier` is genuinely excellent and the most important piece in the codebase. It must not be disrupted until the unified engine matches its behavior exactly. The unified engine should pass all 802 existing tests before replacing the old verifier.

### Why wrap BrowserController instead of rewriting it?

`browser_controller.py` is 710 lines of battle-tested Playwright code that was live-verified on real Chrome. It handles iframe/shadow DOM traversal, DPR-aware viewport, tab management, upload/download — all verified. A rewrite risks regression. Wrap it behind the `EnvironmentContract` and the Kernel never knows it's Playwright.

### Why is Memory already built but completely disconnected?

The memory system was built speculatively before the Kernel and Reflection existed. It's a well-designed standalone module. The wire-up (M8) simply involves:
1. Subscribing memory modules to Kernel events
2. Emitting `memory.candidate` events from the Reflection subsystem
3. Having the controller subscribe to `memory.candidate` events

No rewrite needed. Just connections.

---

## SECTION 13 — IMPLEMENTATION RULES (binding on every commit)

1. **No hardcoding.** If something is specific to one site, app, or person — it's wrong.
2. **No application-specific logic.** No GmailHandler, InstagramAgent, VSCodeCapability.
3. **Every module maps to a FAS chapter.** Docstring: `"""Ch 20 — Cognitive Kernel."""`
4. **Every new subsystem needs:** Design doc + Unit tests + Goal-completion test + Benchmark + Acceptance criteria.
5. **Nothing bypasses the Kernel.** After M1, all subsystems communicate via events.
6. **Stop and escalate if the architecture would be violated.** Do not silently compromise.
7. **Tests must remain ≥ 802 passing at all times.** Never merge a PR that breaks tests.
8. **Do not serve the API** (no `uvicorn.run()`) until M11.

---

## SECTION 14 — PR CHECKLIST (run before every merge)

```
□ Does any new module import directly from another subsystem (after M1)? → FAIL
□ Does any code hardcode a site URL or application name? → FAIL
□ Does any capability assume a specific environment? → FAIL
□ Does the change have unit tests AND a goal-completion test? → FAIL if no
□ Can this module be replaced independently without touching the Kernel? → must be YES
□ Does every significant action have a predicted outcome? (required M4+) → YES
□ Does the change trace back to a FAS chapter? (document in PR description) → YES
□ Would this still work if the LLM was replaced with a different model? → YES
□ Would this still work in 5 years? → YES
□ Is python -m pytest tests/friday/ -q still 802+ passing? → must be YES
□ Did you add the change to FRIDAY_ARCHITECTURE_AUDIT.md traceability matrix? → YES
```

---

## SECTION 15 — FIRST 5 STEPS (start here)

**Step 1 — Clean up repo hygiene (15 min):**
```powershell
# Verify tests pass
$env:PYTHONPATH="C:\Projects\JARVIS\for wind"
python -m pytest tests/friday/ -q
# Expected: 802 passed

# Delete duplicate git directories (safe)
Remove-Item -Recurse -Force "C:\Projects\JARVIS\for wind\.git - Copy"
Remove-Item -Recurse -Force "C:\Projects\JARVIS\for wind\.git - Copy (2)"
```

**Step 2 — Read the three documents (2-3 hours):**
- `FRIDAY_ARCHITECTURE_AUDIT.md` — every section
- `CURRENT_PROJECT_STATE.md` — every section
- `friday/operator.py` + `friday/executor.py` — understand the current pipeline

**Step 3 — Create the M1 package skeleton:**
```powershell
# Create directories
New-Item -ItemType Directory -Force friday/events
New-Item -ItemType Directory -Force friday/kernel/contracts
New-Item -ItemType Directory -Force tests/kernel

# Create empty __init__.py files
"" | Out-File friday/events/__init__.py
"" | Out-File friday/kernel/__init__.py
"" | Out-File friday/kernel/contracts/__init__.py
"" | Out-File tests/kernel/__init__.py

# Create tests/kernel/conftest.py
@"
import os
os.environ.setdefault("FRIDAY_DRY_RUN", "1")
"@ | Out-File tests/kernel/conftest.py
```

**Step 4 — Write `friday/events/event.py` first:**
The immutable Event dataclass. See schema in Section 10. No other dependencies. Write tests immediately: `tests/kernel/test_event.py`. Every field, immutability, signature verification.

**Step 5 — Write `friday/events/bus.py` + `friday/events/store.py`:**
Then `friday/kernel/clock.py`, then `scheduler.py`, then `kernel.py`, then `checkpoint.py`, then `echo_runtime.py`.

**At each step:** write the code → write the tests → run `python -m pytest tests/ -q` → commit only when green.

---

## SECTION 16 — MODELS AND LLM INTEGRATION NOTES

### Currently used models (NVIDIA NIM, live-verified)

| Model | Use case | Latency | Notes |
|---|---|---|---|
| `qwen/qwen3-next-80b-a3b-instruct` | Requirements discovery, decomposition, web agent decisions | ~1-2s | Default for classification tasks. Best speed/quality. |
| `meta/llama-3.3-70b-instruct` | Content generation (reports, synthesis) | ~40s cold | Slow on cold start. Good quality. |
| `meta/llama-guard-4-12b` | Safety classification | ~1s | Used for content safety checks |
| `meta/llama-3.2-90b-vision-instruct` | Vision (screenshot analysis, click_vision) | ~3-5s | Requires base64 image in payload |
| `nvidia/nv-embed-v1` | Semantic memory embeddings | ~1s | 512 token limit |

### NVIDIA NIM API integration

```python
# The provider: friday/models/providers/nvidia_provider.py
# Base URL: https://integrate.api.nvidia.com/v1
# Auth: Bearer token (NVIDIA_API_KEY from .env)
# Endpoint: POST /chat/completions (OpenAI-compatible)
# Vision: include image_url in message content

# ModelRouter usage:
from friday.models.router import ModelRouter, ModelCapability
router = ModelRouter()
router.register_provider(NvidiaProvider())

response = await router.complete(
    "Generate a report about...",
    capability=ModelCapability.REASONING,
    model="meta/llama-3.3-70b-instruct",
    max_tokens=1200,
    temperature=0.4,
    system_prompt="...",
)
# response.text → the completion text
# response.model_used → which model was actually used
# response.latency_ms → how long it took
```

### GROQ fallback

Same interface. Used when NVIDIA is unavailable or rate-limited. Configured via `GROQ_API_KEY`.

### Free-tier latency warning

NVIDIA NIM free tier has 20-30s cold-start latency. The existing Operator fires Requirements + Planning in parallel to mitigate. In M4, the Resource Model should schedule LLM calls as resources with rate limits tracked.

---

## SECTION 17 — CHROME PROFILE SYSTEM (important for all browser work)

### How it works

Profile configuration lives at `~/.friday/config.json`:
```json
{"chrome_profile": "Shreesh"}
```

Resolution chain:
1. `os.environ["FRIDAY_CHROME_PROFILE"]` (highest priority)
2. `~/.friday/config.json` → `chrome_profile` key
3. Fallback: dedicated debug profile (`%LOCALAPPDATA%\friday_chrome_debug`)

`chrome_profiles.py::resolve_profile("Shreesh")` → `Profile 1` in `C:\Users\Shreesh\AppData\Local\Google\Chrome\User Data`

### CDP access tiers

| Tier | When | How | Limitations |
|---|---|---|---|
| CDP_REUSE | Debug port already open | `BrowserController(port=9222)` | None if already running |
| CDP_LAUNCH | Chrome closed | `ensure_chrome_debug(profile_directory="Profile 1")` | Google Sync blocks profile CDP |
| CDP_DEDICATED | Need clean session | `ensure_chrome_debug(force_dedicated=True)` | No user logins |
| DESKTOP_CONTROL | Profile locked / CDP blocked | `DesktopChromeController()` | OCR accuracy, no DOM |

### Why CDP fails on Shreesh's profile

Chrome's Google Sync service detects the CDP debug port and blocks communication. This is a Chrome/Google security feature. It cannot be bypassed without disabling sync or using a clone profile. The `profile_clone.py` module can create a clone (copies Cookies + Local Storage but not Google auth tokens — so most sites work except Google-authenticated ones).

### What works on the signed-in profile

`DesktopChromeController` (OCR + keyboard) was live-verified:
- Focuses the Chrome window
- Navigates via Ctrl+L → type URL → Enter
- Reads screen text via OCR
- Operates like a human on ANY site including Gmail/Instagram (OCR accuracy permitting)
- `observe_interactive()` returns OCR-based elements (not DOM — lower precision)

---

## SECTION 18 — TESTING STRATEGY

### Current state (what you inherit)

802 unit/property tests, all under `FRIDAY_DRY_RUN=1`, all mocked. They prove code consistency. They prove NOTHING about real-world behavior.

### What you must add per milestone

**Every milestone must produce:**

1. **Contract tests** — import boundary checks proving no subsystem calls another directly
2. **Unit tests** — per module, per function, edge cases
3. **Property tests** (Hypothesis) — invariants that hold across random inputs
4. **Goal-completion test** — end-to-end: submit a goal → observe outcome (not mocked)
5. **Replay test** — emit events → checkpoint → restore → assert identical state
6. **Failure injection test** — kill a component → system degrades gracefully, does not crash

### Test directory structure (target)

```
tests/
├── conftest.py               ← sets FRIDAY_DRY_RUN=1 globally
├── friday/                   ← existing 802 tests (DO NOT BREAK)
│   └── conftest.py           ← CRITICAL: sets FRIDAY_DRY_RUN=1
├── kernel/                   ← M1 tests
│   ├── conftest.py
│   ├── test_event.py
│   ├── test_bus.py
│   ├── test_store.py
│   ├── test_clock.py
│   ├── test_kernel.py
│   ├── test_checkpoint.py
│   └── test_echo_runtime.py  ← includes import boundary test
├── world/                    ← M2 tests
├── goals/                    ← M3 tests
├── cognition/                ← M4-M5 tests
├── environments/             ← M6-M7 tests
├── integration/              ← Cross-subsystem (no DRY_RUN)
│   ├── test_goal_completion_research_file.py
│   └── test_goal_completion_web_agent.py
├── replay/                   ← Deterministic replay tests
└── failure_injection/        ← Chaos tests
```

### The import boundary test pattern (use for every new module)

```python
# tests/kernel/test_echo_runtime.py
import ast
import pathlib

def test_echo_runtime_import_boundary():
    """EchoRuntime must only import from friday.events and friday.kernel.contracts."""
    src = pathlib.Path("friday/kernel/echo_runtime.py").read_text()
    tree = ast.parse(src)
    
    allowed_prefixes = ("friday.events", "friday.kernel.contracts", "abc", "typing")
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert any(node.module.startswith(p) for p in allowed_prefixes), \
                f"Illegal import in echo_runtime.py: {node.module}"
```

---

## SECTION 19 — ADR HISTORY (Architecture Decision Records)

All ADRs are in `ARCHITECTURE_DECISIONS.md`. Key decisions relevant to your work:

| ADR | Decision | Why it matters |
|---|---|---|
| ADR-023 | Evidence Law — false completion impossible | The core quality guarantee. Never weaken. |
| ADR-024 | Screenshot evidence + captcha detection | Anti-loop mechanism. Keep. |
| ADR-025 | Universal Action Layer live | Primitives + adapter cascade. Migrate in M6. |
| ADR-027 | BrowserController requires real Chrome | CDP-first. Dedicated profile is the reliable path. |
| ADR-028 | Chrome profile system per-device | Never hardcode Shreesh's profile. |
| ADR-029 | 3-tier browser strategy | CDP→Desktop fallback logic. Extend in M6. |
| ADR-033 | FRIDAY_DRY_RUN=1 for tests | Never remove from conftest.py. |
| ADR-035 | Tests were opening real windows | Reason DRY_RUN exists. Never regress. |
| ADR-043 | CDP blocked on signed-in profile | Permanent limitation. Desktop control is the answer. |
| ADR-047 | Executor WorldState populates live elements | _build_world_state calls observe_interactive. |
| ADR-048 | Operator self-correction revived | made_progress fix. Loop runs all iterations. |
| ADR-049 | Browser hardening batch 2 | Tabs, iframe/shadow DOM, CDP viewport. |
| ADR-050 | Browser hardening batch 3 | networkidle, file upload/download, no-op escalation. |
| ADR-051 | Desktop control full agentic surface | DesktopChromeController now has observe_interactive etc. |

---

## SECTION 20 — THE NORTH STAR

When you are unsure about a design decision, ask these questions in order:

1. Does this violate any of the 20 Axioms? → If yes, stop.
2. Does this hardcode any application or site? → If yes, stop.
3. Can this subsystem be replaced independently without touching the Kernel? → It must be yes.
4. Would this still work if the LLM changed? → It must be yes.
5. Does this reduce human cognitive load? → It should be yes.

The ultimate success criterion (FAS §0.9):

> Can the operator successfully complete arbitrary real-world goals that it has never previously encountered?

Everything you build should move the system closer to that.

**Current state:** 18% of the way there.
**Your job:** Build the foundation (M1-M3) so everything else can be built correctly.

Start with `friday/events/event.py`.

---

*End of FRIDAY Engineering Handoff v2*
*Document created from forensic codebase inspection + FAS v2.0 cross-reference*
*Supersedes HANDOFF_FOR_DEVIN.md*
