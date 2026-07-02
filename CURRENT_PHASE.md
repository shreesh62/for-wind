# FRIDAY — Closed-Loop General Operator

## Status: 381 Tests | Universal Action Layer LIVE | Requirements → Plan → Execute → Verify → Repair

## The Closed Loop (ADR-021) — Built & Live-Verified

```
Goal
  ↓
Requirements Discovery   "What must be TRUE for this to be complete?"
  ↓
Observe Environment      (reuse existing state)
  ↓
Capability Planning      (LLM composes from registry)
  ↓
Execution                (data flows: search → synthesize → file)
  ↓
Verification             (check each requirement against evidence)
  ↓
Repair / Accept          (replan if no progress; accept if partial)
  ↓
Honest Outcome           ("4/6 requirements met, 2 unmet: ...")
```

## New: `friday/operator.py` — The Closed-Loop Engine

Ties the full cycle together. Live test results:

```
Goal: "Write Python vs JavaScript comparison and save to file"
→ Discovered 6 requirements
→ Met 4/6 (content produced, file created)
→ Honestly reported 2 unmet (syntax/use-case coverage)
→ Created comparison.txt (2990 bytes real content)

Goal: "Write 5 productivity tips, save to productivity.txt"
→ Discovered 5 requirements
→ Met 3/5, created productivity.txt (2329 bytes)
→ Single file (dedup fixed), 79s (NVIDIA cold-start)
```

## Key Behaviors (General Operator, not workflows)

1. **Requirements-first**: reasons about completion conditions for ANY goal
2. **Environment-aware**: observes before acting, reuses existing state
3. **Capability-composed**: LLM picks capabilities, no task templates
4. **Honest verification**: reports what's met AND unmet (no illusion success)
5. **Self-correcting**: replans when no progress; accepts meaningful partial
6. **Delivery-gated**: email/send requirements marked non-blocking (need verified interaction)

## What's Proven Live (real files on disk)
- AI language comparison report → .docx
- Python usage research → .txt
- 3-month ML study plan → .md
- Haiku → .txt
- Python vs JS comparison → .txt (with requirement verification)
- 5 productivity tips → .txt
- Desktop app launch, web navigation

## Honest Limitations
- **Latency**: NVIDIA cold-start (~20-30s) × 2 calls (discover + generate) = 60-90s
  for content goals. Tasks complete; they're just not fast on free tier.
- **Web extraction**: needs logged-in Chrome profile (JARVIS_CHROME_USER_DATA_DIR)
- **Verification is heuristic**: checks output type (content/file/nav), not deep
  content quality. A "requirement met" means the right kind of output was produced.
- **Send actions gated**: email/message decompose correctly but final send needs
  verified interaction (safety).

## Test Count: 381
New: operator (6), requirements (8)

## Architecture Components
```
friday/
├── operator.py              ← Closed-loop engine (NEW)
├── executor.py              ← Data-flowing step execution
├── planner/
│   ├── requirements.py      ← Requirements Discovery (NEW)
│   ├── operator_planner.py  ← Capability planning (workflow-free)
│   ├── llm_decomposer.py    ← LLM goal → capabilities
│   └── replanner.py         ← Repair strategies
├── tools/registry.py        ← Capability registry (environment-agnostic)
├── actions/
│   ├── browser_controller.py ← Persistent Playwright session
│   ├── file_tool.py          ← Real file operations
│   ├── system.py             ← Desktop apps
│   └── result.py             ← ActionResult contract
└── perception/
    ├── environment.py        ← What's running/open
    ├── world_state.py        ← Unified perception
    └── priority.py           ← Semantic-first (DOM>UIA>OCR>Vision)
```

## Next (ADR-021 priorities)
1. ~~Universal Action Layer~~ ✓ DONE (primitives: click/type/observe/verify — all 12)
2. Requirement-level repair (replan ONLY the unmet requirement, not whole plan)
3. Latency optimization (parallel LLM calls, faster models for decomposition)
4. Capability Learning System (gap → propose → test → integrate)
