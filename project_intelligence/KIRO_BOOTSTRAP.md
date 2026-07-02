# Kiro Bootstrap (Zero-Context Continuation Guide)

This document is designed for a new AI agent that has no repository history or conversational memory.

## 1) What Is This Project?

Jarvis-style Windows desktop assistant combining:
- Voice input (wake word optional)
- LLM reasoning (Groq)
- Capability routing + automation
- Perception/awareness (UIA/process/browser state)
- Remote control server + dashboards
- Memory (short-term + optional long-term)

Primary entrypoint: `main.py`

## 2) What Currently Works? (High Confidence)

- Core orchestration and routing:
  - `core/assistant.py`, `core/reasoner.py`, `core/capability_dispatcher.py`
- Remote control plane:
  - `server/app.py` (FastAPI server + /execute)
  - `remote/webhook_server.py` (HMAC webhook relay)
  - `remote/telegram_relay.py` (Telegram relay)
- UI/clients:
  - `ui/ipc_server.py` websocket IPC
  - `desktop_app/` Electron shell bundling `ui/`
  - `mobile_dashboard/` React/Vite dashboard
- Memory:
  - `memory/memory_controller.py` short-term + long-term glue
  - `vector_memory.py` persistence with lexical fallback if embeddings disabled

## 3) What Is Partial / In Transition? (Medium Confidence)

- Cognitive automation system (perceive-plan-act-verify-repair):
  - Exists and is routed behind `COGNITIVE_MODE=1`, but verification/learning integration is uneven.
- Chrome automation pivot:
  - Legacy Chrome opening inside `automation/services.py` is disabled.
  - New pipeline exists: `automation/chrome_pipeline.py` + taskbar anchoring/training.
  - Dependencies are not fully pinned.
- OCR/vision:
  - OCR capability exists but depends on system Tesseract and has experimental scripts.

## 4) What Appears Abandoned / Deprecated? (High Confidence)

- Snapshot trees: `* - Copy*` directories (legacy duplicates).
- Obsolete training flows in `core/training_controller.py`:
  - `train_chrome_login` and `train_chrome_extension_unlock` are marked OBSOLETE (taskbar training is preferred).
- Some experimental scripts (CLIP, PydanticAI) are not integrated.

## 5) Do-Not-Modify-Carelessly List

High risk, central invariants:
- `core/assistant.py`: routing logic and cognitive-mode behavior.
- `automation/services.py`: action execution, snapshot capture, verification decisions.
- `automation/cognitive_loop.py`: closed-loop control logic and learning/repair hooks.
- `security/credential_vault.py`: must never leak secrets.
- `server/app.py` and `remote/webhook_server.py`: remote safety surface area (auth, allowlist, rate limiting).

## 6) Fastest Wins (Recommended First)

1. Pin missing runtime deps:
   - `pywin32` (DPAPI)
   - `opencv-python` (cv2)
2. Make Chrome navigation work through exactly one path.
3. Add a single toggle for cognitive strictness vs fallback (avoid surprises when `COGNITIVE_MODE=1`).
4. Ensure every "success" response is backed by semantic verification evidence.

## 7) Highest Risks

- Illusion of success: actions returning success text without real verification.
- Cognitive loop strict routing breaking user workflows (no fallback).
- Remote execute endpoints enabling unsafe action without adequate guardrails.
- Missing external/system dependencies causing silent feature failures (OCR, Chrome DevTools attach).

## 8) How To Reconstruct Full Understanding Quickly

Read in this order:
1. `README.md` (setup and user-facing story)
2. `COGNITIVE_SYSTEM_COMPLETE.md` (phase plan and rationale)
3. `project_intelligence/MASTER_OVERVIEW.md`
4. `project_intelligence/ARCHITECTURE.md`
5. `project_intelligence/FEATURES.md`
6. `project_intelligence/DEPENDENCIES.md`
7. `project_intelligence/FAILURES.md`
8. `project_intelligence/ROADMAP.md`
9. `project_intelligence/TECHNICAL_DEBT.md`

Then inspect indexes:
- `project_intelligence/python_index.json` (symbols/imports/env usage)
- Graph exports in `project_intelligence/GRAPHIFY_EXPORT/`

## 9) Suggested "Safe Bring-Up" Run Mode (No Mic)

Goal: validate core runtime without requiring audio hardware.

Environment flags (PowerShell):
- `DISABLE_MIC=1`
- `DISABLE_WAKE_WORD=1`
- `DISABLE_TTS=1`
- `COGNITIVE_MODE=0` initially (use legacy planner first)

Then:
- Run `python main.py`
- Use remote control: `POST http://127.0.0.1:8801/execute` with `X-API-Key: REMOTE_API_KEY`
- Once stable, flip `COGNITIVE_MODE=1` and re-run the same scripted commands.

Reality check harness:
- `scripts/reality_check.ps1` (requires `.venv312` path as written; update if needed)

## 10) Graphify Ingestion

Graph exports (JSON):
- `project_intelligence/GRAPHIFY_EXPORT/*.json`

Graphs include:
- Master graph, architecture, dependencies, runtime flow, features, failures, roadmap, FRIDAY pivot inference.

