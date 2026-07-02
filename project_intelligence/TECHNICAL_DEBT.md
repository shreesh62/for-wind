# Technical Debt Analysis

This list is derived from static repo inspection and should be refined by running the system.

Scale:
- Impact: how badly this can break correctness/user trust
- Risk: likelihood of causing regressions or hidden failures
- Effort: relative engineering effort

Confidence: Medium.

## Critical Debt

| Debt Item | Impact | Risk | Effort | Recommended Timing | Evidence / Notes |
|---|---|---|---|---|---|
| Missing dependency pinning (`pywin32`, `opencv-python`) | High | High | Low | Immediate | `security/credential_vault.py` imports `win32crypt`; multiple automation modules import `cv2` |
| Disabled Chrome path without full replacement | High | High | Medium | Immediate | `automation/services.py` raises for Chrome in `open_website()`; must ensure user commands route to a working Chrome pipeline |
| Dual automation stack divergence (planner vs cognitive loop) | High | High | High | Immediate -> 30 days | Two code paths can disagree and reintroduce "illusion success" |
| Verification coverage incomplete/uneven | High | High | Medium-High | Immediate -> 30 days | Many actions can succeed/fail without robust postcondition checks; user trust depends on verified outcomes |

## High Priority Debt

| Debt Item | Impact | Risk | Effort | Recommended Timing | Evidence / Notes |
|---|---|---|---|---|---|
| `automation/services.py` monolith (~100k LOC) | High | Medium | High | 30 days | Hard to audit; difficult to enforce invariants consistently |
| Hard-coded assumptions in Chrome pipeline | Medium-High | Medium | Medium | 30 days | `handle_profile_selection(profile_name='Shreesh')` default; OCR heuristics brittle; uses sleeps |
| OCR prerequisites not documented as runtime requirement | Medium | High | Low | Immediate | `pytesseract` requires system Tesseract install; without it OCR features silently fail |
| Excess snapshot copies in repo | Medium | Medium | Medium | 30 days | `automation - Copy`, `core - Copy`, etc. increase confusion and risk wrong edits |
| Environment flag sprawl | Medium | Medium | Medium | 30 days | Many flags (`DISABLE_*`, `STRICT_*`, etc.) without a single authoritative config schema |

## Medium Priority Debt

| Debt Item | Impact | Risk | Effort | Recommended Timing | Evidence / Notes |
|---|---|---|---|---|---|
| Mixed encodings / mojibake in strings | Low-Medium | Medium | Medium | 30-90 days | Many outputs show "âœ…" artifacts; can harm UX |
| Long-term memory quality on Windows | Medium | Medium | Medium | 90 days | Embeddings disabled by default; FAISS/ST off on Windows; retrieval mostly lexical |
| Weak automated test coverage | Medium | Medium | Medium | 30-90 days | Some PS scripts exist; Python unit tests appear limited |
| Observability fragmentation | Medium | Low-Medium | Medium | 90 days | Telemetry logger exists; tool traces exist; unify into a coherent trace schema |

## Low Priority Debt

| Debt Item | Impact | Risk | Effort | Recommended Timing | Evidence / Notes |
|---|---|---|---|---|---|
| Clean up experimental one-off scripts | Low | Low | Low | 90+ days | `clip_test.py`, `roi_change_ocr.py`, `test_pydantic_ai.py` |
| Consolidate duplicated docs | Low | Low | Low | 90+ days | README + cognitive doc overlap; keep single source of truth |

## Debt-to-Graph Links

The following Graphify exports include nodes/edges that reference debt hotspots:
- `project_intelligence/GRAPHIFY_EXPORT/JARVIS_DEPENDENCY_GRAPH1.json`
- `project_intelligence/GRAPHIFY_EXPORT/JARVIS_FAILURE_GRAPH1.json`

