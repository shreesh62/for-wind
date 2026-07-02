# Master Overview (Repository Intelligence Package)

Generated for: handoff to a new AI coding system (Kiro) with zero prior context.

This package is intentionally verbose and redundant. Missing information is acceptable. Lost context is not.

## What This Project Is

Project name (observed): `for wind` / "Jarvis Assistant"

High-level purpose:
- A Jarvis-style, always-on desktop assistant for Windows that combines:
  - Voice I/O (wake word + microphone capture + TTS)
  - Capability routing (intent -> tool/capability handler)
  - Automation (browser automation via Playwright/DevTools + desktop automation via Windows/UIA/pyautogui)
  - Perception/awareness (active window/process + UI automation event monitoring + browser state tracking)
  - Memory (short-term conversation buffer + optional long-term "vector" memory)
  - Remote control plane (FastAPI server + static dashboard, plus webhook/Telegram relays)
  - Desktop/mobile dashboards (Electron desktop shell, React/Vite mobile dashboard)

Primary entrypoint (observed): `main.py`

Confidence: High (README + code corroborate).

## Vision (Inferred)

The system is evolving from:
- "Capability registry + static automation flows"
to
- "Closed-loop cognitive automation" where **perception is the source of truth** and actions are verified against reality.

Evidence:
- `COGNITIVE_SYSTEM_COMPLETE.md` describes a phased "cognitive system" migration.
- `automation/cognitive_loop.py` implements a perceive-plan-act-verify-repair loop (iterations, verification, self-repair, UI pattern memory).
- `core/assistant.py` already routes automation through `CognitiveLoop` when `COGNITIVE_MODE=1` (strict/no fallback in current code).

Confidence: High for the pivot direction; Medium for final desired end-state (some phases are documented but not fully enforced everywhere).

## Repository Structure (Top-Level)

Canonical (non-snapshot) subsystems:
- `main.py`: orchestrates startup and the main run loop(s).
- `core/`: assistant brain (routing, reasoning, scheduler, sanitization, telemetry, training).
- `automation/`: automation services facade + planner + cognitive loop + taskbar visual anchoring for Chrome.
- `awareness/`: perception stack, state cache, UI automation monitor (UIA), process watcher, world-state snapshots.
- `memory/`: memory controller and short-term buffer; UI memory file lives under `memory/`.
- `security/`: DPAPI credential vault and related safety.
- `server/`: FastAPI remote control server + static dashboard serving.
- `ui/`: websocket IPC + local web client UI resources.
- `desktop_app/`: Electron shell bundling `ui/`.
- `mobile_dashboard/`: React/Vite mobile dashboard.
- `services/`: external APIs (weather/maps/news).
- `plugins/`: plugin manifest/module loader that can add/override capability definitions and handlers.
- `remote/`: webhook + Telegram relay forwarding to `server/` `/execute`.
- `scripts/`: PowerShell harnesses for cognitive system tests/reality checks.
- `tests/`: test folder (coverage appears limited).

Snapshot/duplicates:
- Many directories exist as `X - Copy` and `X - Copy (2)` (e.g., `automation - Copy`, `core - Copy`).
  - Interpretation: point-in-time snapshot backups from earlier repo state(s).
  - Risk: divergence/confusion; do not edit these copies unless you are intentionally restoring history.

See also:
- `project_intelligence/FOLDER_INVENTORY.md`
- `project_intelligence/CODEBASE_INVENTORY.md`

Confidence: High.

## Core Runtime Flows (Observed + Inferred)

### Startup
1. Load settings via `config.get_settings()` (loads `.env`).
2. Initialize awareness/perception (`awareness/controller.py` -> UI automation monitor + process watcher + shared `StateCache`).
3. Initialize automation:
   - `automation/services.py` (facade for browser + desktop actions)
   - `automation/planner.py` (legacy-ish planner) and/or `automation/cognitive_loop.py` (new)
4. Initialize UI websocket IPC server: `ui/ipc_server.py` (`UISocketServer`).
5. Initialize remote server: `server/app.py` (`RemoteServer` wrapper around FastAPI+uvicorn).
6. Enter command loop(s):
   - Voice loop (Porcupine wake word + mic) if enabled.
   - Remote command loop (queue fed by `server/` endpoints).

Primary entrypoint implementation: `main.py`

Confidence: Medium-High (we inspected `main.py` head; further details should be verified by reading the rest of `main.py`).

### Command Routing
1. `core/reasoner.py`: returns `ReasoningOutcome(route=capability|automation|llm, capability=...)`.
2. If `COGNITIVE_MODE=1` and route is automation:
   - `core/assistant.py` executes `CognitiveLoop.execute_goal()` (current code: strict/no fallback).
3. Else:
   - Use capability dispatcher (`core/capability_dispatcher.py`) for non-automation capabilities.
   - Use automation planner (`automation/planner.py`) for automation-like commands.
   - Use LLM (`groq_llm.py`) for conversational fallback.

Confidence: High (core files corroborate).

## Configuration and Flags (Do Not Leak Secrets)

### Required/expected env keys (observed in README/config)
- `GROQ_API_KEY`
- `WEATHER_API_KEY`
- `DISTANCEMATRIX_API_KEY`
- `GEOCODING_API_KEY`
- `PORCUPINE_ACCESS_KEY`
- `REMOTE_API_KEY`
- (optional) `NEWS_API_KEY`, `WEBHOOK_SECRET`, `REMOTE_SERVER_URL`, rate limits, audit logs

### Behavioral flags (observed in `main.py` and docs)
- `DISABLE_WAKE_WORD`, `DISABLE_MIC`, `DISABLE_TTS`
- `DISABLE_REMOTE_SERVER`, `DISABLE_BROWSER_TRACKER`, `DISABLE_UI_AUTOMATION_MONITOR`, `DISABLE_CPU_ALERTS`
- `AUTO_LAUNCH_CHROME`, `CHROME_REMOTE_DEBUG_PORT`
- `BROWSER_DOM_STATUS_MAX_CHARS`, `BROWSER_TRACKER_AUTO_LAUNCH`
- `COGNITIVE_MODE` (enables CognitiveLoop routing)
- `MEMORY_EMBEDDINGS` (enables heavy embedding pipeline in `vector_memory.py`)

Security-related remote flags (observed in `server/app.py` and `remote/webhook_server.py`):
- `REMOTE_ALLOWED_IPS` / `REMOTE_IP_ALLOWLIST`
- `REMOTE_RATE_LIMIT_PER_MINUTE`
- `REMOTE_AUDIT_LOG`
- `WEBHOOK_RATE_LIMIT_PER_MINUTE`
- `WEBHOOK_REPLAY_WINDOW_SEC`
- `WEBHOOK_AUDIT_LOG`
- `WEBHOOK_SPEAK`

Note: `.env` exists in repo root; do not copy its values into logs or documentation.

Confidence: High.

## Key Artifacts / State Files

Persistent memory:
- `memory.json` / `memory.index`: long-term memory store (FAISS optional, embeddings disabled by default).
- `interaction_log.json`: logged interactions.
- `memory/ui_memory.json`: UI pattern store schema (patterns/repairs/login_flows).
- `ui_patterns.json`: UI pattern memory used by `automation/ui_pattern_memory.py`.

Automation training:
- `memory/taskbar_anchors.json` (referenced by scripts; produced by taskbar training).

Telemetry/logging:
- `logs/` (runtime logs)

Confidence: Medium (some files referenced by scripts; verify existence when running).

## JARVIS -> "FRIDAY" Pivot (Inferred)

The repo contains strong evidence of a pivot toward a more autonomous, perception-driven agent architecture:
- Vision/perception: screenshots (`PIL.ImageGrab`), UIA monitor, OCR experiments (`pytesseract`), ROI change detection experiments.
- Reasoning: structured goal parsing + action planning + task graphs; LLM usage via Groq; sanitizer.
- Action: desktop automation (pyautogui/pywinauto/uiautomation) + browser automation (Playwright + DevTools).
- Feedback: semantic verification engine + self-repair + UI pattern memory.

The word "FRIDAY" is not present in code identifiers, but `friday_env/` exists as an environment snapshot and the architecture strongly matches a "Friday-style" agent loop.

Confidence: Medium (architecture evidence is clear; naming is not).

## Outputs In This Intelligence Package

Required handoff docs:
- `project_intelligence/ARCHITECTURE.md`
- `project_intelligence/FEATURES.md`
- `project_intelligence/DEPENDENCIES.md`
- `project_intelligence/FAILURES.md`
- `project_intelligence/ROADMAP.md`
- `project_intelligence/TECHNICAL_DEBT.md`
- `project_intelligence/KIRO_BOOTSTRAP.md`

Inventories:
- `project_intelligence/CODEBASE_INVENTORY.md` (markdown table)
- `project_intelligence/FOLDER_INVENTORY.md` (markdown table)
- `project_intelligence/python_index.json` (symbols/imports/env key usage)
- `project_intelligence/repo_index.json` (high-level index)

Graphify exports (JSON graphs):
- `project_intelligence/GRAPHIFY_EXPORT/JARVIS_MASTER_INTELLIGENCE_GRAPH1.json`
- `project_intelligence/GRAPHIFY_EXPORT/JARVIS_ARCHITECTURE_GRAPH1.json`
- `project_intelligence/GRAPHIFY_EXPORT/JARVIS_DEPENDENCY_GRAPH1.json`
- `project_intelligence/GRAPHIFY_EXPORT/JARVIS_RUNTIME_FLOW_GRAPH1.json`
- `project_intelligence/GRAPHIFY_EXPORT/JARVIS_FEATURE_STATUS_GRAPH1.json`
- `project_intelligence/GRAPHIFY_EXPORT/JARVIS_FAILURE_GRAPH1.json`
- `project_intelligence/GRAPHIFY_EXPORT/JARVIS_ROADMAP_GRAPH1.json`
- `project_intelligence/GRAPHIFY_EXPORT/JARVIS_FRIDAY_PIVOT_GRAPH1.json`

## Timeline (Inferred From File Timestamps)

Observed repo hints:
- Many `* - Copy*` directories timestamped around 2025-10-12 (snapshot backups).
- Many cognitive system files timestamped around 2026-01-05 to 2026-02-05.
- `test_pydantic_ai.py` timestamped 2026-05-31, suggesting ongoing experimentation with agent frameworks.

Confidence: Low-Medium (timestamps indicate activity but not exact milestones).

