# Failure Database (Experiments, Broken/Fragile Paths, Abandoned Work)

This file records failures and fragilities found by static inspection (code/docs/scripts).
It is not a runtime incident log.

Confidence: Medium (some items require runtime validation).

## Failure / Fragility Table

| Experiment / Area | Goal | Failure Cause (Observed/Most Likely) | Current State | Recommendation |
|---|---|---|---|---|
| Chrome open via `AutomationServices.open_website(..., browser=chrome)` | Open URLs in Chrome reliably | Code explicitly raises: legacy Chrome opening disabled in `automation/services.py` | Broken-by-design for Chrome path | Ensure all "open website" intents route to `automation/chrome_pipeline.open_chrome()` or re-enable a verified Chrome attach path |
| Cognitive mode strict routing (`COGNITIVE_MODE=1`) | Single source of truth: cognitive loop for automation | In `core/assistant.py`, automation route executes cognitive loop with no fallback; any cognitive failure becomes user-facing failure | Partial; high brittleness | Add a controlled fallback gate (env flag) and a standard outcome schema (success/verified/evidence) |
| Missing dependency pinning: `cv2` | Taskbar anchoring, visual matching, Chrome pipeline | `cv2` imported in multiple production-ish modules but not pinned in requirements | Broken on fresh env | Add `opencv-python` (or `opencv-python-headless`) to requirements with platform notes |
| Missing dependency pinning: `pywin32` | Credential vault via DPAPI | `security/credential_vault.py` depends on `win32crypt` but pywin32 is not pinned | Broken on fresh env | Add `pywin32` to Windows requirements; gate vault more clearly if unavailable |
| OCR feature correctness | Read screen/region text reliably | `pytesseract` needs system Tesseract install; OCR quality varies; integration unclear | Experimental/Partial | Document system prereqs; build OCR contract into `WorldState` (words, confidence, ROI) |
| ROI change + OCR detector (`roi_change_ocr.py`) | Detect change regions and OCR them | Uses `mss` + `cv2` and prints to console; not integrated; deps not pinned | Experimental | Either integrate into awareness pipeline or quarantine into `experiments/` with explicit deps |
| CLIP test (`clip_test.py`) | Classify screenshot context | Requires `torch` + `clip`; not pinned; one-off test | Experimental | If needed, define a vision embedding module with optional extras; otherwise archive |
| PydanticAI probe (`test_pydantic_ai.py`) | Evaluate agent framework integration | `pydantic_ai` not pinned; no integration into assistant routing | Experimental | Decide whether to adopt agent framework; if yes, create an adapter around existing `ReasoningOutcome` routing |
| Vector memory embeddings on Windows | Semantic retrieval memory | Requirements gate `faiss-cpu` and `sentence-transformers` off on Windows; embeddings disabled by default via `MEMORY_EMBEDDINGS=0` | Partial (fallback similarity only) | Provide a Windows-capable embedding/retrieval path or document that vector memory is mostly lexical unless run on non-Windows |
| Encoding artifacts in console output | Clean user-facing output | Many files contain mojibake (e.g., "âœ…") suggesting mixed encodings | Cosmetic but confusing | Normalize file encodings to UTF-8; avoid copying emoji symbols into code comments/strings unless stable |
| Snapshot directories (`* - Copy*`) | Backups | Multiple duplicate trees can cause wrong imports/edits | Ongoing repo hygiene issue | Keep snapshots out of import path; move snapshots to archival directory or remove from repo if safe |

## Evidence Pointers (Where These Show Up)

- Disabled Chrome path: `automation/services.py`
- Cognitive routing block: `core/assistant.py`
- Taskbar anchoring and visual matching: `automation/taskbar_trainer.py`, `automation/taskbar_locator.py`, `automation/chrome_pipeline.py`
- Credential vault: `security/credential_vault.py`
- OCR tests: `ocr_test.py`, `ocr_roi_test.py`, `roi_change_ocr.py`
- CLIP test: `clip_test.py`
- Agent framework test: `test_pydantic_ai.py`
- Memory embeddings gate: `vector_memory.py` (`MEMORY_EMBEDDINGS`)
- Phase plan: `COGNITIVE_SYSTEM_COMPLETE.md`

## Failure Graph

Graphify export:
- `project_intelligence/GRAPHIFY_EXPORT/JARVIS_FAILURE_GRAPH1.json`

