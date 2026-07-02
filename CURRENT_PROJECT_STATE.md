# FRIDAY Project — Forensic Engineering Audit

**Document type:** Reality check — every claim backed by code evidence  
**Generated:** Based on live code inspection of `c:\Projects\JARVIS\for wind\`  
**Total codebase:** ~9,300 lines (friday/) + ~16,283 lines (legacy JARVIS)  
**Test suite:** 802 collected, 802 passing (ALL under FRIDAY_DRY_RUN=1, ALL mocked)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Map](#2-architecture-map)
3. [Entry Points & Boot Sequence](#3-entry-points--boot-sequence)
4. [Operator Pipeline (The Brain)](#4-operator-pipeline-the-brain)
5. [Browser Control Layer](#5-browser-control-layer)
6. [Desktop Control Layer](#6-desktop-control-layer)
7. [LLM Provider Layer](#7-llm-provider-layer)
8. [Memory System](#8-memory-system)
9. [Verification & Evidence Law](#9-verification--evidence-law)
10. [Tool Registry & Execution Dispatch](#10-tool-registry--execution-dispatch)
11. [Web Agent (Generic Site Operator)](#11-web-agent-generic-site-operator)
12. [File & Document Creation](#12-file--document-creation)
13. [Research Capability](#13-research-capability)
14. [API Layer](#14-api-layer)
15. [Legacy Systems & Migration State](#15-legacy-systems--migration-state)
16. [Test Suite Analysis](#16-test-suite-analysis)
17. [Real-World Task Benchmark (50 Tasks)](#17-real-world-task-benchmark-50-tasks)
18. [Critical Issues & Architectural Debt](#18-critical-issues--architectural-debt)
19. [Dependency & Infrastructure Map](#19-dependency--infrastructure-map)
20. [Honest Capability Matrix](#20-honest-capability-matrix)

---

## 1. Executive Summary

### One-Paragraph Truth

FRIDAY is a partially-built autonomous desktop agent with a well-designed architecture
that is approximately 40% implemented to production quality. The core pipeline
(Goal → Requirements → Plan → Execute → Verify → Repair) exists as real code and has
been live-verified for simple single-domain tasks (research + file creation). Browser
control via CDP on a dedicated profile works. Desktop control via pyautogui/OCR works
for basic navigation. However, the system has NEVER been live-tested on its primary
use cases (operating Instagram, Gmail, WhatsApp on the user's signed-in profile),
has no voice I/O integration in the new architecture, has no frontend client, and
has multiple orphaned/disconnected subsystems. The 802 passing tests prove code
compiles and internal logic is consistent, but prove ZERO about real-world functionality.

### Confidence Rating

```
Overall System Readiness:  ██░░░░░░░░  20% (for intended use cases)
Architecture Quality:      ████████░░  80% (well-designed, coherent ADRs)
Code Quality:              ███████░░░  70% (clean, documented, typed)
Real-World Proven:         ██░░░░░░░░  15% (only research + file tasks)
Integration Completeness:  ███░░░░░░░  30% (many orphaned connections)
Test Trustworthiness:      █░░░░░░░░░  10% (all mocked, no real I/O)
```

---

## 2. Architecture Map

### High-Level System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              FRIDAY SYSTEM                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────┐    ┌──────────────────────────────────────────────────────┐  │
│  │  main.py     │    │  friday/ Package (~9,300 lines, 75+ modules)         │  │
│  │  (LEGACY)    │    │                                                      │  │
│  │  BLOCKED     │    │  ┌──────────┐   ┌────────────┐   ┌──────────────┐  │  │
│  │  by default  │◄──►│  │ bridge.py│──►│ operator.py│──►│ executor.py  │  │  │
│  │              │    │  └──────────┘   └────────────┘   └──────────────┘  │  │
│  │  Voice/TTS   │    │       │               │                │           │  │
│  │  Wake Word   │    │       ▼               ▼                ▼           │  │
│  │  Awareness   │    │  ┌─────────┐  ┌────────────┐  ┌──────────────┐   │  │
│  │  Remote Svr  │    │  │ router/ │  │ planner/   │  │ actions/     │   │  │
│  │              │    │  │classify │  │requirements│  │ browser_ctrl │   │  │
│  └──────────────┘    │  │         │  │op_planner  │  │ desktop_chm  │   │  │
│                      │  └─────────┘  │decomposer  │  │ file_tool    │   │  │
│  ┌──────────────┐    │               │repair      │  │ system       │   │  │
│  │  Legacy      │    │               └────────────┘  └──────────────┘   │  │
│  │  automation/ │    │                                      │           │  │
│  │  awareness/  │    │  ┌────────────┐  ┌──────────────┐   ▼           │  │
│  │  core/       │    │  │ memory/    │  │verification/ │  ┌─────────┐  │  │
│  │  services/   │    │  │ 4-tier     │  │evidence_law  │  │ models/ │  │  │
│  │  server/     │    │  │ JSON store │  │verifier      │  │ NVIDIA  │  │  │
│  │              │    │  └────────────┘  └──────────────┘  │ GROQ    │  │  │
│  └──────────────┘    │                                     └─────────┘  │  │
│                      │  ┌────────────┐  ┌──────────────┐               │  │
│                      │  │capabilities│  │ api/         │               │  │
│                      │  │web_agent   │  │ FastAPI app  │               │  │
│                      │  │research    │  │ (NOT SERVED) │               │  │
│                      │  └────────────┘  └──────────────┘               │  │
│                      └──────────────────────────────────────────────────────┘  │
│                                                                                 │
│  ┌──────────────────────────────────────┐                                      │
│  │  External Dependencies               │                                      │
│  │  • Chrome (CDP port 9222)            │                                      │
│  │  • NVIDIA NIM API (httpx)            │                                      │
│  │  • GROQ API (fallback)               │                                      │
│  │  • Playwright (browser automation)   │                                      │
│  │  • pyautogui (desktop control)       │                                      │
│  │  • Windows UIA (via state_cache)     │                                      │
│  └──────────────────────────────────────┘                                      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Module Count by Package

| Package | Modules | Lines (approx) | Status |
|---------|---------|-----------------|--------|
| `friday/actions/` | 12+ | ~2,000 | PARTIAL — browser works, desktop new |
| `friday/api/` | 4+ | ~400 | DEFINED — never served |
| `friday/capabilities/` | 3+ | ~500 | IMPLEMENTED — web_agent, research |
| `friday/config/` | 3+ | ~200 | IMPLEMENTED |
| `friday/learning/` | 1 | ~8 | EMPTY — docstring only |
| `friday/memory/` | 8+ | ~1,200 | IMPLEMENTED — JSON storage |
| `friday/models/` | 5+ | ~800 | IMPLEMENTED — NVIDIA + GROQ |
| `friday/perception/` | 6+ | ~800 | PARTIAL — screen yes, UIA broken |
| `friday/planner/` | 5+ | ~1,000 | IMPLEMENTED |
| `friday/router/` | 3+ | ~400 | IMPLEMENTED |
| `friday/tools/` | 2+ | ~300 | METADATA ONLY — no handlers |
| `friday/verification/` | 4+ | ~600 | IMPLEMENTED |
| `friday/bridge.py` | 1 | ~450 | IMPLEMENTED (has hardcoded URLs) |
| `friday/core.py` | 1 | ~250 | ORPHANED — not used by Operator |
| `friday/executor.py` | 1 | ~700 | IMPLEMENTED |
| `friday/operator.py` | 1 | ~280 | IMPLEMENTED |

---

## 3. Entry Points & Boot Sequence

### Entry Point Matrix

| Entry Point | File | Status | What It Does |
|-------------|------|--------|--------------|
| Legacy JARVIS | `main.py` | **BLOCKED** | Full voice loop + wake word + TTS. Requires `FRIDAY_ALLOW_LEGACY_MAIN=1` |
| FRIDAY Bridge | `friday/bridge.py` | **ACTIVE** | Routes commands between JARVIS (chat) and FRIDAY (agent) modes |
| General Operator | `friday/operator.py` | **ACTIVE** | Goal → Requirements → Plan → Execute → Verify → Repair |
| API Server | `friday/api/app.py` | **DEFINED** | FastAPI endpoints. No `uvicorn.run()` anywhere. Never served. |
| Live test scripts | `scripts/live_*.py` | **MANUAL** | One-off validation scripts, not CI |

### Boot Sequence (New Architecture)

```
FridayBridge.__init__()
    ├── FridayEngine(state_cache=...)          # core.py — NEVER CALLED by Operator
    ├── RequestRouter(jarvis_handler, friday_handler)
    └── ModelRouter (lazy)

bridge.process(command)
    ├── RequestRouter.route(command)
    │   ├── Classify: JARVIS mode → _handle_jarvis() → ModelRouter.complete()
    │   └── Classify: FRIDAY mode → _handle_friday()
    │       ├── SIMPLE_ACTION → _execute_simple_action() → FridayEngine.execute_verified()
    │       └── MULTI_STEP/COMPLEX → _execute_multi_step()
    │           ├── resolve_browser_strategy(goal_text)
    │           ├── BrowserController.start() or DesktopChromeController.start()
    │           └── Operator(model_router, browser_controller).run(goal)
    └── Return BridgeResult
```

### Critical Finding: Two Disconnected Execution Paths

The `FridayEngine` (core.py) provides `execute_verified()` with perception-based
verification. But the `Operator` (operator.py) uses `GoalExecutor` (executor.py)
directly, which has its OWN evidence-based verification. These are TWO DIFFERENT
verification systems that never interact:

| System | Used By | Verification Method |
|--------|---------|---------------------|
| `FridayEngine.execute_verified()` | `bridge._execute_simple_action()` | WorldState before/after diff |
| `GoalExecutor` + `EvidenceVerifier` | `Operator.run()` | Evidence artifacts (files, URLs, content) |

**Verdict:** FridayEngine (core.py) is architecturally orphaned from the main pipeline.

---

## 4. Operator Pipeline (The Brain)

### Pipeline Flow (from operator.py)

```
Goal Text
    │
    ▼
┌───────────────────────────┐
│ RequirementsDiscovery     │  LLM classifies what must be true
│ (friday/planner/          │  Output: RequirementSet with blocking/non-blocking
│  requirements.py)         │  
└───────────────────────────┘
    │
    ▼
┌───────────────────────────┐
│ OperatorPlanner           │  LLM decomposes into capability steps
│ (friday/planner/          │  Maps to ToolCapability enum values
│  operator_planner.py)     │  Output: OperatorPlan with OperatorSteps
└───────────────────────────┘
    │                          ↑ Note: Discovery + Planning run IN PARALLEL
    ▼                            (ThreadPoolExecutor, 2 workers)
┌───────────────────────────┐
│ GoalExecutor              │  Executes steps with data flow
│ (friday/executor.py)      │  Accumulates ExecutionContext
│                           │  Records ExecutionEvidence
└───────────────────────────┘
    │
    ▼
┌───────────────────────────┐
│ EvidenceVerifier          │  Checks each requirement against artifacts
│ (friday/verification/     │  GATHER needs real reads, FILE needs disk artifact
│  evidence_law.py)         │  No evidence → UNMET (no exceptions)
└───────────────────────────┘
    │
    ├── All satisfied → COMPLETE
    │
    ▼ (unmet requirements exist)
┌───────────────────────────┐
│ RepairDiagnoser           │  Diagnoses WHY each requirement is unmet
│ (friday/planner/repair.py)│  Produces targeted repair actions
└───────────────────────────┘
    │
    ▼
┌───────────────────────────┐
│ GoalExecutor.execute_repair│  Runs ONLY repair actions
│                           │  Reuses prior evidence/context
└───────────────────────────┘
    │
    └── Loop up to max_iterations (default: 3, bridge uses 2)
```

### Implementation Rating

| Component | Implemented | Live-Tested | Confidence |
|-----------|-------------|-------------|------------|
| RequirementsDiscovery | ✅ Real LLM call | ✅ Yes | HIGH |
| OperatorPlanner | ✅ Real LLM call | ✅ Yes | HIGH |
| GoalExecutor | ✅ Full capability dispatch | ✅ Partial (file+research) | MEDIUM |
| EvidenceVerifier | ✅ Complete logic | ✅ Yes (prevents false positives) | HIGH |
| RepairDiagnoser | ✅ Implemented | ❓ Never observed in wild | LOW |
| Parallel discovery+plan | ✅ ThreadPoolExecutor | ✅ Yes | HIGH |
| Blocked-state handling | ✅ Captcha detection | ❓ Only synthetic | LOW |

### Evidence: Operator Actually Works (Constrained)

Live-verified producing a real `.txt` file in 6.6s with citations from real web sources.
The full chain (LLM requirements → plan → research → generate → file) executed end-to-end.
This proves the pipeline FUNCTIONS but only for the simplest class of goals.

---

## 5. Browser Control Layer

### Architecture (3-Tier Strategy)

```
resolve_browser_strategy(goal_text)
    │
    ├── Tier 1: CDP REUSE — connect to existing Chrome debug port
    │   └── BrowserController (Playwright over CDP, dedicated loop thread)
    │
    ├── Tier 2: CDP LAUNCH — launch Chrome with debug port on profile
    │   └── ensure_chrome_debug() → BrowserController
    │
    └── Tier 3: DESKTOP CONTROL — pyautogui + OCR on visible Chrome
        └── DesktopChromeController (keyboard + screen reading)
```

### BrowserController (friday/actions/browser_controller.py)

| Feature | Status | Evidence |
|---------|--------|----------|
| Persistent event loop thread | ✅ IMPLEMENTED | Dedicated `threading.Thread` + `asyncio` loop |
| Playwright CDP connection | ✅ IMPLEMENTED | `playwright.chromium.connect_over_cdp()` |
| Multi-step session survival | ✅ IMPLEMENTED | Single loop thread = page stays alive |
| DOM observation (`observe_interactive`) | ✅ LIVE-VERIFIED | 60 elements observed on Wikipedia |
| Click by index | ✅ LIVE-VERIFIED | Real clicks executed |
| Fill by index | ✅ LIVE-VERIFIED | Real typing executed |
| Navigation | ✅ LIVE-VERIFIED | Real page loads |
| Tab management | ✅ LIVE-VERIFIED | Open/close/switch tabs |
| Scroll | ✅ IMPLEMENTED | scroll_to_element, scroll_page |
| Screenshot | ✅ IMPLEMENTED | Full page and element screenshots |
| Shadow DOM / iframes | ✅ IMPLEMENTED | Recursive frame walking |
| File upload/download | ✅ IMPLEMENTED | Via Playwright file chooser |
| User's signed-in profile (CDP) | ❌ FAILS | Google Sync blocks CDP on Shreesh profile |
| Dedicated profile (CDP) | ✅ WORKS | Clean profile without sync issues |

### DesktopChromeController (friday/actions/desktop_chrome.py)

| Feature | Status | Evidence |
|---------|--------|----------|
| Focus Chrome window | ✅ LIVE-VERIFIED | pyautogui.getWindowsWithTitle + activate |
| Navigate via Ctrl+L | ✅ LIVE-VERIFIED | Address bar + type URL + Enter |
| Read screen via OCR | ✅ LIVE-VERIFIED | Screen text read back correctly |
| Click by index (OCR elements) | ✅ IMPLEMENTED | `observe_interactive` + `click_index` |
| Type into fields | ✅ IMPLEMENTED | `fill_index` |
| Same API surface as BrowserController | ✅ IMPLEMENTED | Duck-typed interface |
| Confirmation of actions | ⚠️ BEST-EFFORT | OCR re-read after action (not DOM-verified) |
| Multi-monitor support | ❌ NOT IMPLEMENTED | Single monitor assumed |
| DPI/scaling awareness | ❌ NOT IMPLEMENTED | Coordinates may be wrong on HiDPI |

### Critical Finding: CDP Fails on User's Profile

The primary use case (operating Instagram/Gmail/WhatsApp on the user's signed-in Chrome)
requires the user's real browser session. CDP control of that profile FAILS because
Google Sync interferes. The ONLY path to the user's session is desktop control (Tier 3),
which was just built this session and has never been tested on Instagram/Gmail/WhatsApp.

**Verdict:** PARTIAL — infrastructure works, primary use case path untested.

---

## 6. Desktop Control Layer

### Components

| Component | File | Status |
|-----------|------|--------|
| DesktopChromeController | `friday/actions/desktop_chrome.py` | ✅ IMPLEMENTED, live-verified |
| DesktopPerception | `friday/perception/desktop.py` | ⚠️ BROKEN without state_cache |
| DesktopAdapter (primitives) | `friday/actions/adapters/` | ✅ IMPLEMENTED |
| ScreenCapture | `friday/perception/screen.py` | ✅ IMPLEMENTED |
| SystemActions | `friday/actions/system.py` | ✅ IMPLEMENTED (launch app, focus window) |

### DesktopPerception Dependency Problem

```python
# friday/perception/desktop.py
class DesktopPerception:
    def __init__(self, state_cache=None):
        self._state_cache = state_cache  # FROM LEGACY awareness system

    def get_ui_elements(self):
        if not self._state_cache:
            return []  # ← RETURNS EMPTY if no legacy wiring
```

The Operator (operator.py) creates a GoalExecutor but NEVER passes a `state_cache`.
The FridayEngine (core.py) accepts one but is orphaned. Therefore:

- **DesktopPerception in the Operator pipeline: ALWAYS EMPTY**
- **Windows UIA elements: NEVER AVAILABLE in new architecture**
- **Only DesktopChromeController (OCR path) provides desktop info**

### What Desktop Control Can Actually Do (Proven)

| Action | Method | Verified |
|--------|--------|----------|
| Launch app | `subprocess.Popen` / `os.startfile` | ✅ Live |
| Focus window | `pyautogui.getWindowsWithTitle` + activate | ✅ Live |
| Type text | `pyautogui.write` / `pyautogui.hotkey` | ✅ Live |
| Navigate Chrome address bar | Ctrl+L → type URL → Enter | ✅ Live |
| Read screen text (OCR) | Screenshot + OCR engine | ✅ Live |
| Click at coordinates | `pyautogui.click(x, y)` | ✅ Live |
| Read UIA tree | Requires legacy `state_cache` | ❌ Not wired |
| Interact with non-Chrome apps | SystemActions.launch_app only | ⚠️ Launch only |
| Multi-app coordination | Not implemented | ❌ |

---

## 7. LLM Provider Layer

### Provider Architecture

```
friday/models/
├── router.py          # ModelRouter — routes by capability to provider
├── providers/
│   ├── nvidia_provider.py   # Primary: NVIDIA NIM API (httpx)
│   └── groq_provider.py     # Fallback: GROQ API
└── __init__.py
```

### Provider Details

| Provider | API | Transport | Models Used | Status |
|----------|-----|-----------|-------------|--------|
| NVIDIA NIM | `integrate.api.nvidia.com` | httpx (async) | `meta/llama-3.3-70b-instruct`, `nvidia/llama-3.1-nemotron-70b-instruct` | ✅ LIVE-VERIFIED |
| GROQ | `api.groq.com` | httpx (async) | Various Llama/Mixtral | ✅ Configured, fallback |

### ModelRouter Capabilities

| Capability | Model Selection | Timeout |
|------------|-----------------|---------|
| CONVERSATION | Fast model (low latency) | 45s |
| REASONING | 70B reasoning model | 90s |
| PLANNING | Same as reasoning | 90s |
| EMBEDDING | `nv-embed-v1` (NVIDIA) | 30s |

### Critical Performance Issue

NVIDIA NIM free-tier endpoints have cold-start latency of 20-30s per call.
The Operator fires Requirements Discovery + Planning in parallel to mitigate this,
but each iteration of the repair loop still adds 20-30s. A 3-iteration run with
2 LLM calls per iteration = 60-90s+ total latency.

**Live evidence:** Web agent loop ran 8 steps on Wikipedia but hit LLM latency limit.
The infrastructure works; the model is slow on free tier.

### Embedding Support

Semantic memory uses NVIDIA `nv-embed-v1` for vector embeddings with
lexical (TF-IDF style) fallback when embeddings are unavailable or slow.
This is implemented in `friday/memory/semantic.py`.

---

## 8. Memory System

### Architecture (4-Tier)

```
friday/memory/
├── __init__.py          # Exports all tiers
├── controller.py        # FridayMemory — unified coordinator
├── interfaces.py        # MemoryEntry, MemoryStore, MemoryTier (abstractions)
├── stores.py            # JSONFileStore (persistent backend)
├── working.py           # WorkingMemory — volatile, current task context
├── episodic.py          # EpisodicMemory — interaction history
├── procedural.py        # ProceduralMemory — learned action patterns
└── semantic.py          # SemanticMemory — facts + embeddings
```

### Tier Assessment

| Tier | Implemented | Storage | Retrieval | Live-Used |
|------|-------------|---------|-----------|-----------|
| Working Memory | ✅ Full | In-memory (volatile) | Direct access | ❓ Not observed in Operator |
| Episodic Memory | ✅ Full | JSON file | Recency-based | ❓ Not observed in Operator |
| Procedural Memory | ✅ Full | JSON file | Pattern match | ❓ Not observed in Operator |
| Semantic Memory | ✅ Full | JSON file + embeddings | NVIDIA nv-embed-v1 + lexical fallback | ❓ Not observed in Operator |

### Critical Finding: Memory is NOT Wired to the Operator

The Operator (operator.py) has NO reference to `FridayMemory` or any memory tier.
The GoalExecutor has NO memory lookup. The planner does NOT consult procedural memory
before planning. Memory exists as a standalone system but is disconnected from the
active execution pipeline.

```python
# operator.py — NO memory imports
class Operator:
    def __init__(self, model_router=None, browser_controller=None, ...):
        # NO: self._memory = FridayMemory(...)
        # NO memory consulted during planning or execution
```

### Storage Backend

All tiers use `JSONFileStore` — a simple JSON file per memory tier.
No SQLite, no MongoDB Atlas, no vector database. The docstring mentions
"JSON → SQLite → MongoDB Atlas via Student Pack" as future progression,
but only JSON is implemented.

### Semantic Memory — Embedding Quality

```python
# friday/memory/semantic.py
class Fact:
    content: str
    embedding: Optional[List[float]] = None  # NVIDIA nv-embed-v1
    valid_at: float  # temporal edges (Memory OS pattern)
    invalid_at: Optional[float] = None  # superseded facts

# Retrieval: cosine similarity on embeddings, lexical fallback
```

**Verdict:** IMPLEMENTED but ORPHANED from the execution pipeline. The memory system
is a well-designed standalone module that nothing uses during actual task execution.

---

## 9. Verification & Evidence Law

### The Core Guarantee (evidence_law.py)

```
A requirement is satisfied ONLY when a matching evidence artifact exists.
Generated text can satisfy PRODUCE, but NEVER satisfies GATHER/DELIVER/FILE.
No evidence → UNMET. No exceptions, no heuristics.
```

### Requirement Classification

| RequirementKind | What Satisfies It | What CANNOT Satisfy It |
|-----------------|-------------------|------------------------|
| GATHER | `GATHERED_INFO` artifact (real text from real page) | Generated/synthesized text |
| PRODUCE | `GENERATED_CONTENT` artifact | Nothing (any generation works) |
| FILE | `FILE_ARTIFACT` with byte size > 0 | Empty file, no file |
| NAVIGATE | `NAVIGATION` artifact | Assumed navigation |
| DELIVER | `DELIVERY_CONFIRMATION` (observed "sent" state) | Attempted but unconfirmed send |
| GENERIC | Any real artifact | No artifacts at all |

### Evidence Artifact Types

| EvidenceKind | What Records It | When |
|--------------|-----------------|------|
| `GATHERED_INFO` | `research()` reads real page content | After `browser.read_text()` succeeds |
| `SOURCE_URL` | `research()` records URL of read page | After page is opened AND text extracted |
| `GENERATED_CONTENT` | `_generate()` produces LLM text | After model returns content |
| `FILE_ARTIFACT` | `FileTool.create_file()` verifies on disk | After `os.path.getsize()` confirms |
| `NAVIGATION` | `browser.navigate()` confirms landing | After page load completes |
| `DELIVERY_CONFIRMATION` | WebAgent observes "sent" state | After page text contains "sent" keyword |
| `SCREENSHOT` | `capture_screenshot()` saves to disk | After screenshot file has size > 0 |

### Implementation Rating

| Aspect | Rating | Evidence |
|--------|--------|----------|
| Architecture design | **PASS** | Prevents false positives by construction |
| Keyword classification | **PASS** | `classify_requirement()` covers common patterns |
| Live verification (research) | **PASS** | Proven to reject generated-only content for GATHER |
| Live verification (files) | **PASS** | Proven to require byte size > 0 |
| Live verification (delivery) | **UNTESTED** | DELIVER path never exercised in the wild |
| Edge case handling | **PARTIAL** | Keyword matching can misclassify ambiguous requirements |
| Screenshot evidence | **PARTIAL** | Captured but not analyzed (no vision verification) |

### The Two Verification Systems Problem (Reiterated)

| System | Where | How It Verifies |
|--------|-------|-----------------|
| `EvidenceVerifier` (evidence_law.py) | Operator pipeline | Artifact-based: file exists, URL read, content produced |
| `ActionVerifier` (verifier.py) | FridayEngine (core.py) | WorldState diff: before/after perception comparison |

Only the EvidenceVerifier is active in the Operator. The ActionVerifier is orphaned
with the FridayEngine. They address different verification needs but are never combined.

---

## 10. Tool Registry & Execution Dispatch

### Registry Design (friday/tools/registry.py)

The registry declares 22 tools across 6 environments:

| Environment | Tools | Handler? |
|-------------|-------|----------|
| browser | browser.navigate, browser.click, browser.type, browser.read_page, browser.search | ❌ None |
| desktop | desktop.open_app, desktop.focus_window, desktop.click, desktop.type, desktop.read_ui | ❌ None |
| filesystem | file.create, file.read, file.write, file.move, file.delete | ❌ None |
| any | memory.store, memory.recall, research.web_search, research.summarize | ❌ None |
| browser | communication.send_message, communication.send_email | ❌ None |
| system | system.run_command, system.check_process | ❌ None |
| any | verification.check_result, verification.check_goal | ❌ None |

### Critical Finding: ALL 22 Tools Have `handler: None`

```python
# Every tool in build_default_registry():
registry.register(Tool(
    name="browser.navigate",
    description="Navigate the browser to a URL",
    capabilities=[ToolCapability.NAVIGATE_URL, ToolCapability.OPEN_APPLICATION],
    environment="browser",
    priority=8,
    # handler=None ← IMPLICIT, never set
))
```

The registry is METADATA ONLY. It tells the planner what capabilities exist,
but execution is handled by the GoalExecutor's `_execute_step()` method which
uses its own `if/elif` dispatch on `ToolCapability` enum values.

### How Execution ACTUALLY Works

```python
# executor.py — _execute_step():
def _execute_step(self, step, ctx):
    cap = step.capability
    if cap == ToolCapability.SEARCH_WEB:
        return self._execute_research(target, ctx)
    elif cap in (ToolCapability.NAVIGATE_URL, ToolCapability.OPEN_APPLICATION):
        # ... direct browser/webbrowser calls
    elif cap in (ToolCapability.READ_DOM, ToolCapability.EXTRACT_WEB_CONTENT):
        # ... direct browser.read_text() calls
    elif cap == ToolCapability.CLICK_ELEMENT:
        return self._execute_click(target, ctx)
    # ... 10+ more elif branches
```

**Verdict:** The registry is a planning aid, not an execution framework. The "tools"
are never called via their registry entries. The executor hardcodes all dispatch logic.

---

## 11. Web Agent (Generic Site Operator)

### Design (friday/capabilities/web_agent.py)

```
Loop:
  1. OBSERVE — browser.observe_interactive() → numbered element list
  2. DECIDE — LLM sees goal + elements + history → picks ONE action (JSON)
  3. ACT — execute the chosen action (click/type/scroll/navigate/done/stuck)
  4. Repeat until "done" or step budget hit
```

### Available Actions

| Action | Method | Reliability |
|--------|--------|-------------|
| `click` (index) | `browser.click_index(N)` | HIGH — DOM element by index |
| `type` (index, text) | `browser.fill_index(N, text)` | HIGH — focused input |
| `press` (key) | `browser.press(key)` | HIGH — keyboard event |
| `scroll` (direction) | `browser.scroll_page(direction)` | HIGH — page scroll |
| `navigate` (url) | `browser.navigate(url)` | HIGH — direct nav |
| `click_vision` (describe) | Vision-based coordinate click | LOW — OCR/VLM dependent |
| `done` | Loop exit | N/A |
| `stuck` | Loop exit with failure | N/A |

### Implementation Assessment

| Aspect | Rating | Notes |
|--------|--------|-------|
| Generic design (no site hardcoding) | **PASS** | Zero site-specific logic in web_agent.py |
| LLM decision quality | **PARTIAL** | Depends on model; 70B works, smaller may not |
| Live CDP execution | **LIVE-VERIFIED** | 8 steps on Wikipedia (hit latency limit) |
| Live on signed-in sites | **UNTESTED** | Never tested on Instagram/Gmail/WhatsApp |
| Error recovery (stuck state) | **UNTESTED** | Never observed in practice |
| Step budget management | ✅ IMPLEMENTED | `max_steps` parameter (default 14 for delivery) |
| Evidence recording | ✅ IMPLEMENTED | Evidence passed through from executor |

### Critical Finding: bridge.py STILL Has Hardcoded URLs

Despite web_agent.py being generic, `bridge.py` contains:

```python
# bridge.py — _target_to_url():
known_urls = {
    "instagram": "https://www.instagram.com/direct/inbox/",
    "insta": "https://www.instagram.com/direct/inbox/",
    "whatsapp": "https://web.whatsapp.com",
    "gmail": "https://mail.google.com",
    "youtube": "https://www.youtube.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "reddit": "https://www.reddit.com",
    "github": "https://github.com",
    "amazon": "https://www.amazon.in",
    "google": "https://www.google.com",
}
```

This is used for initial navigation (knowing WHERE to go), not for site-specific
interaction logic. The web agent still operates generically once on the page.
However, this hardcoded map means adding a new site requires code changes.

---

## 12. File & Document Creation

### Implementation (friday/actions/file_tool.py)

| Format | Method | Verified |
|--------|--------|----------|
| `.txt` | `open(path, 'w').write(content)` | ✅ LIVE-VERIFIED (6.6s test) |
| `.md` | Same as txt | ✅ LIVE-VERIFIED |
| `.csv` | `csv.writer` | ✅ Unit tested |
| `.xlsx` | `openpyxl` | ✅ Unit tested |
| `.docx` | `python-docx` | ✅ Unit tested |
| `.html` | Template-based | ✅ Unit tested |
| `.pdf` | NOT IMPLEMENTED | ❌ |
| `.pptx` | NOT IMPLEMENTED | ❌ |

### Evidence Recording

```python
# executor.py — CREATE_FILE step:
result = self._file_tool.create_file(filename, content)
if result.is_success:
    size = self._file_size(result.target)
    ctx.evidence.add_file(result.target, size)  # Real bytes on disk
```

Files are verified to exist with `os.path.getsize()` before being recorded as evidence.
An empty or non-existent file cannot satisfy a FILE requirement.

### File Location

Files are created in the project's working directory or a configured output path.
No user-configurable output directory in the Operator (it infers filename from target text).

---

## 13. Research Capability

### Implementation (friday/capabilities/research.py)

```
research(query, browser_controller, evidence, max_sources=3)
    │
    ├── browser.search_web(query)          → DuckDuckGo results
    │
    ├── For each result (up to max_sources):
    │   ├── browser.navigate(result_url)
    │   ├── check is_blocked_page()
    │   ├── browser.read_text(2500 chars)
    │   ├── evidence.add_gathered_info(text, source=url)
    │   └── evidence.add_source_url(url)
    │
    └── Return ResearchResult(sources_read, source_urls, gathered_text)
```

### Assessment

| Aspect | Rating | Evidence |
|--------|--------|----------|
| DuckDuckGo search | ✅ WORKS | Navigates to DDG, reads results |
| Follow links to sources | ✅ WORKS | Opens actual pages |
| Read real content | ✅ WORKS | Extracts page text |
| Record source URLs | ✅ WORKS | URLs in evidence |
| Blocked page detection | ✅ IMPLEMENTED | Captcha/verification wall check |
| Citation in generated content | ✅ WORKS | Sources section appended |
| Rate limiting awareness | ❌ NOT IMPLEMENTED | May hit CAPTCHA |
| Cookie consent handling | ❌ NOT IMPLEMENTED | May be blocked |

### Live Verification Evidence

The Operator's file creation task was live-verified including research:
- DuckDuckGo search executed
- Real source pages opened and read
- Content synthesized with citations from actual URLs
- File written to disk with verified byte size

**Verdict:** Research WORKS for public, non-authenticated content.
UNTESTED for anything requiring login or bypassing CAPTCHAs.

---

## 14. API Layer

### Definition (friday/api/)

```python
# friday/api/__init__.py
from friday.api.app import create_friday_api

# Endpoints defined:
# POST /api/command     — Execute command (JARVIS/FRIDAY routing)
# GET  /api/status      — System status + active goal
# POST /api/memory/search — Search memory by query
# GET  /api/memory/recent — Recent interaction history
# GET  /api/models      — Available models + usage stats
# WS   /api/ws          — WebSocket for real-time updates
# GET  /api/health      — Health check (no auth)
```

### Reality Check

| Aspect | Status |
|--------|--------|
| FastAPI app defined | ✅ Yes |
| Endpoints implemented | ✅ Yes (in code) |
| Auth (API key) | ✅ Defined |
| WebSocket support | ✅ Defined |
| `uvicorn.run()` call | ❌ NOWHERE in codebase |
| Server ever started | ❌ NEVER |
| Client consuming it | ❌ NONE EXISTS |
| Load tested | ❌ NEVER |
| Error handling under load | ❌ UNKNOWN |

### Grep Evidence

```
$ grep -r "uvicorn" friday/     → 0 results
$ grep -r "uvicorn" *.py        → 0 results
```

**Verdict:** The API is a DEFINITION, not a running service. No server has ever
been started. No client has ever consumed these endpoints. This is architecture
documentation masquerading as implementation.

---

## 15. Legacy Systems & Migration State

### Legacy Codebase Size

| Package | Lines | What It Does | Used by friday/ ? |
|---------|-------|--------------|-------------------|
| `automation/` | 10,387 | Browser automation, app control, planner | ⚠️ Fallback only |
| `awareness/` | 1,659 | Windows UIA, system monitor, state_cache | ❌ Broken wire |
| `core/` | 3,466 | Assistant orchestrator, capability dispatcher, telemetry | ❌ Legacy only |
| `server/` | 300 | Remote control server (WebSocket) | ❌ Legacy only |
| `services/` | 471 | Weather, maps | ❌ Legacy only |
| `main.py` | ~400 | Voice loop + wake word + TTS | ❌ BLOCKED |

### Migration Status

| Feature | Legacy Location | friday/ Status |
|---------|-----------------|----------------|
| Voice input (Porcupine wake word) | `main.py` | ❌ NOT PORTED |
| TTS output (edge-tts) | `main.py` + `edge_tts_voice.py` | ❌ NOT PORTED |
| Speech recognition (Groq Whisper) | `main.py` | ❌ NOT PORTED |
| Windows UIA monitoring | `awareness/windows_accessibility.py` | ❌ BROKEN (state_cache not wired) |
| System monitor (CPU/RAM alerts) | `awareness/system_monitor.py` | ❌ NOT PORTED |
| Browser state tracker | `automation/browser_state_tracker.py` | ✅ REPLACED by BrowserController |
| Remote server | `server/app.py` | ❌ NOT PORTED |
| Weather service | `services/weather_service.py` | ❌ NOT PORTED |
| Maps service | `services/maps_service.py` | ❌ NOT PORTED |
| Plugin system | `plugins/` | ❌ NOT PORTED |
| Routine scheduler | `core/routine_scheduler.py` | ❌ NOT PORTED |
| Personality manager | `personality.py` | ❌ NOT PORTED |
| Capability registry (old) | `capabilities.py` | ✅ REPLACED by ToolRegistry |

### The Bridge Layer's Role

`friday/bridge.py` acts as adapter between old and new:
- Wraps legacy `AutomationServices` with `FridayEngine`
- Provides `ALLOW_LEGACY_FALLBACK` behavior
- Routes between JARVIS mode (chat) and FRIDAY mode (agent)
- But the bridge itself has accumulated code debt (hardcoded URLs, duplicate dispatch logic)

---

## 16. Test Suite Analysis

### High-Level Numbers

```
Total tests collected:  802
Total tests passing:    802 (100%)
Test environment:       FRIDAY_DRY_RUN=1 (ALL external actions blocked)
Mock references:        ~409 instances of MagicMock/monkeypatch/Fake
Real I/O tests:         0
Integration tests:      0 (LLM → browser → page → verification)
```

### What Tests Actually Verify

| Category | Count (est.) | What They Prove |
|----------|-------------|-----------------|
| Unit logic (pure functions) | ~300 | Internal algorithms work |
| Mock interactions (component glue) | ~350 | Components wire together correctly |
| DRY_RUN behavior | ~100 | System doesn't crash when everything is faked |
| Error handling paths | ~50 | Exception paths don't blow up |

### What Tests DO NOT Verify

| Scenario | Test Exists? | Risk |
|----------|-------------|------|
| Real Chrome opens and navigates | ❌ | Browser may not connect in production |
| Real LLM call returns useful response | ❌ | Model may timeout, return garbage |
| Real file creation on user's system | ❌ | Permission issues, path problems |
| Real desktop click hits target | ❌ | Coordinates may be wrong |
| Real OCR reads correct text | ❌ | OCR may misread |
| Multi-step task completes end-to-end | ❌ | Steps may fail to chain |
| Error recovery actually recovers | ❌ | Repair logic may loop forever |
| Memory persists across sessions | ❌ | JSON corruption, file locking |
| Concurrent operations don't conflict | ❌ | Thread safety issues |
| Large page DOM handling | ❌ | Memory/timeout issues |

### Live Validation Scripts

```
scripts/live_*.py  — Manual one-off scripts
```

These exist for CDP browser control and desktop control validation.
They are NOT automated, NOT in CI, NOT regression-safe. They prove
things worked ONCE at the time they were run.

### Test Confidence Assessment

```
Confidence that code compiles:           ██████████  100%
Confidence that logic is correct:        ███████░░░   70%
Confidence that system works in reality: █░░░░░░░░░   10%
Confidence in regression safety:         ██░░░░░░░░   20%
```

**Verdict:** The test suite is a CODE QUALITY tool, not a FUNCTIONALITY proof.
It proves the architecture is internally consistent but says NOTHING about
whether FRIDAY can actually do anything useful on a real machine.

---

## 17. Real-World Task Benchmark (50 Tasks)

### Rating Scale

| Rating | Meaning |
|--------|---------|
| ✅ PASS | Would succeed reliably (>80% of the time) right now |
| ⚠️ PARTIAL | Infrastructure exists but untested or unreliable |
| ❌ FAIL | Cannot succeed — missing implementation or known blocker |
| 🔶 THEORY | Architecture supports it but zero code path exists |

### Category A: Information & Research (10 Tasks)

| # | Task | Rating | Reasoning |
|---|------|--------|-----------|
| 1 | "Research the best laptops under $1000 and save a report" | ✅ PASS | Proven: DDG search → read pages → synthesize → write .txt |
| 2 | "Find today's weather in my city" | ❌ FAIL | No weather API wired in friday/. Legacy service not ported |
| 3 | "What's the latest score of the cricket match?" | ⚠️ PARTIAL | Could search DDG + read sports page, but real-time scores unreliable via scraping |
| 4 | "Summarize this Wikipedia article about quantum computing" | ✅ PASS | Navigate → read_text → LLM summarize → file. Proven path |
| 5 | "Compare iPhone 15 vs Galaxy S24 — features and pricing" | ✅ PASS | Research multiple pages + synthesize comparison. Proven capability |
| 6 | "What are the opening hours of the nearest Starbucks?" | ⚠️ PARTIAL | DDG search works but "nearest" requires location awareness (not implemented) |
| 7 | "Find me 5 free courses on machine learning" | ✅ PASS | DDG search + follow links + extract course info + save report |
| 8 | "What's my schedule for today?" | ❌ FAIL | No calendar integration. Cannot access Google Calendar |
| 9 | "Research France's position on AI regulation" | ✅ PASS | Multi-source research + synthesis. Proven path |
| 10 | "Find the cheapest flight from Delhi to London next month" | ⚠️ PARTIAL | Can navigate to flight sites but CAPTCHA/dynamic pricing will block |

**Category A Score: 5/10 PASS, 3/10 PARTIAL, 2/10 FAIL**

### Category B: Communication (10 Tasks)

| # | Task | Rating | Reasoning |
|---|------|--------|-----------|
| 11 | "Send a WhatsApp message to Mom saying I'll be late" | ❌ FAIL | CDP fails on signed-in profile. Desktop OCR path untested on WhatsApp Web. Delivery never verified |
| 12 | "Reply to the latest email from my professor" | ❌ FAIL | Gmail requires login. CDP blocked. Desktop path untested on Gmail |
| 13 | "Send an Instagram DM to @friend123" | ❌ FAIL | Same CDP/profile issue. Instagram DM flow never tested |
| 14 | "Schedule a meeting invite for tomorrow at 3pm" | ❌ FAIL | No calendar API. No email invite capability proven |
| 15 | "Forward this email to my teammate" | ❌ FAIL | Cannot access Gmail in signed-in profile |
| 16 | "Post a status on WhatsApp" | ❌ FAIL | WhatsApp Web status posting never tested. CDP blocked |
| 17 | "Reply to the top unread message on Instagram" | ❌ FAIL | Instagram interaction never live-tested |
| 18 | "Send an email with an attachment" | ❌ FAIL | Email compose + attachment flow never tested |
| 19 | "Check if I have any missed calls on WhatsApp" | ❌ FAIL | Cannot read WhatsApp state. CDP blocked |
| 20 | "Send a message on Teams/Slack" | ❌ FAIL | No Teams/Slack integration. Desktop OCR path untested |

**Category B Score: 0/10 PASS, 0/10 PARTIAL, 10/10 FAIL**

### Category C: File & Document Management (10 Tasks)

| # | Task | Rating | Reasoning |
|---|------|--------|-----------|
| 21 | "Create a text file with my daily to-do list" | ✅ PASS | File creation proven. LLM generates from prompt |
| 22 | "Write a markdown document comparing 3 programming languages" | ✅ PASS | Research + synthesize + write .md. Proven |
| 23 | "Create an Excel spreadsheet of monthly expenses" | ⚠️ PARTIAL | .xlsx creation works but needs user data (not gathered) |
| 24 | "Generate a Word document report on renewable energy" | ✅ PASS | Research + .docx creation. Unit tested |
| 25 | "Create an HTML page with a portfolio template" | ⚠️ PARTIAL | HTML creation works but quality/complexity untested |
| 26 | "Convert this CSV to a formatted Excel file" | ❌ FAIL | No file conversion pipeline. Can create both but not read+convert |
| 27 | "Organize my Downloads folder by file type" | ❌ FAIL | No file organization logic. No directory scanning in executor |
| 28 | "Create a PDF of my research findings" | ❌ FAIL | PDF creation NOT IMPLEMENTED |
| 29 | "Make a PowerPoint presentation about climate change" | ❌ FAIL | PPTX creation NOT IMPLEMENTED |
| 30 | "Rename all screenshots on my desktop to include dates" | ❌ FAIL | No batch file renaming. No desktop file access logic |

**Category C Score: 3/10 PASS, 2/10 PARTIAL, 5/10 FAIL**

### Category D: Application & Desktop Control (10 Tasks)

| # | Task | Rating | Reasoning |
|---|------|--------|-----------|
| 31 | "Open Spotify and play my liked songs" | ⚠️ PARTIAL | Can launch Spotify (SystemActions) but cannot interact with its UI |
| 32 | "Open Notepad and write today's date" | ⚠️ PARTIAL | Can launch Notepad + type via pyautogui. Untested end-to-end |
| 33 | "Take a screenshot and save it to Desktop" | ⚠️ PARTIAL | ScreenCapture exists but save-to-desktop pipeline untested |
| 34 | "Open Calculator, compute 15% of 4500" | ❌ FAIL | Can launch Calculator but cannot read result or type expression |
| 35 | "Minimize all windows and show desktop" | ⚠️ PARTIAL | `pyautogui.hotkey('win', 'd')` possible but not wired |
| 36 | "Open Chrome and navigate to YouTube" | ✅ PASS | SystemActions launches Chrome; bridge navigates to YouTube URL |
| 37 | "Switch between Chrome and VS Code" | ⚠️ PARTIAL | focus_window exists but never tested with real app switching |
| 38 | "Close the current application" | ❌ FAIL | No close/kill logic in SystemActions |
| 39 | "Adjust system volume to 50%" | ❌ FAIL | No volume control implemented |
| 40 | "Open File Explorer to Documents folder" | ⚠️ PARTIAL | `os.startfile` can open Explorer but no folder navigation |

**Category D Score: 1/10 PASS, 6/10 PARTIAL, 3/10 FAIL**

### Category E: Complex Multi-Step Goals (10 Tasks)

| # | Task | Rating | Reasoning |
|---|------|--------|-----------|
| 41 | "Research AI trends, write a report, and email it to my professor" | ❌ FAIL | Research+file works, but email delivery FAILS |
| 42 | "Find a recipe for pasta, create a shopping list, save as Excel" | ⚠️ PARTIAL | Research+extract+xlsx creation possible but untested chain |
| 43 | "Check my emails, summarize unread ones, save summary" | ❌ FAIL | Cannot access Gmail (signed-in profile blocked) |
| 44 | "Download a paper from arXiv and summarize it" | ❌ FAIL | No PDF download+read capability |
| 45 | "Book a restaurant on Zomato for 4 people tonight" | ❌ FAIL | Requires login + complex multi-step interaction. UNTESTED |
| 46 | "Play a YouTube video about meditation in the background" | ⚠️ PARTIAL | Can navigate to YouTube but cannot click specific video reliably |
| 47 | "Create a Word doc from web research, then share via email" | ❌ FAIL | Doc creation works but email delivery FAILS |
| 48 | "Monitor a webpage and alert me when price drops below $500" | ❌ FAIL | No scheduling, no monitoring, no alerting |
| 49 | "Back up my Documents folder to a USB drive" | ❌ FAIL | No file copy/backup logic |
| 50 | "Set up a morning routine: weather, news, calendar summary" | ❌ FAIL | No scheduling. No weather API. No calendar. No news aggregation |

**Category E Score: 0/10 PASS, 2/10 PARTIAL, 8/10 FAIL**

### Benchmark Summary

| Category | PASS | PARTIAL | FAIL | Pass Rate |
|----------|------|---------|------|-----------|
| A: Research & Info | 5 | 3 | 2 | 50% |
| B: Communication | 0 | 0 | 10 | 0% |
| C: Files & Docs | 3 | 2 | 5 | 30% |
| D: Desktop Control | 1 | 6 | 3 | 10% |
| E: Complex Multi-Step | 0 | 2 | 8 | 0% |
| **TOTAL** | **9** | **13** | **28** | **18%** |

### Benchmark Verdict

```
Tasks that would DEFINITELY succeed right now:     9 / 50  (18%)
Tasks that MIGHT work with luck:                  13 / 50  (26%)
Tasks that will DEFINITELY fail:                  28 / 50  (56%)
```

The system is effectively a **research + file creation tool** today.
Communication, desktop app interaction, and complex multi-step workflows
all fail due to the signed-in profile blocker and missing integrations.

---

## 18. Critical Issues & Architectural Debt

### Priority 1 — Showstoppers (Prevent Primary Use Cases)

| # | Issue | Impact | Root Cause |
|---|-------|--------|------------|
| 1 | **CDP fails on user's signed-in Chrome profile** | Cannot operate Instagram/Gmail/WhatsApp with user's sessions | Google Sync blocks CDP. Only workaround is desktop control (OCR) |
| 2 | **Desktop OCR path never tested on target apps** | The only path to signed-in sites is unproven | Just built, zero validation on Instagram/Gmail/WhatsApp |
| 3 | **No voice I/O in new architecture** | User must type commands (not the intended UX) | Voice/TTS/wake-word exist only in blocked legacy main.py |
| 4 | **No frontend client** | No way for user to interact with the system | API defined but never served. No desktop/mobile app |
| 5 | **DesktopPerception requires legacy state_cache** | New Operator gets ZERO UIA info about desktop apps | Operator never passes state_cache to perception |

### Priority 2 — Architectural Disconnects

| # | Issue | Impact | Where |
|---|-------|--------|-------|
| 6 | **FridayEngine (core.py) orphaned from Operator** | WorldState-based verification unused in main pipeline | operator.py uses GoalExecutor directly |
| 7 | **Tool registry handlers are None** | Registry can't execute anything, only describe | tools/registry.py — all tools metadata-only |
| 8 | **Memory not wired to Operator** | No learning, no recall of past tasks, no user preferences consulted | operator.py has zero memory imports |
| 9 | **bridge.py has hardcoded URL map** | Adding new sites requires code changes | `_target_to_url()` with 11 hardcoded mappings |
| 10 | **Two verification systems never combined** | EvidenceVerifier and ActionVerifier solve different problems separately | evidence_law.py vs verifier.py (core.py) |

### Priority 3 — Missing Features (Documented as Planned)

| # | Feature | Status | Impact |
|---|---------|--------|--------|
| 11 | Learning system | `learning/__init__.py` is a docstring only | Cannot improve from experience |
| 12 | Scheduling / long-running tasks | NOT IMPLEMENTED | Cannot "remind me", "check every hour", etc. |
| 13 | Pause/resume | NOT IMPLEMENTED | Cannot interrupt and continue tasks |
| 14 | Multi-monitor support | NOT IMPLEMENTED | Desktop control assumes single monitor |
| 15 | DPI/scaling awareness | NOT IMPLEMENTED | Coordinates wrong on HiDPI displays |
| 16 | PDF/PowerPoint creation | NOT IMPLEMENTED | Common doc formats missing |
| 17 | Clipboard operations | NOT IMPLEMENTED | Cannot copy/paste programmatically |
| 18 | Process monitoring | NOT IMPLEMENTED | Cannot check if apps are running reliably |
| 19 | App installer interaction | NOT IMPLEMENTED | Cannot install or update software |
| 20 | Login credential handling | NOT IMPLEMENTED | Cannot authenticate on new sites |

### Priority 4 — Code Quality Debt

| # | Issue | Where | Severity |
|---|-------|-------|----------|
| 21 | Bridge has duplicate execution paths | `bridge.py` — `_execute_operator_step` AND GoalExecutor | MEDIUM |
| 22 | Async/sync boundary inconsistency | `_run_async()` creates new thread pool per call | LOW |
| 23 | Evidence screenshots captured but never analyzed | `capture_screenshot` saves file but no vision checks content | LOW |
| 24 | Delivery verification uses keyword matching | "sent" in page text is not reliable confirmation | MEDIUM |
| 25 | No timeout on Operator-level execution | Multi-iteration runs can take minutes | MEDIUM |

---

## 19. Dependency & Infrastructure Map

### Python Dependencies (Required)

| Package | Purpose | Version Constraint | Risk |
|---------|---------|-------------------|------|
| `playwright` | Browser automation (CDP) | Latest | Chrome version drift |
| `httpx` | Async HTTP for LLM APIs | Latest | Low risk |
| `pyautogui` | Desktop mouse/keyboard | Latest | DPI issues on HiDPI |
| `fastapi` | API framework (unused) | Latest | Low risk |
| `python-docx` | DOCX file creation | Latest | Low risk |
| `openpyxl` | XLSX file creation | Latest | Low risk |
| `pydantic` | Data validation | v2 | Low risk |

### External Services (Required at Runtime)

| Service | Purpose | Auth | Fallback |
|---------|---------|------|----------|
| NVIDIA NIM API | Primary LLM inference | API key in .env | GROQ |
| GROQ API | Fallback LLM inference | API key in .env | None (system non-functional) |
| Chrome (local) | Browser automation target | None (local) | No browser = no web tasks |
| DuckDuckGo | Web search | None (public) | None |

### Infrastructure Requirements

| Requirement | Status | Notes |
|-------------|--------|-------|
| Windows 10/11 | ✅ Required | pyautogui, Windows UIA |
| Chrome installed | ✅ Required | CDP target |
| Python 3.10+ | ✅ Required | asyncio features |
| NVIDIA API key | ✅ Required | Primary LLM |
| Internet connection | ✅ Required | LLM calls, web research |
| Microphone | ❌ Legacy only | Voice input not in friday/ |
| Speakers | ❌ Legacy only | TTS not in friday/ |
| Porcupine access key | ❌ Legacy only | Wake word not in friday/ |

### Port Usage

| Port | Service | Status |
|------|---------|--------|
| 9222 | Chrome CDP debug | Used by BrowserController |
| 8000 | FastAPI (intended) | NEVER BOUND |
| 8765 | Legacy WebSocket server | Legacy only |

### File System Usage

| Path | Purpose | Created By |
|------|---------|------------|
| `friday_memory/` | JSON memory files | FridayMemory |
| `output/` | Created files from tasks | FileTool |
| `screenshots/` | Screenshot evidence | capture_screenshot |
| `.env` | API keys | User (manual) |
| `chrome_config.json` | Per-device browser config | browser_config.py |

---

## 20. Honest Capability Matrix

### Full Capability Assessment

Rating scale:
- 🟢 **WORKS** — Implemented, tested, live-verified, reliable
- 🟡 **PARTIAL** — Implemented but unproven in real conditions
- 🔴 **BROKEN** — Implemented but known to fail
- ⚫ **MISSING** — Not implemented at all
- 🔵 **LEGACY** — Exists only in blocked legacy code

| Capability | Rating | Confidence | Evidence |
|------------|--------|------------|----------|
| **LLM Chat (conversational)** | 🟢 WORKS | 90% | NVIDIA NIM via ModelRouter, live-verified |
| **LLM Planning (goal decomposition)** | 🟢 WORKS | 85% | RequirementsDiscovery + OperatorPlanner proven |
| **Web Search (DuckDuckGo)** | 🟢 WORKS | 80% | Research capability live-verified |
| **Web Page Reading** | 🟢 WORKS | 80% | browser.read_text() proven on multiple sites |
| **Navigate to URL (CDP)** | 🟢 WORKS | 85% | BrowserController.navigate() proven |
| **DOM Click (CDP, dedicated profile)** | 🟢 WORKS | 85% | click_index live-verified |
| **DOM Type (CDP, dedicated profile)** | 🟢 WORKS | 85% | fill_index live-verified |
| **Tab Management (CDP)** | 🟢 WORKS | 80% | open/close/switch proven |
| **File Creation (.txt, .md)** | 🟢 WORKS | 90% | Live-verified with evidence |
| **File Creation (.docx, .xlsx)** | 🟡 PARTIAL | 60% | Unit tested only, never live |
| **Research → Synthesize → File** | 🟢 WORKS | 75% | Full pipeline live-verified (6.6s) |
| **Generic Web Agent (observe→decide→act)** | 🟡 PARTIAL | 50% | 8 steps on Wikipedia worked, LLM latency issue |
| **Desktop: Launch App** | 🟢 WORKS | 80% | SystemActions proven |
| **Desktop: Focus Window** | 🟡 PARTIAL | 60% | Implemented, pyautogui available |
| **Desktop: Navigate Chrome (Ctrl+L)** | 🟢 WORKS | 75% | Live-verified via DesktopChromeController |
| **Desktop: OCR Screen Read** | 🟢 WORKS | 70% | Live-verified reading Chrome content |
| **Desktop: Click by OCR Index** | 🟡 PARTIAL | 40% | Implemented but accuracy unproven |
| **Desktop: Type in focused app** | 🟡 PARTIAL | 60% | pyautogui.write works but focus issues possible |
| **CDP on User's Signed-In Profile** | 🔴 BROKEN | 0% | Google Sync blocks. Known, documented |
| **Operate Instagram (signed-in)** | 🔴 BROKEN | 0% | No working path to signed-in Instagram |
| **Operate Gmail (signed-in)** | 🔴 BROKEN | 0% | No working path to signed-in Gmail |
| **Operate WhatsApp Web (signed-in)** | 🔴 BROKEN | 0% | No working path to signed-in WhatsApp |
| **Send Email** | 🔴 BROKEN | 0% | Delivery never confirmed in real test |
| **Send Message (any platform)** | 🔴 BROKEN | 0% | Delivery never confirmed in real test |
| **Evidence-Based Verification** | 🟢 WORKS | 85% | EvidenceVerifier prevents false positives |
| **Requirement Discovery (LLM)** | 🟢 WORKS | 80% | Proven with real NVIDIA calls |
| **Repair/Replan Loop** | 🟡 PARTIAL | 40% | Implemented but never observed recovering in wild |
| **Memory (Working/Episodic/Procedural)** | 🟡 PARTIAL | 50% | Implemented, JSON storage, but NOT USED by Operator |
| **Memory (Semantic + Embeddings)** | 🟡 PARTIAL | 50% | NVIDIA embeddings implemented, lexical fallback, NOT USED |
| **Voice Input** | 🔵 LEGACY | 0% (in friday/) | Porcupine wake word in main.py only |
| **Voice Output (TTS)** | 🔵 LEGACY | 0% (in friday/) | edge-tts in main.py only |
| **API Server** | ⚫ MISSING | 0% | Defined but never served |
| **Frontend (Desktop App)** | ⚫ MISSING | 0% | No Tauri/Electron/web app |
| **Frontend (Mobile App)** | ⚫ MISSING | 0% | Not started |
| **Learning from Experience** | ⚫ MISSING | 0% | Empty module |
| **Scheduling / Cron** | ⚫ MISSING | 0% | Not implemented |
| **Long-Running Task Management** | ⚫ MISSING | 0% | Not implemented |
| **Multi-App Coordination** | ⚫ MISSING | 0% | Never tested browser+desktop+file in one goal |
| **PDF Creation** | ⚫ MISSING | 0% | Not implemented |
| **PowerPoint Creation** | ⚫ MISSING | 0% | Not implemented |
| **Clipboard Operations** | ⚫ MISSING | 0% | Not implemented |
| **Multi-Monitor Handling** | ⚫ MISSING | 0% | Not implemented |
| **DPI-Aware Coordinates** | ⚫ MISSING | 0% | Not implemented |
| **Login/Auth Handling** | ⚫ MISSING | 0% | Cannot enter credentials on new sites |
| **CAPTCHA Solving/Bypass** | ⚫ MISSING | 0% | Not implemented |
| **Calendar Integration** | ⚫ MISSING | 0% | Not implemented |
| **Notification System** | ⚫ MISSING | 0% | Not implemented |
| **Error Recovery in Wild** | 🟡 PARTIAL | 30% | Repair loop exists but never stress-tested |
| **Remote Server Control** | 🔵 LEGACY | 0% (in friday/) | WebSocket server in legacy only |
| **Plugin System** | 🔵 LEGACY | 0% (in friday/) | Plugin loader in legacy only |
| **Browser Strategy (goal-aware)** | 🟢 WORKS | 70% | Selects CDP/desktop based on goal text |

### Summary Counts

```
🟢 WORKS (reliable):    15 capabilities
🟡 PARTIAL (unproven):  11 capabilities
🔴 BROKEN (known fail):  5 capabilities
⚫ MISSING (not built):  16 capabilities
🔵 LEGACY (old code):    4 capabilities
─────────────────────────────────────────
TOTAL assessed:          51 capabilities
```

### Capability Coverage Visualization

```
Intended Capabilities (what FRIDAY should do):
████████████████████████████████████████████████████  100%

Actually Working Reliably:
███████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   29%

Working + Partially Working:
█████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  51%

Broken + Missing:
░░░░░░░░░░░░░░░░░░░░░░░░░█████████████████████████   41%
```

---

## Final Assessment: Where FRIDAY Stands

### The Good

1. **Architecture is sound.** The Goal → Requirements → Plan → Execute → Verify → Repair
   loop is a legitimate AI agent architecture. Evidence Law prevents false completion.
   The code is well-documented with clear ADRs.

2. **Core pipeline works for simple tasks.** Research + synthesis + file creation is
   live-verified end-to-end. This is a real, functioning capability.

3. **Browser control (CDP) is robust.** On a dedicated profile, DOM observation,
   clicking, typing, scrolling, and multi-step sessions all work reliably.

4. **Code quality is high.** ~9,300 lines of well-typed, well-documented Python.
   Clean separation of concerns. Consistent patterns.

5. **Evidence-based verification is novel.** The EvidenceVerifier/Evidence Law pattern
   is architecturally strong and prevents the "hallucinated completion" problem.

### The Bad

1. **Primary use cases don't work.** Operating Instagram/Gmail/WhatsApp on the user's
   signed-in profile—the original motivation—FAILS due to CDP/Google Sync conflict.

2. **Test suite proves nothing about reality.** 802 tests, all mocked. Zero real I/O.
   Zero integration tests. High test count creates false confidence.

3. **Multiple orphaned systems.** FridayEngine (core.py), tool registry handlers,
   memory system, API server—all implemented but disconnected from execution.

4. **No user interface.** No voice, no GUI, no mobile app. The only "interface" is
   importing Python classes and calling methods programmatically.

5. **Legacy/new boundary is messy.** Bridge.py has accumulated its own debt.
   Two verification systems. Duplicate dispatch logic. Hardcoded URL maps.

### The Path Forward (Not a Roadmap—Just Physics)

To make FRIDAY do what it was designed for, these must be solved IN ORDER:

```
1. Signed-in profile access     ← Without this, communication tasks = 0%
   (solve CDP/Sync OR validate desktop OCR path on real apps)

2. Voice I/O in new arch        ← Without this, no hands-free UX
   (port wake word + TTS + STT to friday/ package)

3. Wire memory to Operator      ← Without this, every task starts from scratch
   (procedural memory informs planning, episodic tracks context)

4. Frontend client              ← Without this, no real user interaction
   (serve the API + build a Tauri/web client)

5. Integration tests            ← Without this, changes break things silently
   (real CDP + real LLM + real file = one E2E test)
```

### One Number

If someone asked "what percentage of FRIDAY's intended functionality works reliably
in the real world right now?" the honest answer is:

```
╔═══════════════════════════════════════╗
║                                       ║
║          18% — EIGHTEEN PERCENT       ║
║                                       ║
║  (9 of 50 representative tasks pass)  ║
║                                       ║
╚═══════════════════════════════════════╝
```

The architecture is 80% designed. The code is 40% complete. The real-world
functionality is 18% operational. These are three very different numbers,
and confusing them is how projects lose years.

---

*End of forensic audit. Every claim above is backed by code inspection of the
actual files in `c:\Projects\JARVIS\for wind\`. No aspirational claims. No roadmap
promises. Just what IS.*


---

## Appendix A: Component Wiring Diagram (What Calls What)

### Actual Call Graph (from code analysis)

```
User Input (text)
    │
    ▼
FridayBridge.process()
    │
    ├── RequestRouter.route()
    │       │
    │       ├── ClassifyRequest → JARVIS mode
    │       │       │
    │       │       └── ModelRouter.complete() → Response text
    │       │
    │       └── ClassifyRequest → FRIDAY mode
    │               │
    │               ├── ComplexityLevel.SIMPLE_ACTION
    │               │       │
    │               │       └── FridayEngine.execute_verified()
    │               │               │
    │               │               ├── DesktopPerception.get_ui_elements()  ← EMPTY (no state_cache)
    │               │               ├── ScreenCapture.grab_hash_only()
    │               │               ├── BrowserPerception.get_visible_elements() ← EMPTY (no CDP here)
    │               │               ├── action_fn()  ← dispatches to SystemActions/webbrowser
    │               │               └── ActionVerifier.verify()
    │               │
    │               └── ComplexityLevel.MULTI_STEP / COMPLEX_GOAL
    │                       │
    │                       ├── resolve_browser_strategy(goal_text)
    │                       │       ├── BrowserController.start() (CDP)
    │                       │       └── DesktopChromeController.start() (OCR fallback)
    │                       │
    │                       └── Operator(model_router, browser_controller).run(goal)
    │                               │
    │                               ├── RequirementsDiscovery.discover(goal)  ←┐ PARALLEL
    │                               ├── OperatorPlanner.plan(goal, env_state) ←┘ (ThreadPool)
    │                               │
    │                               ├── GoalExecutor.execute_plan(plan, goal)
    │                               │       │
    │                               │       ├── _execute_research(query, ctx)
    │                               │       │       └── research(query, browser, evidence)
    │                               │       │               ├── browser.search_web(query)
    │                               │       │               ├── browser.navigate(url)
    │                               │       │               ├── browser.read_text()
    │                               │       │               └── evidence.add_gathered_info()
    │                               │       │
    │                               │       ├── _execute_click(target, ctx)
    │                               │       │       ├── primitives.click(target, ws)  ← IF initialized
    │                               │       │       └── browser.click(target)          ← FALLBACK
    │                               │       │
    │                               │       ├── _generate(target, ctx)
    │                               │       │       └── ModelRouter.complete(prompt)
    │                               │       │
    │                               │       ├── _file_tool.create_file(filename, content)
    │                               │       │       └── evidence.add_file(path, size)
    │                               │       │
    │                               │       └── _execute_delivery(cap, target, ctx)
    │                               │               └── WebAgent(browser, model_router).run(send_goal)
    │                               │
    │                               ├── EvidenceVerifier.verify_one(req, evidence)
    │                               │       └── classify_requirement() + artifact matching
    │                               │
    │                               └── RepairDiagnoser.diagnose(req, evidence)
    │                                       └── GoalExecutor.execute_repair(actions, goal, prior)
    │
    └── Return BridgeResult(response, mode, complexity)
```

### What DOESN'T Connect (Orphaned Paths)

```
FridayEngine.execute_with_repair()
    └── NEVER called by Operator (only bridge simple actions)

FridayEngine.perceive_as_dict()
    └── Intended for /api/worldstate endpoint (API never served)

ToolRegistry.find_tools(capability)
    └── Used by OperatorPlanner for planning metadata
    └── NEVER used for execution dispatch (executor uses if/elif)

FridayMemory.store() / .recall()
    └── NEVER called by anything in the execution pipeline

learning/
    └── Empty module, nothing imports from it
```

---

## Appendix B: Environment Variable Reference

| Variable | Default | Purpose | Who Uses It |
|----------|---------|---------|-------------|
| `FRIDAY_DRY_RUN` | `0` | Blocks ALL external actions | GoalExecutor, tests |
| `FRIDAY_ALLOW_LEGACY_MAIN` | unset | Allows main.py to run | main.py startup guard |
| `ALLOW_LEGACY_FALLBACK` | `1` | Bridge falls back to legacy automation | FridayBridge |
| `FRIDAY_REQUIRE_REAL_CHROME` | `0` | Must connect to user's actual Chrome | BrowserController |
| `CHROME_REMOTE_DEBUG_PORT` | `9222` | CDP debug port | BrowserController |
| `JARVIS_CHROME_USER_DATA_DIR` | unset | Chrome profile path for CDP | BrowserController |
| `USE_FRIDAY_BRIDGE` | unset | Enable bridge in legacy main.py | main.py |
| `DISABLE_WAKE_WORD` | unset | Skip Porcupine wake word | main.py (legacy) |
| `DISABLE_MIC` | unset | Disable microphone | main.py (legacy) |
| `DISABLE_TTS` | unset | Disable text-to-speech | main.py (legacy) |
| `NVIDIA_API_KEY` | (required) | NVIDIA NIM API access | nvidia_provider.py |
| `GROQ_API_KEY` | (optional) | GROQ API fallback | groq_provider.py |
| `AUTO_LAUNCH_CHROME` | unset | Auto-launch Chrome with debug port | main.py (legacy) |

---

## Appendix C: File Inventory (friday/ Package)

### Core Files (Top Level)

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `__init__.py` | ~10 | Package init | ✅ |
| `bridge.py` | ~450 | JARVIS↔FRIDAY routing + execution | ✅ Active (has debt) |
| `core.py` | ~250 | FridayEngine (Observe→Act→Verify) | ⚠️ ORPHANED |
| `executor.py` | ~715 | GoalExecutor (step dispatch) | ✅ Active |
| `operator.py` | ~280 | Closed-loop Operator | ✅ Active |

### Actions Package

| File | Purpose | Status |
|------|---------|--------|
| `browser_controller.py` | CDP Playwright session (dedicated thread) | ✅ Live-verified |
| `browser_session.py` | Older browser session (being replaced) | ⚠️ Legacy overlap |
| `browser_strategy.py` | Goal-aware browser mode selection | ✅ Active |
| `chrome_launcher.py` | Ensure Chrome running with debug port | ✅ Implemented |
| `delivery.py` | DeliveryRequest/Gate types | ✅ Types only |
| `desktop_chrome.py` | OCR-based Chrome control | ✅ Live-verified |
| `file_tool.py` | File creation (txt/md/csv/xlsx/docx/html) | ✅ Live-verified |
| `result.py` | ActionResult contract | ✅ Core contract |
| `system.py` | SystemActions (launch, focus) | ✅ Implemented |
| `target.py` | Target resolution types | ✅ Types |
| `adapters/` | UAL adapter implementations | ✅ Implemented |
| `primitives.py` | Universal Action Layer | ✅ Wired to Operator |

### Capabilities Package

| File | Purpose | Status |
|------|---------|--------|
| `web_agent.py` | Generic observe→decide→act loop | ✅ Implemented |
| `research.py` | DDG search + follow links + read | ✅ Live-verified |

### Memory Package

| File | Purpose | Status |
|------|---------|--------|
| `controller.py` | FridayMemory coordinator | ✅ Implemented, NOT USED |
| `working.py` | Volatile task context | ✅ Implemented, NOT USED |
| `episodic.py` | Interaction history | ✅ Implemented, NOT USED |
| `procedural.py` | Learned patterns | ✅ Implemented, NOT USED |
| `semantic.py` | Facts + NVIDIA embeddings | ✅ Implemented, NOT USED |
| `interfaces.py` | Abstract base types | ✅ Implemented |
| `stores.py` | JSONFileStore backend | ✅ Implemented |

### Models Package

| File | Purpose | Status |
|------|---------|--------|
| `router.py` | ModelRouter (capability→provider) | ✅ Active |
| `providers/nvidia_provider.py` | NVIDIA NIM httpx calls | ✅ Live-verified |
| `providers/groq_provider.py` | GROQ API fallback | ✅ Configured |

### Planner Package

| File | Purpose | Status |
|------|---------|--------|
| `requirements.py` | RequirementsDiscovery (LLM) | ✅ Active |
| `operator_planner.py` | OperatorPlanner (LLM decomposition) | ✅ Active |
| `decomposer.py` | TaskDecomposer (legacy bridge) | ⚠️ Bridge support |
| `repair.py` | RepairDiagnoser | ✅ Implemented |

### Verification Package

| File | Purpose | Status |
|------|---------|--------|
| `evidence_law.py` | EvidenceVerifier + artifact types | ✅ Core guarantee |
| `verifier.py` | ActionVerifier (WorldState diff) | ⚠️ Used only by FridayEngine |
| `screenshot_evidence.py` | Screenshot capture + block detection | ✅ Implemented |

### Router Package

| File | Purpose | Status |
|------|---------|--------|
| `classifier.py` | ComplexityLevel + RequestMode enums | ✅ Active |
| `request_router.py` | Route to JARVIS/FRIDAY handler | ✅ Active |

### API Package

| File | Purpose | Status |
|------|---------|--------|
| `app.py` | create_friday_api() FastAPI factory | ⚫ Never served |
| Endpoints | /api/command, /status, /memory/*, /ws | ⚫ Never served |

---

## Appendix D: What Was Live-Verified This Session (Evidence Log)

### Test 1: CDP Browser Control (Dedicated Profile)

```
Method: BrowserController.start() → observe_interactive()
Result: ✅ PASS
Evidence: 60 elements observed on page, navigate/click/type all work
Profile: Dedicated (clean, no sync issues)
```

### Test 2: CDP on User's Shreesh Profile

```
Method: BrowserController with JARVIS_CHROME_USER_DATA_DIR=Shreesh profile
Result: ❌ FAIL
Evidence: Google Sync interferes, connection drops
Root cause: Chrome's profile lock + sync service conflicts with CDP
```

### Test 3: Desktop Control (DesktopChromeController)

```
Method: DesktopChromeController.start() → navigate/read
Result: ✅ PASS
Evidence: OCR reads screen text, Ctrl+L navigation works
Limitation: Best-effort confirmation (no DOM verification)
```

### Test 4: Web Agent Loop (CDP Dedicated)

```
Method: WebAgent.run() on Wikipedia task
Result: ⚠️ PARTIAL (8 steps, then LLM latency timeout)
Evidence: Infrastructure works, model response time is bottleneck
```

### Test 5: Full Operator E2E (Research + File)

```
Method: Operator.run("Research X, write report, save file")
Result: ✅ PASS (6.6 seconds)
Evidence: Real .txt file created with real content + citations from real URLs
Pipeline: RequirementsDiscovery → OperatorPlanner → research() → generate → FileTool
```

---

## Appendix E: Confidence Calibration Guide

When reading this document, interpret confidence levels as:

| Confidence | Meaning | Evidence Required |
|------------|---------|-------------------|
| 90-100% | Would bet money | Live-verified multiple times, no known edge cases |
| 70-89% | Very likely works | Live-verified at least once OR extensive unit coverage |
| 50-69% | Probably works | Implemented + unit tested but never live-verified |
| 30-49% | Might work | Implemented but significant unknowns |
| 10-29% | Unlikely to work | Partially implemented, known blockers exist |
| 0-9% | Will not work | Missing, broken, or fundamentally blocked |

### Applying This to the System

```
"Can FRIDAY research a topic and save a report?"
→ 90% confidence. Live-verified. Known to work.

"Can FRIDAY send a WhatsApp message?"  
→ 0% confidence. CDP blocked. OCR path untested. Delivery unverified.

"Can FRIDAY learn from past tasks?"
→ 0% confidence. Learning module is empty. Memory not wired.

"Can FRIDAY recover from errors automatically?"
→ 30% confidence. Repair loop exists but never observed actually recovering.
```

---

## Appendix F: Glossary of Internal Terms

| Term | Meaning |
|------|---------|
| ADR | Architecture Decision Record (design rationale docs) |
| CDP | Chrome DevTools Protocol (Playwright connection to Chrome) |
| Evidence Law | Principle: requirements satisfied ONLY by real evidence artifacts |
| DRY_RUN | Environment flag that blocks all external actions (test mode) |
| GoalExecutor | Step-by-step executor with data flow between steps |
| Operator | Closed-loop controller: plan → execute → verify → repair |
| OperatorPlanner | LLM-based decomposition of goals into capability steps |
| RequirementsDiscovery | LLM-based extraction of what must be true for goal completion |
| RepairDiagnoser | Determines why a requirement is unmet and what to do about it |
| ToolCapability | Enum of what actions are possible (CLICK, TYPE, NAVIGATE, etc.) |
| ToolRegistry | Metadata catalog of available tools (no execution handlers) |
| UAL | Universal Action Layer — unified click/type/scroll across environments |
| WorldState | Snapshot of desktop/browser state (from perception layer) |
| WebAgent | Generic LLM-driven browser operator (observe→decide→act loop) |
| BrowserStrategy | Goal-aware selection of CDP vs desktop control |
| DesktopChromeController | OCR+keyboard based Chrome control (user's real session) |
| BrowserController | Playwright CDP-based Chrome control (dedicated profile) |
| FridayEngine | Perception→Action→Verify loop (ORPHANED from Operator) |
| FridayBridge | Adapter between legacy JARVIS runtime and new friday/ package |

---

*Document complete. 20 sections + 6 appendices. Total assessment: 51 capabilities
rated, 50 real-world tasks benchmarked, all claims traceable to specific source files.*
