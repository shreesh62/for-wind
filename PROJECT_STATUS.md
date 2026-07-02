# PROJECT STATUS — FRIDAY Phase 0 Audit

Generated: 2026-06-08  
Lead Architect: Kiro (AI)  
Owner: Shreesh

---

## Executive Summary

The repository contains a **functional but architecturally fragmented** Jarvis-style desktop assistant. Core routing, remote control, voice I/O, and basic automation work. The cognitive loop (perceive-plan-act-verify-repair) exists but is partially integrated and brittle. The system is **not production-ready** for distribution to non-technical users.

The path to FRIDAY requires:
1. Architecture consolidation (eliminate dual-stack, monoliths, snapshot clutter)
2. Perception layer hardening (unified WorldState from multiple sources)
3. Verified action contract (every action returns evidence)
4. Production packaging (installable desktop app without dev environment)

---

## Current State

### What Works (High Confidence)

| Subsystem | Status | Key Files |
|-----------|--------|-----------|
| Voice I/O (wake word + mic + TTS) | Working | `main.py`, `jarvis_io.py`, `edge_tts_voice.py` |
| LLM reasoning (Groq) | Working | `groq_llm.py`, `core/reasoner.py` |
| Capability routing + intent matching | Working | `capabilities.py`, `core/capability_dispatcher.py` |
| Remote control server (FastAPI) | Working | `server/app.py` |
| Webhook relay (HMAC + replay protection) | Working | `remote/webhook_server.py` |
| Telegram relay | Working | `remote/telegram_relay.py` |
| Electron desktop shell | Working | `desktop_app/` |
| React mobile dashboard | Working | `mobile_dashboard/` |
| WebSocket IPC | Working | `ui/ipc_server.py` |
| Short-term memory buffer | Working | `memory/short_term_buffer.py` |
| Long-term memory (lexical fallback) | Working | `vector_memory.py`, `memory/memory_controller.py` |
| Awareness controller + state cache | Working | `awareness/controller.py`, `awareness/state_cache.py` |
| Credential vault (DPAPI) | Working | `security/credential_vault.py` |
| Plugin loader | Working | `plugins/loader.py` |
| Personality + TTS formatter | Working | `personality.py`, `tts_formatter.py` |
| External services (weather/maps/news) | Working | `services/` |

### What Is Partial / In Transition

| Subsystem | Status | Gap |
|-----------|--------|-----|
| Cognitive loop (perceive-plan-act-verify) | ~60% | Wired behind `COGNITIVE_MODE=1` but strict/no fallback; verification uneven |
| WorldState schema | ~70% | Well-designed dataclass but not consistently populated from all sources |
| Verification engine | ~55% | Functions exist for click/type/scroll/nav but not enforced on all paths |
| Self-repair engine | ~50% | Repair strategies exist; depend on diagnostic quality and stable snapshots |
| UI pattern memory (learning) | ~45% | Schema exists, 1 recorded pattern; not fully integrated into loop |
| Chrome pipeline (taskbar-anchored) | ~55% | `cv2` dependency not pinned; hard-coded profile name; uses sleeps |
| Goal parser + task graph | ~50% | Exists but coverage of intents is narrow |
| Desktop OCR | ~45% | `pytesseract` requires system Tesseract; integration uncertain |
| Browser state tracker | ~60% | Requires Chrome with `--remote-debugging-port`; can fail silently |

### What Is Broken / Deprecated

| Item | Why |
|------|-----|
| Chrome open via `open_website(browser=chrome)` | Explicitly disabled in `automation/services.py` |
| `pywin32` not pinned | Credential vault crashes on fresh install |
| `opencv-python` not pinned | Taskbar anchoring and chrome pipeline crash on fresh install |
| `faiss-cpu` + `sentence-transformers` gated off Windows | Vector memory is lexical-only on target platform |
| Legacy `automation/planner.py` monolith | Large, regex-driven, diverges from cognitive loop |
| `* - Copy` snapshot directories | Confusing; risk of wrong imports/edits |
| Obsolete training flows (`train_chrome_login`) | Marked OBSOLETE in code |
| Experimental scripts (CLIP, PydanticAI, ROI) | Deps not pinned; not integrated |

---

## Architecture Strengths

1. **WorldState dataclass is well-designed** — Clean schema with desktop/visual/browser perception, derived facts, hash-based change detection. This is a solid foundation for the perception layer.

2. **Cognitive loop architecture is sound** — The perceive→plan→act→verify→repair cycle in `cognitive_loop.py` is the right pattern. It just needs to be the *only* path.

3. **Verification functions exist** — `verification.py` covers click, type, login, open_website, dismiss_dialog, focus_window, scroll. Just needs enforcement.

4. **Self-repair engine has real strategies** — Element not found, dialog blocking, state unchanged, focus lost. Good diagnostic taxonomy.

5. **UI pattern memory schema is learnable** — JSON-backed, success-count weighted, hash-matched. Ready to be scaled.

6. **Remote control plane is solid** — FastAPI with API key auth, rate limiting, IP allowlist, HMAC webhook relay with replay protection.

7. **Plugin system exists** — Manifest + module loader with capability registration. Extensible.

8. **Memory controller design is reasonable** — Short-term buffer + long-term with salience/recency filtering and deduplication.

---

## Architecture Weaknesses

### Critical

1. **Dual automation stack** — `automation/planner.py` (legacy regex) and `automation/cognitive_loop.py` (new) coexist. When `COGNITIVE_MODE=0`, the legacy planner runs unverified. When `COGNITIVE_MODE=1`, failures have no fallback. This is the #1 source of "illusion success."

2. **`automation/services.py` is a monolith** — Hundreds of methods mixing browser actions, desktop actions, screenshot/OCR, verification hooks. Impossible to audit for coverage or enforce invariants.

3. **No unified action contract** — Actions return strings or mixed dict/bool. No consistent `ActionResult(success, evidence, before_hash, after_hash)` enforcement.

4. **Missing critical dependencies** — `pywin32` and `opencv-python` are imported by production code but not in `requirements.txt`. Fresh installs break.

5. **No production packaging** — Requires Python dev environment, VS Code, manual `.env` setup. Cannot share with friends.

### High Priority

6. **Environment flag sprawl** — 15+ `DISABLE_*` / behavioral flags with no schema, no validation, no config UI.

7. **No model router** — Everything goes through Groq. No local model support, no task-based routing, no vision model integration.

8. **Memory system is platform-limited** — Embeddings disabled on Windows (the target platform). Memory retrieval is basic lexical matching.

9. **No learning persistence loop** — UI pattern memory exists but the cognitive loop doesn't consistently write to it after verified success.

10. **Hard-coded assumptions** — Chrome profile "Shreesh", specific taskbar positions, OCR heuristics.

### Medium Priority

11. **Weak test coverage** — Tests exist but are limited and many are stale.
12. **Mixed encodings / mojibake** — `"âœ…"` artifacts throughout.
13. **Snapshot directory pollution** — 10+ `* - Copy` directories cluttering the repo.
14. **Observability fragmentation** — Telemetry exists but no unified trace format.

---

## Missing Systems (Required for FRIDAY)

| System | Current Status | Priority |
|--------|---------------|----------|
| Unified perception layer (MSS + OCR + CLIP + UIA + DOM) | Partial/fragmented | Phase 2 |
| Verified action contract (ActionResult everywhere) | Missing | Phase 3 |
| Verification enforcement (no unverified success) | Partial | Phase 4 |
| Planner with task decomposition + replanning | Partial | Phase 5 |
| Multi-tier memory (working/episodic/procedural/semantic) | Basic only | Phase 6 |
| Model router (Groq + local + NVIDIA NIM) | Missing | Phase 7 |
| Production API layer (auth, sessions, streaming) | Basic | Phase 8 |
| Mobile remote control (WebSocket, screenshots, notifications) | Basic | Phase 9 |
| Desktop app backend (system tray, settings, profiles) | Basic Electron only | Phase 10 |
| Windows installer + auto-updates | Missing | Phase 11 |
| Research integration framework | Missing | Phase 12 |

---

## Migration Recommendations

### Strategy: Incremental Consolidation

Do NOT rewrite from scratch. The existing code has working functionality. Instead:

1. **Create new directory structure alongside existing code**
2. **Migrate subsystem by subsystem with tests**
3. **Gate migration behind feature flags**
4. **Delete old code only after new code passes all tests**

### Proposed Target Architecture

```
friday/
├── perception/          # Unified perception (screen, OCR, vision, UIA, browser DOM)
│   ├── screen.py        # MSS screenshot capture
│   ├── ocr.py           # Tesseract OCR with confidence
│   ├── vision.py        # CLIP/visual understanding
│   ├── desktop.py       # Windows UIA elements
│   ├── browser.py       # DevTools/Playwright DOM state
│   └── world_state.py   # Unified WorldState builder
├── memory/              # Multi-tier memory system
│   ├── working.py       # Current task context
│   ├── episodic.py      # Interaction history
│   ├── procedural.py    # Learned action patterns (UI patterns)
│   ├── semantic.py      # Facts and knowledge
│   └── user.py          # User preferences and profiles
├── planner/             # Goal decomposition and planning
│   ├── goal_parser.py   # NL → structured Goal
│   ├── decomposer.py    # Goal → task graph
│   ├── planner.py       # Task graph → action sequence
│   └── replanner.py     # Failure → revised plan
├── actions/             # All actuators with verified outcomes
│   ├── desktop.py       # Win32/UIA/pyautogui actions
│   ├── browser.py       # Playwright/DevTools actions
│   ├── system.py        # App launch, file ops, window management
│   └── result.py        # ActionResult contract
├── verification/        # Post-action verification
│   ├── verifier.py      # Verify action outcomes
│   ├── repair.py        # Self-repair strategies
│   └── evidence.py      # Evidence collection
├── learning/            # Learning from experience
│   ├── pattern_memory.py # UI pattern memory
│   ├── repair_memory.py  # Repair strategy memory
│   └── consolidation.py  # Memory consolidation
├── models/              # Model routing and inference
│   ├── router.py        # Task → model routing
│   ├── groq.py          # Groq API client
│   ├── local.py         # Local model inference
│   └── nvidia.py        # NVIDIA NIM API client
├── api/                 # Backend API for all clients
│   ├── app.py           # FastAPI application
│   ├── auth.py          # Authentication
│   ├── websocket.py     # Real-time communication
│   └── routes/          # API route modules
├── desktop_app/         # Electron/Tauri desktop application
│   ├── backend/         # Python backend integration
│   ├── frontend/        # UI (React/Svelte)
│   └── installer/       # Windows installer config
└── mobile_backend/      # Mobile app API extensions
```

### Migration Order

1. **Phase 0** (this document) — Audit complete. Await approval.
2. **Phase 1** — Create `friday/` structure, migrate WorldState + verification + action result contract.
3. **Phase 2** — Build unified perception layer using existing awareness code.
4. **Phase 3** — Consolidate action layer with enforced ActionResult.
5. **Phase 4** — Wire verification into every action path.
6. **Phase 5** — Upgrade planner (absorb cognitive loop + goal parser).
7. **Phase 6** — Build multi-tier memory (preserve existing short-term + vector).
8. **Phase 7** — Add model router (Groq + NVIDIA NIM free endpoints + local).
9. **Phase 8-12** — API, remote, desktop, packaging, research.

### Key Decisions Needed From Owner

1. **Electron vs Tauri for desktop app?** Tauri is lighter, Rust-backed, better for packaging. Electron is proven but heavy.
2. **Keep legacy planner as fallback during transition?** Recommend yes, behind `ALLOW_LEGACY_FALLBACK=1`.
3. **Target Python version?** Currently 3.12. Confirm.
4. **NVIDIA NIM API credentials** — Ready when needed for Phase 7.
5. **Distribution target** — Windows only? Or cross-platform eventually?

---

## Immediate Next Steps (Pending Approval)

1. Create `friday/` directory structure
2. Pin missing dependencies (`pywin32`, `opencv-python`)
3. Create `ActionResult` contract
4. Migrate `WorldState` to `friday/perception/`
5. Create test harness for migrated modules
6. Begin Phase 1 migration

---

*Awaiting owner approval before proceeding with restructuring.*
