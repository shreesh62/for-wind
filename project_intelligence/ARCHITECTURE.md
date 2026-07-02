# Architecture Extraction

This file documents:
- Current architecture (as implemented)
- Intended architecture (as hinted by phase docs and module naming)
- Legacy architecture (pre-cognitive-loop patterns still present)
- Experimental architecture (tests/probes not yet integrated)
- Future architecture (recommended evolution path)

Confidence levels are provided per section.

## Current Architecture (Implemented)

Confidence: Medium-High

### Component Map (Coarse)

```
                +-------------------+
                |     main.py       |
                |  JarvisAssistant  |
                +---------+---------+
                          |
                          v
      +-------------------+-------------------+
      |                                       |
      v                                       v
+-----+------------------+          +---------+----------+
| AwarenessController     |          | RemoteServer       |
| awareness/controller.py |          | server/app.py      |
| - UIA monitor (optional)|          | - /execute, /status|
| - process watcher       |          | - static dashboard  |
| - StateCache            |          +---------+----------+
+-----+------------------+                    |
      |                                       |
      v                                       v
+-----+------------------+          +---------+----------+
| AssistantOrchestrator   |<---------| command_queue      |
| core/assistant.py       |          +--------------------+
| - reason_about_command  |
| - CapabilityDispatcher  |
| - AutomationPlanner     |
| - CognitiveLoop (opt)   |
| - MemoryController      |
+-----+------------------+
      |
      +------------------------------+
      |                              |
      v                              v
+-----+------------------+   +-------+-------------------+
| CapabilityDispatcher     |   | AutomationServices       |
| core/capability_*.py     |   | automation/services.py   |
| - weather/maps/news      |   | - browser + desktop       |
| - simple automations     |   | - verification hooks      |
+-------------------------+   +-------+-------------------+
                                      |
                                      v
                         +------------+-------------+
                         | Browser automation        |
                         | - PlaywrightManager       |
                         | - DevToolsBridge          |
                         | - BrowserStateTracker     |
                         +------------+-------------+
                                      |
                                      v
                         +------------+-------------+
                         | Desktop automation        |
                         | - pyautogui/pywinauto     |
                         | - uiautomation            |
                         +---------------------------+
```

### Data Flow: Perception ("Awareness")

Core data structure:
- `awareness/state_cache.py` (StateCache) caches the latest:
  - Active window context (title/process/pid)
  - UI automation elements summary (from UIA monitor)
  - Process start/stop events
  - Browser tab/DOM summary and error state (from browser tracker)

Ingestion:
- `awareness/controller.py` wires monitors to an `EventDispatcher` and feeds `StateCache` via `_cache_listener`.

Consumers:
- `core/reasoner.py` uses `StateCache` to add context bits to justifications.
- `core/assistant.py` uses `StateCache` to build/redact perception snapshots for prompts and tool traces.
- `automation/services.py` uses `StateCache` snapshots to verify and to finalize "before/after" snapshots for actions.
- `automation/cognitive_loop.py` uses `StateCache` to build `WorldState` snapshots (via `awareness_state.build_world_state()` where available).

Failure points:
- UI automation monitor is optional and can be unavailable on systems lacking dependencies/permissions.
- Browser state tracking requires Chrome remote debugging attach; can fail or be throttled.

### Control Flow: Command Handling

Primary router:
- `core/assistant.py:AssistantOrchestrator.process_command()`

Decision steps (as implemented):
1. Normalize command.
2. Decide response word budget (heuristic).
3. Optionally run special follow-up commands: cancel/undo/repeat/open last website/screen queries.
4. Call `core/reasoner.reason_about_command()` -> `ReasoningOutcome(route, capability, justification)`.
5. If `COGNITIVE_MODE=1` and route == automation:
   - Execute `automation/cognitive_loop.CognitiveLoop.execute_goal()`
   - No fallback in current code path (strict).
6. Else route:
   - capability: `core/capability_dispatcher.CapabilityDispatcher.dispatch()`
   - automation: `automation/planner.AutomationPlanner.execute()` (legacy planner)
   - llm: `groq_llm.query_groq()` based generation plus personality/formatting.
7. Persist turn via `memory/memory_controller.MemoryController.add_turn()`.
8. Speak (Edge-TTS) unless disabled; push UI updates.

### Automation Architecture: Two Stacks Running in Parallel

1) Legacy-ish planner stack:
- `automation/planner.py` (large; routes many command patterns and uses `AutomationServices`)
- `automation/services.py` facade:
  - Desktop actions: focus, click, type, scroll, screenshot, OCR region
  - Browser actions: DevTools describe/summarize active tab, attach to chrome, etc.

2) Cognitive loop stack (new):
- `automation/cognitive_loop.py`:
  - parse goal (`automation/goal_parser.py` -> `Goal`)
  - perceive (`awareness/world_state.py` and `awareness/perception_snapshot.py`)
  - plan (`automation/action_planner.py`, `automation/task_graph.py`)
  - execute one action (`automation/services.py` as actuator)
  - verify (`automation/verification.py`)
  - repair (`core/self_repair.py` + repair strategies/diagnostics)
  - learn (`automation/ui_pattern_memory.py`, `memory/ui_memory.json`)

This dual-stack indicates an ongoing migration.

## Intended Architecture (Phase-Driven, Documented)

Primary source: `COGNITIVE_SYSTEM_COMPLETE.md`

Confidence: Medium (documentation exists; code may drift)

Intended goal:
- Cognitive loop becomes the **single source of truth** for any automation.
- Every action must be followed by a forced perception refresh and semantic verification.
- "Illusion paths" (returning success text without verification) must be removed.
- The system should learn UI patterns over time and reuse them when the environment matches.

Phases mentioned:
- Phase 7: Cognitive loop routing in `core/assistant.py` (automation -> cognitive loop first).
- Phase 8: Replace sleeps with state-change waits in `automation/services.py`.
- Phase 9: Persist UI memory patterns in `automation/cognitive_loop.py` after verified success.
- Phase 10: Credential-aware element resolution in `automation/element_resolver.py` integrated with `security/credential_vault.py`.
- Phase 11: Audit for unverified success messages.
- Phase 12: End-to-end "reality check" harness (PowerShell) driving commands via remote API.
- Phase 13: Strict cognitive-only mode flags.

Note:
- Current `core/assistant.py` already has a strict cognitive routing block, but it may not implement all sub-requirements from the phase doc (verification, forced refresh, learning integration) uniformly.

## Legacy Architecture (Still Present)

Confidence: High

Legacy patterns still in repo:
- A large monolithic planner `automation/planner.py` with regex-driven command parsing and direct calls into `AutomationServices`.
- Multiple "automation-like" capabilities handled by `CapabilityDispatcher` calling `AutomationServices`.
- "Chrome open website" path in `automation/services.py` is intentionally disabled, pushing toward `automation/chrome_pipeline.py` + taskbar anchoring.

Legacy subsystems:
- `jarvis_ai/` and `jarvis_memory/` directories exist but appear to be older snapshots (not analyzed deeply here). Treat as historical residue unless proven active.

## Experimental Architecture (Isolated Tests/Probes)

Confidence: High for existence; Low for integration.

These appear to be experiments rather than production features:
- OCR tests: `ocr_test.py`, `ocr_roi_test.py`, `roi_changes_test.py`, `roi_change_ocr.py`
  - Often require extra deps not in `requirements.txt` (e.g., `mss`, `cv2`).
- Vision embedding/classification: `clip_test.py` (requires `clip`, `torch`, not pinned).
- Agent framework probe: `test_pydantic_ai.py` (requires `pydantic_ai`, not pinned).

Interpretation:
- Repo is actively exploring a "vision layer" and/or agent framework migration but has not productized these pieces.

## Future Architecture (Recommended, Based on Evidence)

Confidence: Medium (recommendations).

Key recommendation: converge on a single automation contract:
- Input: `Goal` (structured intent) + `WorldState` (perception snapshot)
- Output: `Outcome` with `semantic_success`, `evidence`, `after_state_hash`, and `repair_trace`

Suggested layering:
1. Perception Layer
   - Standardize world-state schema (active window + UI elements + browser dom summary + OCR/vision signals).
2. Planning Layer
   - Central action planner producing semantic actions with explicit postconditions.
3. Action Layer
   - One actuator API (`AutomationServices.execute_semantic_action`) with strict verification hooks.
4. Learning Layer
   - UI pattern memory + repair memory integrated with a stable schema and bounded growth.
5. Safety Layer
   - Credential vault + redaction + execution policy gating (remote allowlist, rate limiting).
6. Test Harness
   - E2E reality check should be runnable on a fresh machine with documented prerequisites.

## Architecture Risk Map

| Area | Risk | Why it Matters | Mitigation |
|---|---|---|---|
| Dual-stack automation | High | Two code paths (planner vs cognitive loop) can diverge and reintroduce "illusion success" | Choose one contract; gate legacy behind explicit flag; test both |
| Missing dependency pinning (cv2/mss/torch) | High | Cognitive/vision experiments require deps not in requirements; runtime fails | Declare optional extras or add to requirements with platform guards |
| `automation/services.py` size/complexity | Medium-High | Hard to audit verification coverage and invariants | Split into modules: desktop, browser, verification, screenshot/OCR |
| Remote execution safety | Medium | Remote /execute runs actions; must be hardened | Keep allowlist/rate limit/audit log; ensure key rotation and logging without secrets |
| Windows-specific UIA/DPAPI | Medium | Non-portable; fragile across Windows versions | Isolate Windows-only modules; provide graceful degradation |

