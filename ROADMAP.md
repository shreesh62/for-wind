# FRIDAY — Authoritative Roadmap (v2)

> Supersedes all previous roadmaps (CURRENT_PHASE.md "Next", NEXT_TASK.md priorities).
> Written after a full reality-check audit against live code on 2026-06-18.
> Governing question for every item: **"Does this make FRIDAY better at completing arbitrary real-world goals?"**

---

## PART 1 — CURRENT REALITY (updated 2026-06-18 after M0-M4 + latency)

FRIDAY has moved from "plan-and-generate-text-to-file with unproven actuation" to a closed loop with honest verification, a live action layer, real-browser capability, and per-requirement repair. Remaining gaps are mostly live-validation (real LLM/browser runs) and desktop element precision.

### Fixed this session (verified by 491 tests, 0 regressions)
- **Evidence Law (ADR-023)**: false completion is architecturally impossible — requirements satisfied only by real evidence artifacts. Generated text can NEVER satisfy gather/deliver.
- **Screenshot evidence + captcha/block detection (ADR-024)**: visual proof + anti-loop on verification walls.
- **Universal Action Layer LIVE + tested (ADR-025)**: `init_primitives`/`register_primitives` wired into the operator; was orphaned.
- **Focused search queries + spreadsheets (ADR-026)**: no more whole-sentence searches; real .csv/.xlsx.
- **Real Chrome control (ADR-027)** + **profile selection system (ADR-028)** + **browser access strategy (ADR-029)** + **DesktopChromeController (ADR-030)**: operate the user's real Chrome, or fall back to driving the visible window like a human.
- **Executor routes click/type through primitives + dry-run safety (ADR-031)**.
- **Phantom-action elimination (ADR-033, ADR-035)**: legacy main.py guarded; the TRUE cause — tests executing real OS actions — fixed via conftest dry-run.
- **Honest research with citations (ADR-032)**: opens real pages, records source URLs, cites them.
- **Per-requirement repair (ADR-034)**: diagnoses WHY a requirement failed, fixes only that one, reuses prior work.
- **Latency: parallel discovery+planning (ADR-036)**: first-goal cold-start cut roughly in half.

### Still pending (honest)
- Live wall-clock validation with real (non-dry-run) NVIDIA + real browser.
- Element-precise desktop clicking (DESKTOP_CONTROL does navigate/search/type/read; click-by-element needs the desktop/vision adapter wired for coordinates).
- Delivery (email/send) remains safety-gated.
- M5 desktop operator polish, M6 delivery, M7 doc quality, M8 self-improvement.

### Subsystem scores (updated)
Planning 6 · Perception 5 · Browser 6 (real CDP proven) · Desktop 4 · Memory 7 · Research 6 · Verification 8 (Evidence Law) · Adaptation 6 (per-req repair) · Recovery 5 (captcha/block handling) · Generalization 6.

---

## PART 1-LEGACY — ORIGINAL AUDIT REALITY (kept for history)

FRIDAY is a real Python package with genuine building blocks, but it is **not yet a general-purpose computer operator**. It is, today, a **plan-and-generate-text-to-file engine with unproven actuation**.

### What is actually real (verified)
- `ActionResult` contract, `WorldState` schema, perception types — solid, well-tested.
- `FileTool.create_file/read/append/delete` — real, creates real files (verified).
- 4-tier memory (JSON stores) — real, tested.
- Model router + NVIDIA/Groq providers — real, but tests are mock-only.
- Universal Action Layer (`primitives.py` + 4 adapters + resolver) — **code exists, zero tests, NOT wired into the operator**.

### What is overstated / broken (verified)
| Claim | Reality |
|-------|---------|
| "Every capability composes from primitives" | False. `GoalExecutor` bypasses the Universal Action Layer entirely. |
| "Universal Action Layer is live" | False. `register_primitives()` never called; `build_default_registry()` doesn't include them. |
| "Research works" | False-positive. Generated text satisfies research requirements even when search/read fail. |
| "Closed-loop verify → repair" | Shallow. Verification is keyword heuristics; repair re-runs the whole plan and accepts partial. |
| "Uses your real Chrome" | Unproven. CDP 9222 not reachable; silently launches fresh Chromium. |
| "Email/send" | Placeholder string in the operator. |
| Honest 381 tests | True count, but they prove unit behavior with mocks — not real-world capability. |

### The single most dangerous property
**False completion.** The operator can return `completed=True` for a goal where search failed, no real source was read, and the document is empty boilerplate. This must become **architecturally impossible**, not patched case-by-case.

### Subsystem honesty scores (from audit, accepted)
Planning 5 · Perception 4 · Browser 3 · Desktop 3 · Memory 7 · Research 2 · Verification 3 · Adaptation 2 · Recovery 2 · Generalization 2.

---

## PART 2 — FINAL VISION (unchanged, reaffirmed)

One operator. The computer is the environment. Browser, desktop, Explorer, Word, VS Code, Discord — all just environments the operator moves between like a human. The user gives a goal; FRIDAY discovers the path through Observe → Understand → Infer Requirements → Plan → Execute → Observe → Verify → Repair → Complete → Evidence → Learn. No workflows. No pipelines. No false success.

**Acceptance bar:** complete a never-before-seen goal end-to-end with objective evidence for every requirement.

---

## PART 3 — ARCHITECTURE TARGET

```
Goal
 ↓
Observe (real WorldState: tabs, windows, files, clipboard, processes)
 ↓
Requirements Discovery (LLM) ── each requirement carries a VERIFIER, not just a description
 ↓
Plan (compose capabilities from registry)
 ↓
Execute  ── ALL actuation flows through Universal Action Layer primitives
 ↓
Observe again (fresh WorldState)
 ↓
Verify EACH requirement against EVIDENCE (no evidence ⇒ not satisfied)
 ↓
Repair the specific unmet requirement (diagnose → different approach → retry)
 ↓
Complete ONLY when all blocking requirements have evidence
 ↓
Produce evidence bundle + Learn
```

Two architectural laws introduced by this roadmap:
1. **Evidence Law** — a requirement is satisfied only by an evidence artifact (file bytes + content check, URL + DOM match, screenshot diff, delivery confirmation). Generated text never satisfies a "gather/research/send" requirement.
2. **Single Actuation Path Law** — no module touches Playwright/pyautogui directly except adapters. The executor calls primitives only.

---

## PART 4 — MILESTONES

Every milestone ends with a **real demonstration on real Windows**, not unit tests.

### M0 — Truth & Guardrails (foundation) — DONE (2026-06-18)
**Goal:** make the system stop lying.
- DONE: Replaced heuristic `_verify_requirements` with the Evidence Law in `friday/verification/evidence_law.py`; requirement satisfied only if a matching evidence artifact exists.
- DONE: Generated content can ONLY satisfy "produce content" requirements — never "gather/research/source/send/deliver".
- DONE: Executor (`friday/executor.py`) now collects REAL evidence artifacts (gathered info, source URLs, file bytes, navigation).
- DONE (live-verified): "Research laptops and create a summary" with no browser -> `completed=False`, 1/3 met, research reported UNMET. Was a false-pass before. See `scripts/m0_demo.py`.
- DONE (acceptance): 20 new Evidence Law tests; full suite 401 passing. A gather/file/deliver requirement cannot be satisfied without a real artifact.
- CARRIED: thread a structured `EvidenceBundle` into `OperatorOutcome` (today honest reasons live in `requirement.evidence` + trace).

### M1 — Unify the Actuation Path (wire the Universal Action Layer) — IN PROGRESS
**Goal:** make the Universal Action Layer the ONLY way actions happen.
- DONE: `init_primitives` + `register_primitives` called in `Operator.__init__`. The layer is LIVE.
- DONE: wrote the previously-zero tests for primitives + adapters (18 tests).
- DONE: DESKTOP_CONTROL execution path — `DesktopChromeController` operates the visible Chrome via keyboard + screen OCR (navigate/search/type/read work), injected by the bridge when the user's profile is locked and the goal needs their session (ADR-030).
- TODO: route `GoalExecutor` element actions (click/type on specific elements) through `primitives.*` desktop/vision adapters so element-precise desktop interaction works, not just keyboard/omnibox.
- TODO: add a `navigate` primitive.
- **Acceptance:** element actuation flows through `primitives`; live demo on the owner's real Chrome.

### M2 — Real Browser Control (prove the Chrome story) — LIVE-VERIFIED (core)
**Goal:** operate the user's actual Chrome, not a fresh Chromium.
- DONE: `BrowserController(require_real_chrome=True)` fails LOUDLY on CDP failure instead of silently launching fresh Chromium. Exposes `connection_mode` ('cdp'|'fresh') and `is_real_chrome`.
- DONE: `friday/actions/chrome_launcher.py` + `scripts/launch_chrome_debug.py` start Chrome on the CDP debug port. Detects the #1 real-world failure (Chrome already open without the flag -> profile locked) and falls back to a dedicated debug profile so a controllable session still comes up.
- DONE: bridge wires `FRIDAY_REQUIRE_REAL_CHROME=1` -> ensure_chrome_debug -> real-Chrome controller; honest failure (no fake session) otherwise.
- DONE (LIVE-VERIFIED, `scripts/m2_live_demo.py`): connected via CDP (`connection_mode=cdp`, `is_real_chrome=True`), navigated to example.com, read 129 real chars (not blocked), captured a real 284KB screenshot artifact, DuckDuckGo search returned 3189 chars + 15 links with NO captcha wall.
- TODO: live DOM perception into WorldState (not cache-dependent); real tab enumeration in `EnvironmentObserver`; profile-chooser/login/consent handling as capabilities.
- **Acceptance (met for core):** CDP reachable check passes; real page read returns real content; screenshot + search proven live.
- Real browser-tab enumeration in `EnvironmentObserver` (currently deferred).
- Handle: profile chooser, login detection, consent/permission dialogs (port the old `automation/chrome_pipeline.py` logic into capabilities).
- **Demo:** with the user's real Chrome open and logged in, FRIDAY reads the actual page DOM, clicks a real element, and the trace shows BrowserAdapter executing against the live session.
- **Acceptance:** CDP reachable check passes; reading a logged-in page returns real user-specific content.

### M3 — Honest Research Capability
**Goal:** research = trustworthy sources, read, cross-reference, cite. Never hallucinate.
- Search → open results → read DOM → extract → record **source URLs as evidence**.
- Source-quality preference (official/gov/primary domains ranked first) — as a reusable capability, NOT a pipeline.
- Citations are a verifiable requirement: a research requirement is satisfied only if ≥N real sources were read and recorded.
- **Demo:** "Research France's position on [topic] using official sources" → produces a summary whose citations map to URLs FRIDAY actually opened and read.
- **Acceptance:** remove any source and the citation count requirement fails honestly.

### M4 — Per-Requirement Repair + Real Verification
**Goal:** fix what's broken, not re-run everything.
- Repair targets the specific unmet requirement: diagnose (element not found / wrong page / missing data / timeout) → choose a *different* approach → retry that requirement only.
- LLM-based content-quality verification (does the document actually address the goal?), layered on top of the Evidence Law.
- **Demo:** a goal where step 2 fails on first attempt; trace shows ONLY step 2 replanned and retried with a different approach, then completion.
- **Acceptance:** repair does not re-execute already-satisfied requirements.

### M5 — Desktop Operator (arbitrary apps)
**Goal:** operate real Windows apps like a human.
- Live UIA tree into WorldState (not state-cache dependent).
- DPI / multi-monitor coordinate correctness for pyautogui actions.
- File picker, dialog handling, window move/resize as capabilities.
- **Demo:** open Notepad (real launch), type, save via the Save dialog, verify the file on disk — entirely through primitives + UIA.
- **Acceptance:** a desktop goal completes with no browser involved, fully through the action layer.

### M6 — Delivery (the gated actions, done for real)
**Goal:** sending becomes real and verified, not a placeholder.
- Email send through the user's real Gmail session (compose → attach → send) as composed capabilities.
- Attachment/upload via real file-picker handling (depends on M5).
- Delivery is a **blocking, evidence-backed** requirement: confirmed only by observing the "sent" state (sent-folder entry / confirmation UI), with explicit user-confirmation safety gate.
- **Demo:** the full final-question task — research → DOCX with flag + citations → open real Gmail → attach → send → verify delivery.
- **Acceptance:** delivery requirement passes only with observed confirmation; safety gate requires explicit approval before send.

### M7 — Document Quality
**Goal:** documents stop being one-paragraph-per-line `.docx`.
- Real DOCX formatting (headings, sections, image/flag insertion, citation formatting).
- PowerPoint creation capability.
- **Demo:** a professional position paper renders with structure, an inserted image, and formatted citations.

### M8 — Self-Improvement (future, gated)
**Goal:** detect capability gaps → propose → generate → test → request approval → integrate. Never autonomous self-modification. Sandbox + human approval mandatory.

### M9 — Mobile-Ready Backend Surface
**Goal:** everything a future UI/mobile agent needs already exists. Remote execution, streaming, screenshots, notifications, task progress, logs, memory, conversation, auth — all API-first. (Frontend stays deferred per ADR-017.)

---

## PART 5 — DEPENDENCY ORDER

```
M0 (truth)  →  M1 (unify actuation)  →  M2 (real browser)  →  M3 (research)
                                     ↘  M5 (desktop)        ↗
M1 → M4 (repair/verify) gates M3, M5, M6 quality
M2 + M5 → M6 (delivery)
M6 → M7 (doc quality) → final end-to-end demo
M9 runs in parallel; M8 last.
```

M0 and M1 are non-negotiable prerequisites for everything. Nothing else matters while the system can still report false success and while the action layer is orphaned.

---

## PART 6 — RISK ANALYSIS

| Risk | Severity | Mitigation |
|------|----------|------------|
| False success persists if M0 slips | Critical | M0 first; add a regression test that the no-browser research goal reports UNMET. |
| NVIDIA cold-start latency (20–90s) | High | Parallelize discover+decompose; small models for planning; keepalive warmer. |
| Live Chrome/CDP fragility | High | Explicit reachable-check; loud failure; documented launch helper. |
| pyautogui DPI/multi-monitor errors | Medium | Coordinate-correctness layer in M5 before trusting desktop clicks. |
| Disk full → silent 0-byte writes | Medium | FileTool already verifies size; extend to all artifact writes. |
| Send actions cause real-world side effects | High | Mandatory human-confirmation gate on all delivery. |
| Re-introducing workflow drift under pressure | Medium | Litmus test enforced in every PR/spec. |

---

## PART 7 — ENGINEERING STANDARD (definition of done)

A capability is complete only when: **implemented → unit-tested → demonstrated on real Windows → verified with evidence → benchmarked (latency/success) → documented.** Unit tests alone never count as "done" for a capability.

---

## PART 8 — OWNER ACTIONS vs AI ACTIONS

**Owner (Shreesh):**
- Start Chrome with `--remote-debugging-port=9222` + real profile when browser demos run (or approve the launch helper doing it).
- Approve before any real send/delivery action executes.
- Confirm acceptance at each milestone demo.
- Keep `NVIDIA_API_KEY` valid; flag if Groq usage must drop further.

**AI (me):**
- Execute M0→M9 in dependency order, each behind a spec where warranted.
- Never report success without evidence.
- Verify every capability live before claiming it works.
- Keep this ROADMAP.md and ADRs as the source of truth; update reality sections as milestones land.

---

## PART 9 — IMMEDIATE NEXT STEP

**Begin M0 (Truth & Guardrails).** It is the highest-leverage work: it converts FRIDAY from a system that *claims* completion into one that *proves* it. Everything else builds on an operator that cannot lie.

Recommended path: spec M0 as "evidence-based-verification", implement the Evidence Law in `operator.py`, add the regression demos, then proceed to M1 (which the existing `universal-action-layer` spec already covers for the wiring + tests).
