# Roadmap Extraction

This roadmap is inferred from:
- `COGNITIVE_SYSTEM_COMPLETE.md` (phases 7-13)
- Code hotspots (`core/assistant.py`, `automation/services.py`, `automation/cognitive_loop.py`)
- PowerShell harnesses (`scripts/reality_check.ps1`, `scripts/self_repair_test.ps1`, `scripts/test_open_chrome.ps1`)
- Missing dependency pinning discovered in code imports

Confidence: Medium (actual priorities may differ).

## Immediate Tasks (0-7 days)

Critical path items first:
1. Pin missing runtime dependencies required by production-ish code paths:
   - `pywin32` (DPAPI vault)
   - `opencv-python` or `opencv-python-headless` (taskbar + chrome pipeline)
2. Make "open website in chrome" work again in a single, verified path:
   - Either route all Chrome navigation through `automation/chrome_pipeline.open_chrome()` + DevTools navigation,
   - Or re-enable a verified legacy attach path in `automation/services.py` with semantic verification.
3. Add an explicit cognitive routing policy:
   - Introduce `ALLOW_LEGACY_FALLBACK` (or similar) as a single source of truth.
   - Avoid "strict no fallback" surprises when `COGNITIVE_MODE=1` unless explicitly requested.
4. Ensure every automation action returns a verifiable outcome object:
   - `semantic_success` (bool)
   - `evidence` (state hash change, window change, URL match, focused element change, etc.)
   - `before_hash` / `after_hash`
5. Run and fix the reality harness:
   - `scripts/reality_check.ps1` should pass on a clean environment with documented prerequisites.

## Next 30 Tasks (Ordered, With Dependencies)

Legend:
- DependsOn: upstream tasks that must be done first
- Files: primary touch points

| # | Task | DependsOn | Files | Notes |
|---:|---|---|---|---|
| 1 | Pin `pywin32` for Windows vault | Immediate-1 | `requirements.txt` | Gate vault clearly if unavailable |
| 2 | Pin `opencv-python` and document | Immediate-1 | `requirements.txt`, `DEPENDENCIES.md` | Needed for taskbar + chrome pipeline |
| 3 | Decide Chrome navigation contract | Immediate-2 | `automation/services.py`, `automation/chrome_pipeline.py` | Avoid disabled Chrome path for user commands |
| 4 | Implement Phase 8 state-change waits everywhere | Immediate-4 | `automation/services.py`, `automation/timing.py` | Replace sleeps with `wait_for_state_change` |
| 5 | Standardize `WorldState` schema (versioned) | 4 | `awareness/world_state.py` | Make verification robust |
| 6 | Extend verification coverage (click/type/scroll/nav) | 4,5 | `automation/verification.py` | Ensure no unverified success |
| 7 | Integrate Phase 9 UI memory persistence | 5,6 | `automation/cognitive_loop.py`, `automation/ui_pattern_memory.py`, `memory/ui_memory.json` | Define bounded storage |
| 8 | Integrate credential-aware resolution (Phase 10) | 1,5 | `automation/element_resolver.py`, `security/credential_vault.py`, `core/training_controller.py` | Never log secrets |
| 9 | Audit illusion paths (Phase 11) | 6 | `automation/services.py`, `automation/planner.py`, `core/capability_dispatcher.py` | Search for success strings without verification |
| 10 | Strengthen remote safety defaults | - | `server/app.py`, `remote/webhook_server.py` | Allowlist + rate limit + audit logging |
| 11 | Unify command normalization | - | `automation/planner.py`, `core/assistant.py` | Reduce duplicate regex logic |
| 12 | Modularize `automation/services.py` | 4,6 | `automation/services.py` | Split browser vs desktop vs screenshot/OCR |
| 13 | Improve UI telemetry and trace | - | `core/telemetry.py`, `ui/ipc_server.py`, `desktop_app/renderer/*` | Make debugging easier |
| 14 | Add regression tests for cognitive loop | 5,6 | `tests/*` | Use mocked `StateCache` and deterministic snapshots |
| 15 | Move experiments to `experiments/` | - | `clip_test.py`, `roi_change_ocr.py`, `test_pydantic_ai.py` | Keep runtime clean |
| 16 | Document clean setup with prerequisites | - | `README.md`, `DEPENDENCIES.md` | Include Tesseract + Chrome flags |
| 17 | Reduce duplicate snapshot trees | - | repo hygiene | Prefer archive outside repo or git branches/tags |
| 18 | Decide long-term memory approach for Windows | - | `vector_memory.py`, `memory/memory_controller.py` | Either lexical fallback is ok, or add Windows embeddings |
| 19 | Verify plugin system end-to-end | - | `plugins/loader.py`, sample plugin | Ensure manifest schema and handler registration works |
| 20 | Ensure secrets never leak into prompts/logs | 1,8 | `core/llm_sanitizer.py`, `security/*` | Redaction enforcement |

## Next 90-Day Vision (Coherent Milestones)

Milestone A: "Cognitive Automation MVP"
- Cognitive loop handles top 10 automation intents with strict verification:
  - open/navigate/search, click, type, scroll, focus, screenshot, summarize tab, simple form fill
- End-to-end tests via remote `/execute` prove no hallucinated success (at least in strict mode).

Milestone B: "Learning + Repair"
- UI pattern memory stores successful strategies and repair outcomes.
- Self-repair uses a consistent diagnostic taxonomy and produces bounded, interpretable repair traces.

Milestone C: "Safe Remote Operator"
- Hardened remote plane:
  - IP allowlist defaults, rate limit enabled, audit log recommended
  - webhook replay protection enabled with default window

## Long-Term Vision (6-18 months)

- A single agent loop (Observe -> Plan -> Act -> Verify -> Learn) becomes the dominant architecture.
- Vision layer upgrades:
  - ROI change detection integrated into awareness for incremental perception.
  - Optional visual classifiers (CLIP-like) if and only if they improve reliability.
- Automated training flows:
  - Taskbar anchoring generalized to other pinned apps.
  - Credential-aware resolution is safe-by-construction and never exposes secrets.
- Packaging:
  - Repeatable build pipeline for backend + Electron desktop with environment bootstrap.

## Roadmap Graph

Graphify export:
- `project_intelligence/GRAPHIFY_EXPORT/JARVIS_ROADMAP_GRAPH1.json`

